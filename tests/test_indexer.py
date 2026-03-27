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
    client.get_all_points.return_value = []
    return client


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
