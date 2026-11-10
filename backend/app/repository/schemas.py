"""Pydantic schemas for repository ingestion, metadata, and directory tree."""

from typing import List, Optional
from pydantic import BaseModel, Field


class LanguageDistribution(BaseModel):
    """Distribution statistics for an identified programming language."""

    name: str = Field(..., description="Programming language name (e.g., Python, TypeScript)")
    file_count: int = Field(..., ge=0, description="Total files detected in this language")
    byte_count: int = Field(..., ge=0, description="Total size in bytes of source files")
    percentage: float = Field(..., ge=0.0, le=100.0, description="Percentage of total code volume")


class TreeNode(BaseModel):
    """Recursive directory tree node representation."""

    name: str = Field(..., description="File or folder name")
    path: str = Field(..., description="Relative path from repository root")
    type: str = Field(..., description="'file' or 'directory'")
    size_bytes: int = Field(0, ge=0, description="File size in bytes (0 for directories)")
    extension: Optional[str] = Field(None, description="File extension with leading dot if applicable")
    language: Optional[str] = Field(None, description="Identified language name for source files")
    children: Optional[List["TreeNode"]] = Field(None, description="Sub-nodes for directory types")


# Enable self-referential Pydantic model resolution
TreeNode.model_rebuild()


class CloneRepoRequest(BaseModel):
    """Request payload for GitHub repository ingestion."""

    url: str = Field(..., description="HTTPS URL of the public GitHub repository")
    branch: Optional[str] = Field(None, description="Optional branch or tag to clone")


class RepositorySummary(BaseModel):
    """Summary overview of an ingested repository."""

    id: str = Field(..., description="Unique repository UUID")
    name: str = Field(..., description="Sanitized repository name")
    source_type: str = Field(..., description="'ZIP' or 'GITHUB'")
    remote_url: Optional[str] = Field(None, description="Original GitHub URL if cloned")
    default_branch: Optional[str] = Field(None, description="Default or active branch")
    total_files: int = Field(..., ge=0, description="Total source files indexed")
    total_directories: int = Field(..., ge=0, description="Total directories indexed")
    total_size_bytes: int = Field(..., ge=0, description="Total size in bytes")
    languages: List[LanguageDistribution] = Field(default_factory=list, description="Language breakdown")
    status: str = Field(default="READY", description="'READY', 'PROCESSING', or 'FAILED'")
    created_at: str = Field(..., description="ISO 8601 ingestion timestamp")


class RepositoryDetail(RepositorySummary):
    """Detailed repository view including full directory tree hierarchy."""

    tree: TreeNode = Field(..., description="Root directory tree node")


class RepositoryTreeResponse(BaseModel):
    """Standalone response for directory tree query."""

    repository_id: str
    name: str
    tree: TreeNode
