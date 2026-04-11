# Collection Setup Guide

This guide covers setting up collections for different use cases with qmcp.

## Quick Reference: Model Selection

| Use Case | Model | Command |
|----------|-------|---------|
| Code search | `jinaai/jina-embeddings-v2-base-code` | `model="jinaai/jina-embeddings-v2-base-code"` |
| English docs (lightweight) | `BAAI/bge-small-en-v1.5` | `model="BAAI/bge-small-en-v1.5"` |
| English docs (quality) | `BAAI/bge-large-en-v1.5` | `model="BAAI/bge-large-en-v1.5"` |
| Multilingual KB (RU+EN) | `intfloat/multilingual-e5-large` | `model="intfloat/multilingual-e5-large"` |

> ⚠️ **E5 Prefix Handling**: The `intfloat/multilingual-e5-large` model requires special prefixes (`query: ` and `passage: `). **qmcp handles this automatically** — no action needed!

---

## 1. Corporate Knowledge Base (Multilingual)

Best for: Company-wide documentation, policies, wiki, multilingual content.

### Setup

```bash
# Index corporate documentation
qdrant_index_directory(
    path="/shared/corporate-docs",
    collection="company-kb-docs",
    model="intfloat/multilingual-e5-large",
    patterns=["*.md", "*.txt", "*.doc"],
    metadata={
        "team": "documentation",
        "visibility": "internal",
        "source": "confluence"
    }
)

# Index reusable templates/snippets
qdrant_index_directory(
    path="/shared/templates",
    collection="company-kb-snippets",
    model="jinaai/jina-embeddings-v2-base-code",
    patterns=["*.py", "*.js", "*.go", "*.sql"],
    metadata={
        "team": "all",
        "visibility": "public"
    }
)
```

### Search Across KB

```bash
# Search across all KB collections
qdrant_search_many(
    collections=["company-kb-docs", "company-kb-snippets"],
    query="How do I request access to production?",
    limit=10,
    score_threshold=0.6
)
```

---

## 2. Team-Specific Collections

Best for: Team documentation, shared code, project-specific knowledge.

### Setup

```bash
# Backend team code
qdrant_index_directory(
    path="/projects/backend",
    collection="team-backend-code",
    model="jinaai/jina-embeddings-v2-base-code",
    patterns=["*.py", "*.go", "*.java"],
    metadata={
        "team": "backend",
        "project": "core-api"
    }
)

# Backend team documentation
qdrant_index_directory(
    path="/projects/backend/docs",
    collection="team-backend-docs",
    model="BAAI/bge-small-en-v1.5",
    patterns=["*.md", "*.rst"],
    metadata={
        "team": "backend",
        "project": "core-api"
    }
)
```

### Ensure Team Paths Are Watched

```bash
# When starting work in a new workspace
qdrant_watch_ensure(paths=["/projects/backend"])

# This merges with existing watched paths, so other projects keep indexing
```

---

## 3. Project Code Collection

Best for: Project-specific code search with high relevance.

### Setup

```bash
# Full project indexing with code-optimized model
qdrant_index_directory(
    path="/projects/myapp",
    collection="project-myapp-code",
    model="jinaai/jina-embeddings-v2-base-code",
    patterns=["*.py", "*.go", "*.js", "*.ts", "*.java", "*.cs"],
    metadata={
        "project": "myapp",
        "team": "platform"
    }
)

# Project documentation
qdrant_index_directory(
    path="/projects/myapp/docs",
    collection="project-myapp-docs",
    model="BAAI/bge-small-en-v1.5",
    patterns=["*.md"],
    metadata={
        "project": "myapp"
    }
)
```

### Incremental Updates

```bash
# After initial full indexing, use incremental mode
# Only changed files will be re-indexed
qdrant_reindex(
    path="/projects/myapp",
    collection="project-myapp-code",
    model="jinaai/jina-embeddings-v2-base-code",
    mode="incremental"
)
```

---

## 4. Lightweight Documentation (Single Collection)

Best for: Small projects, quick setup, minimal resource usage.

### Setup

```bash
# Simple indexing with lightweight model
qdrant_index_directory(
    path="/my-docs",
    collection="my-docs",
    model="BAAI/bge-small-en-v1.5",
    patterns=["*.md", "*.txt"]
)
```

---

## Model-Specific Notes

### E5 Models (`intfloat/multilingual-e5-large`)

**Automatic prefix handling** — qmcp adds the required prefixes for you:

| Operation | Prefix Applied | Example |
|-----------|----------------|---------|
| Indexing (passage) | `passage: ` | `passage: This is document content...` |
| Search (query) | `query: ` | `query: Find authentication docs` |

**Why prefixes matter**: E5 models were trained with these prefixes. Without them, retrieval quality drops significantly.

### Jina Code Model (`jinaai/jina-embeddings-v2-base-code`)

- Optimized for code syntax and semantics
- Supports 30+ programming languages
- No prefix required
- Good for mixed code/documentation collections

### BGE Models (`BAAI/bge-*-v1.5`)

- General-purpose models for text
- `bge-small`: Fast, low memory, good quality
- `bge-large`: Best quality for English, larger

---

## Verifying Collection Setup

### Check Collection Info

```bash
qdrant_get_collection_info(collection="company-kb-docs")
# Returns:
# {
#   "name": "company-kb-docs",
#   "points_count": 1500,
#   "embedding_model": "intfloat/multilingual-e5-large",
#   "status": "green"
# }
```

### Run Diagnostics

```bash
qdrant_diagnose_collection(collection="company-kb-docs")
# Shows: vectors, files, file types, chunk types, issues
```

---

## Changing Collection Model

To change a collection's embedding model:

```bash
# WARNING: This recreates the collection and deletes all existing vectors!
# Only use if you want to switch to a different model entirely.

qdrant_reindex(
    path="/path/to/reindex",
    collection="my-collection",
    model="new-model-name",
    mode="full"  # Must be "full" to change model
)
```

---

## Collection Naming Best Practices

```
company-kb-<type>    — Shared corporate knowledge
team-<name>-<type>  — Team-specific content
project-<name>-<type> — Project-specific content
<name>-<type>       — Personal/small project content
```

| Pattern | Example | Model Suggestion |
|---------|---------|------------------|
| `company-kb-docs` | Corporate wiki | `multilingual-e5-large` |
| `company-kb-snippets` | Shared code | `jina-embeddings-v2-base-code` |
| `team-backend-code` | Backend team code | `jina-embeddings-v2-base-code` |
| `team-backend-docs` | Backend docs | `bge-small-en-v1.5` |
| `project-api-code` | API project | `jina-embeddings-v2-base-code` |
| `project-api-docs` | API documentation | `bge-large-en-v1.5` or `bge-small-en-v1.5` |
