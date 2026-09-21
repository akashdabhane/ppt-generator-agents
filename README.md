# Production-Ready AI RAG-Based PowerPoint Generator

Full-stack production application where users upload documents (PDF, DOCX, XLSX, CSV, PPTX, TXT, Markdown), the system indexes them into a multi-query hybrid RAG pipeline, and users generate PowerPoint presentations (`.pptx`) via natural-language prompts.

---

## Architectural Principle

> **Core Architectural Rule**:
> **RAG determines what information is relevant $\rightarrow$ The LLM determines the presentation content and structure (JSON specification only) $\rightarrow$ The Layout Engine determines exact dimensions, positioning, and table pagination $\rightarrow$ The PPT Renderer creates the final PowerPoint (`.pptx`).**
>
> The LLM **NEVER** generates or controls slide layout, $x, y$ coordinates, widths, heights, font sizes, margins, or element positioning.

---

## System Architecture

```mermaid
flowchart TD
    subgraph Client ["Frontend (Next.js 16 + React 19)"]
        UI["User Interface / Prompts"]
        Dropzone["Document Upload Dropzone"]
        Viewer["Slide Deck & Citation Previewer"]
    end

    subgraph API ["Backend (FastAPI Python 3.12)"]
        Router["API Route Controllers"]
        Auth["JWT Auth Service"]
        Storage["Storage Service"]
    end

    subgraph RAG ["RAG & Background Engine"]
        Celery["Celery & Redis Worker"]
        Chunker["Document Chunker & Metadata Extractor"]
        VectorDB["Pinecone Vector Store"]
        LangGraph["LangGraph Workflow Machine"]
    end

    subgraph Rendering ["Deterministic Layout & PPTX Layer"]
        LayoutEngine["Layout Engine (Table Pagination & Bounds Math)"]
        PPTRenderer["python-pptx Renderer (Themes)"]
    end

    Dropzone -->|Upload File| Storage
    Storage -->|Trigger Task| Celery
    Celery --> Chunker
    Chunker --> VectorDB

    UI -->|Prompt Request| Router
    Router --> LangGraph
    LangGraph -->|Hybrid Query| VectorDB
    VectorDB -->|Retrieved Context + Citations| LangGraph
    LangGraph -->|Structured JSON Spec| LayoutEngine
    LayoutEngine -->|Bounds & Split Tables| PPTRenderer
    PPTRenderer -->|.pptx File| Viewer
```

---

## Key Features

- **Multi-Format Ingestion**: Ingests PDF, DOCX, XLSX, CSV, PPTX, TXT, and Markdown files while preserving spreadsheet table headers, sheets, and rows.
- **Hybrid RAG & LangGraph Workflow**: Query decomposition, multi-query retrieval, reranking, context assembly, and document citation tracking (filename, page, section, excerpt).
- **Deterministic Table Pagination**: Automatically splits long tables (e.g. 25 rows into $10 + 10 + 5$ rows across 3 slides) with dynamic cell density calculations to guarantee **zero visual overflow**.
- **Visual Design Themes**: Built-in support for Professional, Minimal, Dark, Corporate, and Modern themes.
- **Single Slide Regeneration**: Allows users to rewrite or re-style individual slides without re-generating the entire deck.
- **Async Job Queue**: Celery + Redis workers manage non-blocking ingestion and presentation creation with real-time SSE step progress tracking.

---

## Project Structure

```text
ppt-generator-agents/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # FastAPI Route Controllers (auth, projects, documents, presentations)
│   │   ├── core/            # Config & Pydantic settings
│   │   ├── database/        # Async SQLAlchemy 2.0 Engine & session
│   │   ├── document_processing/ # Multi-format extractors & smart chunker
│   │   ├── models/          # DB Models (User, Project, Document, Chunk, Presentation, Slide, Job)
│   │   ├── presentation/    # Layout Engine, Table Pagination & python-pptx Renderer
│   │   ├── rag/             # LangGraph State Machine, Vector Store & Hybrid Retriever
│   │   ├── schemas/         # Pydantic Schemas (PresentationSpec, User, Project, Document)
│   │   ├── services/        # File Storage Service
│   │   └── workers/         # Celery App & Async Tasks
│   ├── tests/               # Pytest suite for Table Pagination & Layout Bounds
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js 16 App Router pages
│   │   ├── components/      # UI Components (Navbar, Providers)
│   │   └── lib/             # Axios API client & Zustand store
│   ├── Dockerfile
│   └── package.json
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Quick Start (Docker Compose)

Start all services (Frontend, Backend, Worker, PostgreSQL, Redis) with a single command:

```bash
docker compose up --build
```

Access the Web Application at:
- **Frontend App**: `http://localhost:3000`
- **FastAPI Documentation**: `http://localhost:8000/docs`

---

## Manual Local Development

### 1. Backend Setup

```bash
cd backend
python -m venv myvenv
# On Windows:
myvenv\Scripts\activate
# On Linux/macOS:
source myvenv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Run Automated Layout Engine Tests

```bash
cd backend
$env:PYTHONPATH="."  # Windows Powershell
pytest tests/test_layout_engine.py
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

---

## Environment Variables

Copy `.env.example` to `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ppt_generator_db
REDIS_URL=redis://localhost:6379/0
VECTOR_DB_TYPE=pinecone
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_INDEX_NAME=ppt-generator-rag
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_anthropic_api_key_here
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```
