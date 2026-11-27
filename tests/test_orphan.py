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

"""Tests for the stdio self-termination guards."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest

from qmcp.orphan import start_idle_guard, start_orphan_guard, start_replacement_guard


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


class TestStartIdleGuard:
    """Tests for the idle self-termination guard."""

    @pytest.mark.asyncio
    async def test_disabled_for_non_stdio_transport(self):
        """HTTP/SSE daemons are service-managed and never idle-exit."""
        task = start_idle_guard(
            timeout_seconds=60,
            idle_seconds=lambda: 999.0,
            is_active=lambda: False,
            transport="streamable-http",
        )

        assert task is None

    @pytest.mark.asyncio
    async def test_disabled_for_zero_timeout(self):
        """IDLE_TIMEOUT_SECONDS=0 must turn the guard off entirely."""
        task = start_idle_guard(
            timeout_seconds=0,
            idle_seconds=lambda: 999.0,
            is_active=lambda: False,
            transport="stdio",
        )

        assert task is None

    def test_missing_callbacks_rejected(self):
        """The guard cannot run without its liveness probes."""
        with pytest.raises(ValueError):
            start_idle_guard(timeout_seconds=60, transport="stdio")

    @pytest.mark.asyncio
    async def test_idle_server_exits(self):
        """No traffic past the timeout triggers shutdown + exit."""
        exit_fn = Mock()
        shutdown = AsyncMock()

        task = start_idle_guard(
            shutdown=shutdown,
            timeout_seconds=30.0,
            idle_seconds=lambda: 60.0,
            is_active=lambda: False,
            check_interval=0.01,
            exit_fn=exit_fn,
            transport="stdio",
        )
        await asyncio.wait_for(task, timeout=1.0)

        shutdown.assert_awaited_once()
        exit_fn.assert_called_once_with(0)

    @pytest.mark.asyncio
    async def test_recent_activity_keeps_guard_running(self):
        """Fresh traffic postpones the exit indefinitely."""
        exit_fn = Mock()

        task = start_idle_guard(
            timeout_seconds=3600.0,
            idle_seconds=lambda: 1.0,
            is_active=lambda: False,
            check_interval=0.01,
            exit_fn=exit_fn,
            transport="stdio",
        )
        await asyncio.sleep(0.05)
        assert not task.done()

        task.cancel()
        exit_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_active_work_blocks_exit(self):
        """In-flight work must never be cut short, even past the timeout."""
        exit_fn = Mock()

        task = start_idle_guard(
            timeout_seconds=30.0,
            idle_seconds=lambda: 3600.0,
            is_active=lambda: True,
            check_interval=0.01,
            exit_fn=exit_fn,
            transport="stdio",
        )
        await asyncio.sleep(0.05)
        assert not task.done()

        task.cancel()
        exit_fn.assert_not_called()


class TestStartReplacementGuard:
    """Tests for the replaced-by-newer-sibling guard."""

    @pytest.mark.asyncio
    async def test_disabled_for_non_stdio_transport(self, tmp_path):
        """HTTP/SSE daemons are service-managed and never replacement-exit."""
        task = start_replacement_guard(
            registry_dir=tmp_path,
            idle_seconds=lambda: 999.0,
            transport="streamable-http",
        )

        assert task is None

    @pytest.mark.asyncio
    async def test_replaced_and_idle_exits(self, tmp_path, monkeypatch):
        """A newer live sibling plus idle grace ends this leftover instance."""
        monkeypatch.setattr("qmcp.orphan.os.getppid", lambda: 4242)
        exit_fn = Mock()
        shutdown = AsyncMock()
        # A newer sibling (pid 111, started at t=100) already registered
        _write_record_for_test(tmp_path, 4242, {"pid": 111, "started": 100.0})

        task = start_replacement_guard(
            shutdown=shutdown,
            registry_dir=tmp_path,
            grace_seconds=300.0,
            idle_seconds=lambda: 600.0,
            check_interval=0.01,
            exit_fn=exit_fn,
            transport="stdio",
            pid=222,
            now_fn=lambda: 50.0,  # we are older (started before the sibling)
            pid_alive=lambda pid: True,
        )
        await asyncio.wait_for(task, timeout=1.0)

        shutdown.assert_awaited_once()
        exit_fn.assert_called_once_with(0)

    @pytest.mark.asyncio
    async def test_replaced_but_busy_stays_alive(self, tmp_path, monkeypatch):
        """A multiplexed live connection is never reaped, only rechecked."""
        monkeypatch.setattr("qmcp.orphan.os.getppid", lambda: 4242)
        exit_fn = Mock()
        _write_record_for_test(tmp_path, 4242, {"pid": 111, "started": 100.0})

        task = start_replacement_guard(
            registry_dir=tmp_path,
            grace_seconds=300.0,
            idle_seconds=lambda: 5.0,  # idle, but below grace
            check_interval=0.01,
            exit_fn=exit_fn,
            transport="stdio",
            pid=222,
            now_fn=lambda: 50.0,
            pid_alive=lambda pid: True,
        )
        await asyncio.sleep(0.05)
        assert not task.done()

        task.cancel()
        exit_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_older_sibling_is_ignored(self, tmp_path, monkeypatch):
        """An older registration means we are the replacement - keep living."""
        monkeypatch.setattr("qmcp.orphan.os.getppid", lambda: 4242)
        exit_fn = Mock()
        _write_record_for_test(tmp_path, 4242, {"pid": 111, "started": 10.0})

        task = start_replacement_guard(
            registry_dir=tmp_path,
            grace_seconds=0.0,
            idle_seconds=lambda: 999.0,
            check_interval=0.01,
            exit_fn=exit_fn,
            transport="stdio",
            pid=222,
            now_fn=lambda: 100.0,  # we started later than the record
            pid_alive=lambda pid: True,
        )
        await asyncio.sleep(0.05)
        assert not task.done()

        task.cancel()
        exit_fn.assert_not_called()
        # We also took over the registry record
        record = _read_record_for_test(tmp_path, 4242)
        assert record["pid"] == 222

    @pytest.mark.asyncio
    async def test_dead_sibling_record_is_reclaimed(self, tmp_path, monkeypatch):
        """A stale record from a recycled PID never triggers an exit."""
        monkeypatch.setattr("qmcp.orphan.os.getppid", lambda: 4242)
        exit_fn = Mock()
        _write_record_for_test(tmp_path, 4242, {"pid": 111, "started": 100.0})

        task = start_replacement_guard(
            registry_dir=tmp_path,
            grace_seconds=0.0,
            idle_seconds=lambda: 999.0,
            check_interval=0.01,
            exit_fn=exit_fn,
            transport="stdio",
            pid=222,
            now_fn=lambda: 50.0,
            pid_alive=lambda pid: False,  # the registered sibling is dead
        )
        await asyncio.sleep(0.05)
        assert not task.done()

        task.cancel()
        exit_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_corrupt_registry_file_tolerated(self, tmp_path, monkeypatch):
        """A corrupted record is treated as absent, not as a replacement."""
        monkeypatch.setattr("qmcp.orphan.os.getppid", lambda: 4242)
        exit_fn = Mock()
        (tmp_path / "stdio-instance-4242.json").write_text("{not json")

        task = start_replacement_guard(
            registry_dir=tmp_path,
            grace_seconds=0.0,
            idle_seconds=lambda: 999.0,
            check_interval=0.01,
            exit_fn=exit_fn,
            transport="stdio",
            pid=222,
            now_fn=lambda: 50.0,
            pid_alive=lambda pid: True,
        )
        await asyncio.sleep(0.05)
        assert not task.done()

        task.cancel()
        exit_fn.assert_not_called()


def _write_record_for_test(registry_dir, parent_pid, payload):
    """Seed an instance-registry record exactly as the guard writes it."""
    path = registry_dir / f"stdio-instance-{parent_pid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read_record_for_test(registry_dir, parent_pid):
    """Read back an instance-registry record."""
    path = registry_dir / f"stdio-instance-{parent_pid}.json"
    return json.loads(path.read_text(encoding="utf-8"))
