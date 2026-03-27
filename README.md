# qmcp - QDrant MCP Server for OpenCode

Semantic search server for code and documentation using Qdrant vector database.

## Features

- **Semantic Search**: Find code and documentation using natural language queries
- **Multi-language Support**: Python, Go, JavaScript, TypeScript, Java, C#, Markdown
- **Live Updates**: File watcher for automatic reindexing
- **Incremental Indexing**: Only index changed files
- **Cleanup**: Remove stale vectors for deleted/changed files

## Installation

### Via PyPI (Recommended)

```bash
pip install qmcp
```

### Via uv

```bash
uv tool install qmcp
```

### From Source

```bash
git clone https://github.com/BigKAA/qmcp.git
cd qmcp
make install
```

## Quick Start

### 1. Ensure Qdrant is running

```bash
# Use existing Qdrant instance
export QDRANT_URL=http://localhost:6333
```

### 2. Add MCP Server to OpenCode

```bash
opencode mcp add qmcp -- qmcp
```

With custom Qdrant URL:

```bash
QDRANT_URL=http://192.168.218.190:6333 opencode mcp add qmcp -- qmcp
```

### 3. That's It!

OpenCode will automatically discover and use the semantic search tools.

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

### Add MCP Server

```bash
opencode mcp add qmcp -- qmcp
```

### Manage MCP Servers

```bash
opencode mcp list          # List all MCP servers
opencode mcp debug qmcp     # Debug connection issues
opencode mcp logout qmcp    # Remove MCP server
```

## Development

```bash
make install      # Install dependencies
make test         # Run tests
make lint         # Lint code
make format       # Format code
make mcp-dev      # Run with MCP inspector
```

## License

Apache 2.0
