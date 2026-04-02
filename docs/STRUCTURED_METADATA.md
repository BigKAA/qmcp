# Structured Metadata for Filtering

> **Documentation:** English | [Русский](./STRUCTURED_METADATA.ru.md)

## Overview

This document describes the structured metadata implementation for the Qdrant MCP Server, enabling advanced filtering capabilities during semantic search operations.

### What is Structured Metadata?

Structured metadata refers to enriched information extracted from source code during indexing that provides granular details about each code chunk. This enables precise filtering and more relevant search results.

### Why Structured Metadata?

Without metadata filtering, semantic search can return irrelevant results. For example, searching for "authentication" might return documentation about auth in a completely different context than what the user needs. With structured metadata:

- Find exact symbol definitions by name
- Filter results by code type (functions, classes, files)
- Search within specific programming languages
- Combine filters for precise targeting

---

## New Fields in Qdrant Payload

Each indexed chunk now contains the following enhanced metadata:

```json
{
    "file_path": "src/auth/users.py",
    "content": "def get_user(user_id: int) -> User:\n    \"\"\"Retrieve a user by ID.\"\"\"\n    session = Session()\n    return session.query(User).get(user_id)",
    "chunk_type": "function_def",
    "signature": "def get_user(user_id: int) -> User",
    "symbol_names": ["get_user", "user_id", "User", "session", "Session", "query"],
    "imports": ["from models import User", "from db import Session"],
    "language": "python"
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `file_path` | `str` | Relative path to the source file |
| `content` | `str` | The actual code content of the chunk |
| `chunk_type` | `str` | Classification of the code chunk |
| `signature` | `str \| None` | Full function/class signature (Python only) |
| `symbol_names` | `list[str]` | All identifiers found in the chunk |
| `imports` | `list[str]` | Import statements from the source file |
| `language` | `str` | Programming language identifier |

---

## Filter Parameters in qdrant_search

The `qdrant_search` tool now accepts the following filter parameters:

### Available Filters

| Parameter | Type | Description | Example Values |
|-----------|------|-------------|----------------|
| `chunk_type` | `str \| None` | Type of code chunk to filter | `"function_def"`, `"class_def"` |
| `symbol_name` | `str \| None` | Exact symbol name match | `"get_user"`, `"User"` |
| `language` | `str \| None` | Programming language | `"python"`, `"go"`, `"typescript"` |

### API Signature

```python
@mcp.tool()
async def qdrant_search(
    query: str,
    collection: str,
    limit: int = 5,
    score_threshold: float = 0.7,
    chunk_type: str | None = None,      # NEW: Filter by chunk type
    symbol_name: str | None = None,      # NEW: Exact symbol match
    language: str | None = None,         # NEW: Language filter
) -> list[dict[str, Any]]:
    """
    Perform semantic search with optional metadata filters.
    
    All filter parameters are optional. When omitted, search behaves
    as before (unfiltered semantic search).
    """
```

---

## Detailed Usage Examples

### Example 1: Find Functions by Exact Name

**Scenario:** You need to find where a specific function is defined across your codebase.

```
User Query: "Find where get_user is defined"
```

**API Call:**
```python
results = await qdrant_search(
    query="user authentication get_user",
    collection="myproject",
    symbol_name="get_user",
    limit=10
)
```

**Result:** Returns only code chunks where `get_user` appears as a defined symbol, ranked by semantic similarity to the query.

**Why This Works:** The `symbol_names` field contains all identifiers extracted from each chunk. When `symbol_name="get_user"` is specified, Qdrant's filtering mechanism ensures only chunks containing that exact symbol are returned.

---

### Example 2: Search Only Class Definitions

**Scenario:** You want to find all data models and class structures in your project.

```
User Query: "data models and structures"
```

**API Call:**
```python
results = await qdrant_search(
    query="data model structure schema",
    collection="myproject",
    chunk_type="class_def",
    limit=10
)
```

**Result:** Only Python `class` definitions are returned, filtered from the full semantic results.

**Why This Works:** The `chunk_type="class_def"` filter restricts results to chunks classified as class definitions. Other code (functions, imports, etc.) is excluded.

---

### Example 3: Filter by Programming Language

**Scenario:** You want to find API endpoint implementations, but only in Python files.

```
User Query: "API endpoints"
```

**API Call:**
```python
results = await qdrant_search(
    query="api endpoint route handler",
    collection="myproject",
    language="python",
    limit=10
)
```

**Result:** Returns Python-specific API endpoint implementations, excluding Go, TypeScript, or other language implementations.

**Why This Works:** The `language` field is set during parsing based on the file extension. Filtering by `"python"` ensures only Python source files are included.

---

### Example 4: Combining Multiple Filters

**Scenario:** You need to find authentication-related function definitions in Python only.

```
User Query: "authentication logic"
```

**API Call:**
```python
results = await qdrant_search(
    query="authentication login password verify",
    collection="myproject",
    chunk_type="function_def",
    language="python",
    limit=10
)
```

**Result:** Returns only Python function definitions that match the semantic query about authentication.

**Why This Works:** Multiple filters are combined with AND logic. A chunk must satisfy ALL specified filters to be included in results.

---

### Example 5: Async Function Detection

**Scenario:** Finding all asynchronous operations in a Python codebase.

```
User Query: "async operations"
```

**API Call:**
```python
results = await qdrant_search(
    query="async await fetch stream",
    collection="myproject",
    chunk_type="async_function_def",
    limit=10
)
```

**Result:** Only `async def` function definitions are returned.

---

### Example 6: Cross-Reference Search

**Scenario:** You want to find files that import a specific module.

```
User Query: "database operations"
```

**API Call:**
```python
results = await qdrant_search(
    query="database session query",
    collection="myproject",
    limit=50
)
# Then filter client-side for specific imports if needed
```

**Note:** Direct import filtering via Qdrant metadata requires storing imports per-chunk. See Implementation Details below.

---

## Backend Implementation Details

### ParsedChunk Dataclass

The core data structure for indexed code chunks:

```python
# src/qmcp/parser/base.py
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ParsedChunk:
    """
    Represents a parsed code chunk with extracted metadata.
    
    Attributes:
        file_path: Relative path to the source file
        content: The actual code content
        chunk_type: Classification (function_def, class_def, file, etc.)
        name: The primary symbol name (function name, class name, etc.)
        line_start: Starting line number in source file
        line_end: Ending line number in source file
        docstring: Associated docstring text if present
        signature: Full function/class signature (Python AST-based)
        symbol_names: All identifiers found in the chunk
        imports: Import statements from the source file
        language: Programming language identifier
    """
    file_path: str
    content: str
    chunk_type: str
    name: str
    line_start: int
    line_end: int
    docstring: str = ""
    signature: Optional[str] = None       # NEW: "def foo(a: int) -> str"
    symbol_names: list[str] = field(default_factory=list)  # NEW: ["foo", "a"]
    imports: list[str] = field(default_factory=list)      # NEW: ["import os"]
    language: str = "unknown"              # NEW: "python"
```

### Python Parser Implementation

The Python parser (`src/qmcp/parser/python.py`) extracts metadata using Python's AST module:

#### Signature Extraction

```python
def _extract_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    """
    Reconstruct function/class signature from AST node.
    
    Returns a string like: "def function_name(arg1: Type1, arg2: Type2) -> ReturnType"
    
    Handles:
    - Positional and keyword arguments
    - Default values
    - Type annotations
    - *args and **kwargs
    """
    # Implementation details in parser/python.py
```

#### Symbol Names Extraction

```python
def _extract_symbol_names(self, node: ast.AST) -> list[str]:
    """
    Extract all identifier names from an AST node.
    
    Includes:
    - Function/class name itself
    - Parameter names
    - Type annotations references
    - Local variable assignments within the body
    - Called function names
    """
    # Walks the AST and collects all Name nodes
```

#### Import Extraction

```python
def _extract_imports(self, tree: ast.AST) -> list[str]:
    """
    Extract all import statements from a file.
    
    Returns list of strings like:
    - "import os"
    - "from typing import Optional, List"
    - "from models import User, Session"
    """
```

### Search API Implementation

The search tool in `src/qmcp/server.py` implements metadata filtering:

```python
async def qdrant_search(
    query: str,
    collection: str,
    limit: int = 5,
    score_threshold: float = 0.7,
    chunk_type: str | None = None,
    symbol_name: str | None = None,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search with metadata filtering.
    
    Filter Logic:
    1. Perform vector search to get candidate chunks
    2. Apply score threshold
    3. Apply metadata filters (AND combination)
    4. Return filtered, ranked results
    """
    # Build filter conditions
    conditions = []
    
    if chunk_type:
        conditions.append({"key": "chunk_type", "match": {"value": chunk_type}})
    
    if symbol_name:
        conditions.append({"key": "symbol_names", "match": {"value": symbol_name}})
    
    if language:
        conditions.append({"key": "language", "match": {"value": language}})
    
    # Execute search with filters using Qdrant's filter scoring
```

---

## Chunk Types Reference

| chunk_type | Description | AST Node | Example |
|------------|-------------|----------|---------|
| `function_def` | Python function definition | `ast.FunctionDef` | `def hello():` |
| `async_function_def` | Python async function | `ast.AsyncFunctionDef` | `async def fetch():` |
| `class_def` | Python class definition | `ast.ClassDef` | `class User:` |
| `file` | Multi-language file chunk | N/A (tree-sitter) | Go, JS, TS files |
| `document` | Documentation file | N/A | Markdown files |

### Chunk Type Details

#### function_def
Python standard function definitions:
```python
def get_user(user_id: int) -> User:
    return db.query(User).get(user_id)
```

#### async_function_def
Python asynchronous function definitions:
```python
async def fetch_data(url: str) -> bytes:
    async with aiohttp.get(url) as response:
        return await response.read()
```

#### class_def
Python class definitions including methods:
```python
class User(Base):
    id: int
    name: str
    
    def authenticate(self, password: str) -> bool:
        return verify_hash(self.password_hash, password)
```

#### file
Multi-language chunks for languages without native AST support:
- Go source files
- JavaScript/TypeScript files
- Java, C#, and other compiled languages

#### document
Documentation and markdown files:
- README files
- API documentation
- Technical specifications

---

## Backward Compatibility

### Design Principles

All changes are designed to be fully backward compatible:

1. **Optional Filters:** All new filter parameters are optional (`None` by default). When not specified, search behaves exactly as before.

2. **Nullable Fields:** New payload fields (`signature`, `symbol_names`, `imports`, `language`) are nullable. Older indexed data without these fields will have `None` or empty values.

3. **Graceful Degradation:** Search works with partial metadata:
   - Chunks without `signature` still searchable by content
   - Chunks without `symbol_names` still found via `chunk_type` filter
   - Chunks without `language` still searchable without language filter

### Migration Path

Existing indexed data does not need re-indexing. However, to benefit from new filtering capabilities:

```python
# Old data works without changes
results = await qdrant_search(
    query="authentication",
    collection="myproject"
)  # Works exactly as before

# New filtering available when needed
results = await qdrant_search(
    query="authentication",
    collection="myproject",
    chunk_type="function_def"  # Now available
)
```

---

## Future Enhancements

Potential future features:

1. **Import-based Filtering:** Filter chunks by their imports (e.g., find all files using "pytest")
2. **Symbol Relationship Graph:** Track which symbols reference other symbols
3. **File-level Aggregations:** Group results by file
4. **Custom Metadata:** Allow users to add custom tags during indexing
5. **Regex Symbol Matching:** Pattern matching on symbol names

---

## Testing

Run the test suite to verify metadata functionality:

```bash
# Run all tests
make test

# Run parser tests specifically
pytest tests/test_parser.py -v

# Run server tests with metadata filters
pytest tests/test_server.py -v -k "search"
```

### Test Coverage

- `test_python_parser_metadata`: Verifies signature, symbol_names, imports extraction
- `test_search_with_chunk_type_filter`: Tests chunk_type filtering
- `test_search_with_symbol_name_filter`: Tests symbol_name exact matching
- `test_search_with_language_filter`: Tests language filtering
- `test_combined_filters`: Tests multiple filters together
- `test_backward_compatibility`: Ensures unfiltered search still works

---

## Quick Reference

### Search with Filters

```python
# Find specific function
qdrant_search(query="...", symbol_name="get_user")

# Find only classes  
qdrant_search(query="...", chunk_type="class_def")

# Find Python code only
qdrant_search(query="...", language="python")

# Combine filters
qdrant_search(
    query="authentication",
    chunk_type="function_def",
    language="python"
)
```

### Expected Payload Structure

```json
{
    "id": "uuid-here",
    "version": 1,
    "score": 0.95,
    "payload": {
        "file_path": "src/auth/users.py",
        "content": "def get_user(user_id: int) -> User:\n    ...",
        "chunk_type": "function_def",
        "signature": "def get_user(user_id: int) -> User",
        "symbol_names": ["get_user", "user_id", "User"],
        "imports": ["from models import User"],
        "language": "python"
    }
}
```
