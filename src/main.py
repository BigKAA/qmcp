"""Main entry point for qmcp server."""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qmcp.server import mcp


def main():
    """Run the MCP server."""
    # Get configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    transport = os.getenv("TRANSPORT", "streamable-http")

    print(f"Starting QDrant MCP Server on {host}:{port}")
    print(f"Transport: {transport}")
    print(f"Qdrant URL: {os.getenv('QDRANT_URL', 'http://localhost:6333')}")

    # Run server
    mcp.run(host=host, port=port, transport=transport)


if __name__ == "__main__":
    main()
