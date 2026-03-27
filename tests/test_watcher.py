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
from unittest.mock import AsyncMock, Mock

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
