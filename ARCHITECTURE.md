# Architecture

## Overview

qmcp (QDrant MCP Server) provides semantic search capabilities for code and documentation, designed to integrate with OpenCode CLI. It uses vector embeddings to enable natural language search across your codebase.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Kubernetes Cluster                              │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    qmcp Service                                 │   │
│  │  ┌─────────────────────────────────────────────────────────┐  │   │
│  │  │                    Pod (Deployment)                      │  │   │
│  │  │  ┌───────────┐  ┌────────────┐  ┌────────────┐          │  │   │
│  │  │  │   MCP     │  │  Indexer   │  │  Watcher   │          │  │   │
│  │  │  │  Server   │  │  (batch)   │  │ (inotify)  │          │  │   │
│  │  │  │ (FastMCP) │  │            │  │            │          │  │   │
│  │  │  └─────┬─────┘  └──────┬─────┘  └──────┬─────┘          │  │   │
│  │  │        │                │              │                 │  │   │
│  │  │        └────────────────┴──────────────┘                 │  │   │
│  │  │                         │                                │  │   │
│  │  │                    Parser Layer                         │  │   │
│  │  │        ┌────────────────┼────────────────┐              │  │   │
│  │  │        ▼                ▼                ▼              │  │   │
│  │  │  ┌──────────┐   ┌──────────┐   ┌──────────┐              │  │   │
│  │  │  │  Python  │   │  Go/JS   │   │  Markdown│              │  │   │
│  │  │  │   (AST)  │   │(tree-sit)│   │  Parser  │              │  │   │
│  │  │  └──────────┘   └──────────┘   └──────────┘              │  │   │
│  │  └─────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              │ Qdrant Client                            │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Qdrant (existing)                             │   │
│  │         http://192.168.218.190:6333                            │   │
│  │   ┌───────────────┐  ┌────────────────┐                         │   │
│  │   │    code       │  │     docs       │                         │   │
│  │   │  collection   │  │   collection   │                         │   │
│  │   └───────────────┘  └────────────────┘                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    PVC (nfs-client)                              │   │
│  │                 /data/repo (mounted)                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. MCP Server (`server.py`)

The core FastMCP server that exposes tools to OpenCode. Handles:
- Tool registration and execution
- Request validation
- Response formatting

**Transports**: Streamable HTTP (production), Stdio (development)

### 2. Qdrant Client (`client.py`)

Wrapper around `qdrant-client` providing:
- Connection management
- Collection operations
- Vector search
- Batch upserts

### 3. Indexer (`indexer.py`)

Responsible for parsing and indexing code files:
- File discovery (glob patterns)
- Multi-language parsing (AST + tree-sitter)
- Incremental indexing (hash-based change detection)
- Batch processing

### 4. Parser Layer (`parser/`)

```
┌─────────────────┐
│   BaseParser   │  (abstract interface)
└────────┬────────┘
         │
    ┌────┴────┬──────────────┐
    ▼         ▼              ▼
┌───────┐ ┌───────┐      ┌─────────┐
│Python │ │ Multi │      │Markdown│
│Parser │ │Parser │      │ Parser │
│ (AST) │ │(tree- │      │        │
│       │ │sitter)│      │        │
└───────┘ └───────┘      └─────────┘
```

**Supported Languages**:
- Python: AST-based parsing
- Go, JavaScript, TypeScript, Java, C#: tree-sitter
- Markdown: Section extraction

### 5. Watcher (`watcher.py`)

File system watcher for live updates:
- inotify-based change detection
- Debouncing to prevent excessive reindexing
- Async architecture for Kubernetes compatibility

### 6. Cleanup Manager (`cleanup.py`)

Handles removal of stale vectors:
- Compares filesystem with database
- Removes vectors for deleted files
- Updates vectors for changed files

### 7. Diagnostics Manager (`diagnostics.py`)

Provides introspection and analysis of collections:
- **Collection Diagnostics**: Full analysis - vectors, files, file types, chunk distribution, issues
- **Indexed Files Listing**: Paginated file list with metadata
- **Collection Diff**: Compare Qdrant state with filesystem (orphans, missing, modified)

```
DiagnosticsManager
├── diagnose_collection()     → Complete collection analysis
├── list_indexed_files()      → Paginated file listing
└── diff_collection()         → Qdrant ↔ filesystem comparison
```

## OpenCode Skill

The `qmcp-manager` skill provides natural language interface for Qdrant management:

**Location**: `.opencode-skills/qmcp-manager/`

**Trigger phrases**:
- "what's indexed", "show collection stats"
- "clean up orphans", "cleanup"
- "diagnose", "diff", "compare"
- "reindex", "index new files"

**Workflows**:
1. Quick Status - Check collection state
2. Full Diagnostics - Detailed analysis with issues
3. Diff - Compare Qdrant with filesystem
4. Safe Cleanup - Preview before deletion
5. Smart Reindex - Incremental updates

## Data Flow

### Search Flow

```
User Query
    │
    ▼
┌─────────────┐
│ OpenCode    │
│  CLI        │
└──────┬──────┘
       │ MCP Protocol
       ▼
┌─────────────┐
│ MCP Server  │ ──→ qdrant_search()
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Qdrant     │
│  Client     │
└──────┬──────┘
       │ Vector Search
       ▼
┌─────────────┐
│   Qdrant    │
│   (vectors) │
└─────────────┘
```

### Index Flow

```
File System
    │
    ▼
┌─────────────┐
│   Watcher   │ (or manual trigger)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Parser    │ ──→ Extract code chunks
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  FastEmbed  │ ──→ Generate embeddings
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Qdrant    │ ──→ Upsert vectors
│   Client    │
└─────────────┘
```

## Data Models

### Point Structure

```json
{
  "id": "src/main.go:main:10-25",
  "vector": [0.1, 0.2, ...],
  "payload": {
    "file_path": "src/main.go",
    "content_hash": "sha256_abc123",
    "type": "function",
    "name": "main",
    "docstring": "Main function",
    "line_start": 10,
    "line_end": 25
  }
}
```

### Collections

| Collection | Purpose | Document Types |
|------------|---------|----------------|
| `code` | Source code search | Functions, classes, methods |
| `docs` | Documentation search | README, markdown files |

## Deployment

### Kubernetes

```
┌─────────────────────────────────────────┐
│              ArgoCD                     │
│         (GitOps controller)             │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          Helm Release (qmcp)            │
│  - Deployment (1 replica)               │
│  - Service (ClusterIP)                  │
│  - HTTPRoute (Gateway API)              │
│  - PVC (nfs-client)                     │
└─────────────────────────────────────────┘
```

### Resource Requirements

| Resource | Request | Limit |
|----------|---------|-------|
| Memory | 1Gi | 2Gi |
| CPU | 500m | 1000m |

## Security

- Runs as non-root user (UID 1000)
- No external API keys required (Qdrant is internal)
- TLS not required (internal cluster communication)

## Monitoring

Health endpoints:
- `/health` - Liveness probe
- `/ready` - Readiness probe

## Future Enhancements

1. **Hybrid Search**: Combine vector + BM25
2. **Reranking**: Add cross-encoder reranking
3. **Metrics**: Prometheus exporter
4. **Multi-tenant**: Namespace isolation
5. **Cache**: Embedding cache for common queries
