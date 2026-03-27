"""Cleanup module for removing stale vectors from Qdrant."""

import hashlib
from pathlib import Path
from typing import Any

from .client import QdrantClientWrapper
from .logging_config import get_logger


class CleanupManager:
    """Manages cleanup of stale vectors in Qdrant."""

    def __init__(self, qdrant_client: QdrantClientWrapper):
        self.qdrant = qdrant_client
        self.logger = get_logger(f"{__name__}.CleanupManager")

    def cleanup(
        self,
        collection: str,
        repo_path: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Clean up stale vectors.

        Compares files in the repository with vectors in Qdrant
        and removes vectors for files that no longer exist or have changed.

        Args:
            collection: Collection to clean
            repo_path: Path to the repository
            dry_run: If True, only report what would be deleted

        Returns:
            Cleanup results with counts
        """
        self.logger.info(f"Starting cleanup for collection '{collection}' (dry_run={dry_run})")

        # Get current files from filesystem
        current_files = self._get_current_files(repo_path)
        self.logger.debug(f"Found {len(current_files)} files in repository")

        current_hashes = {path: self._compute_hash(Path(path)) for path in current_files}

        # Get all points from Qdrant
        all_points = self.qdrant.get_all_points(collection)
        self.logger.debug(f"Found {len(all_points)} points in collection")

        # Categorize points
        to_delete = []
        to_update = []

        for point in all_points:
            payload = point.get("payload", {})
            file_path = payload.get("file_path", "")

            if not file_path:
                to_delete.append(point["id"])
                continue

            # File no longer exists
            if file_path not in current_files:
                to_delete.append(point["id"])
                continue

            # File has changed
            stored_hash = payload.get("content_hash", "")
            current_hash = current_hashes.get(file_path, "")

            if stored_hash != current_hash:
                to_update.append(file_path)

        if not dry_run:
            # Delete stale points
            if to_delete:
                self.qdrant.delete_points(collection, to_delete)

        self.logger.info(
            f"Cleanup complete: {len(to_delete)} to delete, "
            f"{len(to_update)} to update, {len(all_points) - len(to_delete)} kept"
        )

        return {
            "dry_run": dry_run,
            "total_points": len(all_points),
            "files_in_repo": len(current_files),
            "to_delete": len(to_delete),
            "to_update": len(to_update),
            "kept": len(all_points) - len(to_delete),
            "deleted_ids": to_delete if dry_run else [],
        }

    def _get_current_files(self, repo_path: str) -> set[str]:
        """Get all code files from repository."""
        path = Path(repo_path)
        if not path.exists():
            return set()

        files = set()
        extensions = [".py", ".go", ".js", ".ts", ".java", ".cs", ".md"]

        for ext in extensions:
            for file_path in path.rglob(f"*{ext}"):
                if file_path.is_file() and not self._should_ignore(file_path):
                    files.add(str(file_path))

        return files

    def _should_ignore(self, file_path: Path) -> bool:
        """Check if file should be ignored."""
        path_str = str(file_path)

        ignore_patterns = [
            "__pycache__",
            ".git",
            ".pytest_cache",
            "node_modules",
            ".venv",
            "venv",
            ".mypy_cache",
            ".ruff_cache",
            ".idea",
            ".vscode",
        ]

        for pattern in ignore_patterns:
            if pattern in path_str:
                return True

        # Ignore hidden files
        if file_path.name.startswith("."):
            return True

        return False

    def _compute_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file content."""
        try:
            content = file_path.read_bytes()
            return hashlib.sha256(content).hexdigest()
        except (OSError, UnicodeDecodeError):
            return ""
