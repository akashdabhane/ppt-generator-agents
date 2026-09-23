# Progress Log

Newest entry first. At the end of every session, add: **what changed · what's broken · where to resume.**

---

## 2026-09-23: Gap audit against the PRD + fixes

Audited every PRD feature (F1–F13) and the four "must always hold" rules (§6) against the code. Found and fixed:

| Gap | PRD | Fix |
|---|---|---|
| Login page posted JSON; `/auth/login` expects an OAuth2 form, so sign-in always 422'd | F1 | `login/page.tsx` sends `URLSearchParams` (`username`=email) |
| Bullet/summary/two-column lists, long titles and quotes overflowed the slide | §6 zero overflow | `LayoutEngine` text measurement + pagination/fit (D-010). Renderer rewritten on top of it |
| No-key fallback deck invented numbers and advice. Empty retrieval let the LLM write from memory | §6 grounding | Verbatim, cited fallback. 400 without an INDEXED doc. `NoGroundingContextError`. Unknown citations dropped (D-011) |
| Deleted documents stayed in the vector store and kept being cited. Reindex duplicated chunks | Grounding / privacy | Delete removes vectors; ingestion is idempotent |
| Slide regeneration: no ownership check, replaced the slide with a *title* slide, `.pptx` never updated | F12, §6 isolation | `rag_engine.regenerate_slide` keeps the type; endpoint checks owner/status and re-renders the `.pptx` |
| Reindex had no ownership check. `GET /presentations/{id}` leaked existence (403) | §6 isolation | 404 for non-owners |
| Dark theme: two-column text and quote authors were default black | F8 | All text set on runs with theme colours (D-012) |
| PPTX uploads parsed as plain text (garbage); dropzone didn't accept `.pptx` | F3 | `extractors/pptx_extractor.py` (per slide, tables, notes); dropzone accepts `.pptx` |
| Failed documents showed no reason and had no retry. Document delete had no confirmation | F3 UX | Error text, Retry button (reindex), `ConfirmDialog` |
| Preview drew nothing for quote and summary slides | F6/F11 | Added both previews |
| Regenerate errors were silent. Expired token left pages blank | UX | Error shown in the modal. Axios 401 interceptor → logout + `/login` |
| `npm run lint` failed on `any`s | Quality | `lib/types.ts`, all pages typed. Lint 0 errors / 0 warnings |

**Tests:** 47 backend tests (was 12): layout text fitting, renderer (all themes, bounds, run colours), grounding, regeneration, documents, PPTX extractor, auth,
and an end-to-end no-API-key run (upload → ingest → generate → download a valid in-bounds `.pptx`). Frontend: eslint clean, `tsc` clean, `npm run build` OK.
**Not verified in a browser.** `test_table_pagination_long_text` was relaxed from "exactly 4 rows per slide" to "at most 4" because the new height check packs 3 (D-010).
**Still open (see TASKS):** audience not persisted, preview ≠ `.pptx` slide count for paginated slides, silent upload errors, Docker/requirements fixes, SECRET_KEY/CORS hardening, structured LLM output, Alembic.
**Resume here:** `TASKS.md` → P0 Docker items (`requirements.txt` UTF-16, `output: "standalone"`).

---

## 2026-09-23: Delete presentation from the project's Decks tab

**Changed:** Each deck card in `/projects/[id]` → Decks has a trash button that opens `ConfirmDialog` ("Do you really want to delete …?"). The button is disabled while the deck is `PENDING`/`GENERATING`.
On success, `["presentations", id]` is refetched, `["presentation", presId]` is removed and `["projects"]` is invalidated (dashboard counts).
Backend `DELETE /presentations/{id}` **had no ownership check** (any user could delete any deck). It now returns 404 for non-owners, returns 409 while a non-stale job is generating (the worker would otherwise write to a deleted row), and deletes the `.pptx` file.
**Tests:** the shared SQLite fixture moved to `tests/conftest.py` (`api_env`). New `tests/test_delete_presentation.py` (4 tests). pytest 12/12 passed. `tsc --noEmit` clean. The page's pre-existing `any` lint errors are unchanged.
**Not verified in a browser.**

---

## 2026-09-23: Delete project from the dashboard

**Changed:** Dashboard project cards have a trash button that opens a new reusable `components/ConfirmDialog.tsx` ("Do you really want to delete …?", Esc/backdrop cancel, focus on Cancel).
Cards are now a `div` with a stretched `<Link>` (the `::after` overlay) so the button isn't nested inside an `<a>`. On success, `["projects"]` is invalidated and the project's cached queries are removed.
Backend `DELETE /projects/{id}` (which already existed with an ownership check) now also deletes each document's vectors (best-effort, logged on failure) and the project's storage folder (`StorageService.delete_project_dir`).
**Tests:** new `tests/test_delete_project.py` (SQLite in-memory, projects router only): delete removes rows, files and vectors; another user's delete returns 404 and touches nothing. pytest 8/8 passed. eslint + `tsc --noEmit` clean.
**Not verified in a browser.** Deleting a single *document* still leaves its vectors (TASKS item stays open).

---

## 2026-09-23: Logged-in user now survives a page refresh

**Root cause:** the Zustand store persisted only the token to localStorage, while `user` lived in memory. After a reload the Navbar (which checks `user`) showed "Sign In", even though API calls still sent the valid token.
**Changed:** `lib/store.ts` adds `setUser`. `components/Navbar.tsx` runs a `["me", token]` query to `GET /auth/me` when a token exists but `user` is null, restores the user, and calls `logout()` on a 401 (expired/invalid token).
**Known:** "Sign In" can still show for the moment the `/auth/me` request is in flight after a reload.
**Verified:** eslint + `tsc --noEmit` clean. Not verified in a browser. TASKS items "Load user on refresh" and "Auto-refresh document list" are ticked.

---

## 2026-09-23: Fixed dark-mode flash on page load

**Root cause:** the saved theme was applied in a `useEffect` in `Providers.tsx`, which runs only after hydration, so every full load painted light first and switched to dark 1–2 s later.
**Changed:** `app/layout.tsx` has an inline `<head>` script (Next 16 "preventing flash before hydration" pattern) that adds `.dark` to `<html>` from `localStorage.app_theme` before first paint.
`components/Providers.tsx` no longer uses state + effect: `theme` is read from the `<html>` class via `useSyncExternalStore`, and `setTheme` updates the class, localStorage and the subscribers.
**Verified:** eslint + `tsc --noEmit` clean on the changed files. Not verified in a browser.

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
