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

"""MCP Server for Qdrant - main entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .__init__ import __version__
from .cleanup import CleanupManager
from .client import QdrantClientWrapper, QdrantConnectionError
from .config import get_settings
from .diagnostics import DiagnosticsManager
from .indexer import Indexer
from .logging_config import get_logger, init_logging
from .models import SupportedModel
from .watcher import AsyncWatcher

# Initialize logging
init_logging()
logger = get_logger(__name__)


# Get settings
settings = get_settings()

# Supported embedding models with metadata
SUPPORTED_MODELS: list[SupportedModel] = [
    SupportedModel(
        model="jinaai/jina-embeddings-v2-base-code",
        dim=768,
        size_in_gb=0.64,
        languages="Multilingual (30+ programming languages)",
        use_case="code search",
        notes="Best for code search, supports 30+ programming languages",
        has_prefix=False,
    ),
    SupportedModel(
        model="BAAI/bge-small-en-v1.5",
        dim=384,
        size_in_gb=0.07,
        languages="English",
        use_case="documentation",
        notes="Lightweight, fast, good default for English documentation",
        has_prefix=False,
    ),
    SupportedModel(
        model="BAAI/bge-large-en-v1.5",
        dim=1024,
        size_in_gb=1.2,
        languages="English",
        use_case="documentation",
        notes="Best quality for English documentation",
        has_prefix=False,
    ),
    SupportedModel(
        model="intfloat/multilingual-e5-large",
        dim=1024,
        size_in_gb=2.24,
        languages="Multilingual (100+)",
        use_case="multilingual KB",
        notes="Best for corporate KB with RU+EN content. Requires 'query:' / 'passage:' prefixes (automatic)",
        has_prefix=True,
    ),
    SupportedModel(
        model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        dim=384,
        size_in_gb=0.22,
        languages="Multilingual (50+)",
        use_case="multilingual KB",
        notes="Lightweight multilingual option, good compromise",
        has_prefix=False,
    ),
]

# Global state
_qdrant_client: QdrantClientWrapper | None = None
_indexer: Indexer | None = None
_cleanup_manager: CleanupManager | None = None
_watcher: AsyncWatcher | None = None
_watch_paths: list[str] = settings.watch_paths


def _normalize_watch_paths(paths: list[str]) -> list[str]:
    """Normalize watch paths, remove duplicates, and preserve order.

    Args:
        paths: Raw watch paths provided by configuration or tool calls

    Returns:
        Normalized absolute paths with duplicates removed
    """
    normalized_paths: list[str] = []
    seen_paths: set[str] = set()

    for raw_path in paths:
        if not raw_path:
            continue

        normalized_path = str(Path(raw_path).expanduser().resolve())
        if normalized_path in seen_paths:
            continue

        normalized_paths.append(normalized_path)
        seen_paths.add(normalized_path)

    return normalized_paths


def _split_existing_watch_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    """Split requested watch paths into existing and missing paths.

    Args:
        paths: Normalized watch paths to validate

    Returns:
        Tuple of (existing_paths, missing_paths)
    """
    existing_paths: list[str] = []
    missing_paths: list[str] = []

    for path in _normalize_watch_paths(paths):
        if Path(path).exists():
            existing_paths.append(path)
        else:
            missing_paths.append(path)

    return existing_paths, missing_paths


async def _handle_watch_change(path: str, event_type: str) -> None:
    """Handle a filesystem change event and trigger incremental indexing.

    Args:
        path: Changed filesystem path
        event_type: Type of filesystem event
    """
    indexer = get_indexer()
    extension = Path(path).suffix
    collection = "docs" if extension == ".md" else "code"

    logger.info("Processing watch event '%s' for %s", event_type, path)

    indexer.index_directory(
        path=str(Path(path).parent),
        collection=collection,
    )


async def _stop_watcher() -> None:
    """Stop the active watcher if it is running."""
    global _watcher

    if _watcher and _watcher.is_running:
        await _watcher.stop()

    _watcher = None


async def _start_watcher(paths: list[str]) -> dict[str, Any]:
    """Start watcher for the given set of paths.

    Args:
        paths: Paths that should be watched

    Returns:
        Status payload describing active and skipped paths
    """
    global _watcher, _watch_paths

    valid_paths, skipped_paths = _split_existing_watch_paths(paths)

    if not valid_paths:
        await _stop_watcher()
        _watch_paths = []

        return {
            "status": "skipped",
            "watching": [],
            "skipped_paths": skipped_paths,
            "message": "No existing watch paths were provided.",
        }

    await _stop_watcher()

    _watcher = AsyncWatcher(
        valid_paths,
        _handle_watch_change,
        debounce_seconds=settings.debounce_seconds,
    )
    await _watcher.start()
    _watch_paths = valid_paths

    logger.info("Started watcher for %d path(s): %s", len(valid_paths), valid_paths)

    return {
        "status": "started",
        "watching": valid_paths,
        "skipped_paths": skipped_paths,
    }


async def _ensure_watcher_started(paths: list[str]) -> dict[str, Any]:
    """Ensure watcher is running for the provided paths.

    Args:
        paths: Target watch paths after normalization

    Returns:
        Status payload describing whether watcher was started, restarted, or reused
    """
    global _watcher

    normalized_paths = _normalize_watch_paths(paths)
    valid_paths, skipped_paths = _split_existing_watch_paths(normalized_paths)
    watcher_was_running = _watcher is not None and _watcher.is_running

    if _watcher and _watcher.is_running and _watch_paths == valid_paths:
        return {
            "status": "already_running",
            "watching": valid_paths,
            "skipped_paths": skipped_paths,
        }

    result = await _start_watcher(normalized_paths)
    if result["status"] == "started" and watcher_was_running:
        result["status"] = "restarted"

    return result


@asynccontextmanager
async def app_lifespan(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Manage watcher lifecycle for server startup and shutdown.

    On startup the server attempts to enable automatic indexing for configured
    WATCH_PATHS. This is best-effort so the MCP server can still start even if
    no valid filesystem paths are configured.
    """
    configured_paths = _normalize_watch_paths(settings.watch_paths)

    try:
        startup_result = await _ensure_watcher_started(configured_paths)
        if startup_result["status"] == "skipped":
            logger.warning(
                "Automatic indexing was not enabled on startup. Invalid watch paths: %s",
                startup_result.get("skipped_paths", []),
            )
    except Exception as exc:
        logger.exception("Failed to start watcher during MCP startup: %s", exc)

    try:
        yield {}
    finally:
        try:
            await _stop_watcher()
        except Exception as exc:
            logger.exception("Failed to stop watcher during MCP shutdown: %s", exc)


# Initialize FastMCP server
mcp = FastMCP("Qdrant Vector Search", json_response=True, lifespan=app_lifespan)


def get_qdrant_client() -> QdrantClientWrapper:
    """Get or create Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        logger.info("Creating new Qdrant client")
        _qdrant_client = QdrantClientWrapper()
        _qdrant_client.connect()
    return _qdrant_client


def get_indexer() -> Indexer:
    """Get or create indexer."""
    global _indexer
    if _indexer is None:
        client = get_qdrant_client()
        _indexer = Indexer(client, batch_size=settings.batch_size)
    return _indexer


def get_cleanup_manager() -> CleanupManager:
    """Get or create cleanup manager."""
    global _cleanup_manager
    if _cleanup_manager is None:
        client = get_qdrant_client()
        _cleanup_manager = CleanupManager(client)
    return _cleanup_manager


def get_diagnostics_manager() -> DiagnosticsManager:
    """Get or create diagnostics manager."""
    client = get_qdrant_client()
    return DiagnosticsManager(client)


# ============================================================================
# TOOLS
# ============================================================================


@mcp.tool()
async def qdrant_search(
    query: str = Field(..., description="Search query text"),
    collection: str = Field(
        ..., description="Collection name to search in (use project-specific name to isolate data)"
    ),
    limit: int = Field(default=5, ge=1, le=100, description="Maximum number of results"),
    score_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Minimum score threshold"
    ),
    chunk_type: str | None = Field(
        default=None,
        description="Filter by chunk type (e.g., 'function_def', 'class_def', 'document')",
    ),
    symbol_name: str | None = Field(
        default=None,
        description="Filter by exact symbol name (function, class, variable name)",
    ),
    language: str | None = Field(
        default=None,
        description="Filter by programming language (e.g., 'python', 'go', 'javascript')",
    ),
) -> list[dict[str, Any]]:
    """Search for similar code or documentation using semantic search.

    This tool performs vector search in Qdrant to find relevant code snippets
    or documentation based on semantic similarity to the query.

    Use optional filters to narrow down results:
    - chunk_type: Find only specific code constructs (function_def, class_def, etc.)
    - symbol_name: Find exact symbol by name (e.g., 'get_user', 'MyClass')
    - language: Find only files of a specific language
    """
    try:
        client = get_qdrant_client()
        results = client.search(
            collection=collection,
            query=query,
            limit=limit,
            score_threshold=score_threshold,
            chunk_type=chunk_type,
            symbol_name=symbol_name,
            language=language,
        )
        return results
    except QdrantConnectionError as e:
        return [{"error": str(e)}]


@mcp.tool()
async def qdrant_search_many(
    collections: list[str] = Field(
        ...,
        description="List of collection names to search across",
    ),
    query: str = Field(..., description="Search query text"),
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results per collection"),
    score_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Minimum score threshold"
    ),
) -> list[dict[str, Any]]:
    """Search across multiple collections and merge results.

    This tool is useful for corporate knowledge bases where information
    is spread across multiple collections (e.g., team-docs, company-kb, project-code).

    Results are sorted by score descending across all collections.
    Each result includes a 'collection' field indicating its source.
    """
    try:
        client = get_qdrant_client()
        results = client.search_many(
            collections=collections,
            query=query,
            limit=limit,
            score_threshold=score_threshold,
        )
        return results
    except QdrantConnectionError as e:
        return [{"error": str(e)}]


@mcp.tool()
async def qdrant_list_supported_models(
    filter: str | None = Field(
        default=None,
        description="Filter models: 'code', 'multilingual', 'lightweight', or 'all' (default: all)",
    ),
) -> list[dict[str, Any]]:
    """List supported embedding models with their metadata.

    Returns a list of recommended embedding models for different use cases:
    - code: Models optimized for code search
    - multilingual: Models supporting multiple languages including RU+EN
    - lightweight: Smaller, faster models for quick indexing
    - all: All available models

    Each model includes:
    - model: Full model name (use this for model= parameter)
    - dim: Embedding dimension
    - size_in_GB: Model size in GB
    - languages: Supported languages
    - use_case: Primary use case
    - notes: Additional notes
    - has_prefix: Whether 'query:'/'passage:' prefixes are required (E5 models)
    """
    if filter is None or filter == "all":
        return [m.model_dump() for m in SUPPORTED_MODELS]

    filter_lower = filter.lower()
    filtered_models = []

    for model in SUPPORTED_MODELS:
        if filter_lower == "code" and model.use_case == "code search":
            filtered_models.append(model)
        elif filter_lower == "multilingual" and "multilingual" in model.use_case.lower():
            filtered_models.append(model)
        elif filter_lower == "lightweight":
            # Lightweight = smaller than 0.5 GB
            if model.size_in_GB < 0.5:
                filtered_models.append(model)

    return [m.model_dump() for m in filtered_models]


@mcp.tool()
async def qdrant_index_directory(
    path: str = Field(..., description="Directory path to index"),
    collection: str = Field(
        ...,
        description="Collection name to index into (use unique name per project for data isolation)",
    ),
    patterns: list[str] = Field(
        default=["*.py", "*.go", "*.js", "*.ts", "*.java", "*.cs", "*.md"],
        description="File patterns to include",
    ),
    model: str | None = Field(
        default=None,
        description="Embedding model to use (default: from settings). Example: 'jinaai/jina-embeddings-v2-base-code'",
    ),
    metadata: dict | None = Field(
        default=None,
        description="Extra metadata fields to store with each chunk (e.g., {'team': 'backend', 'visibility': 'internal'})",
    ),
) -> dict[str, Any]:
    """Index a directory of code or documentation into Qdrant.

    This tool parses source files and adds their content as vectors
    to the specified collection for semantic search.

    Use the model parameter to specify which embedding model to use:
    - Default: uses EMBEDDING_MODEL from settings
    - Code search: 'jinaai/jina-embeddings-v2-base-code'
    - Multilingual KB: 'intfloat/multilingual-e5-large'
    - Lightweight: 'BAAI/bge-small-en-v1.5'
    """
    try:
        indexer = get_indexer()
        result = indexer.index_directory(
            path=path,
            collection=collection,
            patterns=patterns,
            model=model,
            metadata=metadata,
        )
        return result
    except Exception as e:
        return {"error": str(e), "files_processed": 0}


@mcp.tool()
async def qdrant_reindex(
    path: str = Field(..., description="Directory path to reindex"),
    collection: str = Field(..., description="Collection name to reindex"),
    mode: str = Field(default="incremental", description="Reindex mode: 'full' or 'incremental'"),
    model: str | None = Field(
        default=None,
        description="Embedding model to use (default: from settings). Example: 'intfloat/multilingual-e5-large'",
    ),
) -> dict[str, Any]:
    """Reindex a directory - either full rebuild or incremental update.

    Full mode deletes the collection and recreates it from scratch.
    Incremental mode only updates changed files.

    Use the model parameter to change the embedding model:
    - 'jinaai/jina-embeddings-v2-base-code' for code
    - 'intfloat/multilingual-e5-large' for multilingual KB
    """
    try:
        indexer = get_indexer()

        if mode == "full":
            result = indexer.full_reindex(path, collection, model=model)
        else:
            result = indexer.incremental_reindex(path, collection, model=model)

        return result
    except Exception as e:
        return {"error": str(e), "files_processed": 0}


@mcp.tool()
async def qdrant_list_collections() -> list[str]:
    """List all collections in Qdrant."""
    try:
        client = get_qdrant_client()
        return client.get_collections()
    except Exception:
        return []


@mcp.tool()
async def qdrant_get_collection_info(
    name: str = Field(..., description="Collection name"),
) -> dict[str, Any]:
    """Get information about a collection."""
    try:
        client = get_qdrant_client()
        return client.get_collection_info(name)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def qdrant_delete_collection(
    name: str = Field(..., description="Collection name to delete"),
) -> dict[str, str]:
    """Delete a collection from Qdrant."""
    try:
        client = get_qdrant_client()
        client.delete_collection(name)
        return {"status": "deleted", "collection": name}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def qdrant_watch_start(
    paths: list[str] = Field(..., description="Paths to watch for changes"),
) -> dict[str, Any]:
    """Start watching paths for file changes and auto-reindex.

    This enables live updates - files are reindexed when modified.
    """
    try:
        return await _start_watcher(paths)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def qdrant_watch_ensure(
    paths: list[str] = Field(..., description="Workspace paths that must be watched"),
    include_existing: bool = Field(
        default=True,
        description="Keep paths that are already being watched by the running server",
    ),
    include_configured: bool = Field(
        default=True,
        description="Keep paths configured through WATCH_PATHS on server startup",
    ),
) -> dict[str, Any]:
    """Ensure watcher is active for the current workspace without dropping other projects.

    This tool is designed for OpenCode sessions where one global MCP server is
    shared across multiple repositories. It merges workspace paths with the
    configured and/or currently watched paths and only restarts the watcher when
    the effective watch set changes.
    """
    requested_paths: list[str] = []

    if include_configured:
        requested_paths.extend(settings.watch_paths)
    if include_existing:
        requested_paths.extend(_watch_paths)
    requested_paths.extend(paths)

    try:
        return await _ensure_watcher_started(requested_paths)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def qdrant_watch_stop() -> dict[str, str]:
    """Stop watching paths for file changes."""
    global _watch_paths

    try:
        await _stop_watcher()
        _watch_paths = []

        return {"status": "stopped"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def qdrant_cleanup(
    collection: str = Field(..., description="Collection name to clean"),
    repo_path: str = Field(
        ..., description="Repository path to compare against (directory that was indexed)"
    ),
    dry_run: bool = Field(default=True, description="If True, only report what would be deleted"),
) -> dict[str, Any]:
    """Clean up stale vectors - remove vectors for deleted or changed files."""
    try:
        cleanup = get_cleanup_manager()
        result = cleanup.cleanup(
            collection=collection,
            repo_path=repo_path,
            dry_run=dry_run,
        )
        return result
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def qdrant_get_status() -> dict[str, Any]:
    """Get status of the Qdrant MCP server."""
    global _watcher, _watch_paths

    try:
        client = get_qdrant_client()
        collections = client.get_collections()

        return {
            "status": "healthy",
            "version": __version__,
            "qdrant_connected": client.is_connected,
            "collections": collections,
            "watcher_active": _watcher.is_running if _watcher else False,
            "watched_paths": _watch_paths,
            "configured_watch_paths": _normalize_watch_paths(settings.watch_paths),
        }
    except QdrantConnectionError:
        return {
            "status": "disconnected",
            "version": __version__,
            "qdrant_connected": False,
            "collections": [],
            "watcher_active": False,
            "watched_paths": [],
            "configured_watch_paths": _normalize_watch_paths(settings.watch_paths),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


@mcp.tool()
async def qdrant_diagnose_collection(
    collection: str = Field(..., description="Collection name to diagnose"),
) -> dict[str, Any]:
    """Perform full diagnostics of a collection.

    Analyzes the collection and returns:
    - Total vectors and files count
    - File type distribution
    - Chunk type distribution
    - Indexing timestamp range (oldest/newest)
    - Issues found (missing hashes, empty chunks, etc.)
    - List of all indexed files with details
    """
    try:
        diagnostics = get_diagnostics_manager()
        return diagnostics.diagnose_collection(collection)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def qdrant_list_indexed_files(
    collection: str = Field(..., description="Collection name"),
    limit: int = Field(default=100, ge=1, le=1000, description="Max files to return"),
    offset: int = Field(default=0, ge=0, description="Pagination offset"),
    file_type: str | None = Field(
        default=None, description="Filter by file extension (e.g., '.py', '.go')"
    ),
) -> dict[str, Any]:
    """List all indexed files in a collection with pagination.

    Returns file metadata including:
    - File path
    - Number of chunks
    - Content hash
    - Indexed timestamp
    - Chunk types found in file
    """
    try:
        diagnostics = get_diagnostics_manager()
        return diagnostics.list_indexed_files(
            collection=collection,
            limit=limit,
            offset=offset,
            file_type_filter=file_type,
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def qdrant_diff_collection(
    collection: str = Field(..., description="Collection name to compare"),
    repo_path: str = Field(..., description="Repository path to compare against"),
) -> dict[str, Any]:
    """Compare Qdrant collection state with filesystem.

    Detects three types of discrepancies:
    - orphans: Vectors in Qdrant but file doesn't exist on disk
    - missing: Files on disk but not indexed in Qdrant
    - modified: Files that exist but content has changed (hash mismatch)
    """
    try:
        diagnostics = get_diagnostics_manager()
        return diagnostics.diff_collection(collection=collection, repo_path=repo_path)
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# RESOURCES
# ============================================================================


@mcp.resource("status://collections")
async def get_collections_status() -> str:
    """Get status of all collections."""
    try:
        client = get_qdrant_client()
        collections = client.get_collections()

        lines = ["# Collections Status\n"]
        for name in collections:
            info = client.get_collection_info(name)
            lines.append(f"## {name}")
            lines.append(f"- Points: {info.get('points_count', 0)}")
            lines.append(f"- Indexed Vectors: {info.get('indexed_vectors_count', 0)}")
            lines.append(f"- Status: {info.get('status', 'unknown')}")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
