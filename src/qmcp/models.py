# Copyright 2024 Artur
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pydantic models for qmcp."""

from typing import Literal

from pydantic import BaseModel, Field

# ============================================================================
# Model Selection Models
# ============================================================================


class SupportedModel(BaseModel):
    """Supported embedding model with metadata."""

    model: str = Field(..., description="Full model name (e.g., 'BAAI/bge-small-en-v1.5')")
    dim: int = Field(..., description="Embedding dimension")
    size_in_gb: float = Field(..., description="Model size in GB")
    languages: str = Field(
        ..., description="Supported languages (e.g., 'English', 'Multilingual (100+)')"
    )
    use_case: str = Field(
        ...,
        description="Primary use case (e.g., 'code search', 'documentation', 'multilingual KB')",
    )
    notes: str = Field(..., description="Additional notes about the model")
    has_prefix: bool = Field(
        default=False,
        description="Whether this model requires 'query:' / 'passage:' prefixes (E5 models)",
    )


class SearchManyRequest(BaseModel):
    """Request model for searching multiple collections."""

    collections: list[str] = Field(..., description="List of collection names to search")
    query: str = Field(..., description="Search query text")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results per collection")
    score_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Minimum score threshold"
    )


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
    collection: str = Field(..., description="Target collection name")
    patterns: list[str] = Field(
        default=["*.py", "*.go", "*.js", "*.ts", "*.java", "*.cs", "*.md"],
        description="File patterns to include",
    )
    model: str | None = Field(
        default=None,
        description="Embedding model to use (default: from settings). Example: 'jinaai/jina-embeddings-v2-base-code'",
    )
    metadata: dict | None = Field(
        default=None,
        description="Extra metadata fields to store with each chunk (e.g., {'team': 'backend', 'visibility': 'internal'})",
    )


class ReindexRequest(BaseModel):
    """Request model for reindex operation."""

    path: str = Field(..., description="Directory path to reindex")
    collection: str = Field(..., description="Target collection name")
    mode: Literal["full", "incremental"] = Field(default="incremental", description="Reindex mode")
    model: str | None = Field(
        default=None,
        description="Embedding model to use (default: from settings). Example: 'intfloat/multilingual-e5-large'",
    )


class WatchRequest(BaseModel):
    """Request model for watch operation."""

    paths: list[str] = Field(..., description="Paths to watch for changes")


class WatchEnsureRequest(BaseModel):
    """Request model for idempotent watch operation."""

    paths: list[str] = Field(..., description="Workspace paths that must be watched")
    include_existing: bool = Field(
        default=True,
        description="Keep paths already watched by the running server",
    )
    include_configured: bool = Field(
        default=True,
        description="Keep paths configured through WATCH_PATHS",
    )


class CleanupRequest(BaseModel):
    """Request model for cleanup operation."""

    collection: str = Field(..., description="Collection name to clean")
    dry_run: bool = Field(default=True, description="If True, only report what would be deleted")


class CollectionInfo(BaseModel):
    """Information about a collection."""

    name: str
    points_count: int
    indexed_vectors_count: int
    status: str
    embedding_model: str | None = Field(
        default=None,
        description="Embedding model used for this collection (e.g., 'BAAI/bge-small-en-v1.5')",
    )


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
    configured_watch_paths: list[str]


# ============================================================================
# Diagnostics Models
# ============================================================================


class FileTypeStats(BaseModel):
    """File type statistics."""

    extension: str
    count: int


class ChunkTypeDistribution(BaseModel):
    """Distribution of chunk types."""

    chunk_type: str
    count: int


class IndexedAtRange(BaseModel):
    """Range of indexing timestamps."""

    oldest: str | None = None
    newest: str | None = None


class IssueReport(BaseModel):
    """Issue found during diagnostics."""

    severity: str  # "error", "warning", "info"
    message: str
    file_path: str | None = None


class DiagnosticsResult(BaseModel):
    """Complete diagnostics result for a collection."""

    collection: str
    total_vectors: int
    total_files: int
    storage_bytes: int | None
    status: str
    file_types: dict[str, int]
    chunk_type_distribution: dict[str, int]
    indexed_at_range: IndexedAtRange
    issues: list[str]


class IndexedFileInfo(BaseModel):
    """Information about a single indexed file."""

    file_path: str
    chunk_count: int
    content_hash: str
    indexed_at: str | None = None
    chunk_types: list[str] = Field(default_factory=list)
    file_type: str = "unknown"


class ListFilesResult(BaseModel):
    """Result of listing indexed files."""

    collection: str
    total_files: int
    returned: int
    offset: int
    limit: int
    files: list[IndexedFileInfo]


class DiffSummary(BaseModel):
    """Summary of differences."""

    total_indexed: int
    total_files_in_repo: int
    orphans_count: int
    missing_count: int
    modified_count: int


class OrphanedEntry(BaseModel):
    """An orphaned vector entry."""

    file_path: str
    chunk_count: int
    reason: str


class MissingEntry(BaseModel):
    """A missing file entry."""

    file_path: str
    reason: str
    size_bytes: int = 0


class ModifiedEntry(BaseModel):
    """A modified file entry."""

    file_path: str
    stored_hash: str
    current_hash: str
    chunk_count: int


class DiffResult(BaseModel):
    """Result of comparing collection with filesystem."""

    collection: str
    repo_path: str
    summary: DiffSummary
    orphans: list[OrphanedEntry]
    missing: list[MissingEntry]
    modified: list[ModifiedEntry]
