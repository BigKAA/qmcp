"""Tests for cleanup module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from qmcp.cleanup import CleanupManager


class TestCleanupManager:
    """Tests for CleanupManager class."""

    @pytest.fixture
    def mock_qdrant_client(self):
        """Create mock Qdrant client."""
        client = Mock()
        client.get_all_points.return_value = []
        client.delete_points.return_value = None
        return client

    @pytest.fixture
    def cleanup_manager(self, mock_qdrant_client):
        """Create CleanupManager instance."""
        return CleanupManager(mock_qdrant_client)

    @pytest.fixture
    def temp_repo(self):
        """Create temporary repository structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)

            # Create directory structure
            (path / "src").mkdir()
            (path / "tests").mkdir()
            (path / "docs").mkdir()
            (path / "__pycache__").mkdir()  # Should be ignored

            # Create files
            (path / "main.py").write_text("def main(): pass")
            (path / "src" / "module.py").write_text("class MyClass: pass")
            (path / "tests" / "test_main.py").write_text("def test_main(): pass")
            (path / "README.md").write_text("# Project")

            # Create hidden file (should be ignored)
            (path / ".hidden.py").write_text("# hidden")

            yield path

    def test_cleanup_manager_initialization(self, cleanup_manager, mock_qdrant_client):
        """Test cleanup manager initializes correctly."""
        assert cleanup_manager.qdrant == mock_qdrant_client

    def test_get_current_files(self, cleanup_manager, temp_repo):
        """Test _get_current_files returns correct files."""
        files = cleanup_manager._get_current_files(str(temp_repo))

        # Should include Python files
        assert any(f.endswith(".py") for f in files)
        # Should include Markdown files
        assert any(f.endswith(".md") for f in files)
        # Should not include __pycache__ files
        assert not any("__pycache__" in f for f in files)
        # Should not include hidden files
        assert not any(Path(f).name.startswith(".") for f in files)

    def test_get_current_files_nonexistent_path(self, cleanup_manager):
        """Test _get_current_files with nonexistent path."""
        files = cleanup_manager._get_current_files("/nonexistent/path")
        assert files == set()

    def test_should_ignore_patterns(self, cleanup_manager):
        """Test _should_ignore correctly identifies ignored patterns."""
        # Should ignore
        assert cleanup_manager._should_ignore(Path("/path/__pycache__/module.py"))
        assert cleanup_manager._should_ignore(Path("/path/.git/config"))
        assert cleanup_manager._should_ignore(Path("/path/node_modules/package.json"))
        assert cleanup_manager._should_ignore(Path("/path/.venv/lib/module.py"))
        assert cleanup_manager._should_ignore(Path("/path/.hidden.py"))
        assert cleanup_manager._should_ignore(Path("/.hidden"))  # Hidden name

        # Should not ignore
        assert not cleanup_manager._should_ignore(Path("/path/module.py"))
        assert not cleanup_manager._should_ignore(Path("/path/main.go"))
        assert not cleanup_manager._should_ignore(Path("/path/src/module.js"))

    def test_compute_hash(self, cleanup_manager, temp_repo):
        """Test _compute_hash generates consistent hashes."""
        file_path = temp_repo / "main.py"
        hash1 = cleanup_manager._compute_hash(file_path)
        hash2 = cleanup_manager._compute_hash(file_path)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_compute_hash_nonexistent_file(self, cleanup_manager):
        """Test _compute_hash with nonexistent file."""
        hash_value = cleanup_manager._compute_hash(Path("/nonexistent/file.py"))
        assert hash_value == ""

    def test_compute_hash_binary_file(self, cleanup_manager, temp_repo):
        """Test _compute_hash handles binary files."""
        binary_file = temp_repo / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03")

        hash_value = cleanup_manager._compute_hash(binary_file)
        # Binary files should be hashed (we need to detect changes to them)
        assert len(hash_value) == 64  # SHA256 hex length

    def test_cleanup_dry_run(self, cleanup_manager, mock_qdrant_client, temp_repo):
        """Test cleanup in dry-run mode."""
        # Setup mock to return some points
        mock_qdrant_client.get_all_points.return_value = [
            {
                "id": "point1",
                "payload": {"file_path": str(temp_repo / "deleted.py"), "content_hash": "abc"},
            },
            {
                "id": "point2",
                "payload": {
                    "file_path": str(temp_repo / "main.py"),
                    "content_hash": cleanup_manager._compute_hash(temp_repo / "main.py"),
                },
            },
        ]

        result = cleanup_manager.cleanup(
            collection="code",
            repo_path=str(temp_repo),
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert result["total_points"] == 2
        assert result["files_in_repo"] >= 2  # Based on temp_repo structure
        assert result["to_delete"] == 1  # deleted.py doesn't exist
        assert result["to_update"] == 0  # main.py unchanged
        assert len(result["deleted_ids"]) == 1
        assert result["deleted_ids"] == ["point1"]

        # Verify delete_points was NOT called in dry run
        mock_qdrant_client.delete_points.assert_not_called()

    def test_cleanup_actual_delete(self, cleanup_manager, mock_qdrant_client, temp_repo):
        """Test cleanup actually deletes points."""
        mock_qdrant_client.get_all_points.return_value = [
            {
                "id": "point1",
                "payload": {"file_path": str(temp_repo / "deleted.py"), "content_hash": "abc"},
            },
        ]

        result = cleanup_manager.cleanup(
            collection="code",
            repo_path=str(temp_repo),
            dry_run=False,
        )

        assert result["dry_run"] is False
        assert result["to_delete"] == 1

        # Verify delete_points WAS called
        mock_qdrant_client.delete_points.assert_called_once_with("code", ["point1"])

    def test_cleanup_handles_missing_file_path(self, cleanup_manager, mock_qdrant_client):
        """Test cleanup handles points with missing file_path."""
        mock_qdrant_client.get_all_points.return_value = [
            {"id": "point1", "payload": {}},  # No file_path
            {
                "id": "point2",
                "payload": {"file_path": "", "content_hash": "abc"},
            },  # Empty file_path
        ]

        result = cleanup_manager.cleanup(
            collection="code",
            repo_path="/some/path",
            dry_run=True,
        )

        assert result["to_delete"] == 2  # Both should be marked for deletion

    def test_cleanup_detects_changed_files(self, cleanup_manager, mock_qdrant_client, temp_repo):
        """Test cleanup detects files that have changed."""
        main_py = temp_repo / "main.py"

        # Point with old hash (file has changed)
        mock_qdrant_client.get_all_points.return_value = [
            {
                "id": "point1",
                "payload": {
                    "file_path": str(main_py),
                    "content_hash": "old_hash_different",
                },
            },
        ]

        result = cleanup_manager.cleanup(
            collection="code",
            repo_path=str(temp_repo),
            dry_run=True,
        )

        assert result["to_update"] == 1  # Should be marked for update

    def test_cleanup_empty_collection(self, cleanup_manager, mock_qdrant_client, temp_repo):
        """Test cleanup with empty collection."""
        mock_qdrant_client.get_all_points.return_value = []

        result = cleanup_manager.cleanup(
            collection="code",
            repo_path=str(temp_repo),
            dry_run=True,
        )

        assert result["total_points"] == 0
        assert result["files_in_repo"] >= 1
        assert result["to_delete"] == 0
        assert result["kept"] == 0
