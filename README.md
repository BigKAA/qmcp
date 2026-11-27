# qmcp - QDrant MCP Server for OpenCode

[![Version](https://img.shields.io/badge/version-0.3.5-blue.svg)](https://github.com/BigKAA/qmcp)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![MCP](https://img.shields.io/badge/MCP-Server-blue.svg)](https://modelcontextprotocol.io/)

**Semantic search server for code and documentation using Qdrant vector database.**

**Language:** English | [Русский](./README.ru.md)

## Features

- **Semantic Search**: Find code and documentation using natural language queries
- **Multi-language Support**: Python, Go, JavaScript, TypeScript, Java, C#, Markdown
- **Markdown Section Chunking**: Markdown files are split into per-section chunks (`##`/`###` headers) with precise line ranges - search points at the exact section instead of the whole file, and file tails beyond 10 KB are indexed too
- **Compact Search Responses**: Search returns pointer fields only (`file_path`, `line_start`, `line_end`, `type`, `name`) - enough for a targeted read, without bloating the context
- **Live Updates**: File watcher for automatic reindexing
- **Incremental Indexing**: Only index changed files
- **Gitignore Support**: Respects `.gitignore` - excludes `node_modules`, `__pycache__`, `.venv`, build artifacts, etc.
- **Cleanup**: Remove stale vectors for deleted/changed files
- **Diagnostics**: Introspection tools to understand what's indexed
- **OpenCode Skill**: Natural language interface for Qdrant management

## Installation

### Via PyPI (Recommended)

```bash
pip install qmcp-qdrant
```

### Via uv

```bash
uv tool install qmcp-qdrant
```

### From Source

```bash
git clone https://github.com/BigKAA/qmcp.git
cd qmcp
make install
```

## Updating

### Via uv (Recommended)

```bash
uv tool upgrade qmcp-qdrant
```

### Via pip

```bash
pip install --upgrade qmcp-qdrant
```

## Quick Start

### 1. Ensure Qdrant is running

For Kubernetes deployment, see [Qdrant on Kubernetes](https://github.com/BigKAA/youtube/tree/master/Utils/Qdrant).

### 2. Add MCP Server to OpenCode

```bash
opencode mcp add qmcp-qdrant qmcp-qdrant
```

> ⚠️ **Note**: Environment variables must be set in `~/.config/opencode/opencode.json` config file.

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server URL |
| `QDRANT_API_KEY` | (none) | Qdrant API key (optional) |
| `TRANSPORT` | `stdio` | MCP transport: `stdio`, `streamable-http`, `sse` |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Bind address for HTTP transports |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Embedding model |
| `EMBEDDING_CACHE_DIR` | (system temp) | Custom directory for model cache |
| `EMBEDDING_THREADS` | `min(4, CPU count)` | ONNX inference threads per process |
| `WATCH_PATHS` | `/data/repo` | Baseline paths to watch on startup (HTTP transports only, see `WATCH_AUTOSTART`) |
| `WATCH_AUTOSTART` | `auto` | Start the watcher on server startup. `auto`: on for HTTP transports, off for stdio; `true`/`false` overrides |
| `IDLE_TIMEOUT_SECONDS` | `1800` | Shut down an idle stdio server after this many seconds without MCP traffic; the client respawns it on the next call. `0` disables |
| `REPLACEMENT_GRACE_SECONDS` | `300` | Idle period that must pass before a stdio server replaced by a newer sibling exits |
| `BATCH_SIZE` | `50` | Batch size for indexing |
| `INDEX_LOCK_DIR` | `~/.cache/qmcp-locks` | Directory for cross-process locks and the stdio instance registry |
| `DEBOUNCE_SECONDS` | `5` | Debounce delay |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `text` | Log format (`text` or `json`) |

> 💡 **Model Cache**: Set `EMBEDDING_CACHE_DIR` to persist models across restarts. First launch downloads the model (~13MB), subsequent launches use cached version.

> 💡 **Multiple clients, one machine**: every MCP client spawns its own qmcp
> process, and each holds its own embedding model. qmcp deduplicates indexing
> across processes with file locks (`INDEX_LOCK_DIR`), elects a single
> machine-wide watcher leader (see [Process Lifecycle](#process-lifecycle-and-resource-hygiene)),
> and caps ONNX threads (`EMBEDDING_THREADS`, default 4) so N processes cannot
> saturate every core. Keep `WATCH_PATHS` scoped to trees you actively work in -
> a monorepo-scale path makes every process walk it on each poll.

> 💡 **WATCH_PATHS examples**:
> - Single path: `WATCH_PATHS=/home/user/project`
> - Multiple paths: `WATCH_PATHS=/home/user/project,/home/user/docs`
> - JSON array: `WATCH_PATHS=["/home/user/project", "/home/user/docs"]`

### 3. That's It!

OpenCode will automatically discover and use the semantic search tools.

### Manual Configuration (Alternative)

If `opencode mcp add` doesn't work, edit `~/.config/opencode/opencode.json` directly:

```json
{
  "mcp": {
    "qmcp-qdrant": {
      "type": "local",
      "command": ["qmcp-qdrant"],
      "environment": {
        "QDRANT_URL": "http://192.168.218.190:6333",
        "WATCH_PATHS": "/home/user/shared-docs,/home/user/shared-snippets"
      }
    }
  }
}
```

For Python module:
```json
{
  "mcp": {
    "qmcp-qdrant": {
      "type": "local",
      "command": ["python", "-m", "qmcp.server"],
      "environment": {
        "QDRANT_URL": "http://192.168.218.190:6333",
        "WATCH_PATHS": "/home/user/shared-docs,/home/user/shared-snippets"
      }
    }
  }
}
```

## Indexing Notes

> ⚠️ **Important**: Full indexing and reindexing of large projects can take a significant amount of time (minutes to hours depending on project size).

For large codebases, prefer:
- **Incremental reindex** (`mode="incremental"`) - only updates changed files based on content hashes
- **File watcher** - enables automatic live updates when files change

### Markdown Chunking

Markdown files are chunked per section (headers `##` and `###` by default). Oversized sections (> 8 KB) are additionally split by paragraph boundaries, never inside code fences. Each chunk carries precise `line_start`/`line_end`, so `qdrant_search` results point to the exact section for a targeted read.

Files without headers fall back to a single `document` chunk (paragraph-split when oversized).

> ⚠️ **BREAKING (existing collections)**: The chunk schema changed (per-section chunks instead of one chunk per markdown file). Existing markdown collections **must be fully reindexed** after upgrading:
>
> ```python
> qdrant_reindex(path="/path/to/project", collection="docs", mode="full")
> ```
>
> Incremental reindex will not migrate unchanged files - they keep the old single-chunk layout until a full reindex runs.

### Score Threshold Note

The default `score_threshold=0.7` is calibrated for `bge-*` embedding models. For `paraphrase-multilingual-*` models the top score is typically ~0.64, so the default threshold filters out everything - lower the threshold explicitly for those models.

### Automatic Indexing Strategy

`qmcp` supports automatic indexing on two levels:

1. **Server startup level (HTTP daemon)** — a shared `streamable-http` daemon starts a watcher for `WATCH_PATHS` on startup, because it is the single machine-wide indexer. A per-connection stdio server does **not** autostart a watcher (N clients would mean N filesystem pollers); override with `WATCH_AUTOSTART=true`.
2. **Workspace session level** — agents check the watcher state for the current workspace and call `qdrant_watch_ensure(paths=[workspace_root])` when the workspace path is missing. For stdio servers this is the primary way watching gets enabled.

Recommended flow for every new workspace:

```python
status = qdrant_get_status()

# If watcher is not active or the current repo is not covered,
# safely extend the watcher without dropping other projects.
qdrant_watch_ensure(paths=["/absolute/path/to/current/workspace"])
```

`qdrant_watch_ensure` merges the current workspace with already watched paths and `WATCH_PATHS`, making it safe for a single global MCP shared by multiple projects. When several qmcp processes watch the same paths, a cross-process leader lock ensures exactly one of them polls the filesystem; the rest idle in standby (`watcher_role` in `qdrant_get_status` shows `leader`/`standby`) and are promoted automatically when the leader dies.

## Process Lifecycle and Resource Hygiene

A stdio MCP server is spawned per client connection, and clients do not always
clean up: an abandoned connection delivers no EOF when the terminal or
supervisor inherited the pipe fd, and a *living* parent that reconnects leaves
the old copy running. Accumulated copies each held an embedding model and a
filesystem poller (the 2026-11 CPU overheat incident: 7 concurrent copies,
~126% CPU, 15 GB of memory pressure). stdio servers now bound their own
lifetime with three guards (all disabled for `streamable-http`/`sse`, whose
lifetime belongs to the service manager):

| Guard | Trigger | Default |
|---|---|---|
| Orphan | Parent process died (`os.getppid()` changed) | always on |
| Idle | No inbound MCP traffic for `IDLE_TIMEOUT_SECONDS` | 1800 s (`0` disables) |
| Replacement | A newer instance from the same client registered, and this one idle for `REPLACEMENT_GRACE_SECONDS` | 300 s grace |

Details:

- Activity is recorded by an MCP middleware wrapping **every** inbound message
  (handshake, pings, tool calls), so a silent-but-alive connection stays
  alive, while an abandoned one (no messages at all) lets the server exit;
  in-flight requests and indexing tasks postpone the exit.
- Clients respawn their server on the next tool call, so an idle exit is
  invisible in normal use.
- After `run()` returns (client disconnected), the entry points hard-exit the
  process so no lingering thread can keep a dead connection alive.
- The watcher is single-instance machine-wide (leader lock in
  `INDEX_LOCK_DIR`), so even leftover copies cannot multiply the polling cost.

Diagnostics and manual cleanup of pre-0.3.5 leftovers:

```bash
# find running copies
ps -eo pid,ppid,%cpu,etime,command | grep -E 'qmcp(-qdrant)?' | grep -v grep

# reap them (active clients respawn on the next call)
kill <PID...>
```

## Deployment: Shared HTTP Daemon (Recommended for Multi-Client Workstations)

With stdio every MCP client (OpenCode, Zed, ZCode, CLI agents) spawns its own
qmcp process - per-connection processes by design, which is what the guards
above keep hygienic. For a workstation with several MCP clients the
recommended alternative is **one shared `streamable-http` daemon**: one
process, one embedding model, one watcher, and no per-connection processes to
orphan at all.

```bash
TRANSPORT=streamable-http HOST=127.0.0.1 PORT=8000 \
WATCH_PATHS=/Users/me/projects,/Users/me/docs \
qmcp-qdrant
```

Clients then connect by URL instead of a command (OpenCode example):

```json
{
  "mcp": {
    "qmcp-qdrant": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### macOS: launchd

`~/Library/LaunchAgents/com.qmcp.qdrant.plist` - starts on login, restarts on
crash, logs to `~/Library/Logs/qmcp.log`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.qmcp.qdrant</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/me/.local/bin/qmcp-qdrant</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>TRANSPORT</key><string>streamable-http</string>
    <key>HOST</key><string>127.0.0.1</string>
    <key>PORT</key><string>8000</string>
    <key>QDRANT_URL</key><string>http://192.168.218.190:6333</string>
    <key>WATCH_PATHS</key><string>/Users/me/projects,/Users/me/docs</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>/Users/me/Library/Logs/qmcp.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.qmcp.qdrant.plist
```

### Linux: systemd (user unit)

`~/.config/systemd/user/qmcp.service`:

```ini
[Unit]
Description=qmcp - Qdrant MCP server (shared daemon)

[Service]
Environment=TRANSPORT=streamable-http
Environment=HOST=127.0.0.1
Environment=PORT=8000
Environment=WATCH_PATHS=/home/me/projects,/home/me/docs
ExecStart=/home/me/.local/bin/qmcp-qdrant
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now qmcp
```

> ⚠️ **Security**: bind to `127.0.0.1` - the daemon has no authentication and
> anyone who can reach the port can search and modify your indexes.

## MCP Tools

### Search & Indexing

| Tool | Description |
|------|-------------|
| `qdrant_search` | Semantic search in code/docs |
| `qdrant_index_directory` | Index a directory |
| `qdrant_reindex` | Reindex (full or incremental) |

> 💡 **Tip**: Use `qdrant_search` with filters for precise results:
> - `chunk_type` — filter by code type (function_def, class_def, `section`, document)
> - `symbol_name` — find exact symbol by name (for markdown: section header text)
> - `language` — filter by programming language
>
> Results are compact pointers (`score`, `file_path`, `type`, `name`, `line_start`, `line_end`) - use them for a targeted file read instead of loading whole files.
>
> See [docs/STRUCTURED_METADATA.md](./docs/STRUCTURED_METADATA.md) for detailed examples.

### Collection Management

| Tool | Description |
|------|-------------|
| `qdrant_list_collections` | List all collections |
| `qdrant_get_collection_info` | Get collection info |
| `qdrant_delete_collection` | Delete collection |

### Diagnostics & Introspection

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
| `qdrant_watch_ensure` | Ensure workspace path is watched without dropping other projects |
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

## Manage MCP Servers

```bash
opencode mcp list          # List all MCP servers
opencode mcp debug qmcp-qdrant     # Debug connection issues
opencode mcp logout qmcp-qdrant    # Remove MCP server
```

## Development

```bash
make install      # Install dependencies
make test         # Run tests
make lint         # Lint code
make format       # Format code
make mcp-dev      # Run with MCP inspector
```

## Troubleshooting

If you encounter issues, see the [Troubleshooting Guide](./docs/TROUBLESHOOTING.md) for:

- **[Embedding Model Issues](./docs/TROUBLESHOOTING.md#embedding-model-issues)** — `indexed_vectors_count: 0` diagnosis and fix
- **[Connection Problems](./docs/TROUBLESHOOTING.md#connection-problems)** — Qdrant connection troubleshooting
- **[Search Returns No Results](./docs/TROUBLESHOOTING.md#search-returns-no-results)** — Empty search results debugging

## License

Apache 2.0
