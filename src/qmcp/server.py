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
from .watcher import AsyncWatcher

# Initialize logging
init_logging()
logger = get_logger(__name__)


# Initialize FastMCP server
mcp = FastMCP("Qdrant Vector Search", json_response=True)

# Get settings
settings = get_settings()

# Global state
_qdrant_client: QdrantClientWrapper | None = None
_indexer: Indexer | None = None
_cleanup_manager: CleanupManager | None = None
_watcher: AsyncWatcher | None = None
_watch_paths: list[str] = settings.watch_paths


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
) -> dict[str, Any]:
    """Index a directory of code or documentation into Qdrant.

    This tool parses source files and adds their content as vectors
    to the specified collection for semantic search.
    """
    try:
        indexer = get_indexer()
        result = indexer.index_directory(
            path=path,
            collection=collection,
            patterns=patterns,
        )
        return result
    except Exception as e:
        return {"error": str(e), "files_processed": 0}


@mcp.tool()
async def qdrant_reindex(
    path: str = Field(..., description="Directory path to reindex"),
    collection: str = Field(..., description="Collection name to reindex"),
    mode: str = Field(default="incremental", description="Reindex mode: 'full' or 'incremental'"),
) -> dict[str, Any]:
    """Reindex a directory - either full rebuild or incremental update.

    Full mode deletes the collection and recreates it from scratch.
    Incremental mode only updates changed files.
    """
    try:
        indexer = get_indexer()

        if mode == "full":
            result = indexer.full_reindex(path, collection)
        else:
            result = indexer.incremental_reindex(path, collection)

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
    global _watcher, _watch_paths

    try:
        # Stop existing watcher
        if _watcher and _watcher.is_running:
            await _watcher.stop()

        # Create new watcher
        async def on_change(path: str, event_type: str):
            indexer = get_indexer()
            # Determine collection based on file extension
            from pathlib import Path

            ext = Path(path).suffix
            collection = "docs" if ext == ".md" else "code"

            # Reindex the file
            indexer.index_directory(
                path=str(Path(path).parent),
                collection=collection,
            )

        _watcher = AsyncWatcher(paths, on_change, debounce_seconds=settings.debounce_seconds)
        await _watcher.start()

        _watch_paths = paths

        return {
            "status": "started",
            "watching": paths,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def qdrant_watch_stop() -> dict[str, str]:
    """Stop watching paths for file changes."""
    global _watcher

    try:
        if _watcher and _watcher.is_running:
            await _watcher.stop()
            _watcher = None

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
        }
    except QdrantConnectionError:
        return {
            "status": "disconnected",
            "version": __version__,
            "qdrant_connected": False,
            "collections": [],
            "watcher_active": False,
            "watched_paths": [],
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
