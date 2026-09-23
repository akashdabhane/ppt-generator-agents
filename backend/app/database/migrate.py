"""Brings the database schema up to date with Alembic (backend/migrations) at startup."""
import logging
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASELINE_REVISION = "0001"


def alembic_config() -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
    cfg.attributes["configure_logger"] = False  # keep the app's logging setup
    return cfg


def run_migrations(engine: Engine) -> None:
    """
    Upgrades to the latest revision. A database created earlier by `create_all` (tables but no
    alembic_version) is first stamped at the baseline, which matches that schema, so no data is touched.
    """
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        if "alembic_version" not in tables and "users" in tables:
            logger.info("Existing database without migration history: stamping baseline %s.", BASELINE_REVISION)
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")
