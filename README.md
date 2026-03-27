# qmcp - QDrant MCP Server for OpenCode

Semantic search server for code and documentation using Qdrant vector database.

## Overview

qmcp is an MCP (Model Context Protocol) server that provides semantic search capabilities for code and documentation. It integrates with OpenCode CLI to enable intelligent code search using vector embeddings.

## Features

- **Semantic Search**: Find code and documentation using natural language queries
- **Multi-language Support**: Python, Go, JavaScript, TypeScript, Java, C#, Markdown
- **Live Updates**: File watcher for automatic reindexing
- **Incremental Indexing**: Only index changed files
- **Cleanup**: Remove stale vectors for deleted/changed files

## Quick Start

### 1. Install Dependencies

```bash
make install
```

### 2. Configure OpenCode

Add to `~/.config/opencode/config.json`:

```json
{
  "mcp": {
    "qmcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "python", "-m", "qmcp.server"]
    }
  }
}
```

### 3. Run the Server

```bash
make run-local
```

OpenCode will now have access to semantic search tools.

## Manual Run (Optional)

If you prefer to run the server manually:

```bash
# Terminal 1: Start server
make run-local

# Terminal 2: OpenCode with manual MCP config
opencode --mcp-config manual_config.json
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server URL |
| `QDRANT_API_KEY` | (none) | Qdrant API key (optional) |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Embedding model |
| `WATCH_PATHS` | `/data/repo` | Paths to watch |
| `BATCH_SIZE` | `50` | Batch size for indexing |
| `DEBOUNCE_SECONDS` | `5` | Debounce delay |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `text` | Log format (`text` or `json`) |

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

### Option 1: Quick Setup

1. Run the server in one terminal:
   ```bash
   make run-local
   ```

2. Add to `~/.config/opencode/config.json`:

```json
{
  "mcp": {
    "qmcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "python", "-m", "qmcp.server"]
    }
  }
}
```

### Option 2: Manual MCP Config

For permanent installation, add to your OpenCode config:

```json
{
  "mcp": {
    "qmcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "python", "-m", "qmcp.server"],
      "env": {
        "QDRANT_URL": "http://localhost:6333"
      }
    }
  }
}
```

## Development

```bash
make test        # Run tests
make lint        # Lint code
make format      # Format code
make mcp-dev     # Run with MCP inspector
```

## License

MIT
