# Troubleshooting Guide

This guide covers common issues with qmcp (Qdrant MCP Server) and how to resolve them.

## Table of Contents

- [Embedding Model Issues](#embedding-model-issues)
- [Connection Problems](#connection-problems)
- [Indexing Problems](#indexing-problems)
- [Search Returns No Results](#search-returns-no-results)

---

## Embedding Model Issues

### Symptom: `indexed_vectors_count: 0`

When checking collection info, you see:
```json
{
  "points_count": 79,
  "indexed_vectors_count": 0,
  "status": "GREEN"
}
```

Vectors exist (`points_count > 0`) but have zero dimensionality. Search returns no meaningful results, and you may see scores like `null` or errors when searching.

### Cause

The **fastembed** library failed to load or initialize when vectors were created. This typically happens when:

1. **Missing dependency**: `qdrant-client[fastembed]` was not installed properly
2. **Model download failed**: The embedding model wasn't downloaded on first use
3. **Wrong Python environment**: MCP server running in a different venv than where fastembed is installed
4. **Memory constraints**: Not enough RAM to load the model

### Diagnosis

1. **Check collection status**:
   ```
   qdrant_get_collection_info(collection="your-collection")
   ```
   Note: The response now includes `vector_size` - if it's 0, vectors are invalid.

2. **Run full diagnostics** (recommended):
   ```
   qdrant_diagnose_collection(collection="your-collection")
   ```
   This will show a **CRITICAL** warning if vectors have zero dimensions.

3. **Test search** (should return `null` scores or no results):
   ```
   qdrant_search(collection="your-collection", query="test", limit=1)
   ```

4. **Check server logs** for fastembed initialization errors:
   ```
   # When the MCP server starts, it now validates the embedding model.
   # Look for messages like:
   # - "Validating embedding model: BAAI/bge-small-en-v1.5"
   # - "Embedding model validated successfully"
   # OR errors like:
   # - "fastembed is not installed"
   # - "Failed to load embedding model"
   ```

5. **Verify fastembed is installed**:
   ```bash
   python -c "from fastembed import TextEmbedding; print('fastembed OK')"
   ```

### Solution

**Option 1: Reindex the collection** (Recommended)

```bash
# Full reindex - deletes and recreates collection
qdrant_reindex(path="/path/to/project", collection="your-collection", mode="full")
```

Or via MCP tool:
```
qdrant_reindex(collection="your-collection", path="/path/to/project", mode="full")
```

This recreates all vectors with the properly initialized embedding model.

**Option 2: Reinstall fastembed**

```bash
# Ensure qdrant-client with fastembed extras is installed
pip install --upgrade "qdrant-client[fastembed]"

# Or via uv
uv pip install --upgrade "qdrant-client[fastembed]"

# Verify installation
python -c "from fastembed import TextEmbedding; model = TextEmbedding()"
```

**Option 3: Download the embedding model manually**

```bash
# First time setup - downloads ~470MB model
python -c "
from fastembed import TextEmbedding
model = TextEmbedding('BAAI/bge-small-en-v1.5')
print('Model downloaded successfully')
"
```

### Prevention

1. **Always use `qdrant-client[fastembed]`** - the fastembed extras are required for embeddings:
   ```toml
   # pyproject.toml
   dependencies = [
       "qdrant-client[fastembed]>=1.14.0",
   ]
   ```

2. **Configure model cache directory** (recommended for production):
   ```bash
   # Set custom cache directory for embedding models
   export EMBEDDING_CACHE_DIR=/opt/qmcp/model_cache
   
   # First launch: model will be downloaded and cached
   # Subsequent launches: model loaded from cache
   ```

3. **Verify MCP server starts correctly** - check logs on startup:
   ```
   Starting qmcp server...
   Loading embedding model: BAAI/bge-small-en-v1.5 (cache: /opt/qmcp/model_cache)
   Embedding model loaded successfully. Vector dimension: 384
   ```
   
   If model download fails, server will exit with error:
   ```
   ERROR: Failed to load embedding model 'BAAI/bge-small-en-v1.5': 
   Could not download model. Network error: ...
   ```

4. **Test search after indexing** - always verify vectors were created properly:
   ```
   qdrant_search(collection="your-collection", query="test", limit=1)
   # Should return score > 0.7, not null
   ```

### Custom Model Cache Directory

By default, fastembed caches models in `/tmp/fastembed_cache`. For production deployments, you may want to use a persistent directory:

```bash
# Environment variable
export EMBEDDING_CACHE_DIR=/var/lib/qmcp/models

# Or in .env file
EMBEDDING_CACHE_DIR=/var/lib/qmcp/models
```

**Benefits:**
- Models persist across restarts (no re-download)
- Can be pre-populated during Docker image build
- Easier to manage in containerized environments

**Docker example:**
```dockerfile
# Build cache into image
COPY model_cache/ /var/lib/qmcp/models

# Or mount at runtime
docker run -v /path/to/model_cache:/var/lib/qmcp/models qmcp-qdrant
```

---

## Connection Problems

### Symptom: "Connection failed" or "Cannot connect to Qdrant"

### Diagnosis

1. **Check if Qdrant is running**:
   ```bash
   curl http://your-qdrant-host:6333
   ```

2. **Check QDRANT_URL environment variable**:
   ```bash
   echo $QDRANT_URL
   ```

3. **Test server status**:
   ```
   qdrant_get_status()
   ```

### Solutions

1. **Verify Qdrant URL** - default is `http://localhost:6333`:
   ```bash
   export QDRANT_URL=http://192.168.1.100:6333
   ```

2. **Check network connectivity**:
   ```bash
   # From MCP server host
   curl -s http://qdrant-host:6333/collections
   ```

3. **For Kubernetes deployments**, see [Qdrant on Kubernetes](https://github.com/BigKAA/youtube/tree/master/Utils/Qdrant)

---

## Indexing Problems

### Symptom: Files not indexed / Missing files

### Diagnosis

```bash
# Compare Qdrant state with filesystem
qdrant_diff_collection(collection="your-collection", repo_path="/path/to/repo")
```

This returns:
- **orphans**: Vectors without corresponding files (cleanup candidates)
- **missing**: Files on disk but not in Qdrant
- **modified**: Files with content hash mismatch

### Solutions

1. **Incremental reindex** (recommended for updates):
   ```
   qdrant_reindex(collection="your-collection", path="/path/to/repo", mode="incremental")
   ```

2. **Full reindex** (if corrupted):
   ```
   qdrant_reindex(collection="your-collection", path="/path/to/repo", mode="full")
   ```

3. **Check gitignore** - files may be excluded:
   ```bash
   # Verify file is not gitignored
   git check-ignore -v path/to/file
   ```

---

## Search Returns No Results

### Symptom: Search returns empty results or `null` scores

### Diagnosis Steps

1. **Check collection has vectors**:
   ```
   qdrant_get_collection_info(collection="your-collection")
   ```
   - `points_count` should be > 0

2. **Verify vectors are valid**:
   ```
   qdrant_diagnose_collection(collection="your-collection")
   ```
   - Check `indexed_vectors_count` - should equal `points_count`
   - If `indexed_vectors_count: 0`, see [Embedding Model Issues](#embedding-model-issues)

3. **Test with generic query**:
   ```
   qdrant_search(collection="your-collection", query="the", limit=5)
   ```

### Common Causes

| Cause | Diagnosis | Solution |
|-------|-----------|----------|
| Empty collection | `points_count: 0` | Run `qdrant_index_directory` |
| Zero-dim vectors | `indexed_vectors_count: 0` | Reindex (see above) |
| Score threshold too high | Results filtered out | Lower `score_threshold` to 0.5 |
| Wrong collection | Wrong project | Check `collection` parameter |
| File not indexed | File missing from diagnose | Reindex project |

---

## Performance Issues

### Slow Indexing

**Cause**: Large project with many files

**Solution**:
1. Use incremental mode: `mode="incremental"`
2. Enable file watcher for live updates
3. Adjust batch size: `BATCH_SIZE=100`

### High Memory Usage

**Cause**: Embedding model loaded in memory

**Solution**:
1. Use smaller embedding model: `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5`
2. Process in smaller batches
3. Limit number of parallel index operations

---

## File Watcher Issues

### Symptom: Changes not detected / Files not reindexed

### Diagnosis

```
qdrant_get_status()
```

Check `watcher_active: true` and `watched_paths` contains your paths.

### Solutions

1. **Restart watcher**:
   ```
   qdrant_watch_stop()
   qdrant_watch_start(paths=["/path/to/watch"])
   ```

2. **Check file permissions** - watcher needs read access

3. **Verify paths are correct**:
   ```
   qdrant_get_status()
   # Look at watched_paths
   ```

---

## Getting Help

### Diagnostic Commands

Run these to gather information for troubleshooting:

```bash
# 1. Server status
qdrant_get_status()

# 2. Collection info
qdrant_get_collection_info(collection="your-collection")

# 3. Full diagnostics
qdrant_diagnose_collection(collection="your-collection")

# 4. List indexed files
qdrant_list_indexed_files(collection="your-collection", limit=10)
```

### Debug Mode

Enable verbose logging:

```bash
export LOG_LEVEL=DEBUG
export LOG_FORMAT=text
qmcp-qdrant
```

### Check Version

```bash
python -m qmcp --version
# or
qmcp-qdrant --version
```
