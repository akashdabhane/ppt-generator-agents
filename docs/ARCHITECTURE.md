# Architecture

_Last updated: 2026-09-22. This describes the code **as it is**. Where the README describes something
aspirational, this file says so._

## 1. System overview

```
Browser (Next.js 16, :3000)
   │  Axios + Bearer JWT (token in localStorage)
   ▼
FastAPI (:8000, /api/v1) ──────────► PostgreSQL (users, projects, documents, chunks, presentations, slides, jobs)
   │  dispatch_*()                        ▲
   ├──► Celery via Redis (broker db1, results db2) ──► worker runs the same run_* functions
   └──► fallback: FastAPI BackgroundTasks (in-process) if the broker is unreachable
                         │
                         ├─ Ingestion:  extractor → DocumentChunker → EmbeddingService → VectorStore
                         └─ Generation: HybridRetriever → LLM (JSON spec) → LayoutEngine → PresentationRenderer → storage/*.pptx
```

Files are stored on local disk: `backend/storage/projects/{project_id}/documents/{doc_id}.{ext}` and
`.../presentations/{presentation_id}.pptx` (see `app/services/storage.py`).

## 2. Backend layout (`backend/app/`)

| Package | Responsibility |
|---|---|
| `main.py` | FastAPI app, CORS, router registration, `Base.metadata.create_all` on startup (no migrations) |
| `core/config.py` | `Settings` (pydantic-settings, reads `.env`); singleton `settings` |
| `database/session.py` | **Sync** SQLAlchemy engine + `SessionLocal`; rewrites `postgresql+asyncpg://` to `postgresql://` |
| `models/` | ORM models (see §4) |
| `schemas/` | Pydantic I/O schemas; `presentation_spec.py` is the LLM ↔ renderer contract |
| `api/v1/` | Routers: `auth`, `projects`, `documents`, `presentations`; `deps.py` has `get_db`, `get_current_user` |
| `document_processing/` | `detector.py` (extension → type), `extractors/*` (raw blocks), `chunker.py` |
| `services/` | `storage.py` (disk I/O), `embeddings.py` (OpenAI → Google → hash fallback) |
| `rag/` | `vector_store.py` (adapters + factory), `retriever.py` (multi-query), `graph.py` (generation engine) |
| `presentation/` | `layout_engine.py` (geometry + pagination), `themes.py`, `renderer.py` (python-pptx) |
| `workers/` | `celery_app.py`, `tasks.py` (`run_*` functions, Celery tasks, `dispatch_*` with fallback) |

### Design patterns in use

- **Layered architecture:** routers → services/engines → models. Routers hold request validation and ownership checks.
- **Adapter + Factory:** `BaseVectorStore` with `PineconeVectorStore`, `PGVectorStore`, `MockInMemoryVectorStore`; `get_vector_store()` picks one from `VECTOR_DB_TYPE`.
- **Graceful degradation:** each external dependency has a fallback (Celery → BackgroundTasks, Pinecone/pgvector → mock, embeddings API → hash vectors, LLM → deterministic spec).
- **Module-level singletons:** `settings`, `vector_store`, `retriever`, `rag_engine`, `embedding_service`, `storage_service`.
- **Strategy by type:** the chunker picks an extractor by file type; the renderer dispatches on `slide.type`.
- **Contract-first spec:** `PresentationSpec` (a Pydantic discriminated set of slide types) separates content from layout.

## 3. Key flows

### Ingestion (`run_document_ingestion`)
1. `POST /projects/{id}/documents` validates the extension, creates a `Document(UPLOADED)` row, saves the file and dispatches the task.
2. Status goes `PROCESSING → CHUNKING`. The extractor returns blocks `{content, page, section, is_table, table_data}`.
3. The chunker keeps tables whole (one chunk each) and splits text into 1000-char windows with 150-char overlap.
4. Status becomes `EMBEDDING`, then `vector_store.upsert_chunks(project_id, chunks)`. Pinecone uses the **namespace = project_id**.
5. A `DocumentChunk` row is written per chunk (with `vector_id`), then `INDEXED`. Any exception sets `FAILED` + `error_message`.

### Generation (`run_presentation_generation`)
1. `POST /projects/{id}/presentations/generate` creates `Presentation(PENDING)` + `GenerationJob(QUEUED)` and dispatches.
2. `rag_engine.execute()` expands the prompt into 4 fixed sub-queries → `HybridRetriever` searches each, dedupes by `filename_page_chunkindex`, sorts by score, keeps the top 15.
3. It builds a context string and makes one LLM call that returns `PresentationSpec` JSON. On a parse error or missing key it falls back to `_generate_fallback_spec`.
4. `PresentationRenderer(theme).render(spec, path)`: a blank 16:9 slide per spec item. Table specs are paginated by `LayoutEngine.split_table_rows`.
5. One `PresentationSlide` row is written per **spec** slide (a paginated table is one DB row but several `.pptx` slides), then `COMPLETED`.
6. The frontend polls `GET /presentations/{id}/progress` every 2 s.

> "LangGraph" appears in names (`graph.py`, `LangGraphRAGEngine`), but no LangGraph graph is built.
> It is a sequential Python pipeline. Converting it into a real graph is a task in `TASKS.md`.

## 4. Data model

```
User 1─* Project 1─* Document 1─* DocumentChunk
                 1─* Presentation 1─* PresentationSlide
                                  1─* GenerationJob
```
- All IDs are UUID strings. Deletes cascade (ORM `cascade="all, delete-orphan"` + FK `ondelete=CASCADE`).
- Enums: `DocumentStatus` (UPLOADED, PROCESSING, CHUNKING, EMBEDDING, INDEXED, FAILED),
  `PresentationStatus` (PENDING, GENERATING, COMPLETED, FAILED),
  `JobStatus` (QUEUED, RETRIEVING_DOCUMENTS, GENERATING_OUTLINE, GENERATING_SLIDE_CONTENT, RENDERING_PRESENTATION, VALIDATING_SLIDES, COMPLETED, FAILED).
- `PresentationSlide.content_json` stores the slide spec dict; `citations_json` stores its citations.
- The schema is created by `create_all` at startup. Changing a column on an existing DB needs a manual migration (Alembic is installed but not set up).

## 5. Layout engine contract (`presentation/layout_engine.py`)

- Slide: 10.0 × 5.625 in. Margins L/R 0.8, top 0.6, bottom 0.5. Title height 0.9, footer 0.4.
- `get_title_rect()`, `get_content_rect()`, `get_two_column_rects()` (0.4 in gap).
- Table pagination: max rows per slide = 10 (cells ≤ 60 chars), 7 (> 60), 4 (> 120).
- `validate_bounds(rect)` checks that the rect is inside the slide. Tested in `backend/tests/test_layout_engine.py`.
- The title slide card (1.0, 1.2, 8.0 × 3.2) is hard-coded in the renderer. It should move into the engine.

## 6. Configuration

All settings are in `core/config.py` and read from `backend/.env`. The important ones are
`DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`,
`VECTOR_DB_TYPE` (pinecone | pgvector | mock), `PINECONE_*`, `LLM_PROVIDER` (anthropic | openai | google),
the provider API keys, `EMBEDDING_MODEL`, `SECRET_KEY`, and `STORAGE_DIR`. The frontend uses `NEXT_PUBLIC_API_URL`.

LLM models: `DEFAULT_MODELS` in `rag/graph.py` (claude-sonnet-5 / gpt-4o / gemini-2.5-flash), overridable with `LLM_MODEL`.
Dispatch pings Redis first (≈2 s) and falls back to BackgroundTasks immediately when it's down. If Redis is up but no worker is running, jobs wait in the queue until the 10-min stale timeout.
Embeddings are fixed at 1536 dimensions, which matches OpenAI `text-embedding-3-small`.
Google `text-embedding-004` returns 768 dimensions and will not fit the same index.

## 7. Frontend layout (`frontend/src/`)

| Path | Purpose |
|---|---|
| `app/layout.tsx` | Root layout: Inter font, `Providers`, `Navbar`, grid background |
| `app/page.tsx` | Redirects to `/dashboard` |
| `app/login`, `app/register` | Auth forms → `useAuthStore.setAuth` |
| `app/dashboard` | Project list + create |
| `app/projects/[id]` | Tabs: Documents (dropzone + list) · Generate PPT (prompt studio + progress) · Decks |
| `app/presentations/[id]` | Slide thumbnails, HTML preview per slide type, regenerate, download |
| `components/Providers.tsx` | TanStack `QueryClient` + light/dark `ThemeContext` (`localStorage.app_theme`) |
| `components/Navbar.tsx` | Brand, nav, theme toggle, user chip, logout |
| `lib/api.ts` | Axios instance, adds `Authorization: Bearer <localStorage.token>` |
| `lib/store.ts` | Zustand `useAuthStore` (user, token) |

Data fetching: `useQuery` / `useMutation` inline in page components, with query keys like
`["project", id]`, `["documents", id]`, `["presentations", id]`. There is no shared types file yet (`any` is used).
