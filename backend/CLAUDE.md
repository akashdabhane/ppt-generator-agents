# Backend conventions (FastAPI, Python 3.12)

Loaded when working inside `backend/`. Project-wide rules are in `../CLAUDE.md`, and the architecture is in `../docs/ARCHITECTURE.md`.

- **Sync SQLAlchemy only.** Handlers are `def` and take `db: Session = Depends(get_db)` and
  `current_user: User = Depends(get_current_user)` from `app/api/v1/deps.py`. Use `db.get(Model, id)` and
  `db.execute(select(...)).scalars()`. Commit explicitly.
- **Ownership:** load the `Project` and return 404 unless `project.user_id == current_user.id`. Do this for every route.
- **Models:** `Mapped[...]` + `mapped_column`, UUID string `id` default, `created_at`/`updated_at` with `datetime.utcnow`,
  status as a `str, Enum`. Export new models from `app/models/__init__.py` so `create_all` sees them.
  There are no migrations: a column change on an existing DB needs a manual `ALTER` or a DB reset.
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
- Dependencies: `requirements.txt` is currently a UTF-16 `pip freeze`. When adding a package, keep the file UTF-8 and pinned (see TASKS P0).
