# qmcp - QDrant MCP Server for OpenCode

Semantic search server for code and documentation using Qdrant vector database.

## Features

- **Semantic Search**: Find code and documentation using natural language queries
- **Multi-language Support**: Python, Go, JavaScript, TypeScript, Java, C#, Markdown
- **Live Updates**: File watcher for automatic reindexing
- **Incremental Indexing**: Only index changed files
- **Cleanup**: Remove stale vectors for deleted/changed files
- **Diagnostics**: Introspection tools to understand what's indexed
- **OpenCode Skill**: Natural language interface for Qdrant management

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

For Kubernetes deployment, see [Qdrant on Kubernetes](https://github.com/BigKAA/youtube/tree/master/Utils/Qdrant).

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

### Search & Indexing

| Tool | Description |
|------|-------------|
| `qdrant_search` | Semantic search in code/docs |
| `qdrant_index_directory` | Index a directory |
| `qdrant_reindex` | Reindex (full or incremental) |

### Collection Management

| Tool | Description |
|------|-------------|
| `qdrant_list_collections` | List all collections |
| `qdrant_get_collection_info` | Get collection info |
| `qdrant_delete_collection` | Delete collection |

### Diagnostics & Introspection (NEW)

| Tool | Description |
|------|-------------|
| `qdrant_diagnose_collection` | Full collection diagnostics - vectors, files, types, issues |
| `qdrant_list_indexed_files` | Paginated list of indexed files with metadata |
| `qdrant_diff_collection` | Compare Qdrant state with filesystem (orphans, missing, modified) |

### Maintenance

| Tool | Description |
|------|-------------|
| `qdrant_cleanup` | Clean stale vectors (dry-run supported) |
| `qdrant_watch_start` | Start file watcher |
| `qdrant_watch_stop` | Stop file watcher |
| `qdrant_get_status` | Server status |

### Diagnostic Tools Usage Examples

```bash
# Diagnose a collection - see what's indexed, file types, issues
qdrant_diagnose_collection(collection="myproject")

# List indexed files with pagination
qdrant_list_indexed_files(collection="myproject", limit=50, offset=0)

# Filter by file type
qdrant_list_indexed_files(collection="myproject", file_type=".py")

# Compare Qdrant state with filesystem
qdrant_diff_collection(collection="myproject", repo_path="/path/to/repo")
```

## OpenCode Skill

The project includes an OpenCode skill for natural language management of Qdrant.

### Installation

```bash
# Copy skill to OpenCode skills directory
cp -r skills/qmcp-manager ~/.config/opencode/skills/
```

### Usage

Once installed, OpenCode will automatically activate the skill when you ask questions like:

| Query | What Happens |
|-------|--------------|
| `what's indexed in my Qdrant?` | Diagnoses collection and shows stats |
| `show collection stats` | Lists all collections with vector counts |
| `clean up orphans in my index` | Finds and previews deletion of orphaned vectors |
| `diagnose my index` | Full diagnostics with issues and file list |
| `compare index with /path/to/repo` | Shows orphans, missing, and modified files |
| `find missing files` | Lists files on disk but not indexed |
| `is my index up to date?` | Compares hashes to detect changes |

### Workflows Provided by Skill

1. **Quick Status** - Check collection state with `qdrant_list_collections`
2. **Full Diagnostics** - Detailed analysis with `qdrant_diagnose_collection`
3. **Diff** - Compare Qdrant with filesystem using `qdrant_diff_collection`
4. **Safe Cleanup** - Preview with dry-run, then confirm deletion
5. **Smart Reindex** - Incremental updates based on file hashes

### Skill Location

```
skills/qmcp-manager/SKILL.md
```

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
