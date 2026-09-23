import logging
import os
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

INSECURE_DEFAULT_SECRET = "supersecretkey_change_in_production_123456789"


class Settings(BaseSettings):
    PROJECT_NAME: str = "Clarion"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # "development" allows the insecure default SECRET_KEY (with a warning); anything else refuses to start with it
    ENVIRONMENT: str = "development"

    # Security
    SECRET_KEY: str = INSECURE_DEFAULT_SECRET
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Comma-separated origins allowed to call the API (the Next.js app)
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Database Configuration (PostgreSQL)
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ppt_generator_db"

    # Redis & Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Vector Storage ("pinecone", "pgvector", or "mock")
    VECTOR_DB_TYPE: str = "pinecone"
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_ENVIRONMENT: Optional[str] = None
    PINECONE_INDEX_NAME: str = "ppt-generator-rag"
    PGVECTOR_DATABASE_URL: Optional[str] = None

    # LLM Providers & Embeddings
    LLM_PROVIDER: str = "anthropic"  # "anthropic", "openai", "google"
    LLM_MODEL: Optional[str] = None  # Overrides the provider's default model in rag/graph.py
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    # "auto" picks one provider at startup (OpenAI key → openai, else Google key → google, else hash) and sticks to it,
    # so documents and queries are always embedded in the same vector space. Or set "openai" | "google" | "hash".
    EMBEDDING_PROVIDER: str = "auto"
    EMBEDDING_MODEL: Optional[str] = None  # default per provider: text-embedding-3-small / gemini-embedding-001
    EMBEDDING_DIMENSION: int = 1536  # must match the vector index (Pinecone index / pgvector column)

    # Storage
    STORAGE_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "PINECONE_API_KEY", "LLM_MODEL",
                     "EMBEDDING_MODEL", mode="before")
    @classmethod
    def _placeholder_is_unset(cls, value):
        """`.env.example` values like "your_openai_api_key_here" (or blanks) mean "not configured"."""
        if value is None:
            return None
        value = str(value).strip()
        if not value or value.lower().startswith("your_") or value.lower().endswith("_here"):
            return None
        return value

    @field_validator("SECRET_KEY", mode="before")
    @classmethod
    def _placeholder_secret_is_default(cls, value):
        """An unfilled template value is as insecure as the built-in default, so check_secret_key() treats it the same."""
        return INSECURE_DEFAULT_SECRET if cls._placeholder_is_unset(value) is None else str(value).strip()

    @field_validator("LLM_PROVIDER", "EMBEDDING_PROVIDER", "VECTOR_DB_TYPE", "ENVIRONMENT", mode="before")
    @classmethod
    def _lowercase(cls, value):
        return str(value).strip().lower() if value is not None else value

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def check_secret_key(self) -> None:
        if self.SECRET_KEY != INSECURE_DEFAULT_SECRET:
            return
        if self.ENVIRONMENT == "development":
            logger.warning("SECRET_KEY is the public default: login tokens can be forged. Set SECRET_KEY in backend/.env.")
            return
        raise RuntimeError("SECRET_KEY must be set (e.g. `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`) "
                           f"when ENVIRONMENT={self.ENVIRONMENT!r}.")


settings = Settings()

# Ensure local storage directory exists
os.makedirs(os.path.join(settings.STORAGE_DIR, "projects"), exist_ok=True)
