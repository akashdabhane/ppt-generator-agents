"""
RAG presentation engine: a plain Python pipeline (not LangGraph).

  plan queries → hybrid retrieval → number sources [S1..Sn] → LLM writes content JSON citing source IDs
  → resolve IDs to exact citations → structural normalisation → grounding check (+ auto-citation)
  → one LLM repair pass for remaining issues → enforce (remove still-unsupported claims) → report

The LLM only writes content. Layout is decided later by LayoutEngine (D-001).
"""
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, get_args

from app.core.config import settings
from app.rag.retriever import retriever
from app.rag.text_utils import REQUEST_WORDS, STOPWORDS, split_sentences, tokenize
from app.rag.validator import (
    Source, SpecValidator, ValidationReport, build_sources, describe_issues,
)
from app.schemas.presentation_spec import Citation, PresentationSpec, SlideSpec

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

# Rules shared by the deck and single-slide prompts. These are what make the content accurate.
CONTENT_RULES = """CONTENT RULES (accuracy matters more than coverage):
- Use ONLY facts stated in the SOURCES. Never use outside knowledge.
- Copy every figure exactly as the source writes it (same value, unit and period). Do NOT calculate, total,
  average, round, convert, extrapolate or estimate new figures.
- Every slide except "title" and "section" MUST have "sources": ["S<n>", ...] listing the source IDs it uses.
  Cite only sources that actually contain the slide's facts.
- If the sources do not cover part of the request, leave it out; do not guess or pad with generic statements.
- One fact or insight per bullet, at most 25 words, 3–6 bullets per slide. Name the subject in each bullet
  (e.g. "EMEA revenue grew 12% in Q3", not "It grew 12%").
- Do not repeat the same fact on several slides (the final summary may restate the most important ones).
- "table": copy columns and rows from a source table; do not add computed columns.
- "chart": only when a source gives at least 3 comparable values of one measure; labels and values in the same order.
- "quote": an exact sentence from a source, with the author only if the source names them.
- Never output layout: no coordinates, sizes, fonts, colours or styling."""


class SlideRegenerationUnavailable(Exception):
    """Raised when a slide type can't be regenerated without an LLM (no invented fallback content)."""


class NoGroundingContextError(Exception):
    """Raised when retrieval finds nothing to ground the deck on. Generating anyway would mean inventing content."""


ProgressCallback = Callable[[str, int, str], None]  # (stage, percent, message)


class RAGPresentationEngine:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER

    # ------------------------------------------------------------------ LLM plumbing

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
    def _text_of(response: Any) -> str:
        content = getattr(response, "content", response)
        # Some providers return a list of content blocks instead of a plain string
        if isinstance(content, list):
            content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
        return str(content)

    @staticmethod
    def _extract_json(text: str) -> Any:
        """The outermost JSON object in a response, ignoring code fences or prose around it."""
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("response contained no JSON object")
        return json.loads(text[start:end + 1])

    def _invoke_json(self, llm, prompt: str) -> Dict[str, Any]:
        """Calls the LLM and parses JSON, retrying once with the parse error before giving up."""
        text = self._text_of(llm.invoke(prompt))
        try:
            return self._extract_json(text)
        except Exception as e:
            logger.warning(f"LLM returned invalid JSON ({e}); retrying once.")
            retry = (f"{prompt}\n\nYour previous reply could not be parsed ({e}). "
                     "Reply again with ONLY the complete, valid JSON object.")
            return self._extract_json(self._text_of(llm.invoke(retry)))

    # ------------------------------------------------------------------ query planning

    @staticmethod
    def heuristic_queries(prompt: str) -> List[str]:
        """Topic phrases from the request, without deck boilerplate ("Create a 10-slide presentation ...")."""
        def core(text: str) -> str:
            words = [w for w in tokenize(text, drop_stopwords=False)
                     if w not in STOPWORDS and w not in REQUEST_WORDS and not re.fullmatch(r"\d+", w)]
            return " ".join(words)

        queries = [core(prompt)]
        for part in re.split(r"[,;:]|\band\b|&|\n", prompt, flags=re.IGNORECASE):
            phrase = core(part)
            if phrase and len(phrase.split()) >= 1:
                queries.append(phrase)
        return [q for q in dict.fromkeys(queries) if q][:6] or [prompt]

    def _plan_queries(self, llm, prompt: str, audience: str) -> List[str]:
        heuristic = self.heuristic_queries(prompt)
        if not llm:
            return heuristic
        plan_prompt = f"""You plan document searches for a presentation.
Request: {prompt}
Audience: {audience}

Return ONLY JSON: {{"queries": [str, ...]}} with 3-6 short keyword search queries (3-8 words each) that together
cover every topic the request asks about. Use the request's own terms, names, metrics and periods.
Do not answer the request."""
        try:
            planned = [str(q).strip() for q in self._invoke_json(llm, plan_prompt).get("queries", []) if str(q).strip()]
        except Exception as e:
            logger.warning(f"Query planning failed ({e}); using heuristic queries.")
            planned = []
        return list(dict.fromkeys(heuristic[:1] + planned[:6] + heuristic[1:]))[:8]

    # ------------------------------------------------------------------ prompts

    @staticmethod
    def _sources_block(sources: List[Source]) -> str:
        blocks = []
        for s in sources:
            c = s.context
            where = " · ".join(str(x) for x in [c["document"], f"p. {c['page']}" if c.get("page") else None,
                                                  c.get("section")] if x)
            blocks.append(f"[{s.id}] {where}\n{c['content']}")
        return "\n\n".join(blocks)

    def _deck_prompt(self, prompt: str, sources: List[Source], num_slides: int, audience: str,
                     tone: str, language: str) -> str:
        type_lines = "\n".join(f"  {i}. \"{t}\": {shape}" for i, (t, shape) in enumerate(SLIDE_TYPE_SCHEMAS.items(), 1))
        sections_hint = ("Use \"section\" slides to separate 2-4 parts of the deck." if num_slides >= 10
                         else "Do not use \"section\" slides.")
        return f"""You are an analyst writing a presentation that must be 100% traceable to the SOURCES below.

REQUEST: {prompt}
AUDIENCE: {audience} (choose the level of detail and emphasis this audience needs)
TONE: {tone}
LANGUAGE: write all slide text in {language}.
SLIDES: {num_slides} in total: slide 1 is "title", the last slide is "summary". {sections_hint}
If the sources cannot support {num_slides} slides of real content, produce fewer rather than padding.

{CONTENT_RULES}

OUTPUT: a single JSON object and nothing else:
{{ "title": str, "subtitle": str, "slides": [ <slide>, ... ] }}
Slide shapes (add "sources" to every slide except title/section):
{type_lines}

SOURCES:
{self._sources_block(sources)}

Write the JSON now."""

    def _repair_prompt(self, spec: PresentationSpec, issues_text: str, sources: List[Source]) -> str:
        current = []
        for slide in spec.slides:
            d = slide.model_dump(exclude={"citations"})
            ids = [s.id for s in sources if any(c.document_name == s.document and c.page in (None, s.context.get("page"))
                                                for c in slide.citations)]
            if ids:
                d["sources"] = ids
            current.append(d)
        return f"""You wrote the presentation JSON below. A fact-check against the SOURCES found problems:
{issues_text}

Fix ONLY these problems: replace each unsupported figure or quote with the exact one from a source, correct the
"sources" IDs, or remove the claim if no source supports it. Keep everything else unchanged.

{CONTENT_RULES}

CURRENT JSON:
{json.dumps({"title": spec.title, "subtitle": spec.subtitle, "slides": current}, ensure_ascii=False)}

SOURCES:
{self._sources_block(sources)}

Return the complete corrected JSON object only."""

    # ------------------------------------------------------------------ deck generation

    def execute(self, project_id: str, prompt: str, num_slides: int = 10, audience: str = "General",
                theme: str = "Professional", tone: str = "Professional & Informative",
                language: str = "English") -> PresentationSpec:
        return self.execute_with_report(project_id, prompt, num_slides, audience, theme, tone, language)[0]

    def execute_with_report(self, project_id: str, prompt: str, num_slides: int = 10, audience: str = "General",
                            theme: str = "Professional", tone: str = "Professional & Informative",
                            language: str = "English",
                            on_progress: Optional[ProgressCallback] = None) -> Tuple[PresentationSpec, ValidationReport]:
        progress = on_progress or (lambda stage, pct, msg: None)
        llm = self._get_llm()

        # 1. Plan + retrieve, with a context budget that grows with the deck
        progress("RETRIEVING_DOCUMENTS", 15, "Planning searches and retrieving relevant passages")
        queries = self._plan_queries(llm, prompt, audience)
        top_k = min(max(num_slides * 3, 12), 40)
        max_chars = min(max(num_slides * 3000, 15000), 45000)
        contexts = retriever.retrieve(project_id, queries[0], sub_queries=queries[1:], top_k=top_k, max_chars=max_chars)
        if not contexts:
            raise NoGroundingContextError(
                "No content from this project's documents could be retrieved. Upload documents, wait until they "
                "show INDEXED (re-index them if the server was restarted), then try again."
            )
        sources = build_sources(contexts)
        validator = SpecValidator(sources, prompt)
        deck_title = prompt.strip().rstrip(".")[:80] if len(prompt) < 80 else "Document Briefing"

        # 2. Write
        if not llm:
            progress("GENERATING_SLIDE_CONTENT", 45, "Assembling slides from document excerpts")
            spec = self._generate_fallback_spec(prompt, contexts, num_slides, theme)
            validator.check(spec)
            spec = validator.enforce(spec, deck_title)
            return spec, validator.finalize_report(spec)

        progress("GENERATING_SLIDE_CONTENT", 35, f"Writing slides from {len(sources)} source passages")
        try:
            spec = self._build_spec(self._invoke_json(llm, self._deck_prompt(
                prompt, sources, num_slides, audience, tone, language)), validator, num_slides, deck_title)
        except Exception as e:
            logger.warning(f"LLM returned an invalid PresentationSpec ({e}). Using deterministic fallback spec.")
            spec = self._generate_fallback_spec(prompt, contexts, num_slides, theme)
            validator.check(spec)
            spec = validator.enforce(spec, deck_title)
            return spec, validator.finalize_report(spec)

        # 3. Fact-check, one repair pass, then strict enforcement
        progress("VALIDATING_SLIDES", 55, "Fact-checking every figure against its sources")
        issues = validator.check(spec)
        if issues:
            logger.info(f"Grounding check found {len(issues)} issue(s); asking the LLM to repair.")
            progress("VALIDATING_SLIDES", 60, f"Correcting {len(issues)} unsupported claim(s)")
            try:
                repaired_validator = SpecValidator(sources, prompt)
                repaired = self._build_spec(self._invoke_json(llm, self._repair_prompt(
                    spec, describe_issues(spec, issues), sources)),
                    repaired_validator, num_slides, deck_title)
                repaired_validator.check(repaired)
                repaired_validator.report.auto_cited += validator.report.auto_cited
                repaired_validator.report.repaired = True
                spec, validator = repaired, repaired_validator
            except Exception as e:
                logger.warning(f"Repair pass failed ({e}); enforcing on the first draft.")
        spec = validator.enforce(spec, deck_title)
        report = validator.finalize_report(spec)
        logger.info(f"Deck grounding: {report.summary()}")
        return spec, report

    @staticmethod
    def _build_spec(raw: Dict[str, Any], validator: SpecValidator, num_slides: int, deck_title: str) -> PresentationSpec:
        if not isinstance(raw, dict) or not isinstance(raw.get("slides"), list):
            raise ValueError('JSON has no "slides" list')
        raw = validator.resolve_sources(raw)
        raw = validator.normalize(raw, num_slides, deck_title)
        valid = []
        for s in raw["slides"]:
            cls = SLIDE_SPEC_CLASSES.get(s.get("type"))
            if not cls:
                continue
            try:
                valid.append(cls.model_validate(s))
            except Exception as e:
                logger.warning(f"Dropping malformed {s.get('type')} slide: {e}")
        if len(valid) <= 1:
            raise ValueError("no valid content slides")
        return PresentationSpec(title=raw.get("title") or deck_title, subtitle=raw.get("subtitle"), slides=valid)

    # ------------------------------------------------------------------ single-slide regeneration

    def regenerate_slide(self, project_id: str, deck_prompt: str, current: Dict[str, Any],
                         instructions: Optional[str] = None, audience: str = "General",
                         tone: str = "Professional & Informative", language: str = "English") -> SlideSpec:
        """Rewrites one slide, keeping its type, grounded and fact-checked like a full deck."""
        slide_type = current.get("type", "bullet")
        slide_cls = SLIDE_SPEC_CLASSES.get(slide_type, SLIDE_SPEC_CLASSES["bullet"])
        focus = " ".join(x for x in [instructions, current.get("title")] if x) or deck_prompt
        contexts = retriever.retrieve(project_id, focus, sub_queries=self.heuristic_queries(deck_prompt)[:2], top_k=12)
        if not contexts:
            raise NoGroundingContextError(
                "No content from this project's documents could be retrieved to regenerate this slide."
            )

        llm = self._get_llm()
        if not llm:
            return self._fallback_slide(slide_type, current, contexts)

        sources = build_sources(contexts)
        validator = SpecValidator(sources, f"{deck_prompt} {instructions or ''}")
        current_json = json.dumps({k: v for k, v in current.items() if k != "citations"}, ensure_ascii=False)
        shape = SLIDE_TYPE_SCHEMAS.get(slide_type, SLIDE_TYPE_SCHEMAS["bullet"])[:-1].rstrip()
        prompt = f"""You are revising ONE slide of a presentation about: {deck_prompt}
AUDIENCE: {audience}
TONE: {tone}
LANGUAGE: write all slide text in {language} (the rest of the deck is in {language}).
CURRENT SLIDE: {current_json}
USER INSTRUCTIONS: {instructions or "Improve this slide with the most relevant facts from the sources."}

{CONTENT_RULES}

OUTPUT: a single JSON object and nothing else, shaped exactly like:
  {shape}, "sources": ["S<n>", ...] }}
Keep "type" exactly "{slide_type}".

SOURCES:
{self._sources_block(sources)}

Write the slide JSON now."""
        try:
            data = self._invoke_json(llm, prompt)
            data["type"] = slide_type
            raw = validator.normalize(validator.resolve_sources({"slides": [
                {"type": "title", "title": "_"}, data]}), 2, "_")
            if len(raw["slides"]) < 2:
                raise ValueError("slide was empty after normalisation")
            slide = slide_cls.model_validate(raw["slides"][1])
        except Exception as e:
            logger.warning(f"LLM returned an invalid {slide_type} slide ({e}). Using fallback slide.")
            return self._fallback_slide(slide_type, current, contexts)

        spec = PresentationSpec(title="_", slides=[slide])
        validator.check(spec)
        spec = validator.enforce(spec, current.get("title") or "Slide")
        if not spec.slides:
            return self._fallback_slide(slide_type, current, contexts)
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

    # ------------------------------------------------------------------ no-LLM fallback deck

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
    def _sentences(text: str, max_items: int, max_len: int = 220) -> List[str]:
        """Verbatim sentences from a chunk, so fallback slides only ever repeat source text."""
        parts = split_sentences(text)
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


rag_engine = RAGPresentationEngine()
