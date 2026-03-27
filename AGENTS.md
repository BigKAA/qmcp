# AGENTS.md - Instructions for AI Agents

This file contains instructions for AI agents working on or with this project.

## Project Overview

- **Project Name**: qmcp (QDrant MCP Server)
- **Purpose**: Semantic search server for code and documentation using Qdrant vector database
- **Language**: Python 3.11+
- **Framework**: FastMCP (MCP Python SDK)

## Key Commands

### Development

```bash
# Install dependencies
make install

# Run in development mode (with MCP inspector)
make mcp-dev

# Run tests
make test

# Run with coverage
make test-cov

# Lint code
make lint

# Format code
make format
```

### Docker

```bash
# Build image
make build

# Run locally
docker run -e QDRANT_URL=http://192.168.218.190:6333 -p 8000:8000 qmcp:latest
```

### Kubernetes

```bash
# Deploy with Helm
helm upgrade --install qmcp ./chart

# Delete deployment
helm uninstall qmcp

# Dry run (check values)
helm install --dry-run --debug qmcp ./chart
```

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed system architecture.

## File Structure

```
qmcp/
├── src/
│   ├── qmcp/
│   │   ├── server.py      # FastMCP server, tools definition
│   │   ├── client.py     # Qdrant client wrapper
│   │   ├── indexer.py    # Code indexing logic
│   │   ├── watcher.py    # File system watcher
│   │   ├── cleanup.py    # Stale vector cleanup
│   │   ├── parser/       # Multi-language parsers
│   │   │   ├── base.py   # Parser interface
│   │   │   ├── python.py # AST parser
│   │   │   └── multi.py  # tree-sitter parsers
│   │   └── models.py     # Pydantic models
│   └── main.py           # Entry point
├── tests/
│   ├── test_server.py
│   ├── test_indexer.py
│   └── test_parser.py
├── chart/                # Helm chart
├── Dockerfile
├── Makefile
└── pyproject.toml
```

## Adding New Features

### Adding a New Tool

1. Add tool function to `src/qmcp/server.py`:
   ```python
   @mcp.tool()
   async def my_new_tool(param: str = Field(...)) -> dict:
       """Tool description for LLM."""
       # Implementation
       return result
   ```

2. Add tests to `tests/test_server.py`

3. Update README.md with tool documentation

### Adding a New Parser

1. Create parser class in `src/qmcp/parser/`
2. Implement `BaseParser` interface:
   - `can_parse(file_path)` - check if parser handles this file
   - `parse_file(file_path)` - parse file and return chunks
3. Add parser to `PARSERS` list in `parser/__init__.py`
4. Add tests

### Adding Configuration

1. Add to `chart/values.yaml`
2. Add environment variable handling in `chart/templates/deployment.yaml`
3. Add to `.env.example`
4. Document in README.md

## Testing

### Running Tests

```bash
# All tests
make test

# With coverage
make test-cov

# Specific test file
pytest tests/test_parser.py -v
```

### Test Structure

- `tests/test_server.py` - MCP tools tests
- `tests/test_indexer.py` - Indexer tests
- `tests/test_parser.py` - Parser tests

## Docker Build

### Build and Push

```bash
# Build
docker build -t qmcp:latest .

# Tag for registry
docker tag qmcp:latest registry.example.com/qmcp:latest

# Push
docker push registry.example.com/qmcp:latest
```

### Local Testing

```bash
# Run with local Qdrant
docker run -e QDRANT_URL=http://host.docker.internal:6333 -p 8000:8000 qmcp:latest

# Mount local directory
docker run -v /path/to/repo:/data/repo -e QDRANT_URL=http://192.168.218.190:6333 -p 8000:8000 qmcp:latest
```

## Helm Chart

### Values Configuration

Key values in `chart/values.yaml`:

| Key | Description | Default |
|-----|-------------|---------|
| `replicaCount` | Number of pods | 1 |
| `image.tag` | Image version | latest |
| `env.QDRANT_URL` | Qdrant server URL | http://192.168.218.190:6333 |
| `env.EMBEDDING_MODEL` | Embedding model | BAAI/bge-small-en-v1.5 |
| `volume.storageClassName` | Storage class | nfs-client |
| `resources.limits.memory` | Memory limit | 2Gi |

### Deploy Steps

1. Build Docker image
2. Push to registry (if using remote)
3. Update `values.yaml` if needed
4. Deploy: `helm upgrade --install qmcp ./chart`
5. Check status: `kubectl get pods -l app.kubernetes.io/name=qmcp`

## Integration with OpenCode

### Configuration

Add to OpenCode config:

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

### Available Tools

Once configured, OpenCode will have access to:

- `qdrant_search` - Semantic search
- `qdrant_index_directory` - Index code
- `qdrant_reindex` - Full/incremental reindex
- `qdrant_list_collections` - List collections
- `qdrant_get_collection_info` - Collection details
- `qdrant_delete_collection` - Delete collection
- `qdrant_watch_start` - Start watcher
- `qdrant_watch_stop` - Stop watcher
- `qdrant_cleanup` - Clean stale vectors
- `qdrant_get_status` - Server status

## Troubleshooting

### Container Won't Start

```bash
# Check logs
kubectl logs -l app.kubernetes.io/name=qmcp

# Check events
kubectl describe pod -l app.kubernetes.io/name=qmcp
```

### Qdrant Connection Failed

1. Verify Qdrant is running: `curl http://192.168.218.190:6333`
2. Check network policies
3. Verify QDRANT_URL in configmap

### Indexing Not Working

1. Check PVC is mounted: `kubectl exec <pod> -- ls /data/repo`
2. Check file permissions
3. Verify embedding model is available

## Code Style

- **Linter**: ruff
- **Formatter**: ruff format
- **Type Checker**: mypy
- **Line Length**: 100 characters
- **Python Version**: 3.11+

## Common Patterns

### Async Tool

```python
@mcp.tool()
async def my_tool(param: str) -> dict:
    """Description for LLM."""
    # Async operations
    result = await async_function()
    return {"result": result}
```

### Adding Configuration

```python
import os

# From environment
value = os.getenv("MY_VAR", "default")

# From pydantic settings
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    my_var: str = "default"

settings = Settings()
```

### Error Handling

```python
@mcp.tool()
async def safe_tool() -> dict:
    try:
        result = risky_operation()
        return {"status": "success", "data": result}
    except SpecificError as e:
        return {"status": "error", "message": str(e)}
```

## Infrastructure

### Kubernetes Cluster

The Kubernetes cluster is accessible via `kubectl`. Before deploying, verify cluster connectivity:

```bash
# Check cluster connectivity
kubectl cluster-info

# Verify kubectl is configured correctly
kubectl get nodes
```

### Docker

Docker is available locally for building and testing images:

```bash
# Verify Docker is running
docker version
docker ps
```

### Docker Registry

Use the private registry for storing and pulling images during development and testing:

- **Registry URL**: `https://harbor.kryukov.lan/library`
- **Image naming convention**: `harbor.kryukov.lan/library/qmcp:<tag>`

```bash
# Login to registry
docker login harbor.kryukov.lan

# Build and tag for private registry
docker build -t qmcp:latest .
docker tag qmcp:latest harbor.kryukov.lan/library/qmcp:latest

# Push to registry
docker push harbor.kryukov.lan/library/qmcp:latest

# Pull from registry
docker pull harbor.kryukov.lan/library/qmcp:latest
```

## Communication

- **Language**: All communication with users should be in Russian
- **Code comments**: All code comments must be in English
- **Documentation**: Project documentation in English (README.md, etc.)

## Code Comments Guidelines

All code should include detailed comments in English. This includes:

- Module-level docstrings explaining the purpose of each module
- Class docstrings with description, parameters, and return values
- Function/method docstrings with:
  - Brief description
  - Detailed explanation of parameters (type, purpose)
  - Return value description
  - Any exceptions that may be raised
  - Usage examples where helpful
- Inline comments for complex logic or non-obvious decisions

Example:

```python
"""
Module for handling Qdrant client operations.

This module provides a wrapper around the Qdrant client library,
abstracting common operations like collection management and vector search.
"""

class QdrantWrapper:
    """
    Wrapper class for Qdrant client operations.
    
    Provides high-level interface for interacting with Qdrant vector database,
    including collection CRUD operations and semantic search functionality.
    
    Attributes:
        client: The underlying Qdrant client instance
        collection_name: Name of the active collection
    """
    
    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Perform semantic search on the collection.
        
        Args:
            query: The search query string
            limit: Maximum number of results to return (default: 10)
            
        Returns:
            List of dictionaries containing search results with scores
            
        Raises:
            ConnectionError: If unable to connect to Qdrant server
            ValueError: If collection does not exist
        """
        # Implementation...
```

## Dependencies

Key dependencies in `pyproject.toml`:

- `mcp[cli]` - MCP server framework
- `qdrant-client[fastembed]` - Qdrant client + embeddings
- `tree-sitter` - Code parsing
- `watchdog` - File system watching
- `pytest` - Testing
- `ruff` - Linting/formatting
