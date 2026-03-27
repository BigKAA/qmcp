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

from unittest.mock import Mock

import pytest

from qmcp.client import QdrantClientWrapper
from qmcp.indexer import Indexer


class TestIndexer:
    """Tests for Indexer class."""

    @pytest.fixture
    def mock_client(self):
        """Create mock Qdrant client."""
        client = Mock(spec=QdrantClientWrapper)
        client.collection_exists.return_value = False
        client.create_collection.return_value = None
        client.upsert.return_value = 1
        client.get_all_points.return_value = []
        return client

    def test_indexer_initialization(self, mock_client):
        """Test indexer initialization."""
        indexer = Indexer(mock_client)
        assert indexer.qdrant == mock_client
        assert indexer.batch_size == 50

    def test_indexer_custom_batch_size(self, mock_client):
        """Test indexer with custom batch size."""
        indexer = Indexer(mock_client, batch_size=100)
        assert indexer.batch_size == 100
