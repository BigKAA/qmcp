# qmcp - QDrant MCP Server for OpenCode

Semantic search server for code and documentation using Qdrant vector database.

## Overview

qmcp is an MCP (Model Context Protocol) server that provides semantic search capabilities for code and documentation. It integrates with OpenCode CLI to enable intelligent code search using vector embeddings.

## Features

- **Semantic Search**: Find code and documentation using natural language queries
- **Multi-language Support**: Python, Go, JavaScript, TypeScript, Java, C#
- **Live Updates**: File watcher for automatic reindexing
- **Incremental Indexing**: Only index changed files
- **Cleanup**: Remove stale vectors for deleted/changed files
- **Kubernetes Ready**: Helm chart for deployment

## Quick Start

### Local Development

```bash
# Install dependencies
make install

# Run locally
make run
```

### Docker

```bash
# Build image
make build

# Run container
docker run -e QDRANT_URL=http://192.168.218.190:6333 -p 8000:8000 qmcp:latest
```

### Kubernetes

```bash
# Deploy with Helm
helm upgrade --install qmcp ./chart
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `QDRANT_URL` | `http://localhost:6333` | QDrant server URL |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Embedding model |
| `WATCH_PATHS` | `/data/repo` | Paths to watch |
| `BATCH_SIZE` | `50` | Batch size for indexing |
| `DEBOUNCE_SECONDS` | `5` | Debounce delay |

## MCP Tools

| Tool | Description |
|------|-------------|
| `qdrant_search` | Semantic search in code/docs |
| `qdrant_index_directory` | Index a directory |
| `qdrant_reindex` | Reindex (full or incremental) |
| `qdrant_list_collections` | List collections |
| `qdrant_get_collection_info` | Get collection info |
| `qdrant_delete_collection` | Delete collection |
| `qdrant_watch_start` | Start file watcher |
| `qdrant_watch_stop` | Stop file watcher |
| `qdrant_cleanup` | Clean stale vectors |
| `qdrant_get_status` | Server status |

## OpenCode Integration

Add to your OpenCode config (`~/.config/opencode/config.json`):

```json
{
  "mcp": {
    "qmcp": {
      "type": "remote",
      "url": "http://qmcp.default.svc.cluster.local:8000/mcp",
      "enabled": true
    }
  }
}
```

## License

MIT
