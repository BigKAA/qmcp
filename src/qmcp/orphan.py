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

"""Self-termination guards for orphaned stdio servers.

Unix never kills children of a dead parent - it reparents them to init
(launchd on macOS), and nothing guarantees they exit. A stdio MCP server
normally quits on stdin EOF, but EOF is only delivered when *every* holder
of the pipe closes it (supervisor daemons and Electron-style clients are
prone to inheriting the fd), and a busy event loop can miss it for minutes.

Worse (CPU overheat incident, 2026-11-27): a *living* client that abandons
a connection never triggers EOF at all - the inherited fd keeps the pipe
open forever, so reconnect-happy clients accumulate zombie servers whose
watchers poll the filesystem around the clock.

Three transport-independent guards close these holes; all are stdio-only
because under streamable-http/sse the server is a service-managed daemon:

- **Orphan guard** - exits when ``os.getppid()`` changes (the original
  parent died and the process was reparented).
- **Idle guard** - exits after a configurable period without any inbound
  MCP traffic. Kills abandoned connections whose parent is still alive.
- **Replacement guard** - exits when a *newer* server instance from the
  *same* client (same parent PID) has registered itself and this one has
  been idle for a grace period. Kills the reconnect leftovers (one client
  holding several stale copies) without ever touching a server that is
  still serving traffic.
"""

import asyncio
import inspect
import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)

# How often the guards re-check their condition. Cheap (one syscall), but it
# also bounds how long a blocked event loop can delay orphan detection.
CHECK_INTERVAL_SECONDS = 10.0

# How long a replaced instance must be idle before it exits. Clients may
# legitimately multiplex several concurrent connections; only an idle
# leftover is safe to reap.
REPLACEMENT_GRACE_SECONDS = 300.0


def _resolve_transport(transport: str | None) -> str:
    """Read the TRANSPORT env var the same way the entry points do."""
    if transport is None:
        return os.getenv("TRANSPORT", "stdio")
    return transport


async def _shutdown_and_exit(
    shutdown: Callable[[], Any] | None,
    exit_fn: Callable[[int], None],
) -> None:
    """Best-effort graceful shutdown, then hard process exit.

    Exiting is the goal, so a failing shutdown callback must not keep the
    process alive.
    """
    if shutdown is not None:
        try:
            result = shutdown()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("Shutdown callback failed; exiting anyway")
    exit_fn(0)


def start_orphan_guard(
    shutdown: Callable[[], Any] | None = None,
    check_interval: float = CHECK_INTERVAL_SECONDS,
    exit_fn: Callable[[int], None] = os._exit,
    transport: str | None = None,
) -> asyncio.Task | None:
    """Start a task that terminates the process when its parent goes away.

    Args:
        shutdown: Optional (async) callback invoked before exiting - used to
            stop the file watcher so no indexing task straddles the exit.
        check_interval: Seconds between parent PID checks.
        exit_fn: Exit primitive, injectable for tests.
        transport: Transport name; ``None`` reads the TRANSPORT env var the
            same way the entry points do (default ``stdio``).

    Returns:
        The guard task, or ``None`` when the guard is disabled (any
        non-stdio transport).
    """
    if _resolve_transport(transport) != "stdio":
        logger.debug("Orphan guard disabled for transport=%s", transport)
        return None

    original_ppid = os.getppid()

    async def _watch_parent() -> None:
        while True:
            await asyncio.sleep(check_interval)
            if os.getppid() == original_ppid:
                continue

            logger.warning(
                "Parent process %d is gone (ppid now %d) - this stdio server "
                "is orphaned, shutting down",
                original_ppid,
                os.getppid(),
            )
            await _shutdown_and_exit(shutdown, exit_fn)
            return

    task = asyncio.create_task(_watch_parent())
    logger.debug("Orphan guard started (parent pid %d)", original_ppid)
    return task


def start_idle_guard(
    shutdown: Callable[[], Any] | None = None,
    timeout_seconds: float = 0.0,
    idle_seconds: Callable[[], float] | None = None,
    is_active: Callable[[], bool] | None = None,
    check_interval: float = CHECK_INTERVAL_SECONDS,
    exit_fn: Callable[[int], None] = os._exit,
    transport: str | None = None,
) -> asyncio.Task | None:
    """Start a task that terminates the process after an idle period.

    An abandoned stdio connection (client alive, fd inherited by a terminal
    or supervisor) never delivers EOF, so traffic is the only reliable
    liveness signal: when no MCP message has arrived for ``timeout_seconds``
    and no work is in flight, the server shuts itself down. Clients respawn
    their server on the next tool call.

    Args:
        shutdown: Optional (async) callback invoked before exiting - used to
            stop the file watcher so no indexing task straddles the exit.
        timeout_seconds: Idle period after which to exit; ``0`` disables the
            guard entirely.
        idle_seconds: Returns seconds since the last inbound MCP message.
        is_active: Returns ``True`` while a request or indexing task is in
            flight - activity in progress must never be cut short.
        check_interval: Seconds between idle checks.
        exit_fn: Exit primitive, injectable for tests.
        transport: Transport name; ``None`` reads the TRANSPORT env var the
            same way the entry points do (default ``stdio``).

    Returns:
        The guard task, or ``None`` when the guard is disabled (any
        non-stdio transport, or a zero timeout).
    """
    if _resolve_transport(transport) != "stdio":
        logger.debug("Idle guard disabled for transport=%s", transport)
        return None
    if timeout_seconds <= 0:
        logger.debug("Idle guard disabled (timeout=%s)", timeout_seconds)
        return None
    if idle_seconds is None or is_active is None:
        raise ValueError("idle_seconds and is_active are required")

    async def _watch_idle() -> None:
        while True:
            await asyncio.sleep(check_interval)
            if is_active():
                continue
            idle_for = idle_seconds()
            if idle_for < timeout_seconds:
                continue

            logger.warning(
                "No MCP traffic for %.0f s (timeout %.0f s) - shutting down "
                "the idle stdio server; the client will respawn it on demand",
                idle_for,
                timeout_seconds,
            )
            await _shutdown_and_exit(shutdown, exit_fn)
            return

    task = asyncio.create_task(_watch_idle())
    logger.debug("Idle guard started (timeout %.0f s)", timeout_seconds)
    return task


def _pid_alive(pid: int) -> bool:
    """Check whether a process with this PID exists.

    Args:
        pid: Process ID to probe.

    Returns:
        ``True`` when the process exists (signal 0 succeeded or we lack
        permission to probe it), ``False`` when it is gone.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        # PermissionError et al.: the process exists, it is just not ours.
        return True
    return True


def _registry_record_path(registry_dir: Path, parent_pid: int) -> Path:
    """Map a parent PID to its instance-registry file.

    Args:
        registry_dir: Shared directory for lifecycle registries.
        parent_pid: Parent (client) process PID.

    Returns:
        Path of the JSON file where instances spawned by that client
        register themselves.
    """
    return registry_dir / f"stdio-instance-{parent_pid}.json"


def _read_record(path: Path) -> dict[str, Any] | None:
    """Read a registry record, tolerating absence and corruption."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_record(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write a registry record (rename, so readers never tear)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp_path, path)


def start_replacement_guard(
    shutdown: Callable[[], Any] | None = None,
    registry_dir: Path | None = None,
    grace_seconds: float = REPLACEMENT_GRACE_SECONDS,
    idle_seconds: Callable[[], float] | None = None,
    check_interval: float = CHECK_INTERVAL_SECONDS,
    exit_fn: Callable[[int], None] = os._exit,
    transport: str | None = None,
    pid: int | None = None,
    now_fn: Callable[[], float] = time.time,
    pid_alive: Callable[[int], bool] = _pid_alive,
) -> asyncio.Task | None:
    """Start a task that exits this process when a newer sibling replaces it.

    Reconnect-happy clients spawn a fresh server per reconnection but leave
    the old one running (no EOF, parent alive - see module docs). Each
    stdio instance registers ``(pid, started)`` in a per-parent-PID file
    inside ``registry_dir``; when this instance sees a *newer*, *live*
    registration from the same client and has itself been idle for
    ``grace_seconds``, it exits. The idle grace keeps clients that
    legitimately multiplex several concurrent connections safe: a server
    still serving traffic is never reaped.

    Args:
        shutdown: Optional (async) callback invoked before exiting - used to
            stop the file watcher so no indexing task straddles the exit.
        registry_dir: Shared directory for the instance registry; defaults to
            the cross-process lock directory (``INDEX_LOCK_DIR`` or
            ``~/.cache/qmcp-locks``).
        grace_seconds: Idle period that must pass before a replaced instance
            exits.
        idle_seconds: Returns seconds since the last inbound MCP message.
        check_interval: Seconds between registry checks.
        exit_fn: Exit primitive, injectable for tests.
        transport: Transport name; ``None`` reads the TRANSPORT env var the
            same way the entry points do (default ``stdio``).
        pid: This process's PID; defaults to ``os.getpid()`` (injectable for
            tests).
        now_fn: Wall-clock source (injectable for tests).
        pid_alive: Liveness probe (injectable for tests).

    Returns:
        The guard task, or ``None`` when the guard is disabled (any
        non-stdio transport).
    """
    if _resolve_transport(transport) != "stdio":
        logger.debug("Replacement guard disabled for transport=%s", transport)
        return None

    if registry_dir is None:
        from .locking import resolve_lock_dir

        registry_dir = resolve_lock_dir()
    if idle_seconds is None:
        raise ValueError("idle_seconds is required")

    own_pid = os.getpid() if pid is None else pid
    parent_pid = os.getppid()
    record_path = _registry_record_path(registry_dir, parent_pid)
    started_at = now_fn()

    async def _watch_replacement() -> None:
        while True:
            await asyncio.sleep(check_interval)
            other = _read_record(record_path)
            if (
                other is not None
                and other.get("pid") is not None
                and other["pid"] != own_pid
                and other.get("started", 0.0) > started_at
                and pid_alive(int(other["pid"]))
            ):
                idle_for = idle_seconds()
                if idle_for < grace_seconds:
                    # Still serving traffic - this client multiplexes
                    # connections; re-check on the next tick.
                    continue

                logger.warning(
                    "Replaced by a newer stdio server (pid %s) from the same "
                    "client (parent pid %d) and idle for %.0f s - shutting "
                    "down this leftover instance",
                    other["pid"],
                    parent_pid,
                    idle_for,
                )
                await _shutdown_and_exit(shutdown, exit_fn)
                return

            # Reclaim the record: either no sibling registered yet, or it is
            # older/dead (stale file from a recycled PID).
            _write_record(record_path, {"pid": own_pid, "started": started_at})

    task = asyncio.create_task(_watch_replacement())
    logger.debug(
        "Replacement guard started (pid %d, parent pid %d, registry %s)",
        own_pid,
        parent_pid,
        record_path,
    )
    return task
