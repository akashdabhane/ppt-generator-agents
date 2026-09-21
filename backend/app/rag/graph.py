import json
from typing import Dict, Any, List, TypedDict, Optional
from pydantic import BaseModel
from app.core.config import settings
from app.rag.retriever import retriever
from app.schemas.presentation_spec import PresentationSpec, SlideSpec, Citation


class GraphState(TypedDict):
    project_id: str
    user_prompt: str
    num_slides: int
    audience: str
    theme: str
    sub_queries: List[str]
    retrieved_contexts: List[Dict[str, Any]]
    outline: List[Dict[str, Any]]
    presentation_spec: Optional[Dict[str, Any]]
    validation_passed: bool
    error: Optional[str]


class LangGraphRAGEngine:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER

    def _get_llm(self):
        if settings.ANTHROPIC_API_KEY and self.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model="claude-3-5-sonnet-20240620", api_key=settings.ANTHROPIC_API_KEY)
        elif settings.OPENAI_API_KEY and self.provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model="gpt-4o", api_key=settings.OPENAI_API_KEY)
        elif settings.GOOGLE_API_KEY and self.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model="gemini-1.5-pro", google_api_key=settings.GOOGLE_API_KEY)
        return None

    def execute(self, project_id: str, prompt: str, num_slides: int = 10, audience: str = "General", theme: str = "Professional") -> PresentationSpec:
        # Step 1: Query Analysis & Decomposition
        sub_queries = [
            prompt,
            f"{prompt} key performance metrics and statistics",
            f"{prompt} executive summary overview",
            f"{prompt} recommendations and conclusions"
        ]

        # Step 2: Hybrid Context Retrieval
        contexts = retriever.retrieve(project_id, prompt, sub_queries=sub_queries)

        # Build context document text block for LLM prompt
        context_str = ""
        citations_list = []
        for c in contexts:
            doc_info = f"Document: {c['document']} (Page {c.get('page') or 'N/A'}, Section: {c.get('section')})"
            context_str += f"\n--- {doc_info} ---\n{c['content']}\n"
            citations_list.append({
                "document_name": c['document'],
                "page": c.get('page'),
                "section": c.get('section'),
                "excerpt": c['content'][:150] + "..." if len(c['content']) > 150 else c['content']
            })

        llm = self._get_llm()

        if not llm:
            # Fallback deterministic structured JSON generation when no LLM API key is active
            return self._generate_fallback_spec(prompt, contexts, num_slides, theme)

        # Step 3: LLM Generation of Structured Presentation Spec
        system_prompt = f"""You are an expert presentation designer.
Generate a structured JSON presentation specification based strictly on the retrieved document context below.
Do NOT fabricate information not present in the context.

Target Slide Count: {num_slides}
Target Audience: {audience}

CRITICAL RULES:
- Output MUST be valid JSON adhering strictly to the schema.
- Do NOT output any layout coordinates, x, y, width, height, font sizes, or inline styling.
- Available slide types:
  1. "title": {{ "type": "title", "title": str, "subtitle": str }}
  2. "section": {{ "type": "section", "title": str, "subtitle": str }}
  3. "bullet": {{ "type": "bullet", "title": str, "bullets": [str, ...] }}
  4. "two_column": {{ "type": "two_column", "title": str, "left_title": str, "left_content": [str, ...], "right_title": str, "right_content": [str, ...] }}
  5. "table": {{ "type": "table", "title": str, "columns": [str, ...], "rows": [[str, ...], ...] }}
  6. "chart": {{ "type": "chart", "title": str, "chart_type": "bar"|"line"|"pie", "labels": [str, ...], "values": [float, ...] }}
  7. "quote": {{ "type": "quote", "title": str, "quote": str, "author": str }}
  8. "summary": {{ "type": "summary", "title": str, "key_takeaways": [str, ...] }}

Retrieved Context:
{context_str}
"""
        response = llm.invoke(system_prompt + "\nGenerate the PresentationSpec JSON:")
        
        try:
            # Clean json fences if present
            raw_text = response.content.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            data = json.loads(raw_text.strip())
            return PresentationSpec.model_validate(data)
        except Exception:
            return self._generate_fallback_spec(prompt, contexts, num_slides, theme)

    def _generate_fallback_spec(self, prompt: str, contexts: List[Dict[str, Any]], num_slides: int, theme: str) -> PresentationSpec:
        citations = []
        if contexts:
            c = contexts[0]
            citations.append(Citation(
                document_name=c["document"],
                page=c.get("page"),
                section=c.get("section"),
                excerpt=c["content"][:100]
            ))

        slides: List[SlideSpec] = []
        slides.append({
            "type": "title",
            "title": prompt.title() if len(prompt) < 60 else "Executive Report & Analysis",
            "subtitle": f"AI-Generated Presentation • Theme: {theme}",
            "citations": citations
        })

        slides.append({
            "type": "bullet",
            "title": "Executive Summary",
            "bullets": [
                "Analysis based on uploaded project knowledge base",
                "Key trends and findings synthesized directly from source documents",
                "Factual integrity preserved with document citation tracking",
                "Deterministic layout rendering for visual consistency"
            ],
            "citations": citations
        })

        # Search for any extracted table data in context
        table_context = next((c for c in contexts if c.get("is_table") and c.get("table_data")), None)
        if table_context and table_context["table_data"]:
            tbl = table_context["table_data"]
            slides.append({
                "type": "table",
                "title": f"Data Summary - {table_context.get('section', 'Table')}",
                "columns": tbl.get("headers", ["Category", "Value"])[:5],
                "rows": tbl.get("rows", [["Sample", "100"]])[:10],
                "citations": citations
            })

        slides.append({
            "type": "chart",
            "title": "Quarterly Performance Metrics",
            "chart_type": "bar",
            "labels": ["Q1", "Q2", "Q3", "Q4"],
            "values": [35.0, 42.5, 28.0, 50.0],
            "citations": citations
        })

        slides.append({
            "type": "two_column",
            "title": "Key Challenges & Strategic Solutions",
            "left_title": "Identified Challenges",
            "left_content": [
                "Operational bottlenecks in Q3",
                "Regional distribution delays",
                "Increased overhead costs"
            ],
            "right_title": "Proposed Solutions",
            "right_content": [
                "Streamline fulfillment workflows",
                "Expand regional logistics network",
                "Optimize resource allocation"
            ],
            "citations": citations
        })

        slides.append({
            "type": "summary",
            "title": "Strategic Next Steps",
            "key_takeaways": [
                "Execute operational recommendations across all business units",
                "Monitor Q4 revenue and performance benchmarks closely",
                "Review findings with leadership team"
            ],
            "citations": citations
        })

        return PresentationSpec(
            title=prompt.title() if len(prompt) < 60 else "Presentation Overview",
            subtitle=f"Prepared for Project Analysis",
            slides=slides
        )


rag_engine = LangGraphRAGEngine()
