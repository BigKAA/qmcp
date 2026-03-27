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

"""Entry point for running qmcp as a module: python -m qmcp"""

import sys


def main():
    """Run the MCP server."""
    # Import here to avoid issues with relative imports
    import os

    os.environ.setdefault("TRANSPORT", "stdio")

    from qmcp.server import mcp

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    transport = os.getenv("TRANSPORT", "stdio")

    print(f"Starting QDrant MCP Server")
    print(f"Transport: {transport}")
    print(f"Qdrant URL: {qdrant_url}")
    sys.stdout.flush()

    # Run server - FastMCP.run() handles stdio blocking
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
