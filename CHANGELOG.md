# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
