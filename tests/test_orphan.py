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

"""Tests for the orphan self-termination guard."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from qmcp.orphan import start_orphan_guard


class TestStartOrphanGuard:
    """Tests for the stdio orphan guard."""

    @pytest.mark.asyncio
    async def test_disabled_for_non_stdio_transport(self):
        """HTTP/SSE servers must never kill themselves on parent death."""
        task = start_orphan_guard(transport="streamable-http")

        assert task is None

    @pytest.mark.asyncio
    async def test_orphaned_process_exits(self, monkeypatch):
        """A changed ppid (parent died, reparented) triggers shutdown + exit."""
        ppids = iter([4242])  # at start; afterwards the parent is gone (ppid 1)
        monkeypatch.setattr("qmcp.orphan.os.getppid", lambda: next(ppids, 1))
        exit_fn = Mock()
        shutdown = AsyncMock()

        task = start_orphan_guard(
            shutdown=shutdown,
            check_interval=0.01,
            exit_fn=exit_fn,
            transport="stdio",
        )
        await asyncio.wait_for(task, timeout=1.0)

        shutdown.assert_awaited_once()
        exit_fn.assert_called_once_with(0)

    @pytest.mark.asyncio
    async def test_sync_shutdown_callback_supported(self, monkeypatch):
        """Plain sync shutdown callbacks work without awaiting."""
        ppids = iter([4242])
        monkeypatch.setattr("qmcp.orphan.os.getppid", lambda: next(ppids, 1))
        exit_fn = Mock()
        shutdown = Mock(return_value=None)

        task = start_orphan_guard(
            shutdown=shutdown,
            check_interval=0.01,
            exit_fn=exit_fn,
            transport="stdio",
        )
        await asyncio.wait_for(task, timeout=1.0)

        shutdown.assert_called_once()
        exit_fn.assert_called_once_with(0)

    @pytest.mark.asyncio
    async def test_failing_shutdown_still_exits(self, monkeypatch):
        """A broken shutdown callback must not keep the orphan alive."""
        ppids = iter([4242])
        monkeypatch.setattr("qmcp.orphan.os.getppid", lambda: next(ppids, 1))
        exit_fn = Mock()

        task = start_orphan_guard(
            shutdown=Mock(side_effect=RuntimeError("boom")),
            check_interval=0.01,
            exit_fn=exit_fn,
            transport="stdio",
        )
        await asyncio.wait_for(task, timeout=1.0)

        exit_fn.assert_called_once_with(0)

    @pytest.mark.asyncio
    async def test_alive_parent_keeps_guard_running(self, monkeypatch):
        """Unchanged ppid means the guard keeps polling, never exits."""
        monkeypatch.setattr("qmcp.orphan.os.getppid", lambda: 4242)
        exit_fn = Mock()

        task = start_orphan_guard(
            check_interval=0.01,
            exit_fn=exit_fn,
            transport="stdio",
        )
        await asyncio.sleep(0.1)
        assert not task.done()

        task.cancel()
        exit_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_stdio_default_from_env(self, monkeypatch):
        """Without an explicit transport the guard follows TRANSPORT (stdio)."""
        monkeypatch.setenv("TRANSPORT", "stdio")
        monkeypatch.setattr("qmcp.orphan.os.getppid", lambda: 4242)

        task = start_orphan_guard(check_interval=0.05)
        try:
            assert task is not None
        finally:
            task.cancel()
