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

from typing import Any

from qdrant_client import QdrantClient, models

from .config import get_settings
from .logging_config import get_logger

# E5 model prefix constants - these models require special prefixes for optimal performance
E5_PREFIX_QUERY = "query: "
E5_PREFIX_PASSAGE = "passage: "


class QdrantConnectionError(Exception):
    """Raised when connection to Qdrant fails."""

    pass


class ModelMismatchError(Exception):
    """Raised when the embedding model used for search/upsert doesn't match the collection's model."""

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
        self._default_embedding_model = settings.embedding_model
        self._embedding_cache_dir = settings.embedding_cache_dir
        # Cache multiple embedding models by name: {model_name: model_instance}
        self._embedding_model_cache: dict[str, Any] = {}

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
            # Pre-load the default embedding model to validate it works
            self._load_embedding_model(self._default_embedding_model)
        except Exception as e:
            self.logger.error(f"Failed to connect to Qdrant: {e}")
            raise QdrantConnectionError(f"Failed to connect to Qdrant at {self.url}: {e}")

    def _load_embedding_model(self, model_name: str) -> Any:
        """Load and cache an embedding model by name.

        Downloads the model if not cached, then validates it works.
        This method ensures the model is available before any indexing or search operations.

        Args:
            model_name: Name of the embedding model to load

        Returns:
            The loaded embedding model instance
        """
        from fastembed import TextEmbedding

        # If model already loaded and cached, verify it's still valid
        if model_name in self._embedding_model_cache:
            try:
                # Quick verification that model still works
                list(self._embedding_model_cache[model_name].query_embed("test"))
                self.logger.debug(f"Embedding model '{model_name}' instance verified from cache")
                return self._embedding_model_cache[model_name]
            except Exception:
                # Model instance corrupted, reload
                self.logger.warning(f"Embedding model '{model_name}' corrupted, reloading...")
                del self._embedding_model_cache[model_name]

        self.logger.info(
            f"Loading embedding model: {model_name}"
            + (f" (cache: {self._embedding_cache_dir})" if self._embedding_cache_dir else "")
        )

        try:
            # Initialize model with custom cache directory if specified
            init_kwargs: dict[str, Any] = {"model_name": model_name}
            if self._embedding_cache_dir:
                init_kwargs["cache_dir"] = self._embedding_cache_dir
                self.logger.info(f"Using custom model cache directory: {self._embedding_cache_dir}")

            model_instance = TextEmbedding(**init_kwargs)

            # Validate model works with a test encode
            test_result = list(model_instance.query_embed("validation_test"))
            if not test_result or len(test_result[0]) == 0:
                raise QdrantConnectionError(
                    f"Embedding model '{model_name}' returned empty vectors. "
                    f"Model may be corrupted or incompatible."
                )

            # Cache the model
            self._embedding_model_cache[model_name] = model_instance

            self.logger.info(
                f"Embedding model '{model_name}' loaded successfully. Vector dimension: {len(test_result[0])}"
            )

            return model_instance

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
                    f"Failed to download embedding model '{model_name}'"
                    f"{cache_info}. Network error: {e}. "
                    f"Please check your internet connection and try again."
                )
            raise QdrantConnectionError(f"Failed to load embedding model '{model_name}': {e}")
        except Exception as e:
            cache_info = (
                f" from cache '{self._embedding_cache_dir}'" if self._embedding_cache_dir else ""
            )
            raise QdrantConnectionError(
                f"Failed to load embedding model '{model_name}'{cache_info}: {e}. "
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

    @staticmethod
    def is_e5_model(model_name: str) -> bool:
        """Check if model is an E5 model that requires query/passage prefixes.

        E5 models (like 'intfloat/multilingual-e5-large') require special prefixes:
        - Queries must be prefixed with 'query: ' (with trailing space)
        - Passages must be prefixed with 'passage: ' (with trailing space)

        Args:
            model_name: Name of the embedding model

        Returns:
            True if the model is an E5 model
        """
        return "e5" in model_name.lower()

    def _get_embedding_model_instance(self, model_name: str) -> Any:
        """Get embedding model instance from cache or load it.

        Args:
            model_name: Name of the embedding model

        Returns:
            The embedding model instance
        """
        if model_name in self._embedding_model_cache:
            return self._embedding_model_cache[model_name]
        return self._load_embedding_model(model_name)

    def get_collections(self) -> list[str]:
        """Get list of collection names."""
        result = self.client.get_collections()
        return [col.name for col in result.collections]

    def create_collection(
        self,
        name: str,
        embedding_model: str | None = None,
        vector_size: int | None = None,
        distance: models.Distance = models.Distance.COSINE,
    ) -> None:
        """Create a collection if it doesn't exist.

        Args:
            name: Collection name
            embedding_model: Model name to store in collection metadata (default: from settings)
            vector_size: Vector size (auto-detected from model if not provided)
            distance: Distance metric
        """
        # Use provided model or fall back to default
        model_name = embedding_model or self._default_embedding_model

        if vector_size is None:
            # Ensure model is loaded to get its vector size
            model_instance = self._get_embedding_model_instance(model_name)
            # Get vector size by generating a test embedding
            test_vec = list(model_instance.query_embed("size_test"))
            vector_size = len(test_vec[0]) if test_vec else 0

        self.client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=distance,
            ),
        )

        # Store embedding model in collection metadata
        self.client.set_collection_metadata(
            collection_name=name,
            metadata={"embedding_model": model_name},
        )

    def delete_collection(self, name: str) -> None:
        """Delete a collection."""
        self.client.delete_collection(collection_name=name)

    def collection_exists(self, name: str) -> bool:
        """Check if collection exists."""
        return name in self.get_collections()

    def get_collection_info(self, name: str) -> dict[str, Any]:
        """Get collection information including stored metadata.

        Args:
            name: Collection name

        Returns:
            Dictionary with collection info including embedding_model
        """
        info = self.client.get_collection(collection_name=name)

        # Try to get embedding_model from collection metadata
        embedding_model = None
        try:
            metadata = self.client.get_collection_metadata(collection_name=name)
            if metadata:
                embedding_model = metadata.get("embedding_model")
        except Exception:
            # Metadata might not exist for older collections
            pass

        return {
            "name": name,
            "points_count": info.points_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "status": info.status.name,
            "vector_size": info.config.params.size if info.config and info.config.params else 0,
            "embedding_model": embedding_model,
        }

    def get_embedding_model_for_collection(self, collection_name: str) -> str:
        """Get the embedding model used by a collection.

        Reads the model name from collection metadata. Falls back to default
        model if no metadata is found (for backward compatibility).

        Args:
            collection_name: Name of the collection

        Returns:
            The embedding model name

        Raises:
            CollectionNotFoundError: If collection doesn't exist
        """
        if not self.collection_exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")

        info = self.get_collection_info(collection_name)
        return info.get("embedding_model") or self._default_embedding_model

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
            file_path_pattern: Filter by file path glob pattern (e.g., "*.py")

        Returns:
            List of search results with payload
        """
        # Get the embedding model for this collection
        collection_model = self.get_embedding_model_for_collection(collection)
        model_instance = self._get_embedding_model_instance(collection_model)

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

        if file_path_pattern:
            # Convert glob pattern to Qdrant match
            filter_conditions.append(
                models.FieldCondition(
                    key="file_path",
                    match=models.MatchText(text=file_path_pattern),
                )
            )

        # Build query filter
        query_filter = None
        if filter_conditions:
            query_filter = models.Filter(must=filter_conditions)

        # Apply E5 prefix if this is an E5 model
        query_text = query
        if self.is_e5_model(collection_model):
            query_text = f"{E5_PREFIX_QUERY}{query}"
            self.logger.debug(f"E5 model detected, applying query prefix: '{E5_PREFIX_QUERY}'")

        # Generate query embedding using the collection's model
        query_vectors = list(model_instance.query_embed(query_text))
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

        return [
            {
                "score": hit.score,
                "file_path": hit.payload.get("file_path", ""),
                "content": hit.payload.get("content", ""),
                "type": hit.payload.get("type", "unknown"),
                "line_start": hit.payload.get("line_start"),
                "line_end": hit.payload.get("line_end"),
                # Extended metadata
                "signature": hit.payload.get("signature"),
                "symbol_names": hit.payload.get("symbol_names", []),
                "imports": hit.payload.get("imports", []),
                "language": hit.payload.get("language", "unknown"),
            }
            for hit in results.points
        ]

    def upsert(
        self,
        collection: str,
        points: list[dict[str, Any]],
        embedding_model: str | None = None,
        batch_size: int = 50,
    ) -> int:
        """Upsert points into collection.

        Args:
            collection: Collection name
            points: List of points to insert
            embedding_model: Embedding model to use (auto-detected from collection if not provided)
            batch_size: Batch size for insertion

        Returns:
            Number of points inserted
        """
        from qdrant_client.models import PointStruct

        # Determine which model to use
        if embedding_model is None:
            embedding_model = self.get_embedding_model_for_collection(collection)

        model_instance = self._get_embedding_model_instance(embedding_model)

        # Generate embeddings for all points
        contents = [point["content"] for point in points]

        # Apply E5 prefix if this is an E5 model
        if self.is_e5_model(embedding_model):
            self.logger.debug(f"E5 model detected, applying passage prefix: '{E5_PREFIX_PASSAGE}'")
            contents = [f"{E5_PREFIX_PASSAGE}{content}" for content in contents]

        all_embeddings = list(model_instance.passage_embed(contents))

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

    def search_many(
        self,
        collections: list[str],
        query: str,
        limit: int = 10,
        score_threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Search across multiple collections and merge results.

        Args:
            collections: List of collection names to search
            query: Search query text
            limit: Max results per collection (total results may exceed this)
            score_threshold: Minimum score threshold

        Returns:
            Combined list of search results from all collections, sorted by score descending
        """
        all_results = []

        for collection in collections:
            try:
                results = self.search(
                    collection=collection,
                    query=query,
                    limit=limit,
                    score_threshold=score_threshold,
                )
                # Add collection name to each result
                for result in results:
                    result["collection"] = collection
                all_results.extend(results)
            except Exception as e:
                self.logger.warning(f"Error searching collection '{collection}': {e}")

        # Sort by score descending
        all_results.sort(key=lambda x: x["score"], reverse=True)

        return all_results
