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

"""Cross-process single-flight locking.

Several MCP clients (editors, agents) may each spawn their own qmcp server
process, all watching the same trees. Without coordination every file change
is parsed, embedded and uploaded once per process - N-fold duplicated CPU
work that can saturate a workstation.

This module provides a best-effort, non-blocking inter-process lock keyed by
an arbitrary string (typically ``f"{collection}:{file_path}"``). The first
process to grab the lock does the work; the others see ``acquired=False`` and
skip, because the winner's upload makes the result visible to everyone.

The lock is advisory (``flock``) and scoped to the lock file lifetime, so a
crashed holder releases it automatically when the OS closes its descriptors.
On platforms without ``fcntl`` the lock degrades to always-acquired.

``LeaderLock`` extends the same primitive to long-held locks: exactly one
process machine-wide may hold the "leader" role for a key, which is how the
watcher deduplicates filesystem polling across live qmcp instances.
"""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

try:  # POSIX only; degrade gracefully elsewhere
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None  # type: ignore[assignment]


def _lock_file_path(lock_dir: Path, key: str) -> Path:
    """Map a lock key to a file name safe for any filesystem.

    Args:
        lock_dir: Directory holding lock files (created on use).
        key: Arbitrary lock key, e.g. ``"code:/abs/path/file.py"``.

    Returns:
        Path of the lock file inside ``lock_dir``.
    """
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return lock_dir / f"{digest}.lock"


@contextmanager
def try_singleflight(key: str, lock_dir: Path) -> Iterator[bool]:
    """Acquire a non-blocking cross-process lock for ``key``.

    Args:
        key: Lock key - two callers with the same key contend for one lock.
        lock_dir: Directory for lock files; created if missing.

    Yields:
        ``True`` if this caller holds the lock and must do the work,
        ``False`` if another process already holds it and the caller
        should skip.
    """
    if fcntl is None:  # pragma: no cover - non-POSIX platforms
        yield True
        return

    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = _lock_file_path(lock_dir, key)
    handle = open(lock_file, "w")
    acquired = False
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            # Held by another live process - it is doing this work already.
            acquired = False
        yield acquired
    finally:
        if acquired:
            fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


class LeaderLock:
    """Long-held cross-process lock designating the single "leader" for a key.

    ``try_singleflight`` scopes the lock to a ``with`` block, which suits
    one-shot work. Some activities are continuous - the watcher's polling
    loop - and for those the lock must be held for an arbitrary lifetime:
    the holder stays leader until it releases or the process dies (the OS
    then drops the flock, and a standby can take over). This is what keeps
    filesystem polling single-instance machine-wide even when several qmcp
    server processes watch the same trees.

    On platforms without ``fcntl`` the lock always acquires (every process
    is a leader), matching the module's degrade-gracefully policy.
    """

    def __init__(self, key: str, lock_dir: Path):
        """Initialize the lock for ``key`` without acquiring it.

        Args:
            key: Lock key - all processes using the same key elect one leader.
            lock_dir: Directory for lock files; created on acquire.
        """
        self._lock_dir = lock_dir
        self._lock_file = _lock_file_path(lock_dir, key)
        self._handle = None

    def acquire(self) -> bool:
        """Try to become the leader, without blocking.

        Returns:
            ``True`` if this process now holds the lock, ``False`` if
            another live process already leads.
        """
        if fcntl is None:  # pragma: no cover - non-POSIX platforms
            return True

        self._lock_dir.mkdir(parents=True, exist_ok=True)
        # Drop any handle we already hold first: flock is per open file
        # description, so a stale self-held handle would contend with the
        # fresh one and make acquire() always fail.
        self.release()
        handle = open(self._lock_file, "w")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # A live leader exists - stay a standby.
            handle.close()
            return False

        self._handle = handle
        return True

    def release(self) -> None:
        """Give up leadership (idempotent, safe for non-holders)."""
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            handle.close()

    @property
    def is_held(self) -> bool:
        """Whether this process currently holds the lock."""
        return self._handle is not None


def resolve_lock_dir() -> Path:
    """Directory shared by all qmcp processes for locks and registries.

    Explicit ``INDEX_LOCK_DIR`` setting wins; the default lives under the
    user cache dir so independent qmcp processes (one per MCP client) share
    one lock space.

    Returns:
        Path to the lock directory (not created here; callers create on use).
    """
    from .config import get_settings

    configured = get_settings().index_lock_dir
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "qmcp-locks"
