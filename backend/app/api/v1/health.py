"""Health check endpoints for RepoPilot AI backend."""

from datetime import datetime, timezone
from fastapi import APIRouter, status
from app.core.config import settings
from app.schemas.health import HealthResponse
from app.sandbox.container_manager import is_docker_available

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application Health Probe",
    description="Returns the operational status, version, and environment of RepoPilot AI backend.",
)
async def get_health() -> HealthResponse:
    """Returns application health metadata."""
    docker_ready = is_docker_available()
    return HealthResponse(
        status="healthy",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc).isoformat(),
        subsystems={
            "database": "configured" if settings.DATABASE_URL else "unconfigured",
            "docker_sandbox": "ready" if docker_ready else "unavailable (Docker daemon not running)",
            "gemini_api": "ready" if settings.is_gemini_configured else "offline_mode",
            "ai_analysis": settings.ai_analysis_mode,
            "embeddings": settings.embedding_mode,
        },
    )

