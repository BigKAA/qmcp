#!/bin/bash
set -e

echo "Starting QDrant MCP Server..."
echo "QDRANT_URL: ${QDRANT_URL:-http://localhost:6333}"
echo "EMBEDDING_MODEL: ${EMBEDDING_MODEL:-BAAI/bge-small-en-v1.5}"
echo "WATCH_PATHS: ${WATCH_PATHS:-/data/repo}"

exec python -m qmcp.server "$@"
