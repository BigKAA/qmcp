# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Orphan self-termination for stdio servers (`orphan.py`): a background task records the parent PID at startup and exits the process (after a best-effort watcher shutdown) as soon as `os.getppid()` changes - i.e. when the MCP client died and the process was reparented to init. Unix never kills children of a dead parent, and stdin EOF is only delivered when every holder of the pipe closes it (supervisor daemons and Electron-style clients are prone to inheriting the fd), so orphaned servers could keep watching and embedding indefinitely. The guard runs only for the stdio transport; streamable-http/sse deployments under service managers are unaffected

## [0.3.2] - 2026-11-10

### Added
- Deleted files are now tracked end to end: the poll watcher detects paths missing from the snapshot and emits debounced `deleted` events, and `Indexer.delete_file` removes the file's points via a server-side `file_path` filter (`QdrantClientWrapper.delete_points_by_path`). Previously points of deleted files stayed in Qdrant forever and search kept returning pointers to files nothing could read. Atomic saves (unlink + rename) collapse into a reindex via the per-path latest-event-wins debounce, and a file recreated before processing keeps its points
- Lazy self-healing in `qdrant_search`: hits pointing under a watched root at a file missing from disk are dropped from the response, and their points are deleted in a fire-and-forget background task - the read path never mutates the database synchronously. Paths outside this server's watched roots are never judged (a shared Qdrant receives valid indexes from other machines); `qdrant_cleanup` remains the manual reconciliation backstop for deletions that happened while no watcher was running

### Fixed
- The MCP `initialize` response now reports the package version in `serverInfo` (`MCPServer(version=__version__)`); it was empty before
- Watch events now index exactly the changed file instead of re-walking and re-hashing its whole parent directory (`server.py` `_handle_watch_change` + new `Indexer.index_file`) - on busy trees this was the dominant CPU cost of every save, multiplied by each watching process
- Per-file hash checks now fetch only that file's points via a server-side payload filter instead of downloading the entire collection for every file (`QdrantClientWrapper.get_file_points`)
- Cross-process single-flight locking (`locking.py`, lock dir configurable via `INDEX_LOCK_DIR`, default `~/.cache/qmcp-locks`): when several qmcp processes watch the same tree, the first one embeds a changed file and the rest skip it instead of duplicating the inference; the content hash is re-checked under the lock so the winner's upload ends the race
- ONNX embedding inference threads are now capped (`EMBEDDING_THREADS`, default `min(4, CPU count)`) - previously each qmcp process ran inference on all cores, and N client processes could saturate the machine

## [0.3.1] - 2026-11-09

### Fixed
- Watcher no longer blocks MCP server startup or the event loop on large `WATCH_PATHS` trees: the baseline scan and periodic re-scans run in a worker thread, ignored directories (`node_modules`, `.git`, `.venv`, hidden dirs, ...) are pruned during traversal instead of being fully scanned, and the poll interval adapts to the measured scan duration (grows up to `max_poll_interval` on slow scans) - previously the initial `rglob` scan blocked `initialize` until the client timed out (`Timed out after 30000ms`)
- Logs and startup messages now go to stderr instead of stdout, keeping the MCP stdio protocol stream clean (`logging_config.py`, `__main__.py`, `main.py`)

## [0.3.0] - 2026-11-09

### Added
- Markdown section chunking: files are split into per-section chunks (`##`/`###` headers, configurable levels) with precise `line_start`/`line_end`; oversized sections (> 8 KB) are split by paragraph boundaries, never inside code fences; files without headers keep a single `document` chunk
- File tails beyond the former 10 KB embedding cap are now indexed
- Tests for the Markdown parser (sectioning, code-fence handling, merging, splitting, `imports` extraction) and for compact search responses

### Changed
- **BREAKING for existing collections**: the markdown chunk schema changed (per-section chunks instead of one chunk per file) - existing markdown collections require a full reindex (`mode="full"`) after upgrading
- `qdrant_search` now returns compact pointer fields only (`score`, `file_path`, `type`, `name`, `line_start`, `line_end`, `language`, optional `signature`); the always-empty `content`, `imports` and `symbol_names` fields were removed (~90% smaller responses)
- Markdown chunk `imports` now holds unique code-block languages from fence opener lines (max 5) instead of the first word of every line inside blocks
- Changed files now have their stale points deleted before re-upsert (previously a re-chunked file left duplicate chunks behind)
- Migrated from MCP Python SDK v1 (`FastMCP`) to v2 (`MCPServer`); tool surface and wire protocol are unchanged

### Fixed
- `file_path_pattern` now performs real glob matching (fnmatch) against the full path; previously `*.py` was treated as full-text token matching and silently failed as a suffix filter

## [0.2.4] - 2026-04-10

### Added
- N/A

### Changed
- Improved .gitignore to exclude common Python build artifacts

### Fixed
- N/A

### Security
- N/A

## [0.2.3] - 2026-04-10

### Added
- Documentation examples for `WATCH_PATHS` covering single-path, comma-separated, and JSON-array formats in both English and Russian READMEs

### Changed
- Bumped package metadata and README version badges for the v0.2.3 release

### Fixed
- `WATCH_PATHS` environment parsing now accepts plain path strings in addition to comma-separated values and JSON arrays, preventing MCP server startup failures in global OpenCode configuration

### Security
- N/A

## [0.2.2] - 2026-04-10

### Added
- Automatic watcher startup from configured `WATCH_PATHS` during MCP server startup
- New `qdrant_watch_ensure` tool to ensure workspace coverage without dropping already watched projects
- Extended status payload with `configured_watch_paths` for workspace-level watcher checks

### Changed
- Updated OpenCode and agent documentation for the two-level automatic indexing workflow used by a single global MCP server shared across multiple repositories
- Improved watcher path normalization and reuse logic for multi-project environments

### Fixed
- Automatic indexing now activates correctly for OpenCode sessions that need to verify and extend watcher coverage for the current workspace
- Synchronized package and runtime version metadata for the new release

### Security
- N/A

## [0.2.1] - 2026-04-09

### Added
- N/A

### Changed
- N/A

### Fixed
- **Fastembed compatibility**: Replace deprecated `doc_embed` method with `passage_embed` for fastembed 0.7.4+ compatibility

### Security
- N/A

## [0.2.0] - 2026-04-09

### Added
- **Embedding model validation on startup**: MCP server now validates the embedding model when connecting to Qdrant. If fastembed is not installed or model download fails, server exits with clear error message
- **Custom embedding cache directory**: New `EMBEDDING_CACHE_DIR` environment variable allows specifying where to store cached models (persists across restarts)
- **Model instance caching**: Embedding model is loaded once and reused for all operations (search, upsert)
- **Vector validation in diagnostics**: `qdrant_diagnose_collection` now detects and warns about zero-dimension vectors
- **Troubleshooting documentation**: Added `docs/TROUBLESHOOTING.md` with detailed solutions for common issues
- Russian README translation (`README.ru.md`)
- Structured metadata documentation (`docs/STRUCTURED_METADATA.md`, `docs/STRUCTURED_METADATA.ru.md`)
- OpenCode skill with diagnostic workflows

### Changed
- **Improved search performance**: Now uses pre-generated embeddings instead of `models.Document` which created new model instances on each call
- **Better error messages**: Network errors during model download are clearly reported
- Enhanced `ParsedChunk` dataclass with extended metadata fields
- Improved MarkdownParser with code block language extraction
- Updated MultiLanguageParser with import extraction fallback

### Fixed
- **Zero-dimension vectors**: Fixed issue where vectors were created with dimensionality 0 when fastembed failed silently
- Fixed diagnostics mock in tests for `validate_collection_vectors` method
- Fixed import ordering in server.py

### Security
- N/A

## [0.1.5] - 2026-03-27

### Added
- Gitignore support: indexer now respects `.gitignore` files
- Automatically excludes `node_modules/`, `__pycache__/`, `.venv/`, build artifacts, etc.
- Added `pathspec` dependency for gitignore pattern matching
- Added tests for gitignore functionality

### Changed
- Updated README with gitignore documentation and indexing notes
- Updated skill documentation with gitignore support info

### Fixed
- N/A

### Security
- N/A

## [0.1.4] - 2026-03-27

### Added
- N/A

### Changed
- N/A

### Fixed
- Use correct CollectionInfo attributes (indexed_vectors_count instead of vectors_count)
- Update server version to 0.1.4

### Security
- N/A

## [0.1.3] - 2026-03-27

### Added
- N/A

### Changed
- Rename package to qmcp-qdrant (due to name conflict on PyPI)
- Add entry point for command-line execution

### Fixed
- N/A

### Security
- N/A

## [0.1.1] - 2026-03-27

### Added
- N/A

### Changed
- Remove Docker references from documentation

### Fixed
- Change license from MIT to Apache 2.0

### Security
- N/A

## [0.1.0] - 2026-03-27

### Added
- Make collection parameter required for data isolation

### Changed
- Simplify documentation - focus on local development
- Use opencode mcp add for integration
- Change license to Apache 2.0

### Fixed
- Migrate from deprecated tool.uv to dependency-groups

### Security
- N/A
