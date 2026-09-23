# Decision Log

Short records of important choices, so agents don't undo them. Format: context → decision → consequences.
To reverse a decision, add a new entry that supersedes the old one. Don't edit history.
D-001 to D-009 were reconstructed from the existing code on 2026-09-22.

### D-001 — LLM produces content only; layout is deterministic code
- **Context:** LLM-generated layouts overflow, misalign and vary from run to run.
- **Decision:** The LLM returns a `PresentationSpec` JSON (content + slide type). `LayoutEngine` computes all geometry and `PresentationRenderer` draws it.
- **Consequences:** Visual quality is predictable and testable. New visual features need code, not prompt tweaks.

### D-002 — Fixed set of 8 slide types
- **Decision:** title, section, bullet, two_column, table, chart, quote, summary, as a Pydantic union.
- **Consequences:** Adding a type touches schema, prompt, renderer, frontend preview and API docs (see CLAUDE.md).

### D-003 — Tables are never split mid-row; long tables paginate across slides
- **Decision:** Extractors keep a table as one chunk (with `table_data`). The renderer paginates rows at 10/7/4 per slide based on cell length.
- **Consequences:** Zero overflow for tables. One spec slide may become several `.pptx` slides.

### D-004 — Vector store behind an adapter, Pinecone by default
- **Decision:** `BaseVectorStore` with Pinecone (namespace per project), pgvector and in-memory mock, chosen by `VECTOR_DB_TYPE`.
- **Consequences:** Backends can be swapped without touching the RAG code. Project isolation comes from the namespace/`project_id` column.

### D-005 — Every external dependency has a fallback
- **Decision:** No Celery → FastAPI BackgroundTasks. No vector DB → mock. No embedding key → hash vectors. No LLM key or bad JSON → deterministic spec.
- **Consequences:** The app runs locally with zero keys. Failures can be silent, so check logs and job/document status.

### D-006 — Synchronous SQLAlchemy
- **Context:** An async engine caused greenlet/DLL problems on Windows (see the comment in `main.py`).
- **Decision:** Use a sync engine and `SessionLocal`. `postgresql+asyncpg://` URLs are rewritten to `postgresql://`.
- **Consequences:** Route handlers are plain `def` (FastAPI runs them in a threadpool). Don't introduce `AsyncSession` piecemeal.

### D-007 — Custom PBKDF2 password hashing + JWT (python-jose)
- **Decision:** Use hashlib PBKDF2-SHA256 (100k iterations) instead of passlib/bcrypt, and HS256 JWTs valid for 7 days, stored in `localStorage`.
- **Consequences:** No extra native dependencies. localStorage tokens are exposed to XSS, so consider httpOnly cookies later.

### D-008 — Local-disk file storage
- **Decision:** `StorageService` writes under `backend/storage/projects/{id}/...`.
- **Consequences:** Simple, but the API and worker must share the volume. Move to S3-compatible storage before scaling out.

### D-009 — Frontend: Next.js App Router, client components, TanStack Query + Zustand
- **Decision:** Pages are `"use client"` and fetch with TanStack Query via a shared Axios instance. Zustand holds only auth. Tailwind v4 uses class-based dark mode.
- **Consequences:** Simple to extend. No SSR data fetching and no server actions.

### D-010 — Text slides are measured and paginated, like tables (2026-09-23)
- **Context:** Only tables were paginated. Long bullet/summary/two-column lists and long titles overflowed the slide, breaking PRD §6 "zero overflow".
- **Decision:** `LayoutEngine` estimates wrapped line counts (conservative average glyph width 0.55 em, 0.6 bold, 1.2 line spacing, default text insets). Lists are split greedily into "(cont.)" slides. Titles, the title card and quotes step the font down to a minimum and truncate with "…" only as a last resort. Tables keep the 10/7/4 row caps and also respect a height budget.
- **Consequences:** One spec slide can become several `.pptx` slides (the DB/preview still has one row per spec slide). The estimate over-measures slightly, so slides may carry a little less text than would physically fit.

### D-011 — Refuse rather than invent (2026-09-23)
- **Context:** The no-LLM fallback deck contained made-up numbers and generic advice, and with empty retrieval the LLM would write from memory.
- **Decision:** Generation needs at least one `INDEXED` document (400 otherwise) and non-empty retrieval (job `FAILED` with a clear message otherwise). The fallback deck copies sentences/tables verbatim from retrieved chunks and cites each one. LLM citations to documents that weren't retrieved are dropped. Without an LLM, slide regeneration is only offered for types that can be built from excerpts (bullet, summary, table).
- **Consequences:** The no-key deck is plainer, but everything in it is traceable. Users see an error instead of a plausible-looking but ungrounded deck.

### D-012 — Text formatting is set on runs, not only paragraph defaults (2026-09-23)
- **Decision:** `PresentationRenderer._write()` sets font, size, bold/italic and colour on each run as well as `paragraph.font` (which python-pptx writes as `defRPr`, ignored by some importers).
- **Consequences:** Decks look the same in PowerPoint, Google Slides, Keynote and LibreOffice. All text now has an explicit theme colour (this fixed black text on the Dark theme).

