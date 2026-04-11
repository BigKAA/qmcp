# Implementation Plan: Model Selection & Corporate Knowledge Base

## Overview

This plan covers two major features:
1. **Model selection per collection** — ability to choose embedding model when creating/indexing a collection
2. **Corporate knowledge base support** — multi-collection architecture for shared company-wide knowledge

**Branch**: `v0.3.0-pr` — all work MUST be done in this branch

**Requirement**: After completing each checkbox item, mark it as done. Do not leave items unchecked after implementation.

---

## Quick Ref: Recommended Models

| Use Case | Model | Dim | Size | Prefix | Notes |
|----------|-------|-----|------|--------|-------|
| Code search | `jinaai/jina-embeddings-v2-base-code` | 768 | 0.64 GB | No | Best for code, 30+ programming languages |
| English docs (lightweight) | `BAAI/bge-small-en-v1.5` | 384 | 0.07 GB | No | Default, fast, small |
| English docs (quality) | `BAAI/bge-large-en-v1.5` | 1024 | 1.2 GB | No | Best quality for English |
| Multilingual KB (RU+EN) | `intfloat/multilingual-e5-large` | 1024 | 2.24 GB | **Yes** | Best for corporate KB, 100 languages |
| Multilingual KB (lightweight) | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 384 | 0.22 GB | No | Compromise option |

**⚠️ E5 Prefix Requirement**: `intfloat/multilingual-e5-large` and other `e5-*` models **require** `query: ` / `passage: ` prefixes. This is handled **automatically** in Phase 2.5 — no manual action needed. See Phase 2.5 for implementation details.

---

## Phase 1: Model Selection Infrastructure

### 1.1 — Add `embedding_model` to collection metadata

**Files**: `src/qmcp/models.py`, `src/qmcp/client.py`

- [ ] Add `embedding_model: str` field to `CollectionInfo` response model in `models.py`
- [ ] Store `embedding_model` in Qdrant collection metadata (payload) on `create_collection()` in `client.py`
- [ ] Read `embedding_model` from collection metadata on `get_collection_info()` in `client.py`
- [ ] Add field to `qdrant_get_collection_info` tool response in `server.py`
- [ ] Add `qdrant_get_collection_info` test in `tests/test_server.py`

### 1.2 — Validate model compatibility on search/index

**Files**: `src/qmcp/client.py`, `src/qmcp/server.py`

- [ ] Create helper method `_get_collection_embedding_model(name)` in `QdrantClientWrapper` that reads model from collection metadata
- [ ] On `search()` — validate `self._embedding_model == collection_model`, raise clear error if mismatch
- [ ] On `upsert()` / indexing — validate model before upserting
- [ ] On `create_collection()` — store `embedding_model` in collection metadata
- [ ] Add unit tests for model mismatch scenarios in `tests/test_client.py` (create if missing)
- [ ] Add integration test: index with model A, search with model B → expect error

### 1.3 — Add `qdrant_list_supported_models` tool

**Files**: `src/qmcp/server.py`, `src/qmcp/models.py`

- [ ] Define `SupportedModel` pydantic model with fields: `model`, `dim`, `size_in_GB`, `languages`, `use_case`, `notes`
- [ ] Add tool `qdrant_list_supported_models(filter: str | None = None)` where filter can be `"code"`, `"multilingual"`, `"lightweight"`, `"all"`
- [ ] Return hardcoded list of recommended models with descriptions
- [ ] Add tool test in `tests/test_server.py`
- [ ] Add entry to README.md documentation

### 1.4 — Persist model in `create_collection`

**Files**: `src/qmcp/client.py`

- [ ] On `create_collection()` — call `client.set_collection_metadata()` (or alias payload) with `embedding_model` key
- [ ] Verify metadata is stored and retrievable via `get_collection_info()`

---

## Phase 2: Model Selection in Indexing Tools

### 2.1 — Add `model` parameter to `qdrant_index_directory`

**Files**: `src/qmcp/server.py`, `src/qmcp/models.py`, `src/qmcp/indexer.py`

- [ ] Add `model: str | None = Field(default=None, description="Embedding model to use (default: from settings)")` to `IndexRequest` model in `models.py`
- [ ] Add `model` parameter to `qdrant_index_directory()` tool signature
- [ ] Pass `model` through to `Indexer.index_directory()`
- [ ] If `model is None` — use `settings.embedding_model` (current behavior)
- [ ] Add test: call `qdrant_index_directory` with explicit model → verify collection metadata stores it

### 2.2 — Add `model` parameter to `qdrant_reindex`

**Files**: `src/qmcp/server.py`, `src/qmcp/models.py`, `src/qmcp/indexer.py`

- [ ] Add `model: str | None` to `ReindexRequest` model in `models.py`
- [ ] Add `model` parameter to `qdrant_reindex()` tool signature
- [ ] Pass model through to `Indexer.full_reindex()` and `Indexer.incremental_reindex()`
- [ ] For `full` reindex: update collection metadata with new model
- [ ] Add test: reindex with different model → collection metadata reflects new model

### 2.3 — Model-aware `Indexer`

**Files**: `src/qmcp/indexer.py`

- [ ] Update `Indexer.__init__()` to accept `model: str | None = None`
- [ ] If model is `None` — use `settings.embedding_model` (backward compatible)
- [ ] Pass model to `QdrantClientWrapper` when creating/using client for upsert
- [ ] Ensure `Indexer.index_directory()` creates collection with correct model metadata

### 2.4 — Remove global model assumption from `QdrantClientWrapper`

**Files**: `src/qmcp/client.py`

- [ ] Refactor `_load_embedding_model(model_name)` to accept `model_name: str` as parameter
- [ ] Replace singleton `_embedding_model_instance` with a cache dict: `_embedding_model_cache: dict[str, Any]`
- [ ] On any operation requiring embedding model, pass the target collection's model name
- [ ] Add `get_embedding_model_for_collection(collection_name)` helper that reads metadata and returns model name
- [ ] Test: load two different models sequentially → both should be cached and usable

### 2.5 — E5 Model Prefix Handling

**Files**: `src/qmcp/client.py`, `src/qmcp/models.py`, `tests/test_client.py`

**Background**: `intfloat/multilingual-e5-large` and related `e5-*` models require input prefixes:
- Queries must be prefixed with `query: ` (with trailing space)
- Passages must be prefixed with `passage: ` (with trailing space)

Without these prefixes the model produces significantly worse retrieval results. This behavior is automatic and model-specific — it activates only when the collection's `embedding_model` contains `e5`.

**Implementation**:

- [ ] Define constant `E5_PREFIX_QUERY = "query: "` and `E5_PREFIX_PASSAGE = "passage: "`
- [ ] Add helper `is_e5_model(model_name: str) -> bool` that checks if model name contains `e5` (case-insensitive)
- [ ] In `search()` method: if `is_e5_model(collection_model)`, prepend `query: ` prefix to query before `query_embed()`
- [ ] In `upsert()` method: if `is_e5_model(collection_model)`, prepend `passage: ` prefix to all contents before `passage_embed()`
- [ ] In `_get_file_points()` in `indexer.py`: ensure the prefix logic flows through correctly during batch indexing
- [ ] Add unit test: with `multilingual-e5-large` model → query gets `query: ` prefix applied
- [ ] Add unit test: with non-E5 model (e.g., `BAAI/bge-small-en-v1.5`) → no prefix applied
- [ ] Add integration test: index with E5 model, search → results have expected quality (can verify by searching known phrase)

**Important**: The prefix is added **before** embedding, not stored in payload. Search results still return the original text without prefix (only the vector uses the prefixed version).

---

## Phase 3: Corporate Knowledge Base Architecture

### 3.1 — Define collection naming conventions

**Files**: `README.md`, `docs/`

- [ ] Document collection naming convention:
  ```
  company-kb-docs       — corporate knowledge base (multilingual docs, policies, wiki)
  company-kb-snippets   — reusable templates, code snippets, examples
  team-<name>-docs      — team-specific documentation
  team-<name>-code      — team-specific shared code
  project-<name>-code    — project code
  project-<name>-docs    — project documentation
  ```
- [ ] Document recommended models per collection type
- [ ] Document `EMBEDDING_MODEL` usage: only as server-level default, not for shared KB

### 3.2 — Add `qdrant_search_many` tool

**Files**: `src/qmcp/server.py`, `src/qmcp/models.py`, `src/qmcp/client.py`

- [ ] Define `SearchManyRequest` model: `collections: list[str]`, `query: str`, `limit: int`, `score_threshold: float`
- [ ] Implement `qdrant_search_many()` tool that searches multiple collections and merges results
- [ ] Results should include `collection` field to identify source
- [ ] Sort combined results by score descending
- [ ] Add test in `tests/test_server.py`

### 3.3 — Add collection templates / presets documentation

**Files**: `docs/COLLECTION_SETUP.md` (new file)

- [ ] Create `docs/COLLECTION_SETUP.md` with step-by-step setup for:
  - Corporate KB collection (`company-kb-docs`) with `intfloat/multilingual-e5-large`
  - Code collection (`project-<name>-code`) with `jinaai/jina-embeddings-v2-base-code`
  - Lightweight docs collection with `BAAI/bge-small-en-v1.5`
- [ ] Include exact commands for `qdrant_index_directory` with correct `model=` values
- [ ] Include commands for setting up watcher with `qdrant_watch_ensure`
- [ ] Document that E5 prefix handling (`query:` / `passage:`) is **automatic** — no user action required

### 3.4 — Metadata enrichment for KB collections

**Files**: `src/qmcp/models.py`, `src/qmcp/indexer.py`, `docs/COLLECTION_SETUP.md`

- [ ] Add optional `metadata: dict | None` parameter to `qdrant_index_directory` for extra payload fields (e.g., `team`, `source_system`, `visibility`)
- [ ] Propagate these through to `Indexer._get_file_points()` and include in payload
- [ ] Document in `docs/COLLECTION_SETUP.md` how to use metadata for team/project tagging
- [ ] Add test: index with extra metadata → verify it appears in search results payload

---

## Phase 4: Testing

### 4.1 — Unit tests for model selection

**Files**: `tests/test_server.py`, `tests/test_client.py`

- [ ] Test: `qdrant_index_directory` with `model=` parameter → collection metadata has correct model
- [ ] Test: `qdrant_reindex` with `model=` parameter → collection metadata updated
- [ ] Test: `qdrant_list_supported_models()` returns filtered results
- [ ] Test: `qdrant_list_supported_models(filter="code")` returns only code-appropriate models
- [ ] Test: `qdrant_list_supported_models(filter="multilingual")` returns multilingual models

### 4.2 — Integration tests for model compatibility

**Files**: `tests/test_server.py`, `tests/test_indexer.py`, `tests/test_client.py`

- [ ] Test: index collection with model A, search → works correctly
- [ ] Test: index collection with model A, search with model B → returns clear error about mismatch
- [ ] Test: full reindex with new model → collection metadata updated, old vectors replaced
- [ ] Test: incremental reindex with new model → collection metadata updated, only changed files reindexed
- [ ] Test (E5 prefix): index with `multilingual-e5-large` → verify `passage: ` prefix was added to content during embedding
- [ ] Test (E5 prefix): search with `multilingual-e5-large` → verify `query: ` prefix was added to query during embedding
- [ ] Test (E5 prefix): index with non-E5 model → verify no prefix was added

### 4.3 — Unit tests for `qdrant_search_many`

**Files**: `tests/test_server.py`

- [ ] Test: search 2 collections → results from both, sorted by score
- [ ] Test: search with `score_threshold` → only results above threshold returned
- [ ] Test: search non-existent collection → returns error

### 4.4 — Model cache tests

**Files**: `tests/test_client.py`

- [ ] Test: load two different models → both cached, second load is fast (cache hit)
- [ ] Test: load model → use for search → use for index → no reload needed

### 4.5 — Run full test suite

**Files**: project root

- [ ] Run `make test` — all tests must pass
- [ ] Run `make lint` — no linting errors
- [ ] Run `make format` — code is formatted

---

## Phase 5: Documentation Updates

### 5.1 — Update README.md

**Files**: `README.md`

- [ ] Add section "Choosing an Embedding Model" with model comparison table (include Prefix column)
- [ ] Add section "Corporate Knowledge Base" with architecture diagram
- [ ] Add `qdrant_list_supported_models` to MCP Tools table
- [ ] Add `qdrant_search_many` to MCP Tools table
- [ ] Update Configuration table with model selection notes
- [ ] Add "Model Per Collection" section explaining metadata storage
- [ ] Add note that E5 prefix handling (`query:` / `passage:`) is **automatic** — no user action needed

### 5.2 — Update ARCHITECTURE.md

**Files**: `ARCHITECTURE.md`

- [ ] Add model selection architecture section
- [ ] Update data flow diagrams to show model passing
- [ ] Add corporate KB deployment diagram

### 5.3 — Update .env.example

**Files**: `.env.example`

- [ ] Add `EMBEDDING_MODEL` with comment about per-collection override
- [ ] Add `EMBEDDING_CACHE_DIR` comment about persisting models across restarts

---

## Phase 6: Final Verification

### 6.1 — Code review checklist

- [ ] All new functions/classes have docstrings in English
- [ ] All async tools have proper error handling
- [ ] No `TODO` or `FIXME` left in new code
- [ ] All new fields have pydantic `Field()` descriptions
- [ ] New tools follow existing tool patterns in `server.py`

### 6.2 — Functional verification

- [ ] Can create a collection with explicit model via `qdrant_index_directory(model="jinaai/jina-embeddings-v2-base-code")`
- [ ] Can verify model via `qdrant_get_collection_info` — `embedding_model` field present
- [ ] Can search in collection — results returned
- [ ] Model mismatch produces clear error (not silent failure)
- [ ] Can search across multiple collections with `qdrant_search_many`
- [ ] Can list supported models with filter
- [ ] File watcher works with new model-aware architecture

### 6.3 — Commit and PR

- [ ] All changes committed to `v0.3.0-pr` branch with conventional commit message
- [ ] PR created from `v0.3.0-pr` to `main`
- [ ] PR description includes summary of changes and testing performed

---

## Notes for Developers

1. **Always work in `v0.3.0-pr` branch** — do NOT commit directly to `main`
2. **Mark checkboxes as done immediately** after completing the item — do not leave work undocumented
3. **Test after each phase** (Phase 4 tests are split per phase intentionally) — do not skip testing
4. **Read related code before editing** — use `serena_get_symbols_overview` on the file you plan to modify
5. **If model mismatch error occurs** — this is expected behavior, not a bug. Document it clearly in user-facing messages.
6. **For `intfloat/multilingual-e5-large`** — E5 prefix handling is implemented in **Phase 2.5**. Queries and passages are automatically prefixed with `query: ` and `passage: ` respectively when the collection uses an E5 model. This is transparent to users — no action needed.
7. **Collection metadata** in Qdrant is stored via `collection_info` or custom payload. Verify which Qdrant API is available in the current `qdrant-client` version before implementing.

---

## File Changes Summary

| File | Changes |
|------|---------|
| `src/qmcp/config.py` | No changes (model comes from settings or per-call) |
| `src/qmcp/models.py` | Add `SupportedModel`, update `IndexRequest`, `ReindexRequest`, `SearchManyRequest`, add `CollectionMetadata` model |
| `src/qmcp/client.py` | Add model cache dict, `_load_embedding_model(model_name)`, metadata read/write, model validation, E5 prefix handling (`query:` / `passage:`) |
| `src/qmcp/indexer.py` | Accept `model` parameter, pass to client |
| `src/qmcp/server.py` | Add `qdrant_list_supported_models`, `qdrant_search_many`, update `qdrant_index_directory`, `qdrant_reindex`, add model to tools |
| `tests/test_server.py` | Add tests for new tools |
| `tests/test_client.py` | Add model cache and validation tests |
| `tests/test_indexer.py` | Add model parameter tests |
| `README.md` | Add model selection and KB sections |
| `ARCHITECTURE.md` | Update diagrams |
| `docs/COLLECTION_SETUP.md` | New file — collection setup guide |
| `.env.example` | Add model-related env vars |
