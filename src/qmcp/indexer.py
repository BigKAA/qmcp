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

"""Code indexer for qmcp."""

import hashlib
import time
import uuid
from pathlib import Path
from typing import Any

import pathspec

from .client import QdrantClientWrapper
from .logging_config import get_logger
from .parser import find_parser


class Indexer:
    """Indexes code files into Qdrant vector database."""

    DEFAULT_PATTERNS = [
        "*.py",
        "*.go",
        "*.js",
        "*.ts",
        "*.java",
        "*.cs",
        "*.md",
    ]

    def __init__(
        self,
        qdrant_client: QdrantClientWrapper,
        batch_size: int = 50,
    ):
        self.qdrant = qdrant_client
        self.batch_size = batch_size
        self.logger = get_logger(f"{__name__}.Indexer")

    def index_directory(
        self,
        path: str,
        collection: str = "code",
        patterns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Index all files in a directory.

        Args:
            path: Directory path to index
            collection: Target collection name
            patterns: File patterns to include

        Returns:
            Indexing results
        """
        self.logger.info(f"Starting indexing of {path} into collection {collection}")
        start_time = time.time()
        path_obj = Path(path)

        if not path_obj.exists():
            self.logger.error(f"Path does not exist: {path}")
            return {
                "files_processed": 0,
                "points_added": 0,
                "error": f"Path does not exist: {path}",
            }

        # Ensure collection exists
        if not self.qdrant.collection_exists(collection):
            self.logger.debug(f"Creating collection {collection}")
            self.qdrant.create_collection(collection)

        # Find all matching files
        files = self._find_files(path_obj, patterns or self.DEFAULT_PATTERNS)
        self.logger.debug(f"Found {len(files)} files to index")

        # Parse and index files
        files_processed = 0
        points_added = 0
        points_updated = 0

        for file_path in files:
            result = self._index_file(file_path, collection)
            if result["status"] == "added":
                points_added += result["points"]
            elif result["status"] == "updated":
                points_updated += result["points"]
            files_processed += 1

        duration = time.time() - start_time
        self.logger.info(
            f"Indexing complete: {files_processed} files, "
            f"{points_added} points added, {points_updated} updated "
            f"in {duration:.2f}s"
        )

        return {
            "files_processed": files_processed,
            "points_added": points_added,
            "points_updated": points_updated,
            "duration_seconds": round(duration, 2),
        }

    def _find_files(self, path: Path, patterns: list[str]) -> list[Path]:
        """Find all files matching patterns, respecting .gitignore.

        Loads .gitignore files from the root directory and all subdirectories,
        following git's behavior where parent .gitignore affects all children.
        """
        # Load all .gitignore files, starting from root and going deeper
        gitignore_lines = []

        # Collect .gitignore files from path up to root
        current = path
        while current != current.parent:
            gitignore_path = current / ".gitignore"
            if gitignore_path.exists():
                try:
                    with open(gitignore_path) as f:
                        lines = f.readlines()
                    # Add lines with directory prefix for nested gitignores
                    rel_path = gitignore_path.parent.relative_to(path).as_posix()
                    if rel_path != ".":
                        # Prepend directory path to patterns in nested gitignores
                        for line in lines:
                            line = line.rstrip("\r\n")
                            if line and not line.startswith("#"):
                                gitignore_lines.append(f"{rel_path}/{line}")
                    else:
                        gitignore_lines.extend(line.rstrip("\r\n") for line in lines)
                except OSError as e:
                    self.logger.warning(f"Failed to read {gitignore_path}: {e}")
            current = current.parent

        # Build pathspec from collected patterns
        if gitignore_lines:
            spec = pathspec.PathSpec.from_lines("gitignore", gitignore_lines)
            self.logger.debug(f"Loaded {len(gitignore_lines)} gitignore patterns")
        else:
            spec = None

        # Find all matching files
        files = []
        for pattern in patterns:
            if pattern.startswith("*."):
                suffix = pattern[1:]
                for f in path.rglob(f"*{suffix}"):
                    rel_path = f.relative_to(path).as_posix()
                    # Filter out gitignored files
                    if spec and spec.match_file(rel_path):
                        self.logger.debug(f"Skipping gitignored file: {rel_path}")
                        continue
                    files.append(f)

        # Remove duplicates and filter to only existing files
        return list(set(f for f in files if f.is_file()))

    def _index_file(self, file_path: Path, collection: str) -> dict[str, Any]:
        """Index a single file."""
        parser = find_parser(file_path)

        if not parser:
            return {"status": "skipped", "points": 0}

        # Parse file
        chunks = parser.parse_file(file_path)
        if not chunks:
            return {"status": "skipped", "points": 0}

        # Get existing file hash
        current_hash = self._compute_file_hash(file_path)

        # Check if file needs updating
        existing_points = self._get_file_points(collection, str(file_path))

        if existing_points:
            existing_hash = existing_points[0].get("payload", {}).get("content_hash", "")
            if existing_hash == current_hash:
                return {"status": "unchanged", "points": 0}

        # Prepare points for upsert
        points = []
        for chunk in chunks:
            point = {
                "id": str(
                    uuid.uuid5(uuid.NAMESPACE_DNS, f"{file_path}:{chunk.name}:{chunk.line_start}")
                ),
                "content": chunk.content,
                "payload": {
                    "file_path": str(file_path),
                    "content_hash": current_hash,
                    "type": chunk.chunk_type,
                    "name": chunk.name,
                    "docstring": chunk.docstring,
                    "line_start": chunk.line_start,
                    "line_end": chunk.line_end,
                },
            }
            points.append(point)

        # Upsert points
        if points:
            self.qdrant.upsert(collection, points, self.batch_size)

        status = "updated" if existing_points else "added"
        return {"status": status, "points": len(points)}

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file content."""
        content = file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def _get_file_points(self, collection: str, file_path: str) -> list[dict]:
        """Get existing points for a file."""
        # This is a simplified version - full implementation would
        # use Qdrant filtering to get points for specific file
        all_points = self.qdrant.get_all_points(collection)
        return [p for p in all_points if p.get("payload", {}).get("file_path") == file_path]

    def full_reindex(
        self,
        path: str,
        collection: str = "code",
        patterns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Perform full reindex - delete and recreate collection.

        Args:
            path: Directory path
            collection: Collection name
            patterns: File patterns

        Returns:
            Indexing results
        """
        # Delete existing collection
        if self.qdrant.collection_exists(collection):
            self.qdrant.delete_collection(collection)

        # Recreate and index
        return self.index_directory(path, collection, patterns)

    def incremental_reindex(
        self,
        path: str,
        collection: str = "code",
        patterns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Perform incremental reindex - only new/changed files.

        This is the same as index_directory since it already checks hashes.
        """
        return self.index_directory(path, collection, patterns)
