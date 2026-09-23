from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.database.session import engine
from app.database.migrate import run_migrations
from app.api.v1 import auth, projects, documents, presentations


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.check_secret_key()
    # Schema is managed by Alembic (backend/migrations); pre-migration databases are stamped automatically
    run_migrations(engine)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register V1 API routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(projects.router, prefix=settings.API_V1_STR)
app.include_router(documents.router, prefix=settings.API_V1_STR)
app.include_router(presentations.router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    return {
        "message": "Welcome to the Clarion API",
        "version": settings.VERSION,
        "docs": "/docs"
    }
