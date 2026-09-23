# CLAUDE.md — Clarion (AI RAG PowerPoint generator)

Users upload documents into a project, the backend indexes them for RAG, and users generate
`.pptx` decks from a natural-language prompt. Every slide is grounded in (and cites) the uploaded documents.

**Why it exists:** generic AI slide tools make up facts and produce broken, overflowing layouts. This app
fixes both with grounded RAG content and a deterministic layout engine. Users are non-technical professionals
(analysts, consultants, researchers, sales) working with private documents. Details: `docs/PRD.md`.

## Read before working

| When you are…                         | Read                        |
|---------------------------------------|-----------------------------|
| Starting any session                  | `docs/PROGRESS.md`, `docs/TASKS.md` |
| Adding/changing a feature             | `docs/PRD.md`               |
| Touching backend structure, data flow | `docs/ARCHITECTURE.md`      |
| Adding/changing an endpoint           | `docs/API.md`               |
| Building UI or PPT themes             | `docs/DESIGN.md`            |
| Tempted to change a core choice       | `docs/DECISIONS.md`         |

Folder-specific rules: `backend/CLAUDE.md`, `frontend/CLAUDE.md`.

## The one rule you must never break

**RAG decides what is relevant → the LLM outputs a JSON `PresentationSpec` (content only) → the
`LayoutEngine` decides all geometry → the `PresentationRenderer` writes the `.pptx`.**
The LLM never produces coordinates, sizes, fonts, colors or positioning. Layout math lives only in
`backend/app/presentation/layout_engine.py`.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (**sync** sessions) + Alembic, PostgreSQL, Celery + Redis,
  Pinecone / pgvector / in-memory mock vector store, LangChain chat models (Anthropic/OpenAI/Google), python-pptx.
- **Frontend:** Next.js 16 (App Router) + React 19, TypeScript, Tailwind CSS v4, TanStack Query, Zustand, Axios, lucide-react.
  Next 16 has breaking changes: read `frontend/node_modules/next/dist/docs/` before using unfamiliar Next APIs.

## Commands

```bash
# Everything (postgres, redis, backend, worker, frontend)
docker compose up --build

# Backend (from backend/, venv active)
uvicorn app.main:app --reload --port 8000                            # applies Alembic migrations on startup
alembic revision --autogenerate -m "describe change"                 # after changing a model (review the file)
celery -A app.workers.celery_app.celery_app worker --loglevel=info   # optional; API falls back to in-process
PYTHONPATH=. pytest                      # PowerShell: $env:PYTHONPATH="."; pytest

# Frontend (from frontend/)
npm run dev      # http://localhost:3000
npm run lint
npm run build
```

API docs: http://localhost:8000/docs. Config comes from `backend/.env` (template: `backend/.env.example`).
With no API keys, the app still runs: mock vector store, hash vectors + keyword ranking, and a no-LLM deck built verbatim
from document excerpts. Placeholder values like `your_openai_api_key_here` count as unset.

## Working rules

- Keep changes small and consistent with neighbouring code. Match existing naming and patterns.
- New slide type = update **all** of: `schemas/presentation_spec.py`, the LLM prompt in `rag/graph.py`,
  `presentation/renderer.py`, the preview in `frontend/src/app/presentations/[id]/page.tsx`, and `docs/API.md`.
- Every endpoint that touches a project resource must check `project.user_id == current_user.id`.
- Never commit secrets or `backend/.env`. Add any new env var to `backend/.env.example` and `core/config.py`.
- Don't claim the app "uses LangGraph" or "SSE" in new code/docs: the current engine is a plain
  Python pipeline and progress is polled (see `docs/ARCHITECTURE.md`).
- Add or extend pytest tests for backend logic you change, especially the layout engine.

## End of every session

Update `docs/PROGRESS.md` (what changed, what's broken, where you stopped) and tick items in `docs/TASKS.md`.
Record any significant technical choice in `docs/DECISIONS.md`.
