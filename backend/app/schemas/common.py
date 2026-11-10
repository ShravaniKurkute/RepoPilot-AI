"""Common Pydantic schemas shared across endpoints."""

from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class APIResponse(BaseModel, Generic[DataT]):
    """Standardized API response wrapper."""

    success: bool = Field(default=True, description="Indicates if the request succeeded")
    message: str = Field(default="Operation completed successfully", description="Status message")
    data: Optional[DataT] = Field(default=None, description="Payload data")

