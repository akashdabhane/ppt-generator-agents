# AGENTS.md

Instructions for AI coding agents (Cursor, Codex, Copilot, Gemini, etc.).

The canonical agent instructions for this repository live in **[CLAUDE.md](CLAUDE.md)**. Read it first,
then follow its "Read before working" table into `docs/`.

Summary:
- Product: upload documents → RAG index → generate grounded, cited `.pptx` decks from a prompt.
- Architecture rule: the LLM produces a JSON content spec only; `LayoutEngine` owns all geometry.
- Backend: FastAPI + sync SQLAlchemy + Celery/Redis + vector store adapters + python-pptx (`backend/`).
- Frontend: Next.js 16 App Router + Tailwind v4 + TanStack Query + Zustand (`frontend/`).
- Session start: read `docs/PROGRESS.md` and `docs/TASKS.md`. Session end: update both.
