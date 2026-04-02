# AGENTS.md - Instructions for AI Agents

This file contains instructions for AI agents working on or with this project.

## Project Overview

- **Project Name**: qmcp (QDrant MCP Server)
- **Purpose**: Semantic search server for code and documentation using Qdrant vector database
- **Language**: Python 3.11+
- **Framework**: FastMCP (MCP Python SDK)

## Key Commands

### Quick Start

```bash
# Install dependencies
make install

# Install as MCP server for OpenCode
make mcp-install

# Run tests
make test

# Lint code
make lint
```

### Development

```bash
# Run in development mode (with MCP inspector)
make mcp-dev

# Run with coverage
make test-cov

# Format code
make format
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
│   │   ├── config.py     # Pydantic settings
│   │   ├── indexer.py    # Code indexing logic
│   │   ├── watcher.py    # File system watcher
│   │   ├── cleanup.py    # Stale vector cleanup
│   │   ├── logging_config.py  # Logging configuration
│   │   ├── parser/       # Multi-language parsers
│   │   │   ├── base.py   # Parser interface
│   │   │   ├── python.py # AST parser
│   │   │   └── multi.py  # tree-sitter parsers
│   │   └── models.py     # Pydantic models
│   └── main.py           # Entry point
├── tests/
│   ├── test_server.py
│   ├── test_indexer.py
│   ├── test_parser.py
│   ├── test_watcher.py
│   └── test_cleanup.py
├── chart/                # Helm chart (optional, for production)
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

1. Add environment variable to `.env.example`
2. Add to `Settings` class in `src/qmcp/config.py`
3. Update README.md with documentation

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
- `tests/test_watcher.py` - Watcher tests
- `tests/test_cleanup.py` - Cleanup tests

## Integration with OpenCode

### Installation

```bash
# Add MCP server to OpenCode
opencode mcp add qmcp uv run python -m qmcp.server
```

Or edit `~/.config/opencode/opencode.json` directly (for environment variables):

```json
{
  "mcp": {
    "qmcp": {
      "type": "local",
      "command": ["uv", "run", "python", "-m", "qmcp.server"],
      "environment": {
        "QDRANT_URL": "http://192.168.218.190:6333"
      }
    }
  }
}
```

### Manage MCP Servers

```bash
opencode mcp list          # List all MCP servers
opencode mcp debug qmcp    # Debug connection issues
opencode mcp logout qmcp   # Remove MCP server
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

### Qdrant Connection Failed

1. Verify Qdrant is running: `curl http://192.168.218.190:6333`
2. Check network connectivity
3. Verify QDRANT_URL environment variable

### Indexing Not Working

1. Check file permissions
2. Verify embedding model is available
3. Check logs for parsing errors

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

## Publishing to PyPI

### Prerequisites

1. Store PyPI token in `~/.pypirc` (NEVER commit this file to git):
   ```ini
   [pypi]
   username = __token__
   password = pypi-your-token-here
   ```

### Build and Publish

```bash
# 1. Create build environment
uv venv /tmp/build-venv --clear
source /tmp/build-venv/bin/activate

# 2. Install build tools
uv pip install build twine hatch

# 3. Build package
hatch build wheel

# 4. Upload to PyPI (uses ~/.pypirc config)
twine upload wheel/* -c ~/.pypirc
```

### Security Rules
- **Never** store PyPI tokens in AGENTS.md, .env, or any git-tracked files
- **Never** commit `~/.pypirc` to version control
- Use `~/.pypirc` for local token storage

## Dependencies

Key dependencies in `pyproject.toml`:

- `mcp[cli]` - MCP server framework
- `qdrant-client[fastembed]` - Qdrant client + embeddings
- `tree-sitter` - Code parsing
- `watchdog` - File system watching
- `pytest` - Testing
- `ruff` - Linting/formatting
