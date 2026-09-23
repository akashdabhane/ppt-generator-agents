# Tasks

How to use: tell the agent **"do the next unchecked task"**. Do one task at a time, test it, tick it (`[x]`),
and add a line to `PROGRESS.md`. Keep each task small enough for a single session.
Items marked 🐞 are confirmed bugs found by reading the code on 2026-09-22 (details in `PROGRESS.md`).

## P0: Broken core flows
- [ ] 🐞 Fix login: `frontend/src/app/login/page.tsx` posts JSON `{email,password}`, but `/auth/login` expects form-urlencoded `username`/`password`. Send `URLSearchParams` with `username=email`.
- [x] 🐞 Fix download: `presentations/[id]/page.tsx` uses a plain `<a href>` (no Bearer token → 401). Fetch it via `api.get(..., {responseType: "blob"})` and trigger a save.
- [x] 🐞 Pass `num_slides`, `audience` through to `rag_engine.execute` (done via task arguments; `tone`/`language` still ignored and nothing is persisted on `Presentation`).
- [x] 🐞 Pinecone upsert: metadata must not contain `null` values or nested objects (`table_data`, `page=None`). Drop the nulls and serialise `table_data` to a JSON string, then parse it back in the retriever.
- [ ] 🐞 `requirements.txt` is UTF-16 and includes `pywin32` (Windows-only), so the Linux Docker build fails. Rewrite it as UTF-8 with only the direct dependencies.
- [ ] 🐞 `frontend/Dockerfile` copies `.next/standalone`, but `next.config.ts` lacks `output: "standalone"`. Add it (and run `node server.js` in the runner).

## P1: Security & correctness
- [x] Ownership check + stale-job timeout (10 min → FAILED) on `GET /presentations/{id}/progress`; ownership check on `/download`.
- [ ] Show why a document FAILED in the Documents tab (the error message is stored but not displayed).
- [ ] 🐞 Add project-ownership checks to: `/slides/{n}/regenerate`, ~~`DELETE /presentations/{id}`~~ (done), `POST /documents/{id}/reindex`. Extract a shared `get_owned_project` / `get_owned_presentation` dependency in `deps.py`.
- [ ] 🐞 Delete vectors when a document is deleted (`vector_store.delete_document_chunks`) and before reindexing (otherwise duplicate chunks).
- [ ] 🐞 Slide regeneration: re-render the `.pptx` after updating a slide, and ask the LLM for a slide of the same type as the one it replaces (right now it takes `slides[0]` of a new deck, usually a title slide).
- [ ] 🐞 Fallback spec invents data (a "Quarterly Performance" chart with made-up numbers and fixed challenges/solutions). Build it only from retrieved context, or mark it clearly as placeholder.
- [ ] Load `SECRET_KEY` from env with no insecure default in production. Restrict CORS origins to `FRONTEND_URL`.
- [x] Update the LLM model IDs in `rag/graph.py` (Claude 3.5 Sonnet and Gemini 1.5 Pro are outdated) and make the model configurable via `LLM_MODEL` in settings.
- [ ] Use structured output / tool calling for the spec instead of stripping ``` fences, and retry once with the validation error before falling back.
- [ ] Embedding dimension: make it configurable and consistent across providers (Google `text-embedding-004` = 768 ≠ 1536).
- [ ] Map `DocumentChunk` ↔ vector ids correctly for pgvector/Pinecone deletes (store `document_id` in metadata. Already there, but verify the Pinecone filter delete works on serverless).

## P2: Features & UX
- [ ] PPTX ingestion: add `pptx_extractor.py` (python-pptx; per-slide text + tables). It is currently read as plain text, which produces garbage. Also add `.pptx` to the dropzone `accept`.
- [x] Auto-refresh the document list while any doc is not `INDEXED`/`FAILED` (`refetchInterval`).
- [ ] Show `error_message` for failed documents and failed generation jobs in the UI.
- [ ] Add a "Retry / Reindex" button for failed documents.
- [ ] Add a `PATCH /projects/{id}` route (the schema already exists) and an edit UI.
- [ ] Add a shared `frontend/src/lib/types.ts` for API types and remove the `any`s.
- [ ] Add route protection: redirect to `/login` when there's no token, and handle 401 globally in an Axios interceptor.
- [x] Load `user` on refresh (`GET /auth/me`), because the Zustand store only keeps the token.
- [ ] Replace the 2 s `setInterval` polling with TanStack `refetchInterval`, or implement real SSE.

## P3: Architecture & quality
- [ ] Turn `rag/graph.py` into a real LangGraph `StateGraph` (analyze → retrieve → outline → per-slide generate → validate), or rename it to remove the "LangGraph" claim.
- [ ] Add real reranking (e.g. a cross-encoder or LLM rerank) and use the LLM for query decomposition.
- [ ] Set up Alembic migrations and stop relying on `create_all`.
- [ ] Move the title-card geometry from `renderer.py` into `LayoutEngine`. Add bullet overflow handling (split long bullet lists across slides like tables).
- [ ] Use theme text colours for two-column and quote-author text (currently default black, invisible on the Dark theme).
- [ ] Tests: API tests with FastAPI `TestClient` + SQLite, chunker/extractor tests with small fixture files, and a renderer smoke test that opens the output `.pptx`.
- [ ] Fix the README: says async SQLAlchemy/SSE/LangGraph; the root `.env.example` is actually at `backend/.env.example`.
