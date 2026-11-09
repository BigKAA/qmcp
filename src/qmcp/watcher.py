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

"""File watcher for qmcp."""

import asyncio
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from watchdog.events import (
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from .logging_config import get_logger

# Directory names that are never worth watching for code changes. They are
# matched by exact name and pruned during traversal, so their contents are
# never stat'ed - this is what keeps scans cheap on huge trees.
IGNORED_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".git",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
        "node_modules",
        ".venv",
        "venv",
    }
)

# File extensions the async watcher reacts to. Files with other extensions
# are skipped during traversal, so editing them never triggers reindexing.
WATCHED_FILE_EXTENSIONS = frozenset({".py", ".go", ".js", ".ts", ".java", ".cs", ".md"})


class FileChangeHandler(FileSystemEventHandler):
    """Handler for file system events."""

    def __init__(
        self,
        callback: Callable[[str, str], None],
        debounce_seconds: float = 2.0,
    ):
        """Initialize handler.

        Args:
            callback: Function to call on file changes (path, event_type)
            debounce_seconds: Time to wait before processing
        """
        self.logger = get_logger(f"{__name__}.FileChangeHandler")
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.pending_events: dict[str, tuple[str, float]] = {}

    def on_modified(self, event: FileSystemEvent):
        """Handle file modification."""
        if not event.is_directory:
            self.logger.debug(f"File modified: {event.src_path}")
            self._schedule_event(event.src_path, "modified")

    def on_created(self, event: FileSystemEvent):
        """Handle file creation."""
        if not event.is_directory:
            self.logger.debug(f"File created: {event.src_path}")
            self._schedule_event(event.src_path, "created")

    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion."""
        if not event.is_directory:
            self.logger.debug(f"File deleted: {event.src_path}")
            self._schedule_event(event.src_path, "deleted")

    def _schedule_event(self, path: str, event_type: str):
        """Schedule an event with debouncing."""
        self.pending_events[path] = (event_type, time.time())

    def process_pending(self):
        """Process pending events that have passed the debounce period."""
        current_time = time.time()
        processed = []

        for path, (event_type, timestamp) in list(self.pending_events.items()):
            if current_time - timestamp >= self.debounce_seconds:
                self.callback(path, event_type)
                processed.append(path)
                del self.pending_events[path]

        return processed


class Watcher:
    """File system watcher with debouncing."""

    def __init__(
        self,
        paths: list[str],
        callback: Callable[[str, str], None],
        debounce_seconds: float = 5.0,
    ):
        """Initialize watcher.

        Args:
            paths: List of paths to watch
            callback: Callback for file changes (path, event_type)
            debounce_seconds: Debounce delay
        """
        self.logger = get_logger(f"{__name__}.Watcher")
        self.paths = [Path(p) for p in paths]
        self.callback = callback
        self.debounce_seconds = debounce_seconds

        self._handler = FileChangeHandler(
            callback=self._handle_event,
            debounce_seconds=debounce_seconds,
        )
        self._observer = Observer()
        self._running = False

    def _handle_event(self, path: str, event_type: str):
        """Internal event handler."""
        # Skip hidden files and common non-code files
        if self._should_ignore(path):
            return

        self.callback(path, event_type)

    def _should_ignore(self, path: str) -> bool:
        """Check if path should be ignored."""
        # Ignore patterns
        ignore_patterns = [
            "__pycache__",
            ".git",
            ".pytest_cache",
            "node_modules",
            ".venv",
            "venv",
            ".mypy_cache",
            ".ruff_cache",
            ".idea",
            ".vscode",
        ]

        path_obj = Path(path)
        name = path_obj.name

        # Ignore hidden files
        if name.startswith("."):
            return True

        # Ignore patterns in path
        for pattern in ignore_patterns:
            if pattern in path:
                return True

        # Only process supported extensions
        supported = [".py", ".go", ".js", ".ts", ".java", ".cs", ".md"]
        if path_obj.suffix not in supported:
            return True

        return False

    def start(self):
        """Start watching paths."""
        if self._running:
            return

        for path in self.paths:
            if path.exists():
                self._observer.schedule(self._handler, str(path), recursive=True)

        self._observer.start()
        self._running = True
        self.logger.info(f"Started watching {len(self.paths)} paths")

    def stop(self):
        """Stop watching."""
        if not self._running:
            return

        self._observer.stop()
        self._observer.join()
        self._running = False
        self.logger.info("Stopped watching")

    @property
    def is_running(self) -> bool:
        return self._running

    def process_pending(self):
        """Process any pending file events."""
        return self._handler.process_pending()


class AsyncWatcher:
    """Async polling watcher with debouncing and adaptive polling.

    Design notes (GitHub issue #1 - blocking scans on large WATCH_PATHS):
    - The baseline scan and periodic re-scans run in a worker thread
      (``asyncio.to_thread``) so the event loop stays responsive even on
      trees with hundreds of thousands of files.
    - Ignored directories are pruned *during* traversal (``os.walk``
      ``dirnames`` filtering) instead of being fully scanned with
      ``rglob`` and filtered afterwards.
    - The poll interval adapts to the measured scan duration: slow scans
      grow the interval (up to ``max_poll_interval``), fast scans shrink
      it back towards ``poll_interval``.
    """

    def __init__(
        self,
        paths: list[str],
        callback: Callable[[str, str], Any],
        poll_interval: float = 1.0,
        debounce_seconds: float = 5.0,
        max_poll_interval: float | None = None,
    ):
        """Initialize async watcher.

        Args:
            paths: List of paths to watch
            callback: Async callback for file changes
            poll_interval: Base (minimum) delay in seconds between filesystem
                scans. The effective interval may grow adaptively up to
                ``max_poll_interval`` when scans are slow.
            debounce_seconds: Debounce delay
            max_poll_interval: Upper bound for the adaptive poll interval.
                Defaults to ``max(poll_interval * 10, 5.0)``.
        """
        self.logger = get_logger(f"{__name__}.AsyncWatcher")
        self.paths = [Path(p) for p in paths]
        self.callback = callback
        self.poll_interval = poll_interval
        self.debounce_seconds = debounce_seconds

        self._min_interval = poll_interval
        self._max_interval = (
            max_poll_interval if max_poll_interval is not None else max(poll_interval * 10, 5.0)
        )
        self._interval = poll_interval

        self._running = False
        self._task: asyncio.Task | None = None
        self._last_mtimes: dict[str, float] = {}
        self._pending: dict[str, tuple[str, float]] = {}

    async def start(self):
        """Start watching.

        Returns immediately: the baseline snapshot is built inside the
        background task (in a worker thread) and change events only fire
        after it completes. This keeps MCP server startup fast even when
        watching very large directory trees.
        """
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        self.logger.info(f"Started async watching {len(self.paths)} paths")

    async def stop(self):
        """Stop watching."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.logger.info("Stopped async watching")

    async def _run(self):
        """Build the baseline snapshot off the event loop, then poll."""
        await asyncio.to_thread(self._scan_all_paths)
        await self._poll_loop()

    def _scan_all_paths(self) -> None:
        """Snapshot mtimes for every watched path (runs in a worker thread)."""
        for path in self.paths:
            self._scan_path(path)

    def _scan_path(self, path: Path) -> None:
        """Record mtimes for all watchable files under a watched path.

        Runs synchronously - always invoke it via ``asyncio.to_thread`` so
        the event loop is not blocked by the filesystem walk.

        Args:
            path: Watched file or directory path. Missing paths are skipped.
        """
        for file_path in self._iter_watch_files(path):
            self._stat_file(file_path, self._last_mtimes)

    def _collect_snapshot(self) -> dict[str, float]:
        """Build a fresh ``{path: mtime}`` snapshot of all watched files.

        Runs synchronously in a worker thread; ignored directories are
        pruned during traversal, so their contents are never stat'ed.

        Returns:
            Snapshot mapping absolute file paths to mtimes.
        """
        snapshot: dict[str, float] = {}
        for path in self.paths:
            for file_path in self._iter_watch_files(path):
                self._stat_file(file_path, snapshot)
        return snapshot

    @staticmethod
    def _stat_file(file_path: Path, snapshot: dict[str, float]) -> None:
        """Store a file's mtime in a snapshot, tolerating stat errors."""
        try:
            snapshot[str(file_path)] = file_path.stat().st_mtime
        except OSError:
            pass

    def _iter_watch_files(self, path: Path) -> Iterator[Path]:
        """Yield files under a watched path that can trigger change events.

        Directories whose names are in ``IGNORED_DIR_NAMES`` (plus every
        hidden directory) are pruned during the walk, and only files with
        watched extensions are yielded. A watched file path yields itself
        when it is watchable.

        Args:
            path: Watched file or directory path.

        Yields:
            ``Path`` objects for files that should be tracked.
        """
        if not path.exists():
            return

        if path.is_file():
            if self._is_watchable_file(path):
                yield path
            return

        def _on_walk_error(error: OSError):
            self.logger.debug(f"Error while scanning {error.filename}: {error}")

        for dirpath, dirnames, filenames in os.walk(path, onerror=_on_walk_error):
            # Prune ignored directories in place (topdown walk), so the
            # walker never descends into them.
            dirnames[:] = [
                name
                for name in dirnames
                if name not in IGNORED_DIR_NAMES and not name.startswith(".")
            ]
            for filename in filenames:
                file_path = Path(dirpath) / filename
                if self._is_watchable_file(file_path):
                    yield file_path

    @staticmethod
    def _is_watchable_file(file_path: Path) -> bool:
        """Check whether a single file can trigger watch events.

        Hidden files (``.env``, ``.DS_Store``, ...) and files with
        extensions outside ``WATCHED_FILE_EXTENSIONS`` are skipped.
        """
        return not file_path.name.startswith(".") and file_path.suffix in WATCHED_FILE_EXTENSIONS

    async def _poll_loop(self):
        """Poll for file changes, adapting the interval to scan cost."""
        while self._running:
            started_at = time.monotonic()
            try:
                await self._check_changes()
            except Exception as exc:
                self.logger.exception("Error while checking for file changes: %s", exc)

            scan_duration = time.monotonic() - started_at
            self._adapt_interval(scan_duration)
            await asyncio.sleep(self._interval)

    def _adapt_interval(self, scan_duration: float) -> None:
        """Adjust the poll interval based on the measured scan duration.

        When a scan takes at least as long as the current interval, the
        interval doubles (never dropping below the scan duration itself, up
        to ``max_poll_interval``), so huge trees are not re-scanned every
        second; after fast scans it steps back down towards ``poll_interval``.

        Args:
            scan_duration: How long the last scan took, in seconds.
        """
        if scan_duration >= self._interval:
            self._interval = min(max(self._interval * 2, scan_duration), self._max_interval)
        else:
            self._interval = max(self._min_interval, self._interval - self._min_interval)

    async def _check_changes(self):
        """Diff a fresh filesystem snapshot against the last known state.

        The snapshot is collected in a worker thread; only the diff and the
        debounced callback dispatch run on the event loop.
        """
        current_files = await asyncio.to_thread(self._collect_snapshot)
        current_time = time.time()

        for file_str, mtime in current_files.items():
            last_mtime = self._last_mtimes.get(file_str)
            if last_mtime is None:
                self._pending[file_str] = ("created", current_time)
            elif mtime > last_mtime:
                self._pending[file_str] = ("modified", current_time)
            self._last_mtimes[file_str] = mtime

        # Process pending events
        to_process = []
        for file_str, (event_type, timestamp) in list(self._pending.items()):
            if current_time - timestamp >= self.debounce_seconds:
                to_process.append((file_str, event_type))
                del self._pending[file_str]

        # Process events
        for file_str, event_type in to_process:
            if not self._should_ignore(file_str):
                await self._run_callback(file_str, event_type)

    def _should_ignore(self, path: str) -> bool:
        """Check if path should be ignored (final guard before callbacks)."""
        ignore_patterns = [
            "__pycache__",
            ".git",
            ".pytest_cache",
            "node_modules",
            ".venv",
            "venv",
        ]

        for pattern in ignore_patterns:
            if pattern in path:
                return True

        return False

    async def _run_callback(self, path: str, event_type: str):
        """Run the callback."""
        if asyncio.iscoroutinefunction(self.callback):
            await self.callback(path, event_type)
        else:
            self.callback(path, event_type)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_poll_interval(self) -> float:
        """Effective poll interval in seconds (adapts between min and max)."""
        return self._interval
