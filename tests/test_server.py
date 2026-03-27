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

"""Tests for MCP server."""

from unittest.mock import Mock, patch

import pytest

from qmcp.server import (
    qdrant_get_status,
    qdrant_list_collections,
    qdrant_search,
)


class TestMcpServer:
    """Tests for MCP server tools."""

    @pytest.mark.asyncio
    async def test_qdrant_search(self):
        """Test search tool."""
        with patch("qmcp.server.get_qdrant_client") as mock_get_client:
            mock_client = Mock()
            mock_client.search.return_value = [
                {"score": 0.9, "file_path": "test.py", "content": "def foo(): pass"}
            ]
            mock_get_client.return_value = mock_client

            result = await qdrant_search(query="test function")

            assert len(result) == 1
            assert result[0]["score"] == 0.9

    @pytest.mark.asyncio
    async def test_list_collections(self):
        """Test list collections tool."""
        with patch("qmcp.server.get_qdrant_client") as mock_get_client:
            mock_client = Mock()
            mock_client.get_collections.return_value = ["code", "docs"]
            mock_get_client.return_value = mock_client

            result = await qdrant_list_collections()

            assert result == ["code", "docs"]

    @pytest.mark.asyncio
    async def test_get_status_healthy(self):
        """Test status when connected."""
        with patch("qmcp.server.get_qdrant_client") as mock_get_client:
            mock_client = Mock()
            mock_client.is_connected = True
            mock_client.get_collections.return_value = ["code"]
            mock_client.get_collection_info.return_value = {
                "points_count": 100,
                "vectors_count": 100,
                "status": "green",
            }
            mock_get_client.return_value = mock_client

            # Mock watcher
            with patch("qmcp.server._watcher", None):
                with patch("qmcp.server._watch_paths", []):
                    result = await qdrant_get_status()

            assert result["status"] == "healthy"
            assert result["qdrant_connected"] is True
