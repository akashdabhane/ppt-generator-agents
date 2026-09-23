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
| `document_processing/` | `detector.py` (extension → type), `extractors/*` (PDF, DOCX, XLSX/CSV, PPTX, text → raw blocks), `chunker.py` |
| `services/` | `storage.py` (disk I/O), `embeddings.py` (OpenAI → Google → hash fallback) |
| `rag/` | `vector_store.py` (adapters + factory), `retriever.py` (hybrid multi-query + MMR), `graph.py` (engine + prompts), `validator.py` (grounding check/repair/enforce), `text_utils.py` (tokens, figures, sentences) |
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
   Ingestion is idempotent: it first deletes the document's previous vectors and chunk rows, so reindex/retry never duplicates.

### Generation (`run_presentation_generation` → `rag_engine.execute_with_report`)
1. `POST /projects/{id}/presentations/generate` (needs ≥ 1 `INDEXED` document) creates `Presentation(PENDING)` + `GenerationJob(QUEUED)`
   and dispatches with `num_slides`, `audience`, `tone`, `language`. The engine reports each stage to the job through a progress callback.
2. **Plan:** the LLM proposes 3–6 search queries. `heuristic_queries()` always adds topic phrases from the prompt with the deck
   boilerplate removed ("Create a 10-slide presentation…"), and is the only planner when there's no LLM.
3. **Retrieve** (`rag/retriever.py`): each query pulls a pool from the vector store. Vector scores are normalised per query, a BM25
   keyword score is added (0.6 / 0.4), and MMR (λ 0.75) picks diverse chunks. Budget: `3 × num_slides` chunks (12–40), ≤ 45k chars.
4. **Write:** sources are numbered `[S1]…[Sn]` with document/page/section. The LLM returns `PresentationSpec` JSON where slides list
   `"sources": ["S2"]`. `CONTENT_RULES` in `graph.py` forbids outside knowledge and computed figures. Invalid JSON is retried once.
5. **Validate** (`rag/validator.py`, D-013): source IDs → exact citations (excerpt = best-matching sentence). Structural fixes
   (table widths, chart pairs, empty slides, title first, trim to `num_slides`). Every figure must appear in the slide's cited
   sources (scale-aware: `$4.2M` = `$4,200,000`), and quotes must be verbatim. A figure found in another retrieved source is auto-cited.
6. **Repair:** remaining issues go back to the LLM once, listed per slide. Then `enforce()` removes claims that are still unsupported
   (bullets, table rows, charts, quotes). `ValidationReport.summary()` ("9/9 content slides cited · 1 unsupported claim(s) removed")
   is kept on the job's `current_step_description`.
7. No LLM, or unusable output: `_generate_fallback_spec` copies retrieved sentences/tables verbatim and cites each one, then goes through the same check/enforce.
8. `PresentationRenderer(theme).render(spec, path)`. Tables are paginated by `LayoutEngine.split_table_rows`, and bullet/summary/two-column lists by `paginate_text_items`.
9. One `PresentationSlide` row per **spec** slide, then `COMPLETED`. The frontend polls `GET /presentations/{id}/progress` every 2 s.

Ingestion chunking (`DocumentChunker._split_text`) packs whole sentences up to 1000 chars with ~150 chars of sentence overlap,
so a sentence or figure is never split between chunks.

> The engine is `RAGPresentationEngine` in `rag/graph.py` (the file name is historical). It is a sequential Python pipeline, not LangGraph.

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
- Table pagination: max rows per slide = 10 (cells ≤ 60 chars), 7 (> 60), 4 (> 120), and a height budget from the estimated row heights.
- Text fitting (D-010): `estimate_lines`/`text_height` (conservative glyph widths), `paginate_text_items` (lists → pages), `fit_font_size` (step down to ≥ 12 pt, then truncate), `truncate_to_fit`.
- `get_title_card_rect()` (1.0, 1.2, 8.0 × 3.2), `get_footer_rect()`. `validate_bounds(rect)` checks the rect is inside the slide.
- Tested in `tests/test_layout_engine.py`, and end to end (every shape in bounds, every theme) in `tests/test_renderer.py`.

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
| `lib/api.ts` | Axios instance, adds `Authorization: Bearer <localStorage.token>`. On a 401 (non-auth request) it logs out and redirects to `/login` |
| `lib/types.ts` | API response types (`ProjectDocument`, `Presentation`, `Slide`, `SlideContent`, `Citation`, …) + `apiErrorDetail()` |
| `components/ConfirmDialog.tsx` | Confirmation modal for destructive actions (project, deck, document delete) |
| `lib/store.ts` | Zustand `useAuthStore` (user, token) |

Data fetching: `useQuery` / `useMutation` inline in page components, with query keys like
`["project", id]`, `["documents", id]`, `["presentations", id]`, typed with `lib/types.ts`.
