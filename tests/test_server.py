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
from qmcp.config import Settings
from qmcp.server import (
    app_lifespan,
    mcp,
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

    def test_server_identity_includes_version(self):
        """MCP initialize response must report the package version."""
        from qmcp import __version__

        assert mcp.name == "Qdrant Vector Search"
        assert mcp.version == __version__

    @pytest.mark.asyncio
    async def test_watch_event_indexes_single_file(self, tmp_path):
        """Watch events index exactly the changed file, never its directory.

        Indexing the parent directory re-hashed every sibling on each save,
        multiplied by every watching qmcp process.
        """
        changed = tmp_path / "module.py"
        changed.write_text("x = 1\n")

        with patch("qmcp.server.get_indexer") as mock_get_indexer:
            mock_indexer = Mock()
            mock_get_indexer.return_value = mock_indexer

            await server_module._handle_watch_change(str(changed), "modified")

        mock_indexer.index_file.assert_called_once_with(path=str(changed), collection="code")
        mock_indexer.index_directory.assert_not_called()

    @pytest.mark.asyncio
    async def test_watch_event_routes_markdown_to_docs(self, tmp_path):
        """Markdown changes go to the docs collection, code to code."""
        doc = tmp_path / "README.md"
        doc.write_text("# Title\n\nbody\n")

        with patch("qmcp.server.get_indexer") as mock_get_indexer:
            mock_indexer = Mock()
            mock_get_indexer.return_value = mock_indexer

            await server_module._handle_watch_change(str(doc), "modified")

        mock_indexer.index_file.assert_called_once_with(path=str(doc), collection="docs")

    @pytest.mark.asyncio
    async def test_watch_deleted_event_removes_points(self, tmp_path):
        """Deleted watch events clean up the file's points instead of reindexing."""
        gone = tmp_path / "gone.py"

        with patch("qmcp.server.get_indexer") as mock_get_indexer:
            mock_indexer = Mock()
            mock_get_indexer.return_value = mock_indexer

            await server_module._handle_watch_change(str(gone), "deleted")

        mock_indexer.delete_file.assert_called_once_with(path=str(gone), collection="code")
        mock_indexer.index_file.assert_not_called()


class TestStaleHitFiltering:
    """Search must never return pointers to locally deleted files."""

    @staticmethod
    def _hit(path):
        return {"score": 0.9, "file_path": path, "type": "function_def", "name": "f"}

    @staticmethod
    async def _drain_cleanup_tasks():
        """Wait for scheduled background deletions to finish."""
        for task in list(server_module._stale_cleanup_tasks):
            await task

    @pytest.mark.asyncio
    async def test_stale_hit_under_watched_root_dropped(self, tmp_path):
        """Hits pointing under a watched root at a missing file are dropped."""
        here = tmp_path / "here.py"
        here.write_text("x = 1\n")
        gone = tmp_path / "gone.py"

        with patch.object(server_module, "_watch_paths", [str(tmp_path)]):
            with patch("qmcp.server.get_indexer") as mock_get_indexer:
                mock_get_indexer.return_value = Mock()

                results = server_module._drop_stale_hits(
                    [self._hit(str(gone)), self._hit(str(here))], "code"
                )
                await self._drain_cleanup_tasks()

        assert [item["file_path"] for item in results] == [str(here)]

    @pytest.mark.asyncio
    async def test_missing_outside_watched_roots_kept(self, tmp_path):
        """Foreign paths (shared Qdrant, other machines) are never judged locally."""
        foreign = "/other/machine/file.py"

        with patch.object(server_module, "_watch_paths", [str(tmp_path)]):
            results = server_module._drop_stale_hits([self._hit(foreign)], "code")

        assert results == [self._hit(foreign)]
        assert not server_module._stale_cleanup_tasks

    @pytest.mark.asyncio
    async def test_stale_deletion_runs_in_background(self, tmp_path):
        """Dropped hits schedule a background delete, not a synchronous one."""
        gone = tmp_path / "gone.py"

        with patch.object(server_module, "_watch_paths", [str(tmp_path)]):
            with patch("qmcp.server.get_indexer") as mock_get_indexer:
                mock_indexer = Mock()
                mock_get_indexer.return_value = mock_indexer

                results = server_module._drop_stale_hits([self._hit(str(gone))], "code")
                assert results == []
                await self._drain_cleanup_tasks()

        mock_indexer.delete_file.assert_called_once_with(str(gone), "code")

    def test_settings_parse_watch_paths_from_plain_env_string(self):
        """Test WATCH_PATHS accepts plain comma-separated environment values."""
        settings = Settings.model_validate({"watch_paths": "/tmp/a,/tmp/b"})

        assert settings.watch_paths == ["/tmp/a", "/tmp/b"]

    def test_settings_parse_watch_paths_from_json_string(self):
        """Test WATCH_PATHS still accepts JSON array environment values."""
        settings = Settings.model_validate({"watch_paths": '["/tmp/a", "/tmp/b"]'})

        assert settings.watch_paths == ["/tmp/a", "/tmp/b"]
