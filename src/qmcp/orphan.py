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

"""Self-termination guard for orphaned stdio servers.

Unix never kills children of a dead parent - it reparents them to init
(launchd on macOS), and nothing guarantees they exit. A stdio MCP server
normally quits on stdin EOF, but EOF is only delivered when *every* holder
of the pipe closes it (supervisor daemons and Electron-style clients are
prone to inheriting the fd), and a busy event loop can miss it for minutes.

The guard closes both holes transport-independently of the client: a stdio
server records its parent PID at startup, and a background task exits the
process as soon as ``os.getppid()`` changes - which happens exactly once,
when the original parent dies. Enabled only for the stdio transport: under
streamable-http/sse the parent is a service manager whose death must not
kill the server.
"""

import asyncio
import inspect
import os
from collections.abc import Callable
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)

# How often the guard re-checks the parent PID. Cheap (one syscall), but it
# also bounds how long a blocked event loop can delay orphan detection.
CHECK_INTERVAL_SECONDS = 10.0


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
    if transport is None:
        transport = os.getenv("TRANSPORT", "stdio")
    if transport != "stdio":
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
            # Best-effort graceful shutdown; exiting is the goal, so a
            # failing callback must not keep the orphan alive.
            if shutdown is not None:
                try:
                    result = shutdown()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception("Shutdown callback failed; exiting anyway")
            exit_fn(0)
            return

    task = asyncio.create_task(_watch_parent())
    logger.debug("Orphan guard started (parent pid %d)", original_ppid)
    return task
