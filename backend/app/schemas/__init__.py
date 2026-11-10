"""Pydantic schemas for request/response serialization."""

from app.schemas.health import HealthResponse
from app.schemas.common import APIResponse

__all__ = ["HealthResponse", "APIResponse"]

