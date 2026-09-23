import hashlib
import logging
import math
from typing import List

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODELS = {
    "openai": "text-embedding-3-small",
    "google": "gemini-embedding-001",
    "hash": "md5-hash",
}
OPENAI_EMBEDDING_MODELS = {"text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"}


class EmbeddingError(RuntimeError):
    """The configured embedding provider failed. Never silently switch providers: mixing vector spaces breaks search."""


def resolve_provider() -> str:
    provider = settings.EMBEDDING_PROVIDER
    if provider == "auto":
        if settings.OPENAI_API_KEY:
            return "openai"
        if settings.GOOGLE_API_KEY:
            return "google"
        return "hash"
    if provider not in DEFAULT_EMBEDDING_MODELS:
        raise ValueError(f"Unknown EMBEDDING_PROVIDER {provider!r} (use auto, openai, google or hash)")
    return provider


class EmbeddingService:
    """
    One embedding provider for the whole process, chosen once from settings, with a fixed output dimension
    (EMBEDDING_DIMENSION, matching the vector index). A provider error raises EmbeddingError instead of
    falling back, because a document embedded by one model can't be found by queries embedded by another.
    """

    GOOGLE_BATCH = 100

    def __init__(self):
        self.provider = resolve_provider()
        self.model_name = self._model_for(self.provider, settings.EMBEDDING_MODEL)
        self.dimension = settings.EMBEDDING_DIMENSION
        if self.provider == "hash":
            logger.warning("No embedding API key: using hash vectors. Semantic search is disabled; retrieval relies on "
                           "keyword ranking. Set OPENAI_API_KEY or GOOGLE_API_KEY for real embeddings.")
        else:
            logger.info(f"Embeddings: {self.provider}/{self.model_name}, {self.dimension} dimensions.")

    @staticmethod
    def _model_for(provider: str, configured: str) -> str:
        """EMBEDDING_MODEL, unless it names another provider's model (e.g. the template's OpenAI model while only a
        Google key is set), in which case the provider's default is used."""
        default = DEFAULT_EMBEDDING_MODELS[provider]
        if not configured or provider == "hash":
            return default
        foreign = (provider == "google" and configured in OPENAI_EMBEDDING_MODELS) or \
                  (provider == "openai" and (configured.startswith(("gemini", "models/")) or configured == "text-embedding-004"))
        if foreign:
            logger.warning(f"EMBEDDING_MODEL={configured!r} is not a {provider} model; using {default!r}.")
            return default
        return configured

    @property
    def is_semantic(self) -> bool:
        return self.provider != "hash"

    def get_embedding(self, text: str) -> List[float]:
        """Embedding for a search query."""
        return self._embed([text], is_query=True)[0]

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Embeddings for document chunks."""
        return self._embed(texts, is_query=False)

    def _embed(self, texts: List[str], is_query: bool) -> List[List[float]]:
        if not texts:
            return []
        try:
            if self.provider == "openai":
                vectors = self._openai(texts)
            elif self.provider == "google":
                vectors = self._google(texts, is_query)
            else:
                vectors = [self._fallback_embedding(t, self.dimension) for t in texts]
        except EmbeddingError:
            raise
        except Exception as e:
            raise EmbeddingError(f"{self.provider} embedding call failed ({type(e).__name__}: {e}). "
                                 "Check the API key and EMBEDDING_MODEL in backend/.env.") from e
        for v in vectors:
            if len(v) != self.dimension:
                raise EmbeddingError(f"{self.provider}/{self.model_name} returned {len(v)} dimensions, but "
                                     f"EMBEDDING_DIMENSION is {self.dimension}.")
        return vectors

    def _openai(self, texts: List[str]) -> List[List[float]]:
        import openai
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        resp = client.embeddings.create(input=texts, model=self.model_name, dimensions=self.dimension)
        return [d.embedding for d in resp.data]

    def _google(self, texts: List[str], is_query: bool) -> List[List[float]]:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        config = types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT",
            output_dimensionality=self.dimension,
        )
        vectors: List[List[float]] = []
        for i in range(0, len(texts), self.GOOGLE_BATCH):
            res = client.models.embed_content(model=self.model_name, contents=texts[i:i + self.GOOGLE_BATCH], config=config)
            # Truncated Gemini embeddings (< 3072 dims) are not unit length; normalise for cosine search
            vectors += [self._normalise(list(e.values)) for e in res.embeddings]
        return vectors

    @staticmethod
    def _normalise(vec: List[float]) -> List[float]:
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm > 0 else vec

    @staticmethod
    def _fallback_embedding(text: str, dim: int = 1536) -> List[float]:
        """Deterministic pseudo-random vector derived from MD5 hash of text (no semantics)."""
        seed_hash = hashlib.md5(text.encode("utf-8")).digest()
        vec = []
        for i in range(dim):
            byte_val = seed_hash[i % len(seed_hash)]
            val = (float(byte_val) / 255.0) * 2.0 - 1.0 + (i * 0.0001)
            vec.append(round(val, 6))
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


embedding_service = EmbeddingService()
