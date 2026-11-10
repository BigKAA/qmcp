# Copyright 2024 Artur
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Qdrant client wrapper for qmcp."""

import os
from fnmatch import fnmatch
from typing import Any

from qdrant_client import QdrantClient, models

from .config import get_settings
from .logging_config import get_logger


class QdrantConnectionError(Exception):
    """Raised when connection to Qdrant fails."""

    pass


class QdrantClientWrapper:
    """Async wrapper for Qdrant client with convenience methods."""

    def __init__(self, url: str | None = None, api_key: str | None = None):
        """Initialize Qdrant client.

        Args:
            url: Qdrant URL (default from settings)
            api_key: Qdrant API key (optional, from settings)
        """
        settings = get_settings()
        self.logger = get_logger(f"{__name__}.QdrantClientWrapper")

        self.url = url or settings.qdrant_url
        self.api_key = api_key or settings.qdrant_api_key
        self._client: QdrantClient | None = None
        self._embedding_model = settings.embedding_model
        self._embedding_cache_dir = settings.embedding_cache_dir
        # Cap ONNX threads so that several qmcp processes (one per MCP
        # client) together cannot saturate every CPU core.
        self._embedding_threads = settings.embedding_threads
        self._embedding_model_instance: Any = None

    def connect(self) -> None:
        """Establish connection to Qdrant."""
        self.logger.info(f"Connecting to Qdrant at {self.url}")
        try:
            self._client = QdrantClient(
                url=self.url,
                api_key=self.api_key,
                timeout=30,
            )
            # Test connection
            self._client.get_collections()
            self.logger.info("Successfully connected to Qdrant")
            # Validate embedding model is available
            self._load_embedding_model()
        except Exception as e:
            self.logger.error(f"Failed to connect to Qdrant: {e}")
            raise QdrantConnectionError(f"Failed to connect to Qdrant at {self.url}: {e}")

    def _load_embedding_model(self) -> None:
        """Load and cache the embedding model.

        Downloads the model if not cached, then validates it works.
        This method ensures the model is available before any indexing operations.
        """
        from fastembed import TextEmbedding

        # If model already loaded and cached, verify it's still valid
        if self._embedding_model_instance is not None:
            try:
                # Quick verification that model still works
                list(self._embedding_model_instance.query_embed("test"))
                self.logger.debug("Embedding model instance verified")
                return
            except Exception:
                # Model instance corrupted, reload
                self.logger.warning("Embedding model instance corrupted, reloading...")
                self._embedding_model_instance = None

        self.logger.info(
            f"Loading embedding model: {self._embedding_model}"
            + (f" (cache: {self._embedding_cache_dir})" if self._embedding_cache_dir else "")
        )

        try:
            # Initialize model with custom cache directory if specified
            init_kwargs: dict[str, Any] = {"model_name": self._embedding_model}
            if self._embedding_cache_dir:
                init_kwargs["cache_dir"] = self._embedding_cache_dir
                self.logger.info(f"Using custom model cache directory: {self._embedding_cache_dir}")

            # Thread count: explicit setting wins, otherwise cap at 4 cores -
            # inference is bursty and N processes x all cores melts laptops.
            threads = self._embedding_threads
            if threads is None:
                threads = min(4, os.cpu_count() or 1)
            init_kwargs["threads"] = threads
            self.logger.info(f"Embedding inference threads: {threads}")

            self._embedding_model_instance = TextEmbedding(**init_kwargs)

            # Validate model works with a test encode
            test_result = list(self._embedding_model_instance.query_embed("validation_test"))
            if not test_result or len(test_result[0]) == 0:
                raise QdrantConnectionError(
                    f"Embedding model '{self._embedding_model}' returned empty vectors. "
                    f"Model may be corrupted or incompatible."
                )

            self.logger.info(
                f"Embedding model loaded successfully. Vector dimension: {len(test_result[0])}"
            )

        except ImportError:
            raise QdrantConnectionError(
                "fastembed is not installed. Install it with: pip install qdrant-client[fastembed]"
            )
        except OSError as e:
            # Network errors when trying to download model
            if "Could not download" in str(e) or "connection" in str(e).lower():
                cache_info = (
                    f" at '{self._embedding_cache_dir}'"
                    if self._embedding_cache_dir
                    else " (default location)"
                )
                raise QdrantConnectionError(
                    f"Failed to download embedding model '{self._embedding_model}'"
                    f"{cache_info}. Network error: {e}. "
                    f"Please check your internet connection and try again."
                )
            raise QdrantConnectionError(
                f"Failed to load embedding model '{self._embedding_model}': {e}"
            )
        except Exception as e:
            cache_info = (
                f" from cache '{self._embedding_cache_dir}'" if self._embedding_cache_dir else ""
            )
            raise QdrantConnectionError(
                f"Failed to load embedding model '{self._embedding_model}'{cache_info}: {e}. "
                f"The model may need to be re-downloaded."
            )

    @property
    def client(self) -> QdrantClient:
        """Get Qdrant client instance."""
        if self._client is None:
            self.connect()
        return self._client  # type: ignore

    @property
    def is_connected(self) -> bool:
        """Check if connected to Qdrant."""
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    def get_collections(self) -> list[str]:
        """Get list of collection names."""
        result = self.client.get_collections()
        return [col.name for col in result.collections]

    def create_collection(
        self,
        name: str,
        vector_size: int | None = None,
        distance: models.Distance = models.Distance.COSINE,
    ) -> None:
        """Create a collection if it doesn't exist.

        Args:
            name: Collection name
            vector_size: Vector size (auto-detected from model if not provided)
            distance: Distance metric
        """
        if vector_size is None:
            vector_size = self.client.get_embedding_size(self._embedding_model)

        self.client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=distance,
            ),
        )

    def delete_collection(self, name: str) -> None:
        """Delete a collection."""
        self.client.delete_collection(collection_name=name)

    def collection_exists(self, name: str) -> bool:
        """Check if collection exists."""
        return name in self.get_collections()

    def get_collection_info(self, name: str) -> dict[str, Any]:
        """Get collection information."""
        info = self.client.get_collection(collection_name=name)
        return {
            "name": name,
            "points_count": info.points_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "status": info.status.name,
            "vector_size": info.config.params.size if info.config and info.config.params else 0,
        }

    def validate_collection_vectors(self, name: str) -> dict[str, Any]:
        """Validate that collection vectors have proper dimensions.

        Returns diagnostic info about the collection vector health.
        """
        info = self.client.get_collection(collection_name=name)
        vector_size = info.config.params.size if info.config and info.config.params else 0

        return {
            "collection": name,
            "points_count": info.points_count,
            "vector_size": vector_size,
            "is_valid": vector_size > 0,
            "warning": (
                f"Vectors have zero dimensions! "
                f"This usually means fastembed failed during indexing. "
                f"Run: qdrant_reindex(collection='{name}', path='/path/to/project', mode='full')"
            )
            if vector_size == 0
            else None,
        }

    def search(
        self,
        collection: str,
        query: str,
        limit: int = 5,
        score_threshold: float = 0.7,
        chunk_type: str | None = None,
        symbol_name: str | None = None,
        language: str | None = None,
        file_path_pattern: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar vectors with optional structured filters.

        Args:
            collection: Collection name
            query: Query text
            limit: Max results
            score_threshold: Minimum score
            chunk_type: Filter by chunk type (e.g., "function_def", "class_def")
            symbol_name: Filter by exact symbol name match
            language: Filter by programming language (e.g., "python", "go")
            file_path_pattern: Filter results by file path glob pattern (e.g., "*.py",
                "docs/**"). Matched client-side with fnmatch against the full path,
                so "*" and "?" wildcards work as expected.

        Returns:
            List of compact search results (score, file_path, type, name,
            line_start, line_end, language and optional signature) - enough
            for an LLM to perform a targeted file read
        """
        # Build filter conditions
        filter_conditions = []

        if chunk_type:
            filter_conditions.append(
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value=chunk_type),
                )
            )

        if symbol_name:
            filter_conditions.append(
                models.FieldCondition(
                    key="symbol_names",
                    match=models.MatchAny(any=[symbol_name]),
                )
            )

        if language:
            filter_conditions.append(
                models.FieldCondition(
                    key="language",
                    match=models.MatchValue(value=language),
                )
            )

        # Build query filter
        query_filter = None
        if filter_conditions:
            query_filter = models.Filter(must=filter_conditions)

        # Generate query embedding using cached model
        if self._embedding_model_instance is None:
            self._load_embedding_model()

        query_vectors = list(self._embedding_model_instance.query_embed(query))
        if not query_vectors or len(query_vectors[0]) == 0:
            self.logger.error("Query embedding returned empty vector")
            return []

        results = self.client.query_points(
            collection_name=collection,
            query=query_vectors[0],  # Use pre-generated vector
            limit=limit,
            score_threshold=score_threshold,
            query_filter=query_filter,
            with_payload=True,
        )

        # Compact response: only pointer fields an LLM needs for a targeted
        # read. "content" was never stored in payloads (always empty), and
        # "imports"/"symbol_names" bloated every answer with junk data.
        results_list = []
        for hit in results.points:
            payload = hit.payload or {}
            item: dict[str, Any] = {
                "score": hit.score,
                "file_path": payload.get("file_path", ""),
                "type": payload.get("type", "unknown"),
                "name": payload.get("name", ""),
                "line_start": payload.get("line_start"),
                "line_end": payload.get("line_end"),
                "language": payload.get("language", "unknown"),
            }
            if payload.get("signature"):
                # Signature is only present for code chunks and is short
                item["signature"] = payload["signature"]
            results_list.append(item)

        # Glob pattern is matched client-side: Qdrant has no regex matching
        # on keyword fields, and MatchText is token-based full-text search
        if file_path_pattern:
            results_list = [
                item for item in results_list if fnmatch(item["file_path"], file_path_pattern)
            ]

        return results_list

    def upsert(
        self,
        collection: str,
        points: list[dict[str, Any]],
        batch_size: int = 50,
    ) -> int:
        """Upsert points into collection.

        Args:
            collection: Collection name
            points: List of points to insert
            batch_size: Batch size for insertion

        Returns:
            Number of points inserted
        """
        from qdrant_client.models import PointStruct

        # Ensure embedding model is loaded
        if self._embedding_model_instance is None:
            self._load_embedding_model()

        # Generate embeddings for all points
        contents = [point["content"] for point in points]
        all_embeddings = list(self._embedding_model_instance.passage_embed(contents))

        structured_points = []
        for i, point in enumerate(points):
            embedding = all_embeddings[i]
            if len(embedding) == 0:
                self.logger.warning(f"Empty embedding for point {point['id']}, skipping")
                continue

            structured_points.append(
                PointStruct(
                    id=point["id"],
                    vector=embedding,
                    payload=point["payload"],
                )
            )

        # Insert in batches
        total = 0
        for i in range(0, len(structured_points), batch_size):
            batch = structured_points[i : i + batch_size]
            self.client.upsert(collection_name=collection, points=batch)
            total += len(batch)

        return total

    def delete_points(self, collection: str, point_ids: list[str]) -> None:
        """Delete points by IDs."""
        self.client.delete(
            collection_name=collection,
            points_selector=models.PointIdsList(points=point_ids),
        )

    def delete_points_by_path(self, collection: str, file_path: str) -> None:
        """Delete every point of a file, selected by payload filter.

        Idempotent and cheap - no embedding involved - so several watching
        processes may react to the same deletion without harm.

        Args:
            collection: Collection to delete from.
            file_path: Absolute file path stored in point payloads.
        """
        self.client.delete(
            collection_name=collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="file_path",
                            match=models.MatchValue(value=file_path),
                        )
                    ]
                )
            ),
        )

    def scroll(
        self,
        collection: str,
        limit: int = 100,
        offset: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Scroll through collection points.

        Returns:
            Tuple of (points, next_offset)
        """
        results, next_offset = self.client.scroll(
            collection_name=collection,
            limit=limit,
            offset=offset,
            with_payload=True,
        )

        points = [
            {
                "id": str(hit.id),
                "payload": hit.payload,
            }
            for hit in results
        ]

        return points, next_offset

    def get_all_points(self, collection: str) -> list[dict[str, Any]]:
        """Get all points from collection."""
        all_points = []
        offset = None

        while True:
            points, offset = self.scroll(collection, limit=1000, offset=offset)
            all_points.extend(points)
            if offset is None:
                break

        return all_points

    def get_file_points(self, collection: str, file_path: str) -> list[dict[str, Any]]:
        """Get all points of a single file, filtered server-side.

        Uses a payload filter on ``file_path`` so only the file's own points
        travel over the network - unlike ``get_all_points``, which downloads
        the whole collection for every per-file hash check.

        Args:
            collection: Collection to query.
            file_path: Absolute file path stored in point payloads.

        Returns:
            List of ``{"id": ..., "payload": ...}`` dicts for the file.
        """
        result: list[dict[str, Any]] = []
        offset = None
        scroll_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="file_path",
                    match=models.MatchValue(value=file_path),
                )
            ]
        )

        while True:
            hits, offset = self.client.scroll(
                collection_name=collection,
                limit=1000,
                offset=offset,
                scroll_filter=scroll_filter,
                with_payload=True,
            )
            result.extend({"id": str(hit.id), "payload": hit.payload} for hit in hits)
            if offset is None:
                break

        return result
