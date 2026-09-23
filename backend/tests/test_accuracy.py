"""Content accuracy: chunking, figure matching, hybrid retrieval, the grounding validator and the repair loop."""
import json
from types import SimpleNamespace

import pytest

from app.document_processing.chunker import DocumentChunker
from app.rag import graph
from app.rag.graph import RAGPresentationEngine
from app.rag.retriever import HybridRetriever
from app.rag.text_utils import extract_numbers, unsupported_numbers
from app.rag.validator import SpecValidator, build_sources
from app.schemas.presentation_spec import PresentationSpec

REVENUE = {"content": "Q3 revenue was $4,200,000, up 12% year over year. EMEA revenue grew 18% on new accounts.",
           "document": "q3_report.pdf", "page": 2, "section": "Revenue", "chunk_index": 0,
           "is_table": False, "table_data": None, "relevance_score": 1.0}
CHURN = {"content": "Customer churn fell to 3.1% after the loyalty programme launched in July.",
         "document": "cx_review.docx", "page": None, "section": "Retention", "chunk_index": 0,
         "is_table": False, "table_data": None, "relevance_score": 0.9}
SALES = {"content": "Region | Sales\nEMEA | 1.9\nAPAC | 1.1\nAMER | 1.2",
         "document": "sales.xlsx", "page": None, "section": "Sheet1", "chunk_index": 0, "is_table": True,
         "table_data": {"headers": ["Region", "Sales"], "rows": [["EMEA", "1.9"], ["APAC", "1.1"], ["AMER", "1.2"]]},
         "relevance_score": 0.8}
CONTEXTS = [REVENUE, CHURN, SALES]


# ---------------------------------------------------------------- chunking

def test_chunker_never_cuts_a_sentence_or_figure():
    sentences = [f"Region {i} revenue grew {10 + i}.5% to ${i},250,000 in the third quarter of the year." for i in range(40)]
    chunks = DocumentChunker()._split_text(" ".join(sentences), 300, 80)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 300
        for part in chunk.split(". "):
            part = part.rstrip(".")
            assert any(part in s for s in sentences), f"fragment {part!r}"
    # Overlap: each chunk after the first starts with the previous chunk's last sentence
    assert chunks[1].split(". ")[0] in chunks[0]


def test_chunker_splits_an_overlong_sentence_at_word_boundaries():
    chunks = DocumentChunker()._split_text("word " * 400, 100, 20)
    assert all(len(c) <= 100 and not c.startswith("ord") for c in chunks)


# ---------------------------------------------------------------- figures

def test_figure_matching_understands_scales_and_separators():
    src = extract_numbers("Revenue was $4,200,000, up 12%.")
    assert unsupported_numbers("Revenue reached $4.2M, up 12%", src) == []
    assert unsupported_numbers("Revenue grew 15%", src) == ["15%"]
    assert unsupported_numbers("Q3 FY2024: top 3 risks", src) == []  # identifiers and phrasing, not figures


# ---------------------------------------------------------------- retrieval

class FakeStore:
    def __init__(self, chunks):
        self.chunks = chunks

    def similarity_search(self, project_id, query, top_k=10, filter_dict=None):
        # A deliberately weak "embedding": every chunk scores the same
        return [{"content": c["content"], "metadata": c, "score": 0.5} for c in self.chunks][:top_k]


def _meta(content, filename, idx):
    return {"content": content, "filename": filename, "page": 1, "section": "S", "chunk_index": idx}


def test_hybrid_ranking_prefers_exact_terms():
    store = FakeStore([_meta("General commentary on the market outlook.", "a.pdf", 0),
                       _meta("EMEA churn fell to 3.1% in Q3.", "b.pdf", 0)])
    r = HybridRetriever()
    r.vector_store = store
    results = r.retrieve("p", "EMEA churn Q3", top_k=2)
    assert results[0]["document"] == "b.pdf"


def test_mmr_avoids_near_duplicate_chunks_and_respects_budget():
    dup = "EMEA revenue grew 18% on new accounts in the third quarter."
    store = FakeStore([_meta(dup, "a.pdf", 0), _meta(dup, "a.pdf", 1), _meta(dup + " Again.", "a.pdf", 2),
                       _meta("APAC revenue grew 4% as distributors restocked.", "b.pdf", 0)])
    r = HybridRetriever()
    r.vector_store = store
    results = r.retrieve("p", "revenue grew", top_k=2)
    assert {x["document"] for x in results} == {"a.pdf", "b.pdf"}

    budgeted = r.retrieve("p", "revenue grew", top_k=4, max_chars=len(dup) + 5)
    assert len(budgeted) == 1


def test_heuristic_queries_drop_deck_boilerplate():
    q = RAGPresentationEngine.heuristic_queries(
        "Create a 10-slide presentation explaining our Q3 financial performance, key revenue drivers, "
        "regional challenges, and strategic recommendations")
    assert q[0].startswith("q3 financial performance")
    assert "key revenue drivers" in q and "regional challenges" in q and "strategic recommendations" in q
    assert not any("presentation" in x or "slide" in x for x in q)


# ---------------------------------------------------------------- validator

def _validator():
    return SpecValidator(build_sources(CONTEXTS), prompt="Q3 review")


def test_source_ids_become_exact_citations_with_the_matching_sentence():
    raw = {"slides": [{"type": "bullet", "title": "EMEA", "bullets": ["EMEA revenue grew 18%"], "sources": ["S1", "S9"]}]}
    cit = _validator().resolve_sources(raw)["slides"][0]["citations"]
    assert cit == [{"document_name": "q3_report.pdf", "page": 2, "section": "Revenue",
                    "excerpt": "EMEA revenue grew 18% on new accounts."}]


def test_normalize_fixes_structure_and_keeps_requested_length():
    raw = {"title": "Deck", "slides": [
        {"type": "bullet", "title": "Empty", "bullets": ["  "]},
        {"type": "table", "title": "T", "columns": ["A", "B"], "rows": [["1"], ["2", "3", "4"], ["", ""]]},
        {"type": "chart", "title": "C", "labels": ["x", "y", "z"], "values": [1, "n/a"]},
        {"type": "bullet", "title": "B1", "bullets": ["a"]},
        {"type": "bullet", "title": "B2", "bullets": ["b"]},
        {"type": "summary", "title": "S", "key_takeaways": ["k"]},
    ]}
    out = _validator().normalize(raw, num_slides=4, deck_title="Deck")["slides"]
    assert [s["type"] for s in out] == ["title", "table", "bullet", "summary"]  # title added, trimmed to 4
    assert out[1]["rows"] == [["1", ""], ["2", "3"]]


def _spec(slides):
    return PresentationSpec.model_validate({"title": "Deck", "slides": [{"type": "title", "title": "Deck"}] + slides})


def test_check_auto_cites_the_source_that_contains_a_figure():
    v = _validator()
    spec = _spec([{"type": "bullet", "title": "Retention", "bullets": ["Churn fell to 3.1%"],
                   "citations": [{"document_name": "q3_report.pdf", "page": 2}]}])
    assert v.check(spec) == []
    assert "cx_review.docx" in {c.document_name for c in spec.slides[1].citations}
    assert v.report.auto_cited == 1


def test_check_flags_invented_figures_and_quotes():
    v = _validator()
    spec = _spec([
        {"type": "bullet", "title": "Revenue", "bullets": ["Revenue grew 15%"], "citations": [{"document_name": "q3_report.pdf"}]},
        {"type": "quote", "title": "CEO", "quote": "We doubled revenue.", "citations": [{"document_name": "q3_report.pdf"}]},
        {"type": "chart", "title": "Sales", "chart_type": "bar", "labels": ["EMEA", "APAC"], "values": [1.9, 7.7],
         "citations": [{"document_name": "sales.xlsx"}]},
    ])
    kinds = sorted(i.kind for i in v.check(spec))
    assert kinds == ["unsupported_number", "unsupported_number", "unverified_quote"]


def test_enforce_removes_only_unsupported_claims():
    v = _validator()
    spec = _spec([
        {"type": "bullet", "title": "Revenue", "bullets": ["Revenue grew 12%", "Margins rose 40%"],
         "citations": [{"document_name": "q3_report.pdf", "page": 2}]},
        {"type": "table", "title": "Sales", "columns": ["Region", "Sales"], "rows": [["EMEA", "1.9"], ["LATAM", "0.7"]],
         "citations": [{"document_name": "sales.xlsx"}]},
        {"type": "quote", "title": "CEO", "quote": "We doubled revenue.", "citations": [{"document_name": "q3_report.pdf"}]},
        {"type": "bullet", "title": "Outlook", "bullets": ["Revenue will hit 90% growth"],
         "citations": [{"document_name": "q3_report.pdf", "page": 2}]},
    ])
    v.check(spec)
    out = v.enforce(spec, "Deck")
    assert [s.type for s in out.slides] == ["title", "bullet", "table"]
    assert out.slides[1].bullets == ["Revenue grew 12%"]
    assert out.slides[2].rows == [["EMEA", "1.9"]]
    report = v.finalize_report(out)
    assert report.cited_slides == report.content_slides == 2
    assert len(report.removed_claims) == 4 and report.removed_slides == 2


# ---------------------------------------------------------------- engine + fake LLM

class ScriptedLLM:
    """Answers the planning, deck and repair prompts with scripted JSON; records every prompt."""

    def __init__(self, deck, repair=None, invalid_first=False):
        self.deck, self.repair, self.invalid_first = deck, repair, invalid_first
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if prompt.startswith("You plan document searches"):
            body = {"queries": ["q3 revenue growth", "customer churn retention", "regional sales"]}
        elif "A fact-check against the SOURCES found problems" in prompt:
            body = self.repair
        elif self.invalid_first and len([p for p in self.prompts if "SOURCES:" in p]) == 1:
            return SimpleNamespace(content="Sure! Here is the deck: {not json")
        else:
            body = self.deck
        return SimpleNamespace(content="```json\n" + json.dumps(body) + "\n```")


GOOD_DECK = {"title": "Q3 Review", "subtitle": "Board", "slides": [
    {"type": "title", "title": "Q3 Review", "subtitle": "Board update"},
    {"type": "bullet", "title": "Revenue", "bullets": ["Q3 revenue was $4.2M, up 12% year over year",
                                                         "EMEA revenue grew 18% on new accounts"], "sources": ["S1"]},
    {"type": "table", "title": "Sales by region", "columns": ["Region", "Sales"],
     "rows": [["EMEA", "1.9"], ["APAC", "1.1"], ["AMER", "1.2"]], "sources": ["S3"]},
    {"type": "summary", "title": "Takeaways", "key_takeaways": ["Churn fell to 3.1%"], "sources": ["S2"]},
]}


@pytest.fixture
def engine(monkeypatch):
    calls = {}

    def fake_retrieve(project_id, query, sub_queries=None, top_k=None, max_chars=None):
        calls["queries"] = [query] + list(sub_queries or [])
        calls["top_k"] = top_k
        return [dict(c) for c in CONTEXTS]

    monkeypatch.setattr(graph.retriever, "retrieve", fake_retrieve)
    eng = RAGPresentationEngine()
    eng.calls = calls
    return eng


def test_deck_prompt_carries_sources_audience_tone_language(engine, monkeypatch):
    llm = ScriptedLLM(GOOD_DECK)
    monkeypatch.setattr(engine, "_get_llm", lambda: llm)
    spec, report = engine.execute_with_report("p", "Q3 review for the board", num_slides=4, audience="Investors",
                                              tone="Concise", language="German")
    deck_prompt = next(p for p in llm.prompts if "SOURCES:" in p)
    assert "[S1] q3_report.pdf · p. 2 · Revenue" in deck_prompt
    assert "AUDIENCE: Investors" in deck_prompt and "TONE: Concise" in deck_prompt and "in German" in deck_prompt
    assert "q3 revenue growth" in engine.calls["queries"]  # LLM-planned searches were used
    assert [s.type for s in spec.slides] == ["title", "bullet", "table", "summary"]
    assert spec.slides[2].citations[0].document_name == "sales.xlsx"
    assert report.cited_slides == report.content_slides == 3 and not report.removed_claims


def test_invalid_json_is_retried_once(engine, monkeypatch):
    llm = ScriptedLLM(GOOD_DECK, invalid_first=True)
    monkeypatch.setattr(engine, "_get_llm", lambda: llm)
    spec, _ = engine.execute_with_report("p", "Q3 review", num_slides=4)
    assert [s.type for s in spec.slides] == ["title", "bullet", "table", "summary"]
    assert any("could not be parsed" in p for p in llm.prompts)


def test_unsupported_figure_is_repaired_by_the_llm(engine, monkeypatch):
    bad = json.loads(json.dumps(GOOD_DECK))
    bad["slides"][1]["bullets"][0] = "Q3 revenue was $4.2M, up 15% year over year"
    llm = ScriptedLLM(bad, repair=GOOD_DECK)
    monkeypatch.setattr(engine, "_get_llm", lambda: llm)

    spec, report = engine.execute_with_report("p", "Q3 review", num_slides=4)

    repair_prompt = next(p for p in llm.prompts if "fact-check" in p)
    assert "'15%'" in repair_prompt
    assert "up 12% year over year" in spec.slides[1].bullets[0]
    assert report.repaired and not report.removed_claims


def test_claims_still_unsupported_after_repair_are_removed(engine, monkeypatch):
    bad = json.loads(json.dumps(GOOD_DECK))
    bad["slides"][1]["bullets"].append("Operating margin reached 41%")
    llm = ScriptedLLM(bad, repair=bad)  # the "repair" changes nothing
    monkeypatch.setattr(engine, "_get_llm", lambda: llm)

    spec, report = engine.execute_with_report("p", "Q3 review", num_slides=4)

    assert "Operating margin reached 41%" not in spec.slides[1].bullets
    assert report.removed_claims == ["Operating margin reached 41%"]
