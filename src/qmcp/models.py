"""Pydantic models for qmcp."""

from typing import Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Request model for search operation."""

    query: str = Field(..., description="Search query text")
    collection: Literal["code", "docs"] = Field(
        default="code", description="Collection to search in"
    )
    limit: int = Field(default=5, ge=1, le=100, description="Maximum number of results")
    score_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Minimum score threshold"
    )


class IndexRequest(BaseModel):
    """Request model for indexing operation."""

    path: str = Field(..., description="Directory path to index")
    collection: Literal["code", "docs"] = Field(default="code", description="Target collection")
    patterns: list[str] = Field(
        default=["*.py", "*.go", "*.js", "*.ts", "*.java", "*.cs", "*.md"],
        description="File patterns to include",
    )


class ReindexRequest(BaseModel):
    """Request model for reindex operation."""

    path: str = Field(..., description="Directory path to reindex")
    collection: Literal["code", "docs"] = Field(default="code", description="Target collection")
    mode: Literal["full", "incremental"] = Field(default="incremental", description="Reindex mode")


class WatchRequest(BaseModel):
    """Request model for watch operation."""

    paths: list[str] = Field(..., description="Paths to watch for changes")


class CleanupRequest(BaseModel):
    """Request model for cleanup operation."""

    collection: Literal["code", "docs"] = Field(..., description="Collection to clean")
    dry_run: bool = Field(default=True, description="If True, only report what would be deleted")


class CollectionInfo(BaseModel):
    """Information about a collection."""

    name: str
    vectors_count: int
    points_count: int
    status: str


class SearchResult(BaseModel):
    """Single search result."""

    score: float
    file_path: str
    content: str
    type: str = "unknown"
    line_start: int | None = None
    line_end: int | None = None


class IndexResult(BaseModel):
    """Result of indexing operation."""

    files_processed: int
    points_added: int
    points_updated: int
    points_deleted: int = 0
    duration_seconds: float


class StatusResponse(BaseModel):
    """Status response."""

    status: str
    version: str
    qdrant_connected: bool
    collections: list[str]
    watcher_active: bool
    watched_paths: list[str]
