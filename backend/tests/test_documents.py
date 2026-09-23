import os

from app.models import Project, Document, DocumentChunk, DocumentStatus
from app.workers import tasks


def _make_doc(env, text="Revenue grew 12% in Q3. Churn fell to 3.1%.\n\nEMEA drove most of the growth."):
    db, storage = env["db"], env["storage"]
    project = Project(user_id=env["owner"].id, name="Q3")
    db.add(project)
    db.commit()
    path = os.path.join(storage.get_project_dir(project.id), "documents", "notes.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    doc = Document(project_id=project.id, filename="notes.txt", file_type="txt", file_size=len(text), storage_path=path)
    db.add(doc)
    db.commit()
    return project.id, doc.id, path


def _ingest(env, monkeypatch, doc_id):
    monkeypatch.setattr(tasks, "SessionLocal", env["Session"])
    monkeypatch.setattr(tasks, "vector_store", env["vectors"])
    tasks.run_document_ingestion(doc_id)


def test_ingestion_is_idempotent_on_reindex(api_env, monkeypatch):
    project_id, doc_id, _ = _make_doc(api_env)
    _ingest(api_env, monkeypatch, doc_id)
    db = api_env["db"]
    db.expire_all()
    assert db.get(Document, doc_id).status == DocumentStatus.INDEXED
    n_chunks = db.query(DocumentChunk).filter_by(document_id=doc_id).count()
    n_vectors = len(api_env["vectors"].store[project_id])
    assert n_chunks >= 1 and n_vectors == n_chunks

    _ingest(api_env, monkeypatch, doc_id)  # reindex
    db.expire_all()
    assert db.query(DocumentChunk).filter_by(document_id=doc_id).count() == n_chunks
    assert len(api_env["vectors"].store[project_id]) == n_vectors


def test_delete_document_removes_its_vectors(api_env, monkeypatch):
    project_id, doc_id, path = _make_doc(api_env)
    _ingest(api_env, monkeypatch, doc_id)

    res = api_env["client"].delete(f"/documents/{doc_id}")

    assert res.status_code == 204
    assert api_env["vectors"].store[project_id] == []
    assert not os.path.exists(path)


def test_other_user_cannot_reindex_or_delete(api_env):
    _, doc_id, path = _make_doc(api_env)
    api_env["current"]["user"] = api_env["other"]

    assert api_env["client"].post(f"/documents/{doc_id}/reindex").status_code == 404
    assert api_env["client"].delete(f"/documents/{doc_id}").status_code == 404
    assert api_env["dispatched"] == []
    assert os.path.exists(path)


def test_owner_can_reindex(api_env):
    _, doc_id, _ = _make_doc(api_env)
    res = api_env["client"].post(f"/documents/{doc_id}/reindex")
    assert res.status_code == 200
    assert api_env["dispatched"] == [doc_id]
