"""Qdrant client wrapper for qmcp."""

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
        except Exception as e:
            self.logger.error(f"Failed to connect to Qdrant: {e}")
            raise QdrantConnectionError(f"Failed to connect to Qdrant at {self.url}: {e}")

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
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "status": info.status.name,
        }

    def search(
        self,
        collection: str,
        query: str,
        limit: int = 5,
        score_threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Search for similar vectors.

        Args:
            collection: Collection name
            query: Query text
            limit: Max results
            score_threshold: Minimum score

        Returns:
            List of search results with payload
        """
        results = self.client.query_points(
            collection_name=collection,
            query=models.Document(text=query, model=self._embedding_model),
            limit=limit,
            score_threshold=score_threshold,
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
            }
            for hit in results.points
        ]

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

        structured_points = []
        for point in points:
            structured_points.append(
                PointStruct(
                    id=point["id"],
                    vector=models.Document(
                        text=point["content"],
                        model=self._embedding_model,
                    ),
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
