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

"""Tests for diagnostics module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from qmcp.diagnostics import DiagnosticsManager, FileInfo


class TestDiagnosticsManager:
    """Tests for DiagnosticsManager class."""

    @pytest.fixture
    def mock_qdrant_client(self):
        """Create mock Qdrant client."""
        client = Mock()
        client.collection_exists.return_value = True
        client.get_collection_info.return_value = {
            "name": "test_collection",
            "vectors_count": 100,
            "points_count": 50,
            "status": "green",
        }
        client.validate_collection_vectors.return_value = {
            "collection": "test_collection",
            "points_count": 50,
            "vector_size": 384,
            "is_valid": True,
            "warning": None,
        }
        return client

    @pytest.fixture
    def diagnostics_manager(self, mock_qdrant_client):
        """Create DiagnosticsManager instance."""
        return DiagnosticsManager(mock_qdrant_client)

    @pytest.fixture
    def temp_repo(self):
        """Create temporary repository structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)

            # Create directory structure
            (path / "src").mkdir()
            (path / "tests").mkdir()

            # Create files with content
            (path / "main.py").write_text("def main():\n    pass")
            (path / "src" / "module.py").write_text("class MyClass:\n    pass")
            (path / "tests" / "test_main.py").write_text("def test_main():\n    pass")
            (path / "README.md").write_text("# Project Documentation")

            yield path

    def test_diagnostics_manager_initialization(self, diagnostics_manager, mock_qdrant_client):
        """Test diagnostics manager initializes correctly."""
        assert diagnostics_manager.qdrant == mock_qdrant_client

    def test_get_file_type(self, diagnostics_manager):
        """Test _get_file_type correctly identifies file types."""
        assert diagnostics_manager._get_file_type("module.py") == "python"
        assert diagnostics_manager._get_file_type("main.go") == "go"
        assert diagnostics_manager._get_file_type("index.js") == "javascript"
        assert diagnostics_manager._get_file_type("types.ts") == "typescript"
        assert diagnostics_manager._get_file_type("Main.java") == "java"
        assert diagnostics_manager._get_file_type("Program.cs") == "csharp"
        assert diagnostics_manager._get_file_type("README.md") == "markdown"
        assert diagnostics_manager._get_file_type("lib.rs") == "rust"
        assert diagnostics_manager._get_file_type("main.cpp") == "cpp"
        assert diagnostics_manager._get_file_type("header.h") == "header"
        assert diagnostics_manager._get_file_type("unknown.xyz") == "other"

    def test_find_source_files(self, diagnostics_manager, temp_repo):
        """Test _find_source_files finds correct files."""
        files = diagnostics_manager._find_source_files(temp_repo)

        # Should find Python and Markdown files
        extensions = {f.suffix for f in files}
        assert ".py" in extensions
        assert ".md" in extensions

        # Should not find non-source files
        assert not any("__pycache__" in str(f) for f in files)

    def test_compute_hash(self, diagnostics_manager, temp_repo):
        """Test _compute_hash generates consistent hashes."""
        main_py = temp_repo / "main.py"
        hash1 = diagnostics_manager._compute_hash(main_py)
        hash2 = diagnostics_manager._compute_hash(main_py)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_compute_hash_nonexistent_file(self, diagnostics_manager):
        """Test _compute_hash with nonexistent file."""
        hash_value = diagnostics_manager._compute_hash(Path("/nonexistent/file.py"))
        assert hash_value == ""

    def test_diagnose_collection_nonexistent(self, diagnostics_manager, mock_qdrant_client):
        """Test diagnose_collection handles nonexistent collection."""
        mock_qdrant_client.collection_exists.return_value = False

        result = diagnostics_manager.diagnose_collection("nonexistent")

        assert "error" in result
        assert "does not exist" in result["error"]

    def test_diagnose_collection_empty(self, diagnostics_manager, mock_qdrant_client):
        """Test diagnose_collection with empty collection."""
        mock_qdrant_client.get_all_points.return_value = []

        result = diagnostics_manager.diagnose_collection("empty_collection")

        assert result["collection"] == "empty_collection"
        assert result["total_vectors"] == 0
        assert result["total_files"] == 0
        assert result["file_types"] == {}
        assert result["chunk_type_distribution"] == {}

    def test_diagnose_collection_with_data(
        self, diagnostics_manager, mock_qdrant_client, temp_repo
    ):
        """Test diagnose_collection with populated collection."""
        main_py = temp_repo / "main.py"
        hash_value = diagnostics_manager._compute_hash(main_py)

        mock_qdrant_client.get_all_points.return_value = [
            {
                "id": "point1",
                "payload": {
                    "file_path": str(main_py),
                    "content": "def main():",
                    "content_hash": hash_value,
                    "type": "function",
                    "name": "main",
                    "docstring": None,
                    "line_start": 1,
                    "line_end": 2,
                    "indexed_at": "2026-03-27T10:00:00",
                },
            },
            {
                "id": "point2",
                "payload": {
                    "file_path": str(main_py),
                    "content": "    pass",
                    "content_hash": hash_value,
                    "type": "statement",
                    "name": None,
                    "docstring": None,
                    "line_start": 2,
                    "line_end": 2,
                    "indexed_at": "2026-03-27T10:00:00",
                },
            },
        ]

        result = diagnostics_manager.diagnose_collection("test_collection")

        assert result["collection"] == "test_collection"
        assert result["total_vectors"] == 2
        assert result["total_files"] == 1
        assert result["file_types"] == {".py": 1}
        assert result["chunk_type_distribution"] == {"function": 1, "statement": 1}
        assert len(result["files"]) == 1
        assert result["files"][0]["file_path"] == str(main_py)
        assert result["files"][0]["chunk_count"] == 2

    def test_diagnose_collection_detects_missing_file_path(
        self, diagnostics_manager, mock_qdrant_client
    ):
        """Test diagnose_collection handles points without file_path."""
        mock_qdrant_client.get_all_points.return_value = [
            {"id": "point1", "payload": {}},  # No file_path
            {"id": "point2", "payload": {"file_path": ""}},  # Empty file_path
        ]

        result = diagnostics_manager.diagnose_collection("test_collection")

        # Should not crash and should report 0 files
        assert result["total_files"] == 0

    def test_list_indexed_files_nonexistent(self, diagnostics_manager, mock_qdrant_client):
        """Test list_indexed_files handles nonexistent collection."""
        mock_qdrant_client.collection_exists.return_value = False

        result = diagnostics_manager.list_indexed_files("nonexistent")

        assert "error" in result
        assert "does not exist" in result["error"]

    def test_list_indexed_files_empty(self, diagnostics_manager, mock_qdrant_client):
        """Test list_indexed_files with empty collection."""
        mock_qdrant_client.get_all_points.return_value = []

        result = diagnostics_manager.list_indexed_files("empty_collection")

        assert result["collection"] == "empty_collection"
        assert result["total_files"] == 0
        assert result["returned"] == 0
        assert result["files"] == []

    def test_list_indexed_files_with_pagination(
        self, diagnostics_manager, mock_qdrant_client, temp_repo
    ):
        """Test list_indexed_files pagination."""
        main_py = temp_repo / "main.py"
        module_py = temp_repo / "src" / "module.py"
        hash_value = diagnostics_manager._compute_hash(main_py)

        mock_qdrant_client.get_all_points.return_value = [
            {
                "id": "point1",
                "payload": {
                    "file_path": str(main_py),
                    "content_hash": hash_value,
                    "type": "function",
                    "indexed_at": "2026-03-27T10:00:00",
                },
            },
            {
                "id": "point2",
                "payload": {
                    "file_path": str(module_py),
                    "content_hash": hash_value,
                    "type": "class",
                    "indexed_at": "2026-03-27T10:00:00",
                },
            },
        ]

        # Test limit
        result = diagnostics_manager.list_indexed_files("test", limit=1)
        assert result["total_files"] == 2
        assert result["returned"] == 1
        assert result["limit"] == 1

        # Test offset
        result = diagnostics_manager.list_indexed_files("test", offset=1)
        assert result["offset"] == 1
        assert result["returned"] == 1

    def test_list_indexed_files_filter_by_type(
        self, diagnostics_manager, mock_qdrant_client, temp_repo
    ):
        """Test list_indexed_files with file type filter."""
        main_py = temp_repo / "main.py"
        readme_md = temp_repo / "README.md"
        hash_value = diagnostics_manager._compute_hash(main_py)

        mock_qdrant_client.get_all_points.return_value = [
            {
                "id": "point1",
                "payload": {"file_path": str(main_py), "content_hash": hash_value},
            },
            {
                "id": "point2",
                "payload": {"file_path": str(readme_md), "content_hash": hash_value},
            },
        ]

        result = diagnostics_manager.list_indexed_files("test", file_type_filter=".py")

        assert result["total_files"] == 1
        assert result["files"][0]["file_type"] == "python"

    def test_diff_collection_nonexistent(self, diagnostics_manager, mock_qdrant_client):
        """Test diff_collection handles nonexistent collection."""
        mock_qdrant_client.collection_exists.return_value = False

        result = diagnostics_manager.diff_collection("nonexistent", "/some/path")

        assert "error" in result
        assert "does not exist" in result["error"]

    def test_diff_collection_nonexistent_repo_path(self, diagnostics_manager, mock_qdrant_client):
        """Test diff_collection handles nonexistent repo path."""
        result = diagnostics_manager.diff_collection("test", "/nonexistent/repo")

        assert "error" in result
        assert "does not exist" in result["error"]

    def test_diff_collection_detects_orphans(
        self, diagnostics_manager, mock_qdrant_client, temp_repo
    ):
        """Test diff_collection detects orphaned vectors."""
        mock_qdrant_client.get_all_points.return_value = [
            {
                "id": "point1",
                "payload": {
                    "file_path": str(temp_repo / "deleted.py"),
                    "content_hash": "abc123",
                    "chunk_count": 1,
                },
            },
        ]

        result = diagnostics_manager.diff_collection("test", str(temp_repo))

        assert result["summary"]["orphans_count"] == 1
        assert len(result["orphans"]) == 1
        assert "deleted.py" in result["orphans"][0]["file_path"]

    def test_diff_collection_detects_missing(
        self, diagnostics_manager, mock_qdrant_client, temp_repo
    ):
        """Test diff_collection detects missing files."""
        # Indexed file exists
        main_py = temp_repo / "main.py"
        hash_value = diagnostics_manager._compute_hash(main_py)

        # But collection is empty
        mock_qdrant_client.get_all_points.return_value = []

        result = diagnostics_manager.diff_collection("test", str(temp_repo))

        assert result["summary"]["missing_count"] >= 1
        assert any(f["file_path"] == "main.py" for f in result["missing"])

    def test_diff_collection_detects_modified(
        self, diagnostics_manager, mock_qdrant_client, temp_repo
    ):
        """Test diff_collection detects modified files."""
        main_py = temp_repo / "main.py"
        original_hash = diagnostics_manager._compute_hash(main_py)

        # Add file to collection with current hash
        mock_qdrant_client.get_all_points.return_value = [
            {
                "id": "point1",
                "payload": {
                    "file_path": str(main_py),
                    "content_hash": original_hash,
                    "chunk_count": 1,
                },
            },
        ]

        # Modify the file
        main_py.write_text("def main():\n    print('changed')\n")

        result = diagnostics_manager.diff_collection("test", str(temp_repo))

        assert result["summary"]["modified_count"] == 1
        assert len(result["modified"]) == 1
        # file_path is returned as relative to repo
        assert result["modified"][0]["file_path"] == "main.py"

    def test_diff_collection_summary(self, diagnostics_manager, mock_qdrant_client, temp_repo):
        """Test diff_collection summary is correct."""
        main_py = temp_repo / "main.py"
        hash_value = diagnostics_manager._compute_hash(main_py)

        mock_qdrant_client.get_all_points.return_value = [
            {
                "id": "point1",
                "payload": {
                    "file_path": str(main_py),
                    "content_hash": hash_value,
                    "chunk_count": 1,
                },
            },
        ]

        result = diagnostics_manager.diff_collection("test", str(temp_repo))

        assert "summary" in result
        assert result["summary"]["total_indexed"] == 1
        assert result["summary"]["total_files_in_repo"] >= 1
        # No orphans (file exists), no missing (file indexed), no modified (hash matches)
        assert result["summary"]["orphans_count"] == 0
        assert result["summary"]["modified_count"] == 0
