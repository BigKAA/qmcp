# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- N/A

### Changed
- N/A

### Fixed
- N/A

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
