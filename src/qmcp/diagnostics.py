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

"""Diagnostics module for Qdrant collection analysis."""

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import QdrantClientWrapper
from .logging_config import get_logger


@dataclass
class FileInfo:
    """Information about an indexed file."""

    file_path: str
    chunk_count: int
    content_hash: str
    indexed_at: str | None
    chunk_types: list[str] = field(default_factory=list)
    total_lines: int = 0


@dataclass
class CollectionDiagnostics:
    """Complete diagnostics of a collection."""

    collection_name: str
    total_vectors: int
    total_files: int
    storage_bytes: int | None
    status: str
    file_types: dict[str, int]
    chunk_type_distribution: dict[str, int]
    indexed_at_range: tuple[str | None, str | None]
    issues: list[str]
    files: list[FileInfo] = field(default_factory=list)


class DiagnosticsManager:
    """Manages diagnostics and introspection for Qdrant collections."""

    def __init__(self, qdrant_client: QdrantClientWrapper):
        """Initialize diagnostics manager.

        Args:
            qdrant_client: Qdrant client wrapper instance
        """
        self.qdrant = qdrant_client
        self.logger = get_logger(f"{__name__}.DiagnosticsManager")

    def diagnose_collection(self, collection: str) -> dict[str, Any]:
        """Perform full diagnostics of a collection.

        Args:
            collection: Collection name to diagnose

        Returns:
            Dictionary with complete diagnostics
        """
        self.logger.info(f"Running diagnostics on collection: {collection}")

        if not self.qdrant.collection_exists(collection):
            return {
                "error": f"Collection '{collection}' does not exist",
                "collection": collection,
            }

        # Get basic collection info
        info = self.qdrant.get_collection_info(collection)

        # Get all points
        all_points = self.qdrant.get_all_points(collection)

        # Group points by file
        file_data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "chunks": [],
                "chunk_types": [],
                "lines": set(),
                "hash": None,
                "indexed_at": None,
            }
        )

        for point in all_points:
            payload = point.get("payload", {})
            file_path = payload.get("file_path", "")
            if not file_path:
                continue

            # Track chunk info
            file_data[file_path]["chunks"].append(
                {
                    "id": point["id"],
                    "content": payload.get("content", "")[:100],
                    "type": payload.get("type", "unknown"),
                    "name": payload.get("name", ""),
                }
            )
            file_data[file_path]["chunk_types"].append(payload.get("type", "unknown"))

            # Track line range
            line_start = payload.get("line_start")
            line_end = payload.get("line_end")
            if line_start and line_end:
                file_data[file_path]["lines"].update(range(line_start, line_end + 1))

            # Track hash and indexed time
            if not file_data[file_path]["hash"]:
                file_data[file_path]["hash"] = payload.get("content_hash")
                file_data[file_path]["indexed_at"] = payload.get("indexed_at")

        # Build file info list
        files: list[FileInfo] = []
        file_types: Counter = Counter()
        chunk_type_dist: Counter = Counter()
        indexed_at_values: list[str] = []
        issues: list[str] = []

        # Validate vector dimensions (after issues is defined)
        vector_validation = self.qdrant.validate_collection_vectors(collection)
        if not vector_validation["is_valid"]:
            issues.append(
                f"CRITICAL: Vectors have zero dimensions! "
                f"This means the embedding model failed during indexing. "
                f"Run: qdrant_reindex(collection='{collection}', path='/path/to/project', mode='full')"
            )

        for file_path, data in file_data.items():
            chunk_count = len(data["chunks"])
            total_lines = max(data["lines"]) if data["lines"] else 0

            # Detect file type from extension
            ext = Path(file_path).suffix.lower()
            file_types[ext] += 1

            # Track chunk types
            for ct in data["chunk_types"]:
                chunk_type_dist[ct] += 1

            # Track indexed_at
            if data["indexed_at"]:
                indexed_at_values.append(data["indexed_at"])

            # Detect issues
            if chunk_count == 0:
                issues.append(f"File '{file_path}' has no chunks")

            if not data["hash"]:
                issues.append(f"File '{file_path}' missing content hash")

            files.append(
                FileInfo(
                    file_path=file_path,
                    chunk_count=chunk_count,
                    content_hash=data["hash"] or "",
                    indexed_at=data["indexed_at"],
                    chunk_types=data["chunk_types"],
                    total_lines=total_lines,
                )
            )

        # Sort files by path
        files.sort(key=lambda f: f.file_path)

        # Calculate indexed_at range
        indexed_at_range: tuple[str | None, str | None] = (None, None)
        if indexed_at_values:
            indexed_at_range = (min(indexed_at_values), max(indexed_at_values))

        diagnostics = CollectionDiagnostics(
            collection_name=collection,
            total_vectors=len(all_points),
            total_files=len(files),
            storage_bytes=info.get("indexed_vectors_count"),  # Approximate
            status=info.get("status", "unknown"),
            file_types=dict(file_types),
            chunk_type_distribution=dict(chunk_type_dist),
            indexed_at_range=indexed_at_range,
            issues=issues,
            files=files,
        )

        return self._diagnostics_to_dict(diagnostics)

    def list_indexed_files(
        self,
        collection: str,
        limit: int = 100,
        offset: int = 0,
        file_type_filter: str | None = None,
    ) -> dict[str, Any]:
        """List all indexed files in a collection.

        Args:
            collection: Collection name
            limit: Maximum number of files to return
            offset: Offset for pagination
            file_type_filter: Optional file extension filter (e.g., '.py')

        Returns:
            Dictionary with file list and pagination info
        """
        self.logger.info(f"Listing indexed files in collection: {collection}")

        if not self.qdrant.collection_exists(collection):
            return {
                "error": f"Collection '{collection}' does not exist",
                "collection": collection,
            }

        # Get all points
        all_points = self.qdrant.get_all_points(collection)

        # Group by file
        file_map: dict[str, dict[str, Any]] = {}
        for point in all_points:
            payload = point.get("payload", {})
            file_path = payload.get("file_path", "")
            if not file_path:
                continue

            if file_path not in file_map:
                file_map[file_path] = {
                    "file_path": file_path,
                    "chunk_count": 0,
                    "content_hash": payload.get("content_hash", ""),
                    "indexed_at": payload.get("indexed_at"),
                    "chunk_types": [],
                    "file_type": self._get_file_type(file_path),
                    "extension": Path(file_path).suffix.lower(),
                }

            file_map[file_path]["chunk_count"] += 1
            chunk_type = payload.get("type", "unknown")
            if chunk_type not in file_map[file_path]["chunk_types"]:
                file_map[file_path]["chunk_types"].append(chunk_type)

        # Convert to list and sort
        all_files = sorted(file_map.values(), key=lambda f: f["file_path"])

        # Apply filter (file_type_filter is extension like ".py")
        if file_type_filter:
            all_files = [f for f in all_files if f["extension"] == file_type_filter]

        # Paginate
        total = len(all_files)
        paginated = all_files[offset : offset + limit]

        return {
            "collection": collection,
            "total_files": total,
            "returned": len(paginated),
            "offset": offset,
            "limit": limit,
            "files": paginated,
        }

    def diff_collection(self, collection: str, repo_path: str) -> dict[str, Any]:
        """Compare Qdrant collection with filesystem.

        Finds:
        - orphans: vectors without corresponding files
        - missing: files without vectors
        - modified: files whose content hash changed

        Args:
            collection: Collection name
            repo_path: Repository path to compare against

        Returns:
            Dictionary with diff results
        """
        self.logger.info(f"Diffing collection '{collection}' with path '{repo_path}'")

        if not self.qdrant.collection_exists(collection):
            return {
                "error": f"Collection '{collection}' does not exist",
                "collection": collection,
            }

        repo = Path(repo_path)
        if not repo.exists():
            return {
                "error": f"Repository path does not exist: {repo_path}",
                "collection": collection,
            }

        # Get all points and group by file
        all_points = self.qdrant.get_all_points(collection)
        indexed_files: dict[str, dict[str, Any]] = {}

        for point in all_points:
            payload = point.get("payload", {})
            file_path = payload.get("file_path", "")
            if not file_path:
                continue

            if file_path not in indexed_files:
                indexed_files[file_path] = {
                    "file_path": file_path,
                    "content_hash": payload.get("content_hash", ""),
                    "chunk_count": 0,
                }
            indexed_files[file_path]["chunk_count"] += 1

        # Find all source files in repo
        source_files = self._find_source_files(repo)
        source_paths = {str(p.relative_to(repo)) for p in source_files}

        # Find indexed paths - try to make them relative to repo
        indexed_paths: dict[str, str] = {}  # relative_path -> original_path
        for indexed_path in indexed_files.keys():
            try:
                # Try to make it relative to repo
                rel_path = Path(indexed_path).relative_to(repo)
                indexed_paths[str(rel_path)] = indexed_path
            except ValueError:
                # Already relative or not under repo - use as-is
                indexed_paths[indexed_path] = indexed_path

        # Calculate diff
        orphans: list[dict[str, Any]] = []
        for indexed_path in indexed_files:
            indexed_abs = Path(indexed_path)
            # Check if file exists - try original path first, then relative to repo
            if not indexed_abs.exists():
                # Try relative path
                try:
                    rel_check = repo / indexed_path
                    if not rel_check.exists():
                        orphans.append(
                            {
                                "file_path": indexed_path,
                                "chunk_count": indexed_files[indexed_path]["chunk_count"],
                                "reason": "file_not_found",
                            }
                        )
                        continue
                    else:
                        # Use the relative path for future operations
                        indexed_abs = rel_check
                except (ValueError, OSError):
                    orphans.append(
                        {
                            "file_path": indexed_path,
                            "chunk_count": indexed_files[indexed_path]["chunk_count"],
                            "reason": "file_not_found",
                        }
                    )
                    continue

        missing: list[dict[str, Any]] = []
        for source_path in source_paths:
            if source_path not in indexed_paths:
                file_abs = repo / source_path
                missing.append(
                    {
                        "file_path": source_path,
                        "reason": "not_indexed",
                        "size_bytes": file_abs.stat().st_size if file_abs.exists() else 0,
                    }
                )

        modified: list[dict[str, Any]] = []
        for rel_path, original_path in indexed_paths.items():
            if rel_path not in source_paths:
                continue

            indexed_info = indexed_files[original_path]
            indexed_hash = indexed_info.get("content_hash", "")

            if not indexed_hash:
                continue

            file_abs = repo / rel_path
            if not file_abs.exists():
                continue

            # Compute current hash
            current_hash = self._compute_hash(file_abs)

            if current_hash != indexed_hash:
                modified.append(
                    {
                        "file_path": rel_path,
                        "stored_hash": indexed_hash,
                        "current_hash": current_hash,
                        "chunk_count": indexed_info.get("chunk_count", 0),
                    }
                )

        return {
            "collection": collection,
            "repo_path": str(repo),
            "summary": {
                "total_indexed": len(indexed_paths),
                "total_files_in_repo": len(source_paths),
                "orphans_count": len(orphans),
                "missing_count": len(missing),
                "modified_count": len(modified),
            },
            "orphans": orphans[:100],  # Limit for response size
            "missing": missing[:100],
            "modified": modified[:100],
        }

    def _get_file_type(self, file_path: str) -> str:
        """Get file type from extension."""
        ext = Path(file_path).suffix.lower()
        type_map = {
            ".py": "python",
            ".go": "go",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".cs": "csharp",
            ".md": "markdown",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "header",
            ".hpp": "header",
        }
        return type_map.get(ext, "other")

    def _find_source_files(self, repo: Path) -> list[Path]:
        """Find all source files in repository."""
        patterns = [
            "*.py",
            "*.go",
            "*.js",
            "*.ts",
            "*.java",
            "*.cs",
            "*.md",
            "*.rs",
            "*.cpp",
            "*.c",
        ]
        files = []
        for pattern in patterns:
            files.extend(repo.rglob(pattern))
        return [f for f in files if f.is_file()]

    def _compute_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file content."""
        if not file_path.exists():
            return ""
        content = file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def _diagnostics_to_dict(self, diag: CollectionDiagnostics) -> dict[str, Any]:
        """Convert diagnostics dataclass to dictionary."""
        return {
            "collection": diag.collection_name,
            "total_vectors": diag.total_vectors,
            "total_files": diag.total_files,
            "storage_bytes": diag.storage_bytes,
            "status": diag.status,
            "file_types": diag.file_types,
            "chunk_type_distribution": diag.chunk_type_distribution,
            "indexed_at_range": {
                "oldest": diag.indexed_at_range[0],
                "newest": diag.indexed_at_range[1],
            },
            "issues": diag.issues,
            "files": [
                {
                    "file_path": f.file_path,
                    "chunk_count": f.chunk_count,
                    "content_hash": f.content_hash,
                    "indexed_at": f.indexed_at,
                    "chunk_types": f.chunk_types,
                    "total_lines": f.total_lines,
                }
                for f in diag.files
            ],
        }
