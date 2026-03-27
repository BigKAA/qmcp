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

from qmcp.server import mcp


def main():
    """Run the MCP server."""
    # Get configuration
    transport = os.getenv("TRANSPORT", "stdio")

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    print("Starting QDrant MCP Server")
    print(f"Transport: {transport}")
    print(f"Qdrant URL: {qdrant_url}")

    # Run server
    if transport == "streamable-http":
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "8000"))
        mcp.run(transport=transport, host=host, port=port)
    else:
        mcp.run(transport=transport)


if __name__ == "__main__":
    main()
