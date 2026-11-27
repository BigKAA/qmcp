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

import asyncio
import time
from contextlib import contextmanager
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
                "indexed_vectors_count": 100,
                "status": "GREEN",
                "vector_size": 384,
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
    async def test_app_lifespan_http_autostarts_watcher(self):
        """HTTP daemons own indexing machine-wide, so the watcher starts with them."""
        with patch.object(server_module.settings, "transport", "streamable-http"):
            with patch.object(server_module.settings, "watch_paths", []):
                with patch(
                    "qmcp.server._ensure_watcher_started",
                    new=AsyncMock(return_value={"status": "started"}),
                ) as mock_ensure:
                    with self._patched_guards() as patched:
                        async with app_lifespan(Mock()):
                            pass

        mock_ensure.assert_awaited_once()
        for mock_guard, task in patched["guards"]:
            mock_guard.assert_called_once()
            task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_app_lifespan_stdio_skips_watcher_autostart(self):
        """stdio servers must not autostart the watcher (one poller per client)."""
        with patch.object(server_module.settings, "transport", "stdio"):
            with patch.object(server_module.settings, "watch_paths", []):
                with patch(
                    "qmcp.server._ensure_watcher_started",
                    new=AsyncMock(return_value={"status": "started"}),
                ) as mock_ensure:
                    with self._patched_guards() as patched:
                        async with app_lifespan(Mock()):
                            pass

        mock_ensure.assert_not_awaited()
        # Shutdown cleanup still runs
        patched["stop"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_app_lifespan_watch_autostart_override(self):
        """WATCH_AUTOSTART=true forces the watcher on even for stdio."""
        with patch.object(server_module.settings, "transport", "stdio"):
            with patch.object(server_module.settings, "watch_autostart", True):
                with patch.object(server_module.settings, "watch_paths", []):
                    with patch(
                        "qmcp.server._ensure_watcher_started",
                        new=AsyncMock(return_value={"status": "started"}),
                    ) as mock_ensure:
                        with self._patched_guards():
                            async with app_lifespan(Mock()):
                                pass

        mock_ensure.assert_awaited_once()

    @staticmethod
    @contextmanager
    def _patched_guards():
        """Patch the three self-termination guards and watcher stop.

        Yields a dict with ``guards`` - (mock, task) pairs, one per guard -
        and ``stop`` - the AsyncMock replacing ``_stop_watcher``.
        """
        from contextlib import ExitStack

        stack = ExitStack()
        guards = []
        for name in ("start_orphan_guard", "start_idle_guard", "start_replacement_guard"):
            task = Mock()
            mock_guard = stack.enter_context(patch(f"qmcp.server.{name}", return_value=task))
            guards.append((mock_guard, task))
        stop = stack.enter_context(patch("qmcp.server._stop_watcher", new=AsyncMock()))
        try:
            yield {"guards": guards, "stop": stop}
        finally:
            stack.close()

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

    @pytest.mark.asyncio
    async def test_activity_middleware_touches_and_counts(self):
        """Every inbound message refreshes the activity timestamp and is counted."""
        call_next = AsyncMock(return_value={"ok": True})
        before = server_module._idle_seconds()

        await asyncio.sleep(0.01)
        result = await server_module._ActivityMiddleware()(Mock(), call_next)

        assert result == {"ok": True}
        assert server_module._idle_seconds() < before
        assert server_module._active_requests == 0

    @pytest.mark.asyncio
    async def test_activity_middleware_counts_in_flight_requests(self):
        """A slow request is visible as activity while it runs."""
        started = asyncio.Event()

        async def slow_call_next(_ctx):
            started.set()
            # While the handler runs, the request must be counted as active
            assert server_module._is_active() is True
            return None

        task = asyncio.create_task(server_module._ActivityMiddleware()(Mock(), slow_call_next))
        await asyncio.wait_for(started.wait(), timeout=1.0)
        await task
        assert server_module._is_active() is False

    def test_is_active_true_while_indexing(self):
        """In-flight indexing work must hold the idle guard back."""
        original = server_module._indexing_in_progress
        server_module._indexing_in_progress = 1
        try:
            assert server_module._is_active() is True
        finally:
            server_module._indexing_in_progress = original

    def test_idle_seconds_resets_on_touch(self):
        """A fresh activity stamp yields a near-zero idle age."""
        server_module._last_activity_monotonic = time.monotonic()
        assert server_module._idle_seconds() < 1.0

    @pytest.mark.asyncio
    async def test_get_status_reports_watcher_role(self):
        """Status exposes the leader-election role for diagnostics."""
        with patch("qmcp.server.get_qdrant_client") as mock_get_client:
            mock_client = Mock()
            mock_client.is_connected = True
            mock_client.get_collections.return_value = []
            mock_get_client.return_value = mock_client

            mock_watcher = Mock()
            mock_watcher.is_running = True
            mock_watcher.role = "standby"
            with patch("qmcp.server._watcher", mock_watcher):
                with patch("qmcp.server._watch_paths", []):
                    result = await qdrant_get_status()

        assert result["watcher_role"] == "standby"
