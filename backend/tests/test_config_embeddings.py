import pytest

from app.core.config import Settings, INSECURE_DEFAULT_SECRET
from app.services import embeddings
from app.services.embeddings import EmbeddingError, EmbeddingService


def _settings(**env):
    return Settings(_env_file=None, **env)


def test_placeholder_keys_count_as_unset():
    s = _settings(OPENAI_API_KEY="your_openai_api_key_here", ANTHROPIC_API_KEY="  ", GOOGLE_API_KEY="real-key",
                  LLM_PROVIDER="Google ")
    assert s.OPENAI_API_KEY is None and s.ANTHROPIC_API_KEY is None
    assert s.GOOGLE_API_KEY == "real-key"
    assert s.LLM_PROVIDER == "google"


def test_default_secret_key_is_refused_outside_development():
    _settings(ENVIRONMENT="development").check_secret_key()  # warns only
    with pytest.raises(RuntimeError):
        _settings(ENVIRONMENT="production").check_secret_key()
    with pytest.raises(RuntimeError):
        _settings(ENVIRONMENT="production", SECRET_KEY="your_secret_key_here").check_secret_key()
    _settings(ENVIRONMENT="production", SECRET_KEY="x" * 48).check_secret_key()
    assert INSECURE_DEFAULT_SECRET not in _settings(SECRET_KEY="x" * 48).SECRET_KEY


def test_cors_origins_are_explicit():
    assert _settings(CORS_ORIGINS="https://app.example.com, http://localhost:3000").cors_origins == [
        "https://app.example.com", "http://localhost:3000"]


def _service(monkeypatch, **overrides):
    s = _settings(**{"EMBEDDING_PROVIDER": "auto", **overrides})
    monkeypatch.setattr(embeddings, "settings", s)
    return EmbeddingService()


def test_auto_provider_is_resolved_once_from_real_keys(monkeypatch):
    assert _service(monkeypatch, OPENAI_API_KEY="your_openai_api_key_here", GOOGLE_API_KEY="g").provider == "google"
    assert _service(monkeypatch, OPENAI_API_KEY="sk-1", GOOGLE_API_KEY="g").provider == "openai"
    svc = _service(monkeypatch)
    assert svc.provider == "hash" and not svc.is_semantic
    assert len(svc.get_embedding("q")) == 1536


def test_provider_failure_raises_instead_of_switching_vector_space(monkeypatch):
    svc = _service(monkeypatch, GOOGLE_API_KEY="g")

    def boom(texts, is_query):
        raise ConnectionError("network down")

    monkeypatch.setattr(svc, "_google", boom)
    with pytest.raises(EmbeddingError, match="google embedding call failed"):
        svc.get_embeddings(["chunk"])


def test_wrong_dimension_is_rejected(monkeypatch):
    svc = _service(monkeypatch, GOOGLE_API_KEY="g", EMBEDDING_DIMENSION=1536)
    monkeypatch.setattr(svc, "_google", lambda texts, is_query: [[0.1] * 768 for _ in texts])
    with pytest.raises(EmbeddingError, match="768 dimensions"):
        svc.get_embeddings(["chunk"])


def test_google_uses_query_and_document_task_types(monkeypatch):
    svc = _service(monkeypatch, GOOGLE_API_KEY="g", EMBEDDING_DIMENSION=4)
    seen = []

    class FakeModels:
        def embed_content(self, model, contents, config):
            seen.append((model, config.task_type, config.output_dimensionality, len(contents)))
            return type("R", (), {"embeddings": [type("E", (), {"values": [3.0, 4.0, 0.0, 0.0]})() for _ in contents]})()

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    import google.genai
    monkeypatch.setattr(google.genai, "Client", FakeClient)
    assert svc.get_embedding("q") == [0.6, 0.8, 0.0, 0.0]  # normalised
    svc.get_embeddings(["a", "b"])
    assert seen == [("gemini-embedding-001", "RETRIEVAL_QUERY", 4, 1), ("gemini-embedding-001", "RETRIEVAL_DOCUMENT", 4, 2)]


def test_embedding_model_from_another_provider_is_replaced(monkeypatch):
    # The template's OpenAI model with only a Google key must not be sent to Google
    svc = _service(monkeypatch, GOOGLE_API_KEY="g", EMBEDDING_MODEL="text-embedding-3-small")
    assert (svc.provider, svc.model_name) == ("google", "gemini-embedding-001")
    svc = _service(monkeypatch, OPENAI_API_KEY="sk", EMBEDDING_MODEL="text-embedding-3-large")
    assert svc.model_name == "text-embedding-3-large"
    svc = _service(monkeypatch, OPENAI_API_KEY="sk", EMBEDDING_MODEL="gemini-embedding-001")
    assert svc.model_name == "text-embedding-3-small"
