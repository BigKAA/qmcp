"""File watcher for qmcp."""

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from watchdog.events import (
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from .logging_config import get_logger


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
    """Async wrapper for file watcher with polling."""

    def __init__(
        self,
        paths: list[str],
        callback: Callable[[str, str], Any],
        poll_interval: float = 1.0,
        debounce_seconds: float = 5.0,
    ):
        """Initialize async watcher.

        Args:
            paths: List of paths to watch
            callback: Async callback for file changes
            poll_interval: How often to check for changes
            debounce_seconds: Debounce delay
        """
        self.logger = get_logger(f"{__name__}.AsyncWatcher")
        self.paths = [Path(p) for p in paths]
        self.callback = callback
        self.poll_interval = poll_interval
        self.debounce_seconds = debounce_seconds

        self._running = False
        self._task: asyncio.Task | None = None
        self._last_mtimes: dict[str, float] = {}
        self._pending: dict[str, tuple[str, float]] = {}

    async def start(self):
        """Start watching."""
        if self._running:
            return

        # Initialize file mtimes
        for path in self.paths:
            if path.exists():
                await self._scan_path(path)

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
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

    async def _scan_path(self, path: Path):
        """Scan path and record file mtimes."""
        if not path.exists():
            return

        if path.is_file():
            try:
                mtime = path.stat().st_mtime
                self._last_mtimes[str(path)] = mtime
            except OSError:
                pass
        elif path.is_dir():
            for file_path in path.rglob("*"):
                if file_path.is_file():
                    try:
                        mtime = file_path.stat().st_mtime
                        self._last_mtimes[str(file_path)] = mtime
                    except OSError:
                        pass

    async def _poll_loop(self):
        """Poll for file changes."""
        while self._running:
            try:
                await self._check_changes()
            except Exception:
                pass

            await asyncio.sleep(self.poll_interval)

    async def _check_changes(self):
        """Check for file changes."""
        current_time = time.time()

        for path in self.paths:
            if not path.exists():
                continue

            # Check all files in path
            for file_path in path.rglob("*"):
                if not file_path.is_file():
                    continue

                file_str = str(file_path)

                try:
                    mtime = file_path.stat().st_mtime
                except OSError:
                    continue

                # New file
                if file_str not in self._last_mtimes:
                    self._last_mtimes[file_str] = mtime
                    self._pending[file_str] = ("created", current_time)

                # Modified file
                elif mtime > self._last_mtimes[file_str]:
                    self._last_mtimes[file_str] = mtime
                    self._pending[file_str] = ("modified", current_time)

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
        """Check if path should be ignored."""
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
