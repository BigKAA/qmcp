---
name: qmcp-manager
description: |
  Qdrant MCP Server management and diagnostics skill. Use whenever working with the qmcp (QDrant MCP Server) project for semantic code search. Activates on queries about:
  - Qdrant database state, collections, or indexed content
  - Cleaning up vector database (orphans, stale vectors, missing files)
  - Understanding what's indexed in a collection
  - Reindexing or updating the search index
  - Comparing Qdrant state with filesystem
  - Diagnosing collection issues or getting collection statistics
  - Choosing embedding model for collection type (code, docs, multilingual KB)
   
  Examples: "what's indexed in my Qdrant", "clean up orphans", "show collection stats", 
  "find missing files", "diagnose my index", "compare index with repo",
  "which model should I use for code", "set up corporate knowledge base"
---

# QDrant MCP Manager Skill

## Overview

This skill manages the qmcp (QDrant MCP Server) - a semantic search server for code and documentation using Qdrant vector database. It provides tools for introspection, cleanup, and maintenance of indexed codebases.

## Available MCP Tools

### Search & Indexing
| Tool | Purpose |
|------|---------|
| `qdrant_search` | Semantic search in collection |
| `qdrant_search_many` | Search across multiple collections |
| `qdrant_index_directory` | Index directory with optional model selection |
| `qdrant_reindex` | Full or incremental reindex with optional model change |
| `qdrant_list_supported_models` | List available embedding models |

### Diagnostics Tools
| Tool | Purpose |
|------|---------|
| `qdrant_diagnose_collection` | Full collection diagnostics - vectors, files, types, issues |
| `qdrant_list_indexed_files` | Paginated list of indexed files with metadata |
| `qdrant_diff_collection` | Compare Qdrant state with filesystem (orphans, missing, modified) |

### Collection Management
| Tool | Purpose |
|------|---------|
| `qdrant_list_collections` | List all collections |
| `qdrant_get_collection_info` | Get collection metadata (includes embedding_model) |
| `qdrant_delete_collection` | Delete a collection |

### Maintenance
| Tool | Purpose |
|------|---------|
| `qdrant_cleanup` | Clean stale vectors (dry-run supported) |
| `qdrant_watch_start/stop` | Start/stop file watching |
| `qdrant_get_status` | Server status |

## Workflows

### 1. Quick Status Check
When user asks about Qdrant state:
```
1. Use qdrant_list_collections to see what exists
2. For each collection, use qdrant_get_collection_info
3. Summarize: vectors count, files, status
```

### 2. Full Diagnostics
When user asks to diagnose or understand what's indexed:
```
1. Ask for collection name (or use "code" as default)
2. Call qdrant_diagnose_collection(collection="...")
3. Present results:
   - Summary: total vectors, total files, status
   - File type distribution
   - Chunk type distribution  
   - Index age range (oldest/newest indexed)
   - Issues found
   - File list with details
```

### 3. Find Discrepancies (Diff)
When user wants to compare index with filesystem:
```
1. Call qdrant_diff_collection(collection="...", repo_path="/path/to/repo")
2. Present summary:
   - orphans: vectors without files (DELETE THESE)
   - missing: files without vectors (NEED INDEXING)
   - modified: files with hash mismatch (NEED REINDEX)
3. Recommend actions based on findings
```

### 4. Safe Cleanup Workflow
When user asks to clean up the index:
```
1. ALWAYS start with dry_run=True
2. Show what would be deleted
3. Confirm with user before actual deletion
4. Only proceed with dry_run=False after confirmation
5. Default mode is dry_run=True
```

### 5. Smart Reindex
When user wants to update the index:
```
1. Use qdrant_diff_collection first to see what changed
2. If mode="incremental", only changed files are reindexed
3. If mode="full", collection is deleted and recreated
4. Recommend incremental as default (faster, safer)
```

## Gitignore Support

The indexer **automatically respects `.gitignore` files**. This means:

- Files and directories listed in `.gitignore` (e.g., `node_modules/`, `build/`, `*.pyc`, `.venv/`) are **NOT indexed**
- Supports nested `.gitignore` files (parent directory rules apply to children)
- Works with standard gitignore patterns: wildcards (`*.log`), directories (`dist/`), negation (`!important.log`)

This significantly reduces index size by excluding:
- Dependencies (`node_modules/`, `vendor/`, `.venv/`)
- Build artifacts (`dist/`, `build/`, `*.class`)
- Generated files (`*.pyc`, `__pycache__/`)
- Environment files (`.env`, `.env.local`)
- IDE settings (`.idea/`, `.vscode/`)

**Note**: Files not covered by `.gitignore` but that shouldn't be indexed can be added to the project's `.gitignore` to exclude them from future indexing.

## Collection Naming

Default collections:
- `code` - source code files (.py, .go, .js, .ts, .java, .cs, .rs, etc.)
- `docs` - documentation files (.md)

For project isolation, use project-specific names like `myproject-code`, `myproject-docs`.

## Model Selection

qmcp supports per-collection embedding model selection. Use `qdrant_list_supported_models()` to see available models.

### Recommended Models by Use Case

| Use Case | Model | Dimension | When to Use |
|---------|-------|-----------|-------------|
| **Code search** | `jinaai/jina-embeddings-v2-base-code` | 768 | Best for code, 30+ programming languages |
| **English docs (lightweight)** | `BAAI/bge-small-en-v1.5` | 384 | Fast, small, good for small projects |
| **English docs (quality)** | `BAAI/bge-large-en-v1.5` | 1024 | Best quality, larger model |
| **Multilingual KB (RU+EN)** | `intfloat/multilingual-e5-large` | 1024 | Best for corporate knowledge base |
| **Multilingual (lightweight)** | `paraphrase-multilingual-MiniLM-L12-v2` | 384 | Compromise option |

### E5 Model Prefix Handling

> **Important**: The `intfloat/multilingual-e5-large` model requires special prefixes (`query: ` and `passage: `) for optimal retrieval. **This is handled automatically by qmcp** — no action needed!

When using E5 model:
- Queries are automatically prefixed with `query: `
- Content is automatically prefixed with `passage: ` during indexing

### Selection Decision Workflow

```
When user asks "which model should I use?" or "what model for [use case]?":
1. Ask about the use case or detect from context:
   - Code search → jinaai/jina-embeddings-v2-base-code
   - Multilingual (RU+EN) docs → intfloat/multilingual-e5-large
   - Small English project → BAAI/bge-small-en-v1.5
   - Best English quality → BAAI/bge-large-en-v1.5
2. Use qdrant_list_supported_models() to confirm
3. Present recommendation with explanation
```

### Verify Model in Collection

Use `qdrant_get_collection_info()` to see which model a collection uses:
```
qdrant_get_collection_info(collection="my-collection")
# Returns: { ..., "embedding_model": "jinaai/jina-embeddings-v2-base-code" }
```

### Change Collection Model

To change a collection's model, reindex with the new model:
```
qdrant_reindex(path="/path/to/reindex", collection="my-collection", model="new-model", mode="full")
```

## Corporate Knowledge Base Architecture

qmcp supports multi-collection architecture for corporate knowledge bases.

### Collection Patterns

| Pattern | Purpose | Recommended Model |
|---------|---------|-------------------|
| `company-kb-docs` | Corporate docs, policies, wiki | `intfloat/multilingual-e5-large` |
| `company-kb-snippets` | Shared code templates | `jinaai/jina-embeddings-v2-base-code` |
| `team-{name}-docs` | Team documentation | `BAAI/bge-small-en-v1.5` |
| `team-{name}-code` | Team shared code | `jinaai/jina-embeddings-v2-base-code` |
| `project-{name}-code` | Project code | `jinaai/jina-embeddings-v2-base-code` |
| `project-{name}-docs` | Project docs | `BAAI/bge-small-en-v1.5` |

### Workflow: Set Up Corporate KB

```
When user asks "set up corporate knowledge base" or "create team collection":
1. Ask about:
   - Scope: company-wide, team, or project?
   - Content type: docs, code, or both?
   - Languages: English only or multilingual?
2. Recommend model based on scope:
   - Corporate/multilingual → intfloat/multilingual-e5-large
   - Code → jinaai/jina-embeddings-v2-base-code
   - Small English → BAAI/bge-small-en-v1.5
3. Create collection with model:
   qdrant_index_directory(
       path="/path/to/content",
       collection="company-kb-docs",
       model="intfloat/multilingual-e5-large"
   )
4. Optional: Add metadata for organization:
   qdrant_index_directory(
       path="/path/to/docs",
       collection="company-kb-docs",
       model="intfloat/multilingual-e5-large",
       metadata={"team": "docs-team", "visibility": "internal"}
   )
```

### Search Across Collections

For corporate KB, use `qdrant_search_many` to search across all collections:
```
qdrant_search_many(
    collections=["company-kb-docs", "company-kb-snippets", "team-backend-code"],
    query="How to authenticate",
    limit=10
)
```

### Metadata Enrichment

Add custom metadata for filtering and organization:
```
qdrant_index_directory(
    path="/project/docs",
    collection="project-docs",
    model="BAAI/bge-small-en-v1.5",
    metadata={
        "team": "backend",
        "project": "api-gateway",
        "visibility": "internal"
    }
)
```

## Input Parameters

### qdrant_diagnose_collection
- `collection` (required): Collection name to diagnose

### qdrant_list_indexed_files
- `collection` (required): Collection name
- `limit` (optional, default=100): Max files to return
- `offset` (optional, default=0): Pagination offset
- `file_type` (optional): Filter by extension (e.g., ".py", ".go")

### qdrant_diff_collection
- `collection` (required): Collection name to compare
- `repo_path` (required): Repository path to compare against

### qdrant_cleanup
- `collection` (required): Collection to clean
- `repo_path` (required): Repo path for comparison
- `dry_run` (optional, default=True): Preview before deletion

## Response Interpretation

### Diagnose Response
```json
{
  "collection": "myproject",
  "total_vectors": 1500,
  "total_files": 120,
  "status": "green",
  "file_types": {".py": 80, ".go": 30, ".md": 10},
  "chunk_type_distribution": {"function": 500, "class": 200, "statement": 800},
  "indexed_at_range": {"oldest": "2026-03-20T10:00:00", "newest": "2026-03-27T15:30:00"},
  "issues": ["File 'deleted.py' has no chunks"],
  "files": [...]
}
```

### Diff Response
```json
{
  "summary": {
    "total_indexed": 150,
    "total_files_in_repo": 148,
    "orphans_count": 2,
    "missing_count": 0,
    "modified_count": 5
  },
  "orphans": [{"file_path": "src/old.py", "chunk_count": 10, "reason": "file_not_found"}],
  "missing": [],
  "modified": [{"file_path": "src/changed.py", "stored_hash": "...", "current_hash": "..."}]
}
```

## Decision Guide

| User Query | Action |
|------------|--------|
| "What's indexed?" | qdrant_diagnose_collection |
| "Show me files" | qdrant_list_indexed_files |
| "Find orphans" | qdrant_diff_collection |
| "Compare with repo" | qdrant_diff_collection |
| "Clean up" | qdrant_cleanup (dry-run first) |
| "Reindex" | qdrant_reindex (incremental) |
| "Search code" | qdrant_search |
| "Search across collections" | qdrant_search_many |
| "Index new files" | qdrant_index_directory |
| "Which model?" / "what model for code?" | Check use case → recommend model |
| "Set up corporate KB" / "create team collection" | Corporate KB workflow |
| "Search not working" / "null scores" | Check indexed_vectors_count |
| "Show available models" | qdrant_list_supported_models |
| "Which model does collection use?" | qdrant_get_collection_info → embedding_model field |

## Common Issues

### indexed_vectors_count: 0

If `qdrant_get_collection_info` shows:
```json
{"points_count": 79, "indexed_vectors_count": 0}
```

This means **vectors were created but have zero dimensionality** - the embedding model failed to initialize. This typically happens when fastembed is not properly installed.

**Diagnosis**:
1. `qdrant_search(collection="...", query="test", limit=1)` - returns null scores or empty
2. Check MCP server logs for fastembed initialization errors

**Solution**: Full reindex to recreate vectors with working embedding model:
```
qdrant_reindex(collection="your-collection", path="/path/to/project", mode="full")
```

For more details, see [TROUBLESHOOTING.md](./docs/TROUBLESHOOTING.md#embedding-model-issues).

## Safety Rules

1. **Always prefer dry-run** for cleanup operations
2. **Confirm before deletion** - never delete without user approval
3. **Show summary first** - diagnose before acting
4. **Incremental over full** - prefer incremental reindex when possible
5. **Use project isolation** - recommend project-specific collection names

## Example Interactions

### Example 1: User asks "what's in my index?"
```
Assistant: Let me diagnose your collection. Which collection should I check?
User: the code collection
Assistant: 
- Uses qdrant_diagnose_collection(collection="code")
- Reports: 1,500 vectors, 120 files, status: green
- Shows file type distribution
- Lists any issues found
```

### Example 2: User asks "clean up my index"
```
Assistant: I'll run a cleanup preview first to show what would be removed.
- Uses qdrant_diff_collection to find orphans
- Shows: 5 orphaned vectors found
- Recommends: qdrant_cleanup with dry_run=True
User: looks good, proceed
Assistant:
- Runs qdrant_cleanup with dry_run=False
- Confirms: 5 vectors deleted
```

### Example 3: User asks "is my index up to date?"
```
Assistant: Let me compare your index with the filesystem.
- Uses qdrant_diff_collection(collection="code", repo_path="/path/to/repo")
- Reports:
  - 0 orphans (all indexed files exist)
  - 3 missing files (need indexing)
  - 2 modified files (need reindex)
- Recommends actions
```

### Example 4: User asks "which model should I use for code search?"
```
Assistant: For code search, I recommend using the jinaai/jina-embeddings-v2-base-code model.
- Best for code semantics (30+ languages)
- 768 dimensions
- No prefix handling needed
- Use: model="jinaai/jina-embeddings-v2-base-code" in qdrant_index_directory
```

### Example 5: User asks "set up corporate knowledge base"
```
Assistant: I'll help you set up a corporate KB. Let me ask a few questions:
1. Scope: company-wide or team-specific?
2. Content: docs, code, or both?
3. Languages: English only or multilingual (RU+EN)?

User: company-wide docs, multilingual (RU+EN)
Assistant: For multilingual corporate docs, I'll recommend intfloat/multilingual-e5-large:
- Best for 100+ languages
- Handles both Russian and English
- Requires "query:" and "passage:" prefixes (handled automatically)

qdrant_index_directory(
    path="/shared/corporate-docs",
    collection="company-kb-docs",
    model="intfloat/multilingual-e5-large"
)
```