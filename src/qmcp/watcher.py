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
from collections.abc import Callable, Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any

from watchdog.events import (
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from .locking import LeaderLock
from .logging_config import get_logger

# Directory names that are never worth watching for code changes. They are
# matched by exact name and pruned during traversal, so their contents are
# never stat'ed - this is what keeps baseline scans cheap on huge trees.
# The same names are substring-checked as a final guard on incoming events.
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

# File extensions the watcher reacts to. The platform observer delivers
# events for every file type, so this is the dispatch-time filter; during
# baseline/reconcile traversal it additionally decides what gets stat'ed.
WATCHED_FILE_EXTENSIONS = frozenset({".py", ".go", ".js", ".ts", ".java", ".cs", ".md"})


class AsyncWatcher:
    """Event-driven watcher over watchdog's Observer (FSEvents/inotify/polling
    emitter depending on platform), with debouncing and leader election.

    Design notes:

    - Changes arrive as push events from the OS - no periodic filesystem
      scanning, so idle CPU cost is ~0 regardless of tree size (the 2026-11
      CPU overheat incident: the previous poller walked and stat'ed every
      watched file every 1-10 s per process).
    - Events are debounced latest-event-wins per path on the event loop:
      each inbound event (re)arms a ``call_later`` timer, so an editor's
      rapid saves collapse into one callback, and an atomic save
      (unlink + rename) resolves to indexing, never deletion. Dispatch is
      additionally filtered by extension / hidden name / ignored dirs.
    - Leader election (CPU overheat incident, 2026-11-27): when ``lock_dir``
      is set, exactly one qmcp process machine-wide runs an Observer for
      this watch set. Every watcher instance runs, but non-leaders idle in
      standby - no observer, no callbacks, no CPU - and one of them is
      promoted automatically when the current leader dies (the OS drops
      its flock).
    - Standby gap coverage: a standby takes one baseline snapshot at start
      (background thread) and, on promotion, reconciles it against the
      filesystem once - files changed while nobody watched get their
      events late but never lost. The map is freed right after, so the
      steady state keeps no per-file state at all. A watcher that leads
      from the start skips the snapshot entirely: the Observer sees
      everything from activation onward.
    """

    def __init__(
        self,
        paths: list[str],
        callback: Callable[[str, str], Any],
        debounce_seconds: float = 5.0,
        lock_dir: Path | None = None,
        standby_interval: float = 5.0,
    ):
        """Initialize async watcher.

        Args:
            paths: List of paths to watch
            callback: Async callback for file changes (path, event_type)
            debounce_seconds: Delay between the last event for a path and
                its callback dispatch (latest event wins)
            lock_dir: Directory for the cross-process leader lock. When set,
                watching is single-instance machine-wide (see class docs).
                ``None`` disables leader election (tests, embeds).
            standby_interval: Delay between leader-lock attempts while in
                standby.
        """
        self.logger = get_logger(f"{__name__}.AsyncWatcher")
        self.paths = [Path(p) for p in paths]
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self._lock_dir = lock_dir
        self._standby_interval = standby_interval
        self._leader_lock: LeaderLock | None = (
            LeaderLock(self._leader_key(), lock_dir) if lock_dir is not None else None
        )
        self._role = "solo" if lock_dir is None else "standby"

        self._running = False
        self._task: asyncio.Task | None = None
        self._baseline_task: asyncio.Task | None = None
        self._observer: Observer | None = None
        self._stop_event = asyncio.Event()

        # Loop-thread-only state: pending debounced events and their timers.
        # The Observer's dispatch thread reaches _schedule_event only via
        # call_soon_threadsafe, so no locking is needed.
        self._pending: dict[str, str] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}

        # Fire-and-forget dispatch tasks; a set keeps strong references until
        # done (asyncio only keeps weak references to running tasks, so an
        # unreferenced callback task can be garbage-collected mid-flight and
        # the event silently lost - this actually happened with mocks).
        self._dispatch_tasks: set[asyncio.Task] = set()

        self._loop: asyncio.AbstractEventLoop | None = None

        # Baseline mtime snapshot; populated only when leader election is
        # enabled (a standby may later need to reconcile the standby gap)
        # and freed after the promotion reconcile.
        self._last_mtimes: dict[str, float] = {}

    def _leader_key(self) -> str:
        """Build the cross-process leader key for this watch set.

        Returns:
            Lock key stable across processes watching the same paths.
        """
        joined = ",".join(sorted(str(p) for p in self.paths))
        return f"watcher:{joined}"

    async def start(self):
        """Start watching.

        Returns immediately: contention, the Observer and the baseline
        snapshot all run inside background tasks, so MCP server startup
        stays fast even on very large directory trees.
        """
        if self._running:
            return

        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._running = True

        # A standby needs a start-time snapshot to reconcile the gap when
        # it is eventually promoted; a from-the-start leader does not (the
        # Observer sees everything from activation onward).
        if self._leader_lock is not None:
            self._baseline_task = asyncio.create_task(asyncio.to_thread(self._scan_all_paths))

        self._task = asyncio.create_task(self._run())
        self.logger.info(f"Started async watching {len(self.paths)} paths (role={self._role})")

    async def stop(self):
        """Stop watching and release all OS and lock resources."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        if self._baseline_task is not None:
            self._baseline_task.cancel()
            self._baseline_task = None

        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()
        self._pending.clear()

        # Let in-flight dispatch callbacks finish before tearing down
        if self._dispatch_tasks:
            await asyncio.gather(*list(self._dispatch_tasks), return_exceptions=True)

        if self._observer is not None:
            await asyncio.to_thread(self._stop_observer)
            self._observer = None

        if self._leader_lock is not None:
            self._leader_lock.release()
        self.logger.info("Stopped async watching")

    async def _run(self):
        """Contend for leadership, then watch via the platform Observer.

        Standbys retry the (non-blocking) leader lock every
        ``standby_interval`` seconds; promotion happens by itself when the
        current leader process dies and the OS drops its flock.
        """
        if self._leader_lock is None:
            self._role = "solo"
            await self._activate()
            return

        while self._running:
            if self._leader_lock.acquire():
                self._role = "leader"
                self.logger.info(
                    "Won watcher leader lock - this process watches via the platform observer"
                )
                try:
                    await self._activate()
                finally:
                    self._leader_lock.release()
                return

            self._role = "standby"
            try:
                # Sleep in small standby_interval chunks so stop() is quick
                # even from standby.
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._standby_interval)
                return  # stop requested while standby
            except TimeoutError:
                continue

    async def _activate(self):
        """Bring up the Observer for this process's leadership tenure.

        The Observer starts first so the event stream covers the whole
        tenure; the baseline reconcile that may follow only reports
        changes that happened *before* activation (the standby gap).
        """
        observer = Observer()
        handler = _EventHandler(self)
        for path in self.paths:
            if path.exists():
                observer.schedule(handler, str(path), recursive=True)
        observer.start()
        self._observer = observer

        # A promoted standby waits for its start-time snapshot, then diffs
        # it against the filesystem once to cover the standby gap. The map
        # is freed afterwards: from here on the Observer owns change
        # tracking and the steady state keeps no per-file state.
        if self._baseline_task is not None:
            with suppress(asyncio.CancelledError):
                await self._baseline_task
            self._baseline_task = None
            if self._last_mtimes:
                await asyncio.to_thread(self._reconcile)

        await self._stop_event.wait()

    def _stop_observer(self) -> None:
        """Stop the Observer and join its threads (runs in a worker thread)."""
        observer, self._observer = self._observer, None
        if observer is None:
            return
        try:
            observer.stop()
            observer.join()
        except Exception:
            self.logger.exception("Failed to stop filesystem observer cleanly")

    def _reconcile(self) -> None:
        """Report changes made since this process's baseline snapshot.

        Runs synchronously in a worker thread - always invoke via
        ``asyncio.to_thread``. Events are marshalled onto the event loop
        and go through the same debounce as live Observer events.
        """
        current: dict[str, float] = {}
        for path in self.paths:
            for file_path in self._iter_watch_files(path):
                self._stat_file(file_path, current)

        events: list[tuple[str, str]] = []
        for file_str, mtime in current.items():
            last_mtime = self._last_mtimes.get(file_str)
            if last_mtime is None:
                events.append((file_str, "created"))
            elif mtime > last_mtime:
                events.append((file_str, "modified"))
        for file_str in set(self._last_mtimes) - current.keys():
            events.append((file_str, "deleted"))

        self._last_mtimes.clear()
        if events:
            self.logger.info("Reconciled %d change(s) missed during standby", len(events))
            self._post_batch(events)

    # ------------------------------------------------------------------
    # Event intake (Observer dispatch thread -> event loop)
    # ------------------------------------------------------------------

    def _post(self, path: str, event_type: str) -> None:
        """Marshal a raw Observer event onto the event loop (thread-safe)."""
        if self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._schedule_event, path, event_type)
        except RuntimeError:
            # Event loop already closed during shutdown - nothing to deliver.
            pass

    def _post_batch(self, events: list[tuple[str, str]]) -> None:
        """Marshal a batch of reconcile events onto the event loop."""
        if self._loop is None or not events:
            return
        try:
            self._loop.call_soon_threadsafe(self._apply_batch, events)
        except RuntimeError:
            pass

    def _apply_batch(self, events: list[tuple[str, str]]) -> None:
        """Schedule a batch of events on the event loop thread."""
        for path, event_type in events:
            self._schedule_event(path, event_type)

    def _schedule_event(self, path: str, event_type: str) -> None:
        """Record an event and (re)arm its debounce timer.

        Event-loop-thread only. The pending map keeps only the latest event
        per path, so an editor's rapid saves collapse into one dispatch and
        an atomic save (delete + recreate, or rename over the target) can
        never resolve to dropping the file's index.
        """
        if not self._running:
            return
        self._pending[path] = event_type
        old_timer = self._timers.pop(path, None)
        if old_timer is not None:
            old_timer.cancel()
        self._timers[path] = self._loop.call_later(self.debounce_seconds, self._fire, path)

    def _fire(self, path: str) -> None:
        """Dispatch a debounced event if it survived the debounce window."""
        self._timers.pop(path, None)
        event_type = self._pending.pop(path, None)
        if event_type is None or not self._running:
            return
        if self._should_ignore(path):
            return
        task = asyncio.create_task(self._run_callback(path, event_type))
        self._dispatch_tasks.add(task)
        task.add_done_callback(self._dispatch_tasks.discard)

    async def _run_callback(self, path: str, event_type: str):
        """Run the callback."""
        if asyncio.iscoroutinefunction(self.callback):
            await self.callback(path, event_type)
        else:
            self.callback(path, event_type)

    # ------------------------------------------------------------------
    # Path filtering
    # ------------------------------------------------------------------

    def _should_ignore(self, path: str) -> bool:
        """Check whether a path can never trigger an index change.

        Final guard before callbacks: hidden files, ignored directories
        (substring match, as before) and files with extensions outside
        ``WATCHED_FILE_EXTENSIONS`` are all dropped - the platform observer
        delivers events for every file type.
        """
        path_obj = Path(path)

        if path_obj.name.startswith("."):
            return True

        for pattern in IGNORED_DIR_NAMES:
            if pattern in path:
                return True

        return path_obj.suffix not in WATCHED_FILE_EXTENSIONS

    # ------------------------------------------------------------------
    # Baseline snapshot traversal (worker-thread only)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def role(self) -> str:
        """This watcher's role in leader election.

        Returns:
            ``"leader"`` while this process holds the lock and watches,
            ``"standby"`` while another process leads,
            ``"solo"`` when leader election is disabled.
        """
        return self._role

    @property
    def is_polling(self) -> bool:
        """Whether this instance actively watches the filesystem right now.

        Distinct from ``is_running``: a standby watcher runs (its task is
        alive, it waits for promotion) but runs no Observer, so it costs
        no CPU.
        """
        return self._running and self._role != "standby"


class _EventHandler(FileSystemEventHandler):
    """Translate watchdog events into debounced watcher events.

    Runs on the Observer's dispatch thread; everything is marshalled onto
    the watcher's event loop. Directory events are dropped: FSEvents and
    inotify deliver per-file events for file content, so directory events
    carry no indexable payload.
    """

    def __init__(self, watcher: AsyncWatcher):
        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        self._forward(event, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        self._forward(event, "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._forward(event, "deleted")

    def on_moved(self, event: FileSystemEvent) -> None:
        """A rename is a deletion at the source plus a creation at the target.

        Covers atomic editors' saves (write temp file, rename over the
        target): the target gets reindexed and the temp path is dropped by
        the extension/hidden filters.
        """
        if event.is_directory:
            return
        self._watcher._post(str(event.src_path), "deleted")
        self._watcher._post(str(event.dest_path), "created")

    def _forward(self, event: FileSystemEvent, event_type: str) -> None:
        if event.is_directory:
            return
        self._watcher._post(str(event.src_path), event_type)
