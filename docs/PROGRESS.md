# Progress Log

Newest entry first. At the end of every session, add: **what changed · what's broken · where to resume.**

---

## 2026-09-23: Document status now updates live after upload

**Root cause:** the `["documents", id]` query on `/projects/[id]` fetched once, so a status change during background ingestion only showed after a full page reload.
**Changed:** `frontend/src/app/projects/[id]/page.tsx`: the documents query now uses `refetchInterval` to poll every 2 s while any document is not `INDEXED`/`FAILED`, and stops once all are terminal.
**Verified:** `tsc --noEmit` clean. Not verified in a browser. Pre-existing lint errors (`any` types) remain in that file.

---

## 2026-09-23: Fixed "Generate PPT produces no output"

**Root causes found:** (1) the Google model `gemini-1.5-pro` is retired (404), so every generation errored. (2) The user's job was stuck at 40 % because the in-process task died, and the UI showed nothing for failed or stuck jobs.
(3) With Redis down, each dispatch blocked for ~100 s in Celery reconnect retries before falling back. (4) DOCX ingestion failed on Pinecone null metadata. (5) Download returned 401.
**Changed:** `rag/graph.py` (current default models, `LLM_MODEL` override, stricter prompt with top-level JSON shape and exact slide count, robust JSON parsing, logged fallback);
`workers/tasks.py` (num_slides/audience passed through, fast Redis ping before `.delay`); `api/v1/presentations.py` (stale-job → FAILED, ownership on progress/download);
`rag/vector_store.py` + `rag/retriever.py` (Pinecone metadata sanitised, `table_data` JSON round-trip); frontend (blob download helper in `lib/api.ts`, error panel in the Generate tab, status badge on decks without a file).
**Verified:** via TestClient as the real user: the old job was marked FAILED, the DOCX re-indexed OK, a 6-slide Modern deck was generated (COMPLETED) and downloaded (200, valid .pptx). pytest 6/6 passed, `tsc --noEmit` is clean.
Not verified in a browser yet.
**Resume here:** `TASKS.md` → P0 login fix.

---

## 2026-09-23: Merged handoff from previous agent (Anti-Gravity)

**Changed:** `PRD.md` now includes the confirmed motive, target users and deliverables, and the build history below.
**Discrepancies found:** the handoff says PPTX extraction exists. The code has none (`.pptx` is read as plain text), so the task stays open.
The handoff's "6 passing tests" is reported by Anti-Gravity and hasn't been re-run here.
**Resume here:** unchanged, `TASKS.md` → P0 login fix.

## Project history (sessions with Anti-Gravity, before Claude Code)

| # | Focus | Delivered |
|---|---|---|
| 1 | Architectural blueprint | Separating content generation from layout; ORM schema (User, Project, Document, DocumentChunk, Presentation, PresentationSlide, GenerationJob) |
| 2 | Document processing & RAG | Extractors (PDF, DOCX, XLSX, CSV, TXT, MD), table-aware chunker, vector-store adapter hierarchy, HybridRetriever |
| 3 | Layout engine & renderer | `LayoutEngine` bounds + table pagination, 5 themes, `PresentationRenderer`, `test_layout_engine.py` (6 tests) |
| 4 | Backend API & worker | v1 routers, PBKDF2 + JWT auth, file storage, Celery with BackgroundTasks fallback |
| 5 | Next.js 16 web app | `/login`, `/register`, `/dashboard`, `/projects/[id]`, `/presentations/[id]` with slide preview and citations |

Git history (3 commits so far) doesn't show these stages. This table is the only record of them.

---

## 2026-09-22: Project context docs added

**Changed:** Added `CLAUDE.md`, `AGENTS.md`, `backend/CLAUDE.md`, frontend conventions in `frontend/CLAUDE.md`,
and `docs/` (PRD, ARCHITECTURE, API, DESIGN, TASKS, PROGRESS, DECISIONS). No application code was changed.

**Current state:** The full vertical slice exists: auth → projects → upload/ingest → generate → preview → download.
It runs without any API keys using the mock vector store, hash embeddings and the deterministic fallback deck.
There are 6 layout-engine unit tests and no other tests.

**Known broken / risky (from reading the code, not yet run end-to-end):**
1. Login is probably broken: the frontend sends JSON, but the backend expects an OAuth2 form (`username`, `password`).
2. `.pptx` download from the viewer returns 401 because a plain link sends no Bearer token.
3. The worker ignores `num_slides` and `audience` from the request. Every deck targets 10 slides for "General".
4. Pinecone ingestion will likely fail because metadata includes `null` (`page`) and nested dicts (`table_data`), which Pinecone rejects. Docs end up `FAILED`.
5. Several endpoints skip ownership checks (progress, download, regenerate, delete presentation, reindex).
6. Deleting or reindexing a document leaves its vectors behind, so reindexing duplicates chunks.
7. Regenerating a slide doesn't update the `.pptx` and usually replaces the slide with a title slide.
8. The fallback deck contains fabricated numbers, which violates the grounding requirement.
9. `.pptx` uploads are accepted by the backend but parsed as plain text. The frontend dropzone doesn't accept `.pptx` at all.
10. The Docker build is likely to fail: `requirements.txt` is UTF-16 with `pywin32`, and the frontend Dockerfile expects Next `standalone` output that isn't configured.
11. The mock vector store is in-memory per process. Indexed data disappears on restart and isn't shared between the API process and the Celery worker.
12. DB slide numbers ≠ `.pptx` slide numbers when a table is paginated.
13. The README overstates the tech: the DB is sync (not async), progress is polled (not SSE), and there is no real LangGraph graph.

**Resume here:** `TASKS.md` → P0, first item (login fix).
