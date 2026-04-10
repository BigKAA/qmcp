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

from unittest.mock import AsyncMock, Mock, patch

import pytest

import qmcp.server as server_module
from qmcp.server import (
    app_lifespan,
    qdrant_get_status,
    qdrant_list_collections,
    qdrant_search,
    qdrant_watch_ensure,
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
            assert "configured_watch_paths" in result

    @pytest.mark.asyncio
    async def test_watch_ensure_merges_configured_and_workspace_paths(self, tmp_path):
        """Test watch ensure preserves configured paths for global MCP usage."""
        configured_path = tmp_path / "configured"
        workspace_path = tmp_path / "workspace"
        configured_path.mkdir()
        workspace_path.mkdir()

        mock_watcher = Mock()
        mock_watcher.start = AsyncMock()
        mock_watcher.stop = AsyncMock()
        mock_watcher.is_running = True

        with patch.object(server_module.settings, "watch_paths", [str(configured_path)]):
            with patch("qmcp.server.AsyncWatcher", return_value=mock_watcher):
                with patch("qmcp.server._watcher", None):
                    with patch("qmcp.server._watch_paths", []):
                        result = await qdrant_watch_ensure(paths=[str(workspace_path)])

        expected_paths = [str(configured_path.resolve()), str(workspace_path.resolve())]

        assert result["status"] == "started"
        assert result["watching"] == expected_paths
        assert result["skipped_paths"] == []

    @pytest.mark.asyncio
    async def test_app_lifespan_starts_and_stops_watcher(self):
        """Test watcher lifecycle is managed during MCP startup and shutdown."""
        with patch(
            "qmcp.server._ensure_watcher_started", new=AsyncMock(return_value={"status": "started"})
        ) as mock_ensure:
            with patch("qmcp.server._stop_watcher", new=AsyncMock()) as mock_stop:
                async with app_lifespan(Mock()):
                    pass

        mock_ensure.assert_awaited_once()
        mock_stop.assert_awaited_once()
