"""RepoPilot AI — FastAPI Application Entry Point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings, validate_configuration
from app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and shutdown lifecycle events."""
    logger.info("Initializing RepoPilot AI Backend [%s]...", settings.ENVIRONMENT)
    validate_configuration()
    logger.info("CORS origins configured: %s", settings.BACKEND_CORS_ORIGINS)
    yield
    logger.info("Shutting down RepoPilot AI Backend...")


def create_application() -> FastAPI:
    """Application factory for FastAPI."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=(
            "Autonomous AI-powered software engineering platform designed to ingest, "
            "analyze, plan, fix, and validate codebases."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API v1 router under configured prefix (/api/v1)
    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

    # Root redirect / basic info
    @app.get("/", tags=["Root"])
    async def root_info() -> dict:
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "status": "online",
            "docs_url": "/docs",
            "health_url": f"{settings.API_V1_PREFIX}/health",
        }

    return app


app = create_application()

