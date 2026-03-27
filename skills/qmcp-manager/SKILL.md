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
  
  Examples: "what's indexed in my Qdrant", "clean up orphans", "show collection stats", 
  "find missing files", "diagnose my index", "compare index with repo"
---

# QDrant MCP Manager Skill

## Overview

This skill manages the qmcp (QDrant MCP Server) - a semantic search server for code and documentation using Qdrant vector database. It provides tools for introspection, cleanup, and maintenance of indexed codebases.

## Available MCP Tools

### Diagnostics Tools (NEW)
| Tool | Purpose |
|------|---------|
| `qdrant_diagnose_collection` | Full collection diagnostics - vectors, files, types, issues |
| `qdrant_list_indexed_files` | Paginated list of indexed files with metadata |
| `qdrant_diff_collection` | Compare Qdrant state with filesystem (orphans, missing, modified) |

### Existing Tools
| Tool | Purpose |
|------|---------|
| `qdrant_search` | Semantic search in collection |
| `qdrant_index_directory` | Index directory into collection |
| `qdrant_reindex` | Full or incremental reindex |
| `qdrant_list_collections` | List all collections |
| `qdrant_get_collection_info` | Get collection metadata |
| `qdrant_delete_collection` | Delete a collection |
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
| "Index new files" | qdrant_index_directory |

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