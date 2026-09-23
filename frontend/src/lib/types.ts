// API response types. Mirror backend/app/schemas/* (see docs/API.md).

export type DocumentStatus = "UPLOADED" | "PROCESSING" | "CHUNKING" | "EMBEDDING" | "INDEXED" | "FAILED";
export type PresentationStatus = "PENDING" | "GENERATING" | "COMPLETED" | "FAILED";

export interface ProjectDocument {
  id: string;
  project_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
  error_message?: string | null;
  created_at: string;
}

export interface Citation {
  document_name: string;
  page?: number | null;
  section?: string | null;
  excerpt?: string | null;
}

export type SlideType = "title" | "section" | "bullet" | "two_column" | "table" | "chart" | "quote" | "summary";

// Union of every slide type's fields (backend/app/schemas/presentation_spec.py); `type` says which apply.
export interface SlideContent {
  type: SlideType;
  title: string;
  subtitle?: string | null;
  bullets?: string[];
  left_title?: string;
  left_content?: string[];
  right_title?: string;
  right_content?: string[];
  columns?: string[];
  rows?: string[][];
  chart_type?: "bar" | "line" | "pie";
  labels?: string[];
  values?: number[];
  quote?: string;
  author?: string | null;
  key_takeaways?: string[];
  citations?: Citation[];
}

export interface Slide {
  id: string;
  slide_number: number;
  slide_type: SlideType;
  content_json: SlideContent;
  citations_json: Citation[];
  created_at: string;
}

export interface Presentation {
  id: string;
  project_id: string;
  title: string;
  prompt: string;
  theme: string;
  status: PresentationStatus;
  pptx_path?: string | null;
  created_at: string;
  updated_at: string;
  slides: Slide[];
}

export interface GenerationProgress {
  job_id: string;
  presentation_id: string;
  status: string;
  progress: number;
  current_step: string;
  error_message?: string | null;
}

// Shape of an Axios error carrying a FastAPI `detail` message
export interface ApiError {
  response?: { data?: { detail?: string } };
}

export function apiErrorDetail(err: unknown, fallback: string): string {
  const detail = (err as ApiError)?.response?.data?.detail;
  return typeof detail === "string" && detail ? detail : fallback;
}
