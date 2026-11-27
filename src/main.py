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

"""Main entry point for qmcp server."""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qmcp.logging_config import get_logger
from qmcp.server import mcp

# Importing qmcp.server initializes logging (logs go to stderr, so the MCP
# stdio protocol on stdout is never polluted).
logger = get_logger(__name__)


def main():
    """Run the MCP server."""
    # Get configuration
    transport = os.getenv("TRANSPORT", "stdio")

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    logger.info("Starting QDrant MCP Server (transport=%s, qdrant_url=%s)", transport, qdrant_url)

    # Run server (MCP SDK v2: transport options go to run(), not the constructor)
    if transport == "streamable-http":
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "8000"))
        mcp.run(transport=transport, host=host, port=port, json_response=True)
    else:
        mcp.run(transport=transport)

    # run() returning means the client disconnected and the lifespan already
    # cleaned up. Lingering non-daemon threads (thread pool workers, native
    # runtimes) must not keep a dead connection's process alive: exit hard
    # instead of falling through to interpreter shutdown.
    logger.info("MCP server stopped; exiting")
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
