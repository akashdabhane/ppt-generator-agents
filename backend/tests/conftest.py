import os

# Hermetic tests: never reach the real vector DB or LLM/embedding APIs configured in backend/.env.
# Environment variables take precedence over the .env file in pydantic-settings.
os.environ["VECTOR_DB_TYPE"] = "mock"
for _key in ("PINECONE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
    os.environ[_key] = ""
os.environ["EMBEDDING_PROVIDER"] = "hash"

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.api.v1 import projects as projects_api
from app.api.v1 import presentations as presentations_api
from app.api.v1 import documents as documents_api
from app.api.v1.deps import get_db, get_current_user
from app.database.session import Base
from app.models import User
from app.services.storage import StorageService


class FakeVectorStore:
    """Records deletes and keeps upserted chunks per project, like the mock store."""

    def __init__(self):
        self.deleted = []
        self.store = {}

    def upsert_chunks(self, project_id, chunks):
        self.store.setdefault(project_id, []).extend(chunks)
        return [f"v{i}" for i in range(len(chunks))]

    def delete_document_chunks(self, project_id, document_id, vector_ids=None):
        self.deleted.append((project_id, document_id))
        self.store[project_id] = [c for c in self.store.get(project_id, [])
                                  if c["metadata"]["document_id"] != document_id]

    def delete_project(self, project_id):
        self.deleted.append((project_id, "*"))
        self.store.pop(project_id, None)


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    """Projects + presentations routers on in-memory SQLite, with storage in tmp_path and a fake vector store.

    Switch the authenticated user with `env["current"]["user"] = env["other"]`.
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    owner = User(email="owner@example.com", hashed_password="x")
    other = User(email="other@example.com", hashed_password="x")
    db.add_all([owner, other])
    db.commit()

    storage = StorageService(base_dir=str(tmp_path))
    vectors = FakeVectorStore()
    monkeypatch.setattr(projects_api, "storage_service", storage)
    monkeypatch.setattr(projects_api, "vector_store", vectors)
    monkeypatch.setattr(presentations_api, "storage_service", storage)
    monkeypatch.setattr(documents_api, "storage_service", storage)
    monkeypatch.setattr(documents_api, "vector_store", vectors)
    dispatched = []
    monkeypatch.setattr(documents_api, "dispatch_document_ingestion", lambda doc_id, *a, **k: dispatched.append(doc_id))

    current = {"user": owner}
    app = FastAPI()
    app.include_router(projects_api.router)
    app.include_router(presentations_api.router)
    app.include_router(documents_api.router)

    def override_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current["user"]

    yield {"client": TestClient(app), "db": db, "owner": owner, "other": other,
           "current": current, "storage": storage, "vectors": vectors, "Session": Session,
           "dispatched": dispatched}
    db.close()
