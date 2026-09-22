# PRD: AI RAG PowerPoint Generator ("AI SlideRAG")

_Last updated: 2026-09-23. Drafted from the code and README, then confirmed against the project owner's
handoff summary from their previous agent (Anti-Gravity). The **Success metrics** in §7 are still proposals._

## 1. Problem & motive

Building a presentation from corporate reports, financial spreadsheets, PDFs and unstructured notes takes
hours of manual work: reading long files, pulling out metrics, rebuilding tables and fixing slide alignment.

Generic AI slide generators have two major flaws, and this project exists to fix both:
1. **Hallucination / no grounding:** they rely on the LLM's own memory, so they make up figures, dates and facts.
2. **Visual overflow / broken layouts:** they let the LLM generate coordinates or HTML/CSS, which leads to
   overlapping text, clipped table cells and content spilling off the slide.

## 2. Solution

A web app where a user:
1. creates a **project** (a knowledge-base workspace),
2. uploads source **documents** (PDF, DOCX, XLSX/XLS, CSV, TXT, Markdown; PPTX planned),
3. writes a **prompt** such as "10 slides on our Q3 performance for senior management",
4. gets an editable **`.pptx`** whose content comes only from their documents, with a source citation on each slide,
5. can preview the deck in the browser, regenerate individual slides, and download the file.

What sets it apart: **100 % grounded content + deterministic layout**. The AI writes content, and code
guarantees that nothing overflows the slide. Long tables are split across slides automatically.

**Deliverables to the user:** a native 16:9 (10 × 5.625 in) `.pptx` that is fully editable in PowerPoint,
Google Slides and Keynote, plus an in-browser preview of every slide with its citations.

## 3. Target users (confirmed)

Non-technical domain professionals who work with **private documents** and need **verifiable facts**.

| Persona | Need |
|---|---|
| Business / financial analyst | Turn heavy `.xlsx`/`.csv` files and financial filings into quarterly management decks, with headers kept and long tables paginated |
| Consultant / strategy manager | Combine several client documents into executive summaries with section citations |
| Researcher / student | Decks built from academic papers and notes, with page/section citations |
| Sales / marketing | Customer-account or product decks grounded strictly in internal collateral |

They care more about correctness and a clean layout than about flashy design.

## 4. Core features (current scope)

| # | Feature | Status |
|---|---|---|
| F1 | Email/password sign-up and login (JWT) | Built. Login form/API mismatch, see PROGRESS |
| F2 | Projects: create, list (with doc/deck counts), view, delete | Built |
| F3 | Document upload with async ingestion (extract → chunk → embed → index) and a status badge | Built |
| F4 | Table-aware extraction: tables stay intact as single chunks with headers/rows kept | Built |
| F5 | Prompt-based deck generation: slide count, audience, theme | Built (count/audience ignored by worker) |
| F6 | 8 slide types: title, section, bullet, two_column, table, chart, quote, summary | Built |
| F7 | Deterministic table pagination (e.g. 25 rows → 10 + 10 + 5) | Built and tested |
| F8 | 5 PPT themes: Professional, Minimal, Dark, Corporate, Modern | Built |
| F9 | Per-slide citations (document, page, section, excerpt) shown in the footer and preview | Built |
| F10 | Generation progress (job status + %) | Built (polling) |
| F11 | In-browser slide preview and `.pptx` download | Built (download auth bug) |
| F12 | Regenerate a single slide with instructions | Partial: updates DB only, `.pptx` not re-rendered |
| F13 | Light/dark UI theme toggle | Built |

## 5. Non-goals (for now)

- Editing slides as free-form WYSIWYG in the browser. Users edit the downloaded `.pptx` in PowerPoint.
- LLM-controlled layout, custom fonts, or pixel positioning. See `DECISIONS.md` D-001.
- Real-time multi-user collaboration or sharing between users.
- Web search or any knowledge outside the uploaded documents.
- Images or generated artwork inside slides.
- Billing, teams and organizations.

## 6. Requirements that must always hold

- **Grounding:** slide content must come from retrieved context. No invented figures.
- **Zero overflow:** every element stays inside the 10 × 5.625 in (16:9) slide bounds.
- **Isolation:** a user can only see or act on their own projects, documents and decks.
- **Resilience:** the app keeps working without Celery, Pinecone or LLM keys, using the fallbacks.

## 7. Definition of done / success metrics (proposed)

- A 10-slide deck is generated in under 60 s for a project with ≤ 20 documents.
- 0 slides with visual overflow on the table-pagination test suite and a sample corpus.
- ≥ 90 % of content slides carry at least one valid citation.
- The downloaded `.pptx` opens without repair prompts in PowerPoint and Google Slides.

## 8. Future ideas (not committed)

PPTX ingestion, SSE/WebSocket progress, a real LangGraph agent loop (outline → per-slide generation →
validation), reranking, speaker notes, image slides, custom brand themes, deck export to PDF, sharing links.
