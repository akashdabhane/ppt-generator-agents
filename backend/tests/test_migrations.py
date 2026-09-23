from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

import app.models  # noqa: F401
from app.database.migrate import run_migrations
from app.database.session import Base


def _columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_fresh_database_is_created_at_head_and_matches_the_models(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    run_migrations(engine)

    assert {"audience", "tone", "language"} <= _columns(engine, "presentations")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"models and migrations differ: {diff}"


def test_legacy_create_all_database_is_stamped_then_upgraded(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    # Simulate a database created by the old create_all (baseline schema, no alembic_version)
    run_migrations(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))
        conn.execute(text("CREATE TABLE p_backup AS SELECT * FROM presentations"))
        conn.execute(text("DROP TABLE presentations"))
        conn.execute(text(
            "CREATE TABLE presentations (id VARCHAR PRIMARY KEY, project_id VARCHAR NOT NULL, title VARCHAR(255) NOT NULL, "
            "prompt TEXT NOT NULL, theme VARCHAR(50) NOT NULL, status VARCHAR(10) NOT NULL, pptx_path VARCHAR, "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"))
        conn.execute(text("DROP TABLE p_backup"))
        conn.execute(text("INSERT INTO users (id, email, hashed_password, created_at) VALUES ('u1', 'a@b.c', 'x', '2026-01-01')"))

    run_migrations(engine)

    assert {"audience", "tone", "language"} <= _columns(engine, "presentations")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002"
        assert conn.execute(text("SELECT email FROM users")).scalar() == "a@b.c"  # data untouched
