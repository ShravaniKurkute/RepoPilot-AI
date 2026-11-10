"""Health check response models."""

from typing import Dict
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Schema for health-check endpoint."""

    status: str = Field(default="healthy", description="Application health status")
    version: str = Field(description="RepoPilot AI backend version")
    environment: str = Field(description="Current deployment environment")
    timestamp: str = Field(description="ISO 8601 server timestamp")
    subsystems: Dict[str, str] = Field(
        default_factory=dict,
        description="Health status of downstream subsystems",
    )

