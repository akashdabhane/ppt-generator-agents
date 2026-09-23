import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI RAG PowerPoint Generator"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = "supersecretkey_change_in_production_123456789"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

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
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Storage
    STORAGE_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

# Ensure local storage directory exists
os.makedirs(os.path.join(settings.STORAGE_DIR, "projects"), exist_ok=True)
