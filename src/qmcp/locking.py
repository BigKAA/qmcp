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
