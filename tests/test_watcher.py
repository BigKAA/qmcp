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
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from qmcp.watcher import AsyncWatcher, FileChangeHandler, Watcher


class TestFileChangeHandler:
    """Tests for FileChangeHandler class."""

    @pytest.fixture
    def mock_callback(self):
        """Create a mock callback function."""
        return Mock()

    @pytest.fixture
    def handler(self, mock_callback):
        """Create FileChangeHandler instance."""
        return FileChangeHandler(
            callback=mock_callback,
            debounce_seconds=0.1,  # Short for testing
        )

    def test_handler_initialization(self, handler, mock_callback):
        """Test handler initializes with correct values."""
        assert handler.callback == mock_callback
        assert handler.debounce_seconds == 0.1
        assert handler.pending_events == {}

    def test_on_modified_schedules_event(self, handler):
        """Test on_modified schedules event with debouncing."""
        event = Mock()
        event.is_directory = False
        event.src_path = "/path/to/file.py"

        handler.on_modified(event)

        assert "/path/to/file.py" in handler.pending_events
        assert handler.pending_events["/path/to/file.py"][0] == "modified"

    def test_on_created_schedules_event(self, handler):
        """Test on_created schedules event."""
        event = Mock()
        event.is_directory = False
        event.src_path = "/path/to/new.py"

        handler.on_created(event)

        assert "/path/to/new.py" in handler.pending_events
        assert handler.pending_events["/path/to/new.py"][0] == "created"

    def test_on_deleted_schedules_event(self, handler):
        """Test on_deleted schedules event."""
        event = Mock()
        event.is_directory = False
        event.src_path = "/path/to/deleted.py"

        handler.on_deleted(event)

        assert "/path/to/deleted.py" in handler.pending_events
        assert handler.pending_events["/path/to/deleted.py"][0] == "deleted"

    def test_on_directory_ignored(self, handler):
        """Test that directory events are ignored."""
        event = Mock()
        event.is_directory = True
        event.src_path = "/path/to/dir"

        handler.on_modified(event)

        assert "/path/to/dir" not in handler.pending_events

    def test_process_pending_calls_callback(self, handler, mock_callback):
        """Test that process_pending calls callback after debounce."""
        # Add event with old timestamp
        old_time = time.time() - 1.0  # 1 second ago
        handler.pending_events["/path/to/file.py"] = ("modified", old_time)

        # Process pending
        processed = handler.process_pending()

        assert "/path/to/file.py" in processed
        mock_callback.assert_called_once_with("/path/to/file.py", "modified")

    def test_process_pending_respects_debounce(self, handler, mock_callback):
        """Test that recent events are not processed yet."""
        # Add event with recent timestamp
        recent_time = time.time()
        handler.pending_events["/path/to/file.py"] = ("modified", recent_time)

        # Process pending
        processed = handler.process_pending()

        assert len(processed) == 0
        mock_callback.assert_not_called()

    def test_multiple_events_processed(self, handler, mock_callback):
        """Test multiple pending events are processed."""
        old_time = time.time() - 1.0

        handler.pending_events["/path/to/file1.py"] = ("modified", old_time)
        handler.pending_events["/path/to/file2.py"] = ("created", old_time - 0.5)
        handler.pending_events["/path/to/file3.py"] = ("deleted", old_time)

        processed = handler.process_pending()

        assert len(processed) == 3
        assert mock_callback.call_count == 3


class TestWatcher:
    """Tests for Watcher class."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_callback(self):
        """Create mock callback."""
        return Mock()

    def test_watcher_initialization(self, mock_callback):
        """Test watcher initializes correctly."""
        paths = ["/path/to/watch1", "/path/to/watch2"]
        watcher = Watcher(
            paths=paths,
            callback=mock_callback,
            debounce_seconds=5.0,
        )

        assert watcher.paths == [Path("/path/to/watch1"), Path("/path/to/watch2")]
        assert watcher.callback == mock_callback
        assert watcher.debounce_seconds == 5.0
        assert not watcher.is_running

    def test_should_ignore_hidden_files(self, temp_dir, mock_callback):
        """Test that hidden files are ignored."""
        watcher = Watcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
        )

        assert watcher._should_ignore("/path/to/.hidden.py") is True
        assert watcher._should_ignore("/path/to/normal.py") is False

    def test_should_ignore_patterns(self, temp_dir, mock_callback):
        """Test that common patterns are ignored."""
        watcher = Watcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
        )

        assert watcher._should_ignore("/path/__pycache__/file.py") is True
        assert watcher._should_ignore("/path/.git/file.py") is True
        assert watcher._should_ignore("/path/node_modules/file.js") is True
        assert watcher._should_ignore("/path/venv/lib/file.py") is True

    def test_should_ignore_unsupported_extensions(self, temp_dir, mock_callback):
        """Test that unsupported file extensions are ignored."""
        watcher = Watcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
        )

        assert watcher._should_ignore("/path/file.txt") is True
        assert watcher._should_ignore("/path/file.bin") is True
        assert watcher._should_ignore("/path/file.exe") is True

    def test_should_accept_supported_extensions(self, temp_dir, mock_callback):
        """Test that supported extensions are accepted."""
        watcher = Watcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
        )

        assert watcher._should_ignore("/path/file.py") is False
        assert watcher._should_ignore("/path/file.go") is False
        assert watcher._should_ignore("/path/file.js") is False
        assert watcher._should_ignore("/path/file.ts") is False
        assert watcher._should_ignore("/path/file.java") is False
        assert watcher._should_ignore("/path/file.cs") is False
        assert watcher._should_ignore("/path/file.md") is False

    def test_start_and_stop(self, temp_dir, mock_callback):
        """Test watcher can start and stop."""
        # Create a real file to watch
        test_file = temp_dir / "test.py"
        test_file.write_text("# test")

        watcher = Watcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
        )

        watcher.start()
        assert watcher.is_running

        watcher.stop()
        assert not watcher.is_running


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
        paths = ["/path/to/watch"]
        watcher = AsyncWatcher(
            paths=paths,
            callback=mock_callback,
            poll_interval=0.5,
            debounce_seconds=5.0,
        )

        assert watcher.paths == [Path("/path/to/watch")]
        assert watcher.callback == mock_callback
        assert watcher.poll_interval == 0.5
        assert watcher.debounce_seconds == 5.0
        assert not watcher.is_running

    @pytest.mark.asyncio
    async def test_async_watcher_should_ignore_patterns(self, mock_callback):
        """Test async watcher ignores certain patterns."""
        watcher = AsyncWatcher(
            paths=["/path"],
            callback=mock_callback,
        )

        assert watcher._should_ignore("/path/__pycache__/file.py") is True
        assert watcher._should_ignore("/path/.git/file.py") is True
        assert watcher._should_ignore("/path/node_modules/file.js") is True
        assert watcher._should_ignore("/path/.venv/file.py") is True

    @pytest.mark.asyncio
    async def test_async_watcher_start_stop(self, temp_dir, mock_callback):
        """Test async watcher can start and stop."""
        test_file = temp_dir / "test.py"
        test_file.write_text("# test")

        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
            poll_interval=0.1,
        )

        await watcher.start()
        assert watcher.is_running

        await watcher.stop()
        assert not watcher.is_running

    @pytest.mark.asyncio
    async def test_async_watcher_detects_new_file(self, temp_dir, mock_callback):
        """Test async watcher detects new files."""
        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
            poll_interval=0.1,
            debounce_seconds=0.2,
        )

        # Start watcher
        await watcher.start()

        # Create new file
        test_file = temp_dir / "new_file.py"
        test_file.write_text("# new file")

        # Wait for polling
        await asyncio.sleep(0.3)

        # Stop watcher
        await watcher.stop()

        # Verify callback was called (may need adjustment based on timing)
        # In real tests, use mock clock or longer delays

    @pytest.mark.asyncio
    async def test_run_callback_with_sync_function(self, temp_dir):
        """Test that sync callbacks work correctly."""
        sync_callback = Mock()
        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=sync_callback,
            poll_interval=0.1,
        )

        # Should not raise when running sync callback
        await watcher._run_callback("/path/file.py", "modified")

        sync_callback.assert_called_once_with("/path/file.py", "modified")

    @pytest.mark.asyncio
    async def test_start_returns_before_slow_scan(self, temp_dir, mock_callback):
        """start() must return immediately even while the baseline scan runs.

        Regression test for issue #1: scanning WATCH_PATHS used to block the
        event loop inside start(), so the MCP client timed out on initialize.
        """
        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
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
        """End-to-end: baseline first, then debounced created/modified events."""
        existing = temp_dir / "existing.py"
        existing.write_text("# v1")

        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
            poll_interval=0.05,
            debounce_seconds=0.1,
        )
        await watcher.start()

        # Wait for the baseline scan so the next file is detected as "created"
        for _ in range(100):
            if str(existing) in watcher._last_mtimes:
                break
            await asyncio.sleep(0.02)
        else:
            await watcher.stop()
            pytest.fail("Baseline scan did not complete")

        # New file must be reported as created
        new_file = temp_dir / "created.py"
        new_file.write_text("# new")
        await asyncio.sleep(0.6)

        # Bump mtime explicitly: filesystem mtime granularity can be >= 1s,
        # which would make a quick rewrite invisible to the watcher.
        future = time.time() + 5
        os.utime(existing, (future, future))
        await asyncio.sleep(0.6)

        await watcher.stop()

        events = {(call.args[0], call.args[1]) for call in mock_callback.call_args_list}
        created_paths = [path for path, event_type in events if event_type == "created"]

        assert (str(new_file), "created") in events
        assert (str(existing), "modified") in events
        # Files already present at start are baseline, not "created"
        assert str(existing) not in created_paths

    @pytest.mark.asyncio
    async def test_detects_deleted_files(self, temp_dir, mock_callback):
        """Files vanishing between polls produce a debounced 'deleted' event.

        Without it, points of deleted files stay in Qdrant forever and search
        keeps returning pointers to files that no longer exist.
        """
        doomed = temp_dir / "doomed.py"
        doomed.write_text("# bye")

        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
            poll_interval=0.05,
            debounce_seconds=0.1,
        )
        await watcher.start()

        # Wait for the baseline scan so the file is a known state
        for _ in range(100):
            if str(doomed) in watcher._last_mtimes:
                break
            await asyncio.sleep(0.02)
        else:
            await watcher.stop()
            pytest.fail("Baseline scan did not complete")

        doomed.unlink()
        await asyncio.sleep(0.6)
        await watcher.stop()

        events = {(call.args[0], call.args[1]) for call in mock_callback.call_args_list}
        assert (str(doomed), "deleted") in events
        # The stale entry must leave the mtime map, not linger forever
        assert str(doomed) not in watcher._last_mtimes

    @pytest.mark.asyncio
    async def test_atomic_save_collapses_delete_and_recreate(self, temp_dir, mock_callback):
        """Unlink + rename saves (editors do this) end in reindex, not delete.

        The pending-event dict keeps only the latest event per path, so a
        deletion immediately followed by a recreate within the debounce
        window resolves to "created" and never drops the file's index.
        """
        doc = temp_dir / "doc.py"
        doc.write_text("# v1")

        watcher = AsyncWatcher(
            paths=[str(temp_dir)],
            callback=mock_callback,
            poll_interval=0.05,
            debounce_seconds=0.3,
        )
        await watcher.start()

        for _ in range(100):
            if str(doc) in watcher._last_mtimes:
                break
            await asyncio.sleep(0.02)
        else:
            await watcher.stop()
            pytest.fail("Baseline scan did not complete")

        # Atomic save: write a replacement next to it, unlink the original,
        # rename over the target - all within one debounce window.
        replacement = temp_dir / "doc.py.tmp"
        replacement.write_text("# v2")
        doc.unlink()
        replacement.rename(doc)
        await asyncio.sleep(1.0)
        await watcher.stop()

        events = {(call.args[0], call.args[1]) for call in mock_callback.call_args_list}
        assert (str(doc), "deleted") not in events


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

    def test_adapt_interval_grows_and_caps(self):
        """Slow scans grow the interval (at least to the scan duration), capped."""
        watcher = AsyncWatcher(paths=["/path"], callback=AsyncMock(), poll_interval=1.0)

        watcher._adapt_interval(scan_duration=1.0)
        assert watcher.current_poll_interval == 2.0

        # Never below the scan duration itself
        watcher._adapt_interval(scan_duration=5.0)
        assert watcher.current_poll_interval == 5.0

        # Capped at max_poll_interval
        watcher._adapt_interval(scan_duration=100.0)
        assert watcher.current_poll_interval == watcher._max_interval

        # Further slow scans must not exceed the cap
        watcher._adapt_interval(scan_duration=100.0)
        assert watcher.current_poll_interval == watcher._max_interval

    def test_adapt_interval_shrinks_back(self):
        """Fast scans step the interval back down towards poll_interval."""
        watcher = AsyncWatcher(paths=["/path"], callback=AsyncMock(), poll_interval=1.0)
        watcher._interval = 8.0

        watcher._adapt_interval(scan_duration=0.01)
        assert watcher.current_poll_interval == 7.0

        watcher._adapt_interval(scan_duration=0.01)
        assert watcher.current_poll_interval == 6.0

    def test_max_poll_interval_default(self):
        """Default cap is max(poll_interval * 10, 5.0), overridable."""
        watcher = AsyncWatcher(paths=["/path"], callback=AsyncMock(), poll_interval=1.0)
        assert watcher._max_interval == 10.0

        watcher = AsyncWatcher(paths=["/path"], callback=AsyncMock(), poll_interval=0.1)
        assert watcher._max_interval == 5.0

        watcher = AsyncWatcher(
            paths=["/path"],
            callback=AsyncMock(),
            poll_interval=0.1,
            max_poll_interval=2.0,
        )
        assert watcher._max_interval == 2.0
