import re

import pytest

from app.models import Project, Document, DocumentStatus
from app.rag import graph
from app.rag.graph import RAGPresentationEngine, NoGroundingContextError
from app.rag.validator import SpecValidator, build_sources
from app.schemas.presentation_spec import PresentationSpec

CONTEXTS = [
    {
        "content": "Revenue grew 12% year over year to $4.2M in Q3. Growth was driven by the EMEA region. "
                   "Churn fell to 3.1% after the loyalty programme launched.",
        "document": "Q3_report.pdf", "page": 2, "section": "Revenue", "relevance_score": 0.9,
        "chunk_index": 0, "is_table": False, "table_data": None,
    },
    {
        "content": "Region | Sales\nEMEA | 1.9\nAPAC | 1.1",
        "document": "sales.xlsx", "page": None, "section": "Sheet1", "relevance_score": 0.8,
        "chunk_index": 1, "is_table": True,
        "table_data": {"headers": ["Region", "Sales"], "rows": [["EMEA", "1.9"], ["APAC", "1.1"]]},
    },
]


@pytest.fixture
def engine(monkeypatch):
    eng = RAGPresentationEngine()
    monkeypatch.setattr(eng, "_get_llm", lambda: None)  # no API key → fallback deck
    return eng


def _all_text(spec: PresentationSpec) -> list:
    out = []
    for s in spec.slides:
        d = s.model_dump()
        for key in ("bullets", "key_takeaways"):
            out += d.get(key) or []
        for row in d.get("rows") or []:
            out += row
    return out


def test_fallback_deck_only_repeats_source_text(engine, monkeypatch):
    monkeypatch.setattr(graph.retriever, "retrieve", lambda *a, **k: CONTEXTS)
    spec = engine.execute("p1", "Q3 performance", num_slides=6)

    source = " ".join(c["content"] for c in CONTEXTS)
    for text in _all_text(spec):
        assert text.rstrip("…") in source, f"not from the sources: {text!r}"
    # No number appears that the sources don't contain (the old fallback invented 35.0/42.5/28.0/50.0)
    source_numbers = set(re.findall(r"\d+(?:\.\d+)?", source))
    for text in _all_text(spec):
        assert set(re.findall(r"\d+(?:\.\d+)?", text)) <= source_numbers
    assert not any(s.type == "chart" for s in spec.slides)


def test_fallback_deck_cites_the_chunk_each_slide_came_from(engine, monkeypatch):
    monkeypatch.setattr(graph.retriever, "retrieve", lambda *a, **k: CONTEXTS)
    spec = engine.execute("p1", "Q3 performance", num_slides=6)

    table = next(s for s in spec.slides if s.type == "table")
    assert table.columns == ["Region", "Sales"]
    assert [c.document_name for c in table.citations] == ["sales.xlsx"]
    bullet = next(s for s in spec.slides if s.type == "bullet")
    assert [(c.document_name, c.page) for c in bullet.citations] == [("Q3_report.pdf", 2)]
    for s in spec.slides:
        if s.type != "title":
            assert s.citations, f"{s.type} slide has no citation"


def test_no_retrieved_context_refuses_to_generate(engine, monkeypatch):
    monkeypatch.setattr(graph.retriever, "retrieve", lambda *a, **k: [])
    with pytest.raises(NoGroundingContextError):
        engine.execute("p1", "Q3 performance")


def test_llm_citations_to_unknown_documents_are_dropped():
    raw = {"title": "t", "slides": [
        {"type": "bullet", "title": "b", "bullets": ["x"], "citations": [
            {"document_name": "Q3_report.pdf", "page": 2},
            {"document_name": "made_up_source.pdf"},
        ]},
    ]}
    resolved = SpecValidator(build_sources(CONTEXTS)).resolve_sources(raw)
    assert [c["document_name"] for c in resolved["slides"][0]["citations"]] == ["Q3_report.pdf"]


def test_generate_requires_an_indexed_document(api_env, monkeypatch):
    db = api_env["db"]
    project = Project(user_id=api_env["owner"].id, name="Empty")
    db.add(project)
    db.commit()
    db.add(Document(project_id=project.id, filename="a.pdf", file_type="pdf", file_size=1, storage_path="x",
                    status=DocumentStatus.PROCESSING))
    db.commit()

    body = {"prompt": "Q3 deck", "num_slides": 5, "audience": "General", "theme": "Professional"}
    res = api_env["client"].post(f"/projects/{project.id}/presentations/generate", json=body)
    assert res.status_code == 400
    assert "INDEXED" in res.json()["detail"]
