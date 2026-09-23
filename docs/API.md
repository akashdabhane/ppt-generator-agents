# API Reference (v1)

Base URL: `http://localhost:8000/api/v1`. Interactive docs are at `/docs`.
Auth: `Authorization: Bearer <JWT>` on every route except register/login. Tokens expire after 7 days (`sub` = user id).
Keep this file in sync when endpoints change.

## Auth — `api/v1/auth.py`

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/auth/register` | JSON `{email, password, full_name?}` | `Token {access_token, token_type, user}` |
| POST | `/auth/login` | **form-urlencoded** `username=<email>&password=` (OAuth2PasswordRequestForm) | `Token` |
| GET | `/auth/me` | — | `UserResponse {id, email, full_name, created_at}` |

Passwords are hashed with PBKDF2-SHA256 (100k iterations, 16-byte salt), stored as `salt_hex:hash_hex`.

## Projects — `api/v1/projects.py`

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/projects` | `{name, description?}` | `ProjectResponse` |
| GET | `/projects` | — | `ProjectResponse[]` (includes `document_count`, `presentation_count`) |
| GET | `/projects/{project_id}` | — | `ProjectResponse` |
| DELETE | `/projects/{project_id}` | — | 204 (cascades DB rows; also deletes the project's vectors and its storage folder of uploads + decks) |

`ProjectUpdate` exists as a schema, but there is no PATCH route.

## Documents — `api/v1/documents.py`

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/projects/{project_id}/documents` | multipart `file` | `DocumentResponse` (status `UPLOADED`, ingestion is async) |
| GET | `/projects/{project_id}/documents` | — | `DocumentResponse[]` |
| DELETE | `/documents/{document_id}` | — | 204 (deletes the file and row; vectors are **not** removed) |
| POST | `/documents/{document_id}/reindex` | — | `DocumentResponse` |

Allowed extensions: `.pdf .docx .pptx .txt .csv .xlsx .xls .md .markdown`. Anything else returns 400.

## Presentations — `api/v1/presentations.py`

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/projects/{project_id}/presentations/generate` | `PresentationGenerateRequest` | `GenerationProgressResponse` |
| GET | `/projects/{project_id}/presentations` | — | `PresentationResponse[]` (newest first, with slides) |
| GET | `/presentations/{id}` | — | `PresentationResponse` |
| GET | `/presentations/{id}/progress` | — | `GenerationProgressResponse` (latest job) |
| GET | `/presentations/{id}/download` | — | `.pptx` file |
| POST | `/presentations/{id}/slides/{slide_number}/regenerate` | `{instructions?}` | `SlideResponse` |
| DELETE | `/presentations/{id}` | — | 204 (owner only, else 404; also deletes the `.pptx`). 409 while `PENDING`/`GENERATING` and younger than the 10-min stale timeout |

```jsonc
// PresentationGenerateRequest
{ "prompt": "str", "num_slides": 10, "audience": "General", "theme": "Professional",
  "tone": "Professional & Informative", "language": "English" }
// theme ∈ Professional | Minimal | Dark | Corporate | Modern (unknown → Professional)

// GenerationProgressResponse
{ "job_id": "", "presentation_id": "", "status": "JobStatus", "progress": 0, "current_step": "", "error_message": null }
```

## PresentationSpec: the LLM output contract (`schemas/presentation_spec.py`)

```jsonc
{ "title": "str", "subtitle": "str?", "slides": [ SlideSpec, ... ] }
```
Every slide has `type`, `title`, and `citations: [{document_name, page?, section?, excerpt?}]`.

| `type` | Extra fields |
|---|---|
| `title` / `section` | `subtitle?` |
| `bullet` | `bullets: str[]` |
| `two_column` | `left_title, left_content: str[], right_title, right_content: str[]` |
| `table` | `columns: str[], rows: str[][]` (paginated by the LayoutEngine) |
| `chart` | `chart_type: bar\|line\|pie, labels: str[], values: float[]` |
| `quote` | `quote, author?` |
| `summary` | `key_takeaways: str[]` |

No geometry, fonts or colors are allowed in the spec.
