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

"""Tests for indexer."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from qmcp.client import QdrantClientWrapper
from qmcp.indexer import Indexer


@pytest.fixture
def mock_client():
    """Create mock Qdrant client."""
    client = Mock(spec=QdrantClientWrapper)
    client.collection_exists.return_value = False
    client.create_collection.return_value = None
    client.upsert.return_value = 1
    client.get_file_points.return_value = []
    return client


@pytest.fixture(autouse=True)
def isolated_lock_dir(tmp_path, monkeypatch):
    """Point every test Indexer at a per-test lock directory.

    Keeps single-flight locks out of the developer's ~/.cache and makes
    lock contention deterministic between tests.
    """
    lock_dir = tmp_path / "qmcp-locks"
    monkeypatch.setattr(Indexer, "_resolve_lock_dir", staticmethod(lambda: lock_dir))
    return lock_dir


class TestIndexer:
    """Tests for Indexer class."""

    def test_indexer_initialization(self, mock_client):
        """Test indexer initialization."""
        indexer = Indexer(mock_client)
        assert indexer.qdrant == mock_client
        assert indexer.batch_size == 50

    def test_indexer_custom_batch_size(self, mock_client):
        """Test indexer with custom batch size."""
        indexer = Indexer(mock_client, batch_size=100)
        assert indexer.batch_size == 100

    def test_changed_file_deletes_stale_points(self, mock_client, tmp_path):
        """Changed file removes old chunks before upserting new ones.

        Chunk IDs derive from (file, name, line_start), so a re-sectioned
        markdown file produces different IDs - old points must be deleted
        instead of lingering as duplicates.
        """
        doc = tmp_path / "doc.md"
        doc.write_text(
            "# Title\n\n## Old Section\n\n" + ("text " * 60) + "\n",
            encoding="utf-8",
        )

        # Existing point from the previous (single-chunk) layout
        mock_client.get_file_points.return_value = [
            {"id": "old-point-id", "payload": {"file_path": str(doc), "content_hash": "a" * 64}}
        ]

        indexer = Indexer(mock_client)
        result = indexer._index_file(doc, collection="docs")

        assert result["status"] == "updated"
        assert result["points"] >= 1
        mock_client.delete_points.assert_called_once_with("docs", ["old-point-id"])
        mock_client.upsert.assert_called_once()

    def test_unchanged_file_keeps_points(self, mock_client, tmp_path):
        """Unchanged file (same hash) is skipped without deletes or upserts."""
        import hashlib

        doc = tmp_path / "doc.md"
        doc.write_text("# Title\n\nbody\n", encoding="utf-8")

        current_hash = hashlib.sha256(doc.read_bytes()).hexdigest()
        mock_client.get_file_points.return_value = [
            {"id": "p1", "payload": {"file_path": str(doc), "content_hash": current_hash}}
        ]

        indexer = Indexer(mock_client)
        result = indexer._index_file(doc, collection="docs")

        assert result["status"] == "unchanged"
        mock_client.delete_points.assert_not_called()
        mock_client.upsert.assert_not_called()


class TestSingleFileIndexing:
    """Tests for watch-event driven single-file indexing."""

    def test_index_file_creates_collection_and_indexes(self, mock_client, tmp_path):
        """index_file ensures the collection exists and indexes just that file."""
        doc = tmp_path / "doc.md"
        doc.write_text("# Title\n\n" + ("text " * 60) + "\n", encoding="utf-8")

        indexer = Indexer(mock_client)
        result = indexer.index_file(str(doc), collection="docs")

        assert result["status"] == "added"
        assert result["points"] >= 1
        mock_client.collection_exists.assert_called_once_with("docs")
        mock_client.create_collection.assert_called_once_with("docs")
        mock_client.upsert.assert_called_once()

    def test_index_file_missing_file_skipped(self, mock_client, tmp_path):
        """Watch targets deleted between event and processing are skipped."""
        indexer = Indexer(mock_client)
        result = indexer.index_file(str(tmp_path / "gone.md"), collection="docs")

        assert result == {"status": "skipped", "points": 0}
        mock_client.create_collection.assert_not_called()
        mock_client.upsert.assert_not_called()

    def test_delete_file_removes_points(self, mock_client, tmp_path):
        """delete_file removes all of a deleted file's points by path filter."""
        gone = tmp_path / "gone.md"

        mock_client.get_file_points.return_value = [
            {"id": "p1", "payload": {"file_path": str(gone)}},
            {"id": "p2", "payload": {"file_path": str(gone)}},
        ]

        indexer = Indexer(mock_client)
        result = indexer.delete_file(str(gone), collection="docs")

        assert result == {"status": "deleted", "points": 2}
        mock_client.delete_points_by_path.assert_called_once_with("docs", str(gone))

    def test_delete_file_skips_recreated_file(self, mock_client, tmp_path):
        """A file that reappeared must keep its points - a create/modify
        event will reindex it; deleting now would drop a valid index."""
        back = tmp_path / "back.md"
        back.write_text("# back\n", encoding="utf-8")

        indexer = Indexer(mock_client)
        result = indexer.delete_file(str(back), collection="docs")

        assert result["status"] == "skipped"
        mock_client.delete_points_by_path.assert_not_called()

    def test_delete_file_not_indexed(self, mock_client, tmp_path):
        """Deleting a file that never had points is a no-op, not an error."""
        never = tmp_path / "never.md"

        indexer = Indexer(mock_client)
        result = indexer.delete_file(str(never), collection="docs")

        assert result == {"status": "not_indexed", "points": 0}
        mock_client.delete_points_by_path.assert_not_called()

    def test_locked_file_skipped_by_second_process(self, mock_client, tmp_path):
        """While one process holds the single-flight lock, others skip the file.

        Simulates a second qmcp server watching the same tree: the lock file
        is held externally, so this indexer must not embed or upsert.
        """
        fcntl = pytest.importorskip("fcntl")
        from qmcp.locking import _lock_file_path

        doc = tmp_path / "doc.md"
        doc.write_text("# Title\n\n" + ("text " * 60) + "\n", encoding="utf-8")

        indexer = Indexer(mock_client)
        lock_dir = indexer._lock_dir
        lock_file = _lock_file_path(lock_dir, f"docs:{doc}")
        lock_dir.mkdir(parents=True, exist_ok=True)

        with open(lock_file, "w") as holder:
            fcntl.flock(holder, fcntl.LOCK_EX)
            try:
                result = indexer._index_file(doc, collection="docs")
            finally:
                fcntl.flock(holder, fcntl.LOCK_UN)

        assert result["status"] == "skipped_locked"
        mock_client.delete_points.assert_not_called()
        mock_client.upsert.assert_not_called()

    def test_lock_recheck_skips_file_uploaded_by_winner(self, mock_client, tmp_path):
        """Under the lock the hash is re-checked - winner's upload ends the race."""
        import hashlib

        doc = tmp_path / "doc.md"
        doc.write_text("# Title\n\n" + ("text " * 60) + "\n", encoding="utf-8")

        current_hash = hashlib.sha256(doc.read_bytes()).hexdigest()
        # First check (before lock): stale hash; second check (under lock):
        # the other process already uploaded the fresh content.
        mock_client.get_file_points.side_effect = [
            [{"id": "p1", "payload": {"file_path": str(doc), "content_hash": "old"}}],
            [{"id": "p1", "payload": {"file_path": str(doc), "content_hash": current_hash}}],
        ]

        indexer = Indexer(mock_client)
        result = indexer._index_file(doc, collection="docs")

        assert result["status"] == "unchanged"
        mock_client.delete_points.assert_not_called()
        mock_client.upsert.assert_not_called()


class TestGitignore:
    """Tests for .gitignore support."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary directory structure for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create directory structure
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "node_modules").mkdir()
            (root / "build").mkdir()

            # Create files
            (root / "src" / "main.py").write_text("# main")
            (root / "tests" / "test_main.py").write_text("# test")
            (root / "node_modules" / "dep.py").write_text("# dep")
            (root / "build" / "output.py").write_text("# output")
            (root / "config.py").write_text("# config")

            # Create .gitignore
            (root / ".gitignore").write_text("node_modules/\nbuild/\n*.pyc\n")

            yield root

    def test_find_files_respects_gitignore(self, temp_repo, mock_client):
        """Test that _find_files filters out gitignored files."""
        indexer = Indexer(mock_client)

        files = indexer._find_files(temp_repo, ["*.py"])
        file_names = [f.name for f in files]

        # Should find config.py, main.py, test_main.py
        # Should NOT find node_modules/dep.py or build/output.py
        assert "config.py" in file_names
        assert "main.py" in file_names
        assert "test_main.py" in file_names
        assert "dep.py" not in file_names
        assert "output.py" not in file_names

    def test_find_files_without_gitignore(self, temp_repo, mock_client):
        """Test that _find_files works without .gitignore."""
        (temp_repo / ".gitignore").unlink()

        indexer = Indexer(mock_client)
        files = indexer._find_files(temp_repo, ["*.py"])
        file_names = [f.name for f in files]

        # Should find all .py files including in node_modules and build
        assert "config.py" in file_names
        assert "main.py" in file_names
        assert "test_main.py" in file_names
        assert "dep.py" in file_names
        assert "output.py" in file_names
