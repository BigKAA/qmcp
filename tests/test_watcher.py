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

"""Tests for watcher module."""

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from qmcp.watcher import AsyncWatcher

# The platform observer (FSEvents on macOS) coalesces events with a latency
# of a few hundred ms; allow well above that before giving up on a callback.
EVENT_TIMEOUT = 5.0


async def _wait_until(predicate, timeout: float = EVENT_TIMEOUT) -> bool:
    """Poll ``predicate`` until it is true or ``timeout`` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


async def _wait_observing(watcher: AsyncWatcher, timeout: float = EVENT_TIMEOUT) -> bool:
    """Wait until the watcher's platform observer is up and streaming.

    ``start()`` returns before the Observer (started inside a background
    task) is live, so tests must not touch the filesystem before this -
    changes made earlier would fall before the event stream and be missed.
    """
    ok = await _wait_until(lambda: watcher._observer is not None, timeout)
    if ok:
        # Give the FSEvents stream a beat to warm up
        await asyncio.sleep(0.3)
    return ok


def _events_of(callback) -> set[tuple[str, str]]:
    """Collect (path, event_type) pairs an async mock callback has seen.

    A set: duplicates collapse. When a test needs to count repeats (the
    same event can legitimately fire twice), read ``callback.await_args_list``
    directly.
    """
    return {(call.args[0], call.args[1]) for call in callback.await_args_list}


def _count_events(callback, path_suffix: str) -> int:
    """Count callback invocations for paths ending with ``path_suffix``."""
    return sum(1 for call in callback.await_args_list if call.args[0].endswith(path_suffix))


class TestAsyncWatcher:
    """Tests for AsyncWatcher class."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_callback(self):
        """Create async mock callback."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_async_watcher_initialization(self, mock_callback):
        """Test async watcher initializes correctly."""
        watcher = AsyncWatcher(
            paths=["/path/to/watch"],
            callback=mock_callback,
            debounce_seconds=5.0,
        )

        assert watcher.paths == [Path("/path/to/watch")]
        assert watcher.callback == mock_callback
        assert watcher.debounce_seconds == 5.0
        assert not watcher.is_running
        assert watcher._pending == {}
        assert watcher._timers == {}

    @pytest.mark.asyncio
    async def test_should_ignore_hidden_files(self, mock_callback):
        """Hidden files never reach the callback."""
        watcher = AsyncWatcher(paths=["/path"], callback=mock_callback)

        assert watcher._should_ignore("/path/to/.hidden.py") is True
        assert watcher._should_ignore("/path/to/normal.py") is False

    @pytest.mark.asyncio
    async def test_should_ignore_patterns(self, mock_callback):
        """Test async watcher ignores certain patterns."""
        watcher = AsyncWatcher(paths=["/path"], callback=mock_callback)

        assert watcher._should_ignore("/path/__pycache__/file.py") is True
        assert watcher._should_ignore("/path/.git/file.py") is True
        assert watcher._should_ignore("/path/node_modules/file.js") is True
        assert watcher._should_ignore("/path/.venv/file.py") is True

    @pytest.mark.asyncio
    async def test_should_ignore_unsupported_extensions(self, mock_callback):
        """The observer delivers every file type; the dispatch filter drops
        everything outside WATCHED_FILE_EXTENSIONS."""
        watcher = AsyncWatcher(paths=["/path"], callback=mock_callback)

        assert watcher._should_ignore("/path/file.txt") is True
        assert watcher._should_ignore("/path/file.bin") is True
        assert watcher._should_ignore("/path/file.tmp") is True

    @pytest.mark.asyncio
    async def test_should_accept_supported_extensions(self, mock_callback):
        """All indexed languages pass the filter."""
        watcher = AsyncWatcher(paths=["/path"], callback=mock_callback)

        assert watcher._should_ignore("/path/file.py") is False
        assert watcher._should_ignore("/path/file.go") is False
        assert watcher._should_ignore("/path/file.js") is False
        assert watcher._should_ignore("/path/file.ts") is False
        assert watcher._should_ignore("/path/file.java") is False
        assert watcher._should_ignore("/path/file.cs") is False
        assert watcher._should_ignore("/path/file.md") is False

    @pytest.mark.asyncio
    async def test_async_watcher_start_stop(self, temp_dir, mock_callback):
        """Test async watcher can start and stop."""
        test_file = temp_dir / "test.py"
        test_file.write_text("# test")

        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
        )

        await watcher.start()
        assert watcher.is_running

        await watcher.stop()
        assert not watcher.is_running

    @pytest.mark.asyncio
    async def test_async_watcher_detects_new_file(self, temp_dir, mock_callback):
        """A file created after start reaches the callback, debounced."""
        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
            debounce_seconds=0.1,
        )

        await watcher.start()
        await _wait_observing(watcher)

        test_file = temp_dir / "new_file.py"
        test_file.write_text("# new file")

        found = await _wait_until(
            lambda: any(path.endswith("new_file.py") for path, _ in _events_of(mock_callback))
        )
        await watcher.stop()

        assert found, f"no event for new file, got {_events_of(mock_callback)}"
        # Whatever the create/modify coalescing decided, it is not a deletion
        assert not any(
            path.endswith("new_file.py") and event_type == "deleted"
            for path, event_type in _events_of(mock_callback)
        )

    @pytest.mark.asyncio
    async def test_run_callback_with_sync_function(self, temp_dir):
        """Test that sync callbacks work correctly."""
        sync_callback = Mock()
        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=sync_callback,
        )

        # Should not raise when running sync callback
        await watcher._run_callback("/path/file.py", "modified")

        sync_callback.assert_called_once_with("/path/file.py", "modified")

    @pytest.mark.asyncio
    async def test_start_returns_before_slow_scan(self, temp_dir, mock_callback, tmp_path):
        """start() must return immediately even while the baseline scan runs.

        Regression test for issue #1: scanning WATCH_PATHS used to block the
        event loop inside start(), so the MCP client timed out on initialize.
        The baseline only exists for leader-election watchers (standbys need
        it to reconcile the standby gap), so this watcher uses a lock dir.
        """
        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
            lock_dir=tmp_path / "locks",
            standby_interval=0.01,
        )

        def slow_scan():
            time.sleep(0.5)

        with patch.object(watcher, "_scan_all_paths", slow_scan):
            started_at = time.monotonic()
            await watcher.start()
            elapsed = time.monotonic() - started_at

        try:
            assert elapsed < 0.3
        finally:
            await watcher.stop()

    @pytest.mark.asyncio
    async def test_detects_created_and_modified_files(self, temp_dir, mock_callback):
        """End-to-end: a new file and a rewrite both reach the callback.

        FSEvents may deliver a "history" event for files changed just before
        the stream started (watchdog ships suppress_history=False), so the
        waits target the specific file and a *new* existing.py event.
        """
        existing = temp_dir / "existing.py"
        existing.write_text("# v1")

        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
            debounce_seconds=0.1,
        )
        await watcher.start()
        await _wait_observing(watcher)

        new_file = temp_dir / "created.py"
        new_file.write_text("# new")
        saw_new = await _wait_until(
            lambda: any(p.endswith("created.py") for p, _ in _events_of(mock_callback))
        )

        existing_events_before = _count_events(mock_callback, "existing.py")
        existing.write_text("# v2")
        saw_modified = await _wait_until(
            lambda: _count_events(mock_callback, "existing.py") > existing_events_before
        )
        await watcher.stop()

        events = _events_of(mock_callback)
        new_types = {t for p, t in events if p.endswith("created.py")}
        existing_types = {t for p, t in events if p.endswith("existing.py")}

        assert saw_new, f"no event for created.py, got {events}"
        # A fresh create arrives as created (plus possibly a modify)
        assert new_types <= {"created", "modified"}
        assert saw_modified, f"no rewrite event for existing.py, got {events}"
        # An in-place rewrite is a modify, never a create
        assert existing_types == {"modified"}

    @pytest.mark.asyncio
    async def test_detects_deleted_files(self, temp_dir, mock_callback):
        """A deleted file produces a 'deleted' event.

        Without it, points of deleted files stay in Qdrant forever and search
        keeps returning pointers to files that no longer exist.
        """
        doomed = temp_dir / "doomed.py"
        doomed.write_text("# bye")

        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
            debounce_seconds=0.1,
        )
        await watcher.start()
        await _wait_observing(watcher)

        doomed.unlink()
        # FSEvents reports paths through the resolved /private prefix on
        # macOS, so compare against the resolved path, not the raw one.
        found = await _wait_until(
            lambda: (str(doomed.resolve()), "deleted") in _events_of(mock_callback)
        )
        await watcher.stop()

        assert found, f"no deleted event, got {_events_of(mock_callback)}"

    @pytest.mark.asyncio
    async def test_atomic_save_collapses_delete_and_recreate(self, temp_dir, mock_callback):
        """Rename-over-target saves (editors do this) end in reindex, not delete.

        The pending-event map keeps only the latest event per path and the
        move event posts delete-at-source + create-at-target, so the target
        never dispatches "deleted" and its index is never dropped.
        """
        doc = temp_dir / "doc.py"
        doc.write_text("# v1")

        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
            debounce_seconds=0.5,
        )
        await watcher.start()
        await _wait_observing(watcher)

        # Atomic save: write a replacement next to it, unlink the original,
        # rename over the target.
        replacement = temp_dir / "doc.py.tmp"
        replacement.write_text("# v2")
        doc.unlink()
        replacement.rename(doc)
        await asyncio.sleep(1.5)
        await watcher.stop()

        events = _events_of(mock_callback)
        assert (str(doc), "deleted") not in events
        assert any(
            path.endswith("doc.py") and event_type in ("created", "modified")
            for path, event_type in events
        )


class TestAsyncWatcherTraversal:
    """Tests for directory traversal and snapshot filtering (issue #1)."""

    @pytest.fixture
    def tree(self, tmp_path):
        """Build a tree mixing watchable and ignored entries."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("# main")
        (tmp_path / "src" / "README.md").write_text("# readme")
        (tmp_path / "src" / "notes.txt").write_text("not watched")
        (tmp_path / "src" / ".hidden.py").write_text("# hidden")

        for ignored in ("node_modules", ".git", ".venv", "venv", "__pycache__", ".github"):
            nested = tmp_path / ignored / "nested"
            nested.mkdir(parents=True)
            (nested / "file.py").write_text("# ignored")

        return tmp_path

    def test_iter_watch_files_prunes_ignored_dirs(self, tree):
        """Traversal must skip ignored/hidden dirs and unsupported files."""
        watcher = AsyncWatcher(paths=[str(tree)], callback=AsyncMock())
        files = {p.relative_to(tree).as_posix() for p in watcher._iter_watch_files(tree)}
        assert files == {"src/main.py", "src/README.md"}

    def test_scan_path_skips_ignored_content(self, tree):
        """Snapshot must not contain anything under ignored directories."""
        watcher = AsyncWatcher(paths=[str(tree)], callback=AsyncMock())
        watcher._scan_path(tree)

        scanned = set(watcher._last_mtimes)
        assert str(tree / "src" / "main.py") in scanned
        assert str(tree / "src" / "README.md") in scanned
        assert str(tree / "src" / "notes.txt") not in scanned
        assert str(tree / "src" / ".hidden.py") not in scanned
        assert not any("node_modules" in p for p in scanned)
        assert not any("/.git/" in p for p in scanned)
        assert not any("/.venv/" in p for p in scanned)
        assert not any("__pycache__" in p for p in scanned)

    def test_scan_path_handles_single_file(self, tmp_path):
        """A watched file path yields itself; unsupported files yield nothing."""
        py_file = tmp_path / "single.py"
        py_file.write_text("# single")
        txt_file = tmp_path / "single.txt"
        txt_file.write_text("text")

        watcher = AsyncWatcher(paths=[str(py_file)], callback=AsyncMock())
        watcher._scan_path(py_file)
        assert watcher._last_mtimes == {str(py_file): watcher._last_mtimes[str(py_file)]}

        watcher._scan_path(txt_file)
        assert str(txt_file) not in watcher._last_mtimes

    @pytest.mark.asyncio
    async def test_leader_from_start_takes_no_baseline(self, tmp_path):
        """A watcher that leads immediately skips the snapshot entirely.

        The Observer sees every change from activation onward, so the
        steady state must keep no per-file state (the polling watcher's
        mtime map used to dominate RSS on huge trees). Only leader-election
        watchers spawn the baseline task - a standby may need it to
        reconcile the standby gap on promotion.
        """
        watcher = AsyncWatcher(paths=[str(tmp_path)], callback=AsyncMock())
        await watcher.start()
        try:
            assert watcher._baseline_task is None
            assert watcher._last_mtimes == {}
        finally:
            await watcher.stop()

        watcher_with_locks = AsyncWatcher(
            paths=[str(tmp_path)],
            callback=AsyncMock(),
            lock_dir=tmp_path / "locks",
        )
        await watcher_with_locks.start()
        try:
            assert watcher_with_locks._baseline_task is not None
        finally:
            await watcher_with_locks.stop()


class TestAsyncWatcherLeaderElection:
    """Tests for the cross-process watcher leader election (standby mode)."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def lock_dir(self, tmp_path):
        """Create an isolated lock directory per test."""
        return tmp_path / "locks"

    @pytest.mark.asyncio
    async def test_solo_role_without_lock_dir(self, temp_dir):
        """Without a lock directory the watcher runs as the only instance."""
        watcher = AsyncWatcher(paths=[str(temp_dir)], callback=AsyncMock())

        assert watcher.role == "solo"
        assert watcher._leader_lock is None

    @pytest.mark.asyncio
    async def test_first_instance_becomes_leader(self, temp_dir, lock_dir):
        """The uncontended watcher acquires leadership and watches."""
        leader_callback = AsyncMock()
        (temp_dir / "solo.py").write_text("x = 1\n")
        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=leader_callback,
            lock_dir=lock_dir,
            standby_interval=0.01,
        )
        await watcher.start()

        promoted = await _wait_until(lambda: watcher.role == "leader")
        assert watcher.is_polling is True

        await watcher.stop()
        assert promoted

    @pytest.mark.asyncio
    async def test_second_instance_stays_standby(self, temp_dir, lock_dir):
        """A second watcher over the same paths runs no observer and no callbacks."""
        leader_callback = AsyncMock()
        standby_callback = AsyncMock()
        (temp_dir / "solo.py").write_text("x = 1\n")
        leader = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=leader_callback,
            debounce_seconds=0.05,
            lock_dir=lock_dir,
            standby_interval=0.01,
        )
        standby = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=standby_callback,
            debounce_seconds=0.05,
            lock_dir=lock_dir,
            standby_interval=0.01,
        )
        await leader.start()
        await _wait_until(lambda: leader.role == "leader")
        await _wait_observing(leader)
        await standby.start()

        # Change a file while both watch: only the leader reacts
        (temp_dir / "new.py").write_text("y = 2\n")
        fired = await _wait_until(lambda: leader_callback.await_count > 0)

        assert leader.role == "leader"
        assert standby.role == "standby"
        assert standby.is_running is True
        assert standby.is_polling is False
        assert fired
        # The standby runs no Observer - it never sees the change
        assert standby_callback.await_count == 0

        await leader.stop()
        await standby.stop()

    @pytest.mark.asyncio
    async def test_standby_promoted_after_leader_death(self, temp_dir, lock_dir):
        """When the leader stops, a standby takes over automatically."""
        leader_callback = AsyncMock()
        standby_callback = AsyncMock()
        (temp_dir / "solo.py").write_text("x = 1\n")
        leader = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=leader_callback,
            lock_dir=lock_dir,
            standby_interval=0.01,
        )
        standby = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=standby_callback,
            lock_dir=lock_dir,
            standby_interval=0.01,
        )
        await leader.start()
        await _wait_until(lambda: leader.role == "leader")
        await standby.start()
        await _wait_until(lambda: standby.role == "standby")
        assert standby.role == "standby"

        await leader.stop()
        promoted = await _wait_until(lambda: standby.role == "leader")

        assert promoted
        assert standby.is_polling is True

        await standby.stop()

    @pytest.mark.asyncio
    async def test_reconcile_is_silent_when_standby_saw_no_changes(self, temp_dir, lock_dir):
        """Promotion with an unchanged tree baselines quietly - no event storm.

        The promoted standby diffs its start-time snapshot against the
        filesystem; identical state must produce zero callbacks (the old
        poller's replay-storm regression guard).
        """
        leader_callback = AsyncMock()
        standby_callback = AsyncMock()
        for i in range(5):
            (temp_dir / f"solo{i}.py").write_text("x = 1\n")
        leader = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=leader_callback,
            debounce_seconds=0.05,
            lock_dir=lock_dir,
            standby_interval=0.01,
        )
        standby = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=standby_callback,
            debounce_seconds=0.05,
            lock_dir=lock_dir,
            standby_interval=0.01,
        )
        await leader.start()
        await _wait_until(lambda: leader.role == "leader")
        await standby.start()
        # Wait for the standby's baseline snapshot to complete
        await _wait_until(lambda: len(standby._last_mtimes) == 5)

        await leader.stop()
        promoted = await _wait_until(lambda: standby.role == "leader")
        await asyncio.sleep(1.0)  # reconcile + debounce window

        assert promoted
        assert standby.role == "leader"
        # Nothing changed during standby: total silence
        assert standby_callback.await_count == 0

        await standby.stop()

    @pytest.mark.asyncio
    async def test_changes_during_standby_reconciled_on_promotion(self, temp_dir, lock_dir):
        """Files changed while another process led are indexed on promotion.

        The Observer only sees changes from activation onward, so a newly
        promoted standby replays its snapshot diff: the standby-gap window
        (leader died, nothing watched) must not leave files stale.
        """
        leader_callback = AsyncMock()
        standby_callback = AsyncMock()
        (temp_dir / "solo.py").write_text("x = 1\n")
        leader = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=leader_callback,
            debounce_seconds=0.05,
            lock_dir=lock_dir,
            standby_interval=0.01,
        )
        # A long standby interval keeps the standby in standby long enough
        # to write into the gap between leader stop and promotion.
        standby = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=standby_callback,
            debounce_seconds=0.05,
            lock_dir=lock_dir,
            standby_interval=1.0,
        )
        await leader.start()
        await _wait_until(lambda: leader.role == "leader")
        await standby.start()
        await _wait_until(lambda: len(standby._last_mtimes) == 1)

        await leader.stop()
        gap_file = temp_dir / "gap.py"
        gap_file.write_text("# written while nobody watched")

        promoted = await _wait_until(lambda: standby.role == "leader", timeout=3.0)
        reconciled = await _wait_until(
            lambda: (str(gap_file), "created") in _events_of(standby_callback)
        )

        assert promoted
        assert reconciled, f"standby gap not reconciled, got {_events_of(standby_callback)}"
        # The (stopped) leader must not have seen the gap file
        assert not any(path.endswith("gap.py") for path, _ in _events_of(leader_callback))
        # The baseline map is freed after reconcile - no per-file steady state
        assert standby._last_mtimes == {}

        await standby.stop()
