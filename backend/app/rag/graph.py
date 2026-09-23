import json
import logging
import re
from typing import Dict, Any, List, TypedDict, Optional, get_args
from pydantic import BaseModel
from app.core.config import settings
from app.rag.retriever import retriever
from app.schemas.presentation_spec import PresentationSpec, SlideSpec, Citation

logger = logging.getLogger(__name__)

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o",
    "google": "gemini-2.5-flash",
}


# JSON shape of each slide type, shown to the LLM. Must match app/schemas/presentation_spec.py.
SLIDE_TYPE_SCHEMAS = {
    "title": '{ "type": "title", "title": str, "subtitle": str }',
    "section": '{ "type": "section", "title": str, "subtitle": str }',
    "bullet": '{ "type": "bullet", "title": str, "bullets": [str, ...] }',
    "two_column": '{ "type": "two_column", "title": str, "left_title": str, "left_content": [str, ...], '
                  '"right_title": str, "right_content": [str, ...] }',
    "table": '{ "type": "table", "title": str, "columns": [str, ...], "rows": [[str, ...], ...] }',
    "chart": '{ "type": "chart", "title": str, "chart_type": "bar"|"line"|"pie", "labels": [str, ...], "values": [float, ...] }',
    "quote": '{ "type": "quote", "title": str, "quote": str, "author": str }',
    "summary": '{ "type": "summary", "title": str, "key_takeaways": [str, ...] }',
}
SLIDE_SPEC_CLASSES = {cls.model_fields["type"].default: cls for cls in get_args(SlideSpec)}
CITATION_SHAPE = '{ "document_name": str, "page": int|null, "section": str, "excerpt": str }'


class SlideRegenerationUnavailable(Exception):
    """Raised when a slide type can't be regenerated without an LLM (no invented fallback content)."""


class NoGroundingContextError(Exception):
    """Raised when retrieval finds nothing to ground the deck on. Generating anyway would mean inventing content."""


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
        model = settings.LLM_MODEL or DEFAULT_MODELS.get(self.provider)
        if settings.ANTHROPIC_API_KEY and self.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=model, api_key=settings.ANTHROPIC_API_KEY, max_tokens=8192)
        elif settings.OPENAI_API_KEY and self.provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model, api_key=settings.OPENAI_API_KEY)
        elif settings.GOOGLE_API_KEY and self.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=model, google_api_key=settings.GOOGLE_API_KEY)
        logger.warning(f"No API key for LLM_PROVIDER '{self.provider}'. Using deterministic fallback spec.")
        return None

    @staticmethod
    def _parse_spec(content: Any) -> PresentationSpec:
        # Some providers return a list of content blocks instead of a plain string
        if isinstance(content, list):
            content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
        raw_text = str(content)
        # Take the outermost JSON object, ignoring code fences or prose around it
        start, end = raw_text.find("{"), raw_text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("LLM response contained no JSON object")
        return PresentationSpec.model_validate(json.loads(raw_text[start:end + 1]))

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
        if not contexts:
            raise NoGroundingContextError(
                "No content from this project's documents could be retrieved. Upload documents, wait until they "
                "show INDEXED (re-index them if the server was restarted), then try again."
            )

        llm = self._get_llm()

        if not llm:
            # Fallback deterministic structured JSON generation when no LLM API key is active
            return self._generate_fallback_spec(prompt, contexts, num_slides, theme)

        # Step 3: LLM Generation of Structured Presentation Spec
        type_lines = "\n".join(f"  {i}. \"{t}\": {shape}" for i, (t, shape) in enumerate(SLIDE_TYPE_SCHEMAS.items(), 1))
        system_prompt = f"""You are an expert presentation designer.
Generate a structured JSON presentation specification based strictly on the retrieved document context below.
Do NOT fabricate information not present in the context.

Target Slide Count: {num_slides}
Target Audience: {audience}

CRITICAL RULES:
- Output MUST be a single valid JSON object and nothing else, shaped exactly like:
  {{ "title": str, "subtitle": str, "slides": [ <slide>, ... ] }}
- Produce exactly {num_slides} slides. Start with a "title" slide and end with a "summary" slide.
- Every slide except "title" should include "citations": [{CITATION_SHAPE}]
  taken from the document headers in the context below.
- Only use "table" or "chart" slides when the context contains the actual numbers.
- Do NOT output any layout coordinates, x, y, width, height, font sizes, or inline styling.
- Available slide types:
{type_lines}

Retrieved Context:
{self._context_block(contexts)}
"""
        response = llm.invoke(system_prompt + f"\nUser request: {prompt}\n\nGenerate the PresentationSpec JSON:")

        try:
            return self._ground_citations(self._parse_spec(response.content), contexts)
        except Exception as e:
            logger.warning(f"LLM returned an invalid PresentationSpec ({e}). Using deterministic fallback spec.")
            return self._generate_fallback_spec(prompt, contexts, num_slides, theme)

    @staticmethod
    def _context_block(contexts: List[Dict[str, Any]]) -> str:
        block = ""
        for c in contexts:
            block += f"\n--- Document: {c['document']} (Page {c.get('page') or 'N/A'}, Section: {c.get('section')}) ---\n{c['content']}\n"
        return block

    def regenerate_slide(self, project_id: str, deck_prompt: str, current: Dict[str, Any],
                         instructions: Optional[str] = None, audience: str = "General") -> SlideSpec:
        """Rewrites one slide, keeping its type, grounded in freshly retrieved context."""
        slide_type = current.get("type", "bullet")
        slide_cls = SLIDE_SPEC_CLASSES.get(slide_type, SLIDE_SPEC_CLASSES["bullet"])
        focus = " ".join(x for x in [instructions, current.get("title")] if x) or deck_prompt
        contexts = retriever.retrieve(project_id, focus, sub_queries=[deck_prompt])
        if not contexts:
            raise NoGroundingContextError(
                "No content from this project's documents could be retrieved to regenerate this slide."
            )

        llm = self._get_llm()
        if not llm:
            return self._fallback_slide(slide_type, current, contexts)

        current_json = json.dumps({k: v for k, v in current.items() if k != "citations"}, ensure_ascii=False)
        prompt = f"""You are revising ONE slide of an existing presentation about: {deck_prompt}
Target Audience: {audience}

Current slide: {current_json}
User instructions: {instructions or "Improve this slide using the most relevant facts from the context."}

CRITICAL RULES:
- Output MUST be a single valid JSON object and nothing else, shaped exactly like:
  {SLIDE_TYPE_SCHEMAS.get(slide_type, SLIDE_TYPE_SCHEMAS["bullet"])[:-1].rstrip()}, "citations": [{CITATION_SHAPE}] }}
- Keep "type" exactly "{slide_type}".
- Use ONLY facts from the retrieved context below. Do NOT fabricate information.
- Do NOT output any layout coordinates, sizes, fonts or styling.

Retrieved Context:
{self._context_block(contexts)}

Generate the slide JSON:"""
        response = llm.invoke(prompt)
        content = response.content
        if isinstance(content, list):
            content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
        raw = str(content)
        start, end = raw.find("{"), raw.rfind("}")
        try:
            data = json.loads(raw[start:end + 1])
            data["type"] = slide_type
            slide = slide_cls.model_validate(data)
        except Exception as e:
            logger.warning(f"LLM returned an invalid {slide_type} slide ({e}). Using fallback slide.")
            return self._fallback_slide(slide_type, current, contexts)
        spec = self._ground_citations(PresentationSpec(title="", slides=[slide]), contexts)
        return spec.slides[0]

    def _fallback_slide(self, slide_type: str, current: Dict[str, Any], contexts: List[Dict[str, Any]]) -> SlideSpec:
        """No-LLM regeneration built only from retrieved excerpts, for the types that can be built that way."""
        title = current.get("title") or "Slide"
        text_contexts = [c for c in contexts if not c.get("is_table")]
        if slide_type in ("bullet", "summary") and text_contexts:
            items, cites = [], []
            for c in text_contexts:
                for sentence in self._sentences(c["content"], 2):
                    if len(items) < 5:
                        items.append(sentence)
                        if not cites or cites[-1].document_name != c["document"] or cites[-1].page != c.get("page"):
                            cites.append(self._citation_for(c))
            key = "bullets" if slide_type == "bullet" else "key_takeaways"
            return SLIDE_SPEC_CLASSES[slide_type].model_validate(
                {"type": slide_type, "title": title, key: items, "citations": [c.model_dump() for c in cites]})
        if slide_type == "table":
            tbl_ctx = next((c for c in contexts if c.get("is_table") and (c.get("table_data") or {}).get("rows")), None)
            if tbl_ctx:
                tbl = tbl_ctx["table_data"]
                return SLIDE_SPEC_CLASSES["table"].model_validate({
                    "type": "table", "title": title,
                    "columns": [str(h) for h in tbl.get("headers", [])],
                    "rows": [[str(v) for v in row] for row in tbl["rows"]],
                    "citations": [self._citation_for(tbl_ctx).model_dump()],
                })
        raise SlideRegenerationUnavailable(
            f"Regenerating a {slide_type.replace('_', '-')} slide needs an AI model. "
            "Configure an LLM API key, or edit this slide in the downloaded .pptx."
        )

    @staticmethod
    def _citation_for(context: Dict[str, Any]) -> Citation:
        content = context["content"]
        return Citation(
            document_name=context["document"],
            page=context.get("page"),
            section=context.get("section"),
            excerpt=content[:150] + "..." if len(content) > 150 else content,
        )

    @staticmethod
    def _ground_citations(spec: PresentationSpec, contexts: List[Dict[str, Any]]) -> PresentationSpec:
        """Drops citations to documents that were not in the retrieved context (the LLM made them up)."""
        known = {c["document"] for c in contexts}
        dropped = 0
        for slide in spec.slides:
            valid = [c for c in slide.citations if c.document_name in known]
            dropped += len(slide.citations) - len(valid)
            slide.citations = valid
        if dropped:
            logger.warning(f"Dropped {dropped} citation(s) to documents that were not retrieved.")
        return spec

    @staticmethod
    def _sentences(text: str, max_items: int, max_len: int = 220) -> List[str]:
        """Verbatim sentences from a chunk, so fallback slides only ever repeat source text."""
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", text) if p.strip()]
        picked = [p for p in parts if len(p) >= 20] or parts
        return [p if len(p) <= max_len else p[:max_len].rsplit(" ", 1)[0] + "…" for p in picked[:max_items]]

    def _generate_fallback_spec(self, prompt: str, contexts: List[Dict[str, Any]], num_slides: int, theme: str) -> PresentationSpec:
        """
        Deck built without an LLM, strictly from retrieved excerpts: every bullet, table cell and takeaway is
        copied from a source chunk and cited to it. Nothing is invented (no sample numbers, no generic advice).
        """
        deck_title = prompt.title() if len(prompt) < 60 else "Document Briefing"
        slides: List[Dict[str, Any]] = [{
            "type": "title",
            "title": deck_title,
            "subtitle": "Draft assembled directly from document excerpts (no AI model configured)",
        }]

        content_slots = max(num_slides - 2, 1)
        takeaways: List[str] = []
        summary_citations: List[Citation] = []
        for c in contexts[:content_slots]:
            citation = self._citation_for(c)
            where = c["document"] + (f", p. {c['page']}" if c.get("page") else "")
            section = c.get("section")
            heading = section if section and section != "General" else where

            tbl = c.get("table_data") if c.get("is_table") else None
            if tbl and tbl.get("headers") and tbl.get("rows"):
                slides.append({
                    "type": "table",
                    "title": heading,
                    "columns": [str(h) for h in tbl["headers"]],
                    "rows": [[str(v) for v in row] for row in tbl["rows"]],
                    "citations": [citation],
                })
                continue

            bullets = self._sentences(c["content"], 5)
            if not bullets:
                continue
            slides.append({"type": "bullet", "title": heading, "bullets": bullets, "citations": [citation]})
            if len(takeaways) < 4:
                takeaways.append(bullets[0])
                summary_citations.append(citation)

        if takeaways:
            slides.append({
                "type": "summary",
                "title": "Key Points from the Sources",
                "key_takeaways": takeaways,
                "citations": summary_citations,
            })

        return PresentationSpec(title=deck_title, subtitle="Document excerpts", slides=slides)


rag_engine = LangGraphRAGEngine()
