# Backend conventions (FastAPI, Python 3.12)

Loaded when working inside `backend/`. Project-wide rules are in `../CLAUDE.md`, and the architecture is in `../docs/ARCHITECTURE.md`.

- **Sync SQLAlchemy only.** Handlers are `def` and take `db: Session = Depends(get_db)` and
  `current_user: User = Depends(get_current_user)` from `app/api/v1/deps.py`. Use `db.get(Model, id)` and
  `db.execute(select(...)).scalars()`. Commit explicitly.
- **Ownership:** take the resource through `get_owned_project` / `get_owned_presentation` / `get_owned_document`
  from `deps.py` (they 404 for other users). Never load a project/presentation/document by id in a route yourself.
- **Models:** `Mapped[...]` + `mapped_column`, UUID string `id` default, `created_at`/`updated_at` with `datetime.utcnow`,
  status as a `str, Enum`. Export new models from `app/models/__init__.py`.
  **Schema changes need an Alembic migration:** `alembic revision --autogenerate -m "..."` (review it), and keep
  `tests/test_migrations.py` passing (models must equal the migrated schema). The API upgrades on startup.
- **Schemas:** Pydantic v2 in `app/schemas/`, `class Config: from_attributes = True` for ORM responses.
- **Routers:** one file per resource in `app/api/v1/`, `APIRouter(tags=[...])`, registered in `app/main.py` with `settings.API_V1_STR`.
- **Long work goes in a worker:** write a `run_*` function in `workers/tasks.py`, wrap it in a `@celery_app.task`, and call it via a
  `dispatch_*` helper that falls back to `BackgroundTasks`. Update the job/document status + progress at each step and
  catch exceptions into `FAILED` + `error_message`.
- **Singletons:** reuse `settings`, `vector_store`, `retriever`, `rag_engine`, `embedding_service`, `storage_service`. Don't instantiate new clients per request.
- **New vector backend:** subclass `BaseVectorStore` in `rag/vector_store.py`, add it to `get_vector_store()`, and fall back to the mock on init failure.
- **New file type:** add it to `DocumentTypeDetector.SUPPORTED_EXTENSIONS`, add an extractor in `document_processing/extractors/`
  returning blocks `{content, page, section, is_table, table_data}`, and route it in `DocumentChunker`.
- **Layout:** all positions/sizes come from `LayoutEngine` (inches). Colours and fonts come from `self.theme`. Add tests in `tests/`.
- Use `logging.getLogger(__name__)`, not `print`.
- Tests: `PYTHONPATH=. pytest` from `backend/` (PowerShell: `$env:PYTHONPATH="."; pytest`).
- Dependencies: `requirements.txt` lists direct dependencies only, pinned, UTF-8. Add new packages there the same way.
- Embeddings: one provider per process (`services/embeddings.py`); never add a silent fallback to another provider.
- Tests are hermetic (`tests/conftest.py` forces the mock vector store and no API keys). Keep them that way.
