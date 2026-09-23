"""
Grounding validation for LLM-written decks (content only, never layout).

Pipeline used by the RAG engine:
  resolve_sources()  "sources": ["S1", ...] → exact Citation dicts (document, page, section, best-matching sentence)
  normalize()        deterministic structural fixes (table widths, chart pairs, empty slides, title first, slide count)
  check()            every figure must appear in the slide's cited sources; quotes must be verbatim.
                     Auto-cites another retrieved source that contains a figure; returns the issues it can't fix.
  enforce()          last resort after one LLM repair pass: removes claims that are still unsupported.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from app.rag.text_utils import (
    best_matching_sentence, extract_numbers, normalise_for_match, token_set, unsupported_numbers,
)
from app.schemas.presentation_spec import Citation, PresentationSpec

logger = logging.getLogger(__name__)

# Slides that carry no factual body and need no citation
UNCITED_TYPES = {"title", "section"}
LIST_FIELDS = {"bullet": ["bullets"], "summary": ["key_takeaways"], "two_column": ["left_content", "right_content"]}


@dataclass
class Source:
    id: str
    context: Dict[str, Any]
    numbers: Set[str]
    tokens: Set[str]
    norm_text: str

    @property
    def document(self) -> str:
        return self.context["document"]


def build_sources(contexts: List[Dict[str, Any]]) -> List[Source]:
    return [
        Source(
            id=f"S{i}",
            context=c,
            numbers=extract_numbers(c["content"]),
            tokens=token_set(c["content"]),
            norm_text=normalise_for_match(c["content"]),
        )
        for i, c in enumerate(contexts, start=1)
    ]


@dataclass
class Issue:
    slide: int
    kind: str  # unsupported_number | unverified_quote | no_sources
    detail: str


@dataclass
class ValidationReport:
    content_slides: int = 0
    cited_slides: int = 0
    auto_cited: int = 0
    repaired: bool = False
    removed_claims: List[str] = field(default_factory=list)
    removed_slides: int = 0

    def summary(self) -> str:
        parts = [f"{self.cited_slides}/{self.content_slides} content slides cited"]
        if self.removed_claims:
            parts.append(f"{len(self.removed_claims)} unsupported claim(s) removed")
        if self.removed_slides:
            parts.append(f"{self.removed_slides} slide(s) dropped")
        return " · ".join(parts)


class SpecValidator:
    MIN_OVERLAP_TOKENS = 3  # shared content words needed to attach a source to an uncited slide

    def __init__(self, sources: List[Source], prompt: str = ""):
        self.sources = sources
        self.by_id = {s.id: s for s in sources}
        self.by_doc: Dict[str, List[Source]] = {}
        for s in sources:
            self.by_doc.setdefault(s.document, []).append(s)
        # Figures the user typed (e.g. "Q3 2024", "top 10 accounts") may appear on slides
        self.prompt_numbers = extract_numbers(prompt)
        self.all_numbers = set().union(*(s.numbers for s in sources)) if sources else set()
        self.report = ValidationReport()

    # ------------------------------------------------------------------ citations

    def citation(self, source: Source, claim_text: str) -> Dict[str, Any]:
        c = source.context
        return Citation(
            document_name=c["document"],
            page=c.get("page"),
            section=c.get("section"),
            excerpt=best_matching_sentence(c["content"], claim_text),
        ).model_dump()

    def resolve_sources(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Turns each slide's "sources" IDs into exact citations; keeps LLM "citations" only for retrieved documents."""
        for slide in raw.get("slides", []) or []:
            if not isinstance(slide, dict):
                continue
            text = self._slide_text(slide)
            citations = []
            for sid in slide.pop("sources", None) or []:
                src = self.by_id.get(str(sid).strip().strip("[]"))
                if src:
                    citations.append(self.citation(src, text))
            for c in slide.get("citations") or []:
                if isinstance(c, dict) and c.get("document_name") in self.by_doc:
                    citations.append(c)
            slide["citations"] = self._dedupe(citations)
        return raw

    @staticmethod
    def _dedupe(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen, out = set(), []
        for c in citations:
            key = (c.get("document_name"), c.get("page"), c.get("section"))
            if key not in seen:
                seen.add(key)
                out.append(c)
        return out

    # ------------------------------------------------------------------ structure

    def normalize(self, raw: Dict[str, Any], num_slides: int, deck_title: str) -> Dict[str, Any]:
        slides = [s for s in (raw.get("slides") or []) if isinstance(s, dict) and s.get("type")]
        fixed = []
        for s in slides:
            s.setdefault("title", "")
            t = s["type"]
            if t in LIST_FIELDS:
                for f in LIST_FIELDS[t]:
                    s[f] = [str(x).strip() for x in (s.get(f) or []) if str(x).strip()]
                if not any(s.get(f) for f in LIST_FIELDS[t]):
                    continue
            elif t == "table":
                cols = [str(c) for c in (s.get("columns") or [])]
                rows = [[str(v) for v in (r or [])] for r in (s.get("rows") or []) if isinstance(r, list)]
                if not cols and rows:
                    cols, rows = rows[0], rows[1:]
                width = len(cols)
                rows = [(r + [""] * width)[:width] for r in rows if any(v.strip() for v in r)]
                if not cols or not rows:
                    continue
                s["columns"], s["rows"] = cols, rows
            elif t == "chart":
                labels, values = s.get("labels") or [], s.get("values") or []
                pairs = []
                for label, value in zip(labels, values):
                    try:
                        pairs.append((str(label), float(value)))
                    except (TypeError, ValueError):
                        continue
                if len(pairs) < 2:
                    continue  # a chart needs at least two points
                s["labels"], s["values"] = [p[0] for p in pairs], [p[1] for p in pairs]
                if s.get("chart_type") not in ("bar", "line", "pie"):
                    s["chart_type"] = "bar"
            elif t == "quote":
                if not str(s.get("quote") or "").strip():
                    continue
            fixed.append(s)

        if not fixed or fixed[0]["type"] != "title":
            fixed.insert(0, {"type": "title", "title": raw.get("title") or deck_title, "subtitle": raw.get("subtitle")})

        # Keep the requested length: trim from the middle, never the title or a closing summary
        if len(fixed) > num_slides:
            tail = [fixed[-1]] if fixed[-1]["type"] == "summary" and len(fixed) > 1 else []
            body = fixed[1:len(fixed) - len(tail)]
            fixed = [fixed[0]] + body[:max(num_slides - 1 - len(tail), 0)] + tail

        raw["slides"] = fixed
        raw.setdefault("title", deck_title)
        return raw

    # ------------------------------------------------------------------ grounding checks

    @staticmethod
    def _slide_text(slide: Dict[str, Any]) -> str:
        parts = [slide.get("title", ""), slide.get("subtitle") or ""]
        for f in ("bullets", "key_takeaways", "left_content", "right_content", "labels"):
            parts += [str(x) for x in slide.get(f) or []]
        parts += [slide.get("left_title", ""), slide.get("right_title", ""), slide.get("quote", "")]
        parts += [" ".join(map(str, r)) for r in slide.get("rows") or []]
        parts += [str(v) for v in slide.get("values") or []]
        return " ".join(p for p in parts if p)

    def _cited_sources(self, slide) -> List[Source]:
        out = []
        for c in slide.citations:
            for src in self.by_doc.get(c.document_name, []):
                if c.page is None or src.context.get("page") in (None, c.page):
                    out.append(src)
        return out

    def _supported(self, slide) -> Set[str]:
        nums = set(self.prompt_numbers)
        for src in self._cited_sources(slide):
            nums |= src.numbers
        return nums

    def _claims(self, slide) -> List[str]:
        """Text units whose figures must be sourced."""
        d = slide.model_dump()
        items = [d.get("title") or ""]
        for f in LIST_FIELDS.get(slide.type, []):
            items += d.get(f) or []
        if slide.type == "two_column":
            items += [d.get("left_title") or "", d.get("right_title") or ""]
        if slide.type == "table":
            items += [cell for row in d["rows"] for cell in row]
        if slide.type == "chart":
            items += list(d["labels"])  # values are checked exactly in _unsupported_values
        if slide.type in ("title", "section"):
            items.append(d.get("subtitle") or "")
        return [i for i in items if i]

    @staticmethod
    def _unsupported_values(values: List[float], supported: Set[str]) -> List[str]:
        """Chart values are all facts, so each one is checked (no small-number exemption)."""
        return [f"{v:g}" for v in values if f"{v:g}" not in supported]

    def _add_citation_for_figure(self, slide, values: Set[str], claim: str) -> bool:
        """Attaches a retrieved source containing the figure's value, if any (the LLM cited the wrong source)."""
        for src in self.sources:
            if values & src.numbers:
                slide.citations.append(Citation(**self.citation(src, claim)))
                self.report.auto_cited += 1
                return True
        return False

    def check(self, spec: PresentationSpec) -> List[Issue]:
        issues: List[Issue] = []
        for idx, slide in enumerate(spec.slides):
            if slide.type in UNCITED_TYPES:
                for claim in self._claims(slide):
                    for fig in unsupported_numbers(claim, self.all_numbers | self.prompt_numbers):
                        issues.append(Issue(idx, "unsupported_number", f"'{fig}' in \"{claim[:80]}\" is not in any source"))
                continue

            # Uncited slide: attach the retrieved source it clearly draws on, if any
            if not slide.citations:
                text_tokens = token_set(self._slide_text(slide.model_dump()))
                best = max(self.sources, key=lambda s: len(text_tokens & s.tokens), default=None)
                if best and len(text_tokens & best.tokens) >= self.MIN_OVERLAP_TOKENS:
                    slide.citations.append(Citation(**self.citation(best, self._slide_text(slide.model_dump()))))
                    self.report.auto_cited += 1
                else:
                    issues.append(Issue(idx, "no_sources", "slide cites no source and matches none"))

            for claim in self._claims(slide):
                for fig in unsupported_numbers(claim, self._supported(slide)):
                    if not self._add_citation_for_figure(slide, extract_numbers(fig), claim):
                        issues.append(Issue(idx, "unsupported_number",
                                            f"'{fig}' in \"{claim[:80]}\" does not appear in any source"))

            if slide.type == "chart":
                for v in self._unsupported_values(slide.values, self._supported(slide)):
                    if not self._add_citation_for_figure(slide, {v}, slide.title):
                        issues.append(Issue(idx, "unsupported_number", f"chart value {v} does not appear in any source"))

            if slide.type == "quote":
                quote = normalise_for_match(slide.quote)
                match = next((s for s in self.sources if quote and quote in s.norm_text), None)
                if not match:
                    issues.append(Issue(idx, "unverified_quote", "the quote is not verbatim in any source"))
                elif match.document not in {c.document_name for c in slide.citations}:
                    slide.citations.append(Citation(**self.citation(match, slide.quote)))
                    self.report.auto_cited += 1

            slide.citations = [Citation(**c) for c in self._dedupe([c.model_dump() for c in slide.citations])]
        return issues

    # ------------------------------------------------------------------ enforcement

    def enforce(self, spec: PresentationSpec, fallback_title: str) -> PresentationSpec:
        """Removes claims that are still unsupported after repair. Slides left empty are dropped."""
        kept = []
        for slide in spec.slides:
            supported = (self.all_numbers | self.prompt_numbers) if slide.type in UNCITED_TYPES else self._supported(slide)

            def bad(text: str) -> bool:
                missing = unsupported_numbers(text, supported)
                if missing:
                    self.report.removed_claims.append(text)
                return bool(missing)

            if bad(slide.title):
                slide.title = self._safe_title(slide, fallback_title)
            if slide.type in UNCITED_TYPES:
                if slide.subtitle and bad(slide.subtitle):
                    slide.subtitle = None
                kept.append(slide)
                continue

            if slide.type in LIST_FIELDS:
                for f in LIST_FIELDS[slide.type]:
                    setattr(slide, f, [x for x in getattr(slide, f) if not bad(x)])
                if slide.type == "two_column":
                    for f in ("left_title", "right_title"):
                        if bad(getattr(slide, f)):
                            setattr(slide, f, "")
                if not any(getattr(slide, f) for f in LIST_FIELDS[slide.type]):
                    self.report.removed_slides += 1
                    continue
            elif slide.type == "table":
                rows = []
                for r in slide.rows:
                    if any(unsupported_numbers(c, supported) for c in r):
                        self.report.removed_claims.append(" | ".join(r))
                    else:
                        rows.append(r)
                slide.rows = rows
                if not slide.rows:
                    self.report.removed_slides += 1
                    continue
            elif slide.type == "chart":
                if self._unsupported_values(slide.values, supported):
                    self.report.removed_claims.append(f"chart '{slide.title}'")
                    self.report.removed_slides += 1
                    continue
            elif slide.type == "quote":
                quote = normalise_for_match(slide.quote)
                if not any(quote and quote in s.norm_text for s in self.sources):
                    self.report.removed_claims.append(f"quote '{slide.quote[:60]}'")
                    self.report.removed_slides += 1
                    continue
            kept.append(slide)
        spec.slides = kept
        return spec

    def _safe_title(self, slide, fallback_title: str) -> str:
        for c in slide.citations:
            if c.section and c.section not in ("General",) and not unsupported_numbers(c.section, self._supported(slide)):
                return c.section
        return fallback_title

    def finalize_report(self, spec: PresentationSpec) -> ValidationReport:
        content = [s for s in spec.slides if s.type not in UNCITED_TYPES]
        self.report.content_slides = len(content)
        self.report.cited_slides = sum(1 for s in content if s.citations)
        return self.report


def describe_issues(spec: PresentationSpec, issues: List[Issue]) -> str:
    lines = []
    for i in issues:
        title = spec.slides[i.slide].title if i.slide < len(spec.slides) else ""
        lines.append(f"- Slide {i.slide + 1} (\"{title[:60]}\"): {i.detail}.")
    return "\n".join(lines)
