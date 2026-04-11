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

"""Tests for Qdrant client wrapper."""

from unittest.mock import Mock, patch, MagicMock

import pytest

from qmcp.client import (
    QdrantClientWrapper,
    QdrantConnectionError,
    ModelMismatchError,
    E5_PREFIX_QUERY,
    E5_PREFIX_PASSAGE,
)


class TestE5ModelPrefixes:
    """Tests for E5 model prefix handling."""

    def test_e5_prefix_constants_defined(self):
        """Verify E5 prefix constants are defined correctly."""
        assert E5_PREFIX_QUERY == "query: "
        assert E5_PREFIX_PASSAGE == "passage: "

    def test_is_e5_model_with_e5_large(self):
        """Test E5 model detection for multilingual-e5-large."""
        wrapper = QdrantClientWrapper.__new__(QdrantClientWrapper)
        assert wrapper.is_e5_model("intfloat/multilingual-e5-large") is True

    def test_is_e5_model_with_lowercase_e5(self):
        """Test E5 model detection is case-insensitive."""
        wrapper = QdrantClientWrapper.__new__(QdrantClientWrapper)
        assert wrapper.is_e5_model("intfloat/E5-LARGE") is True
        assert wrapper.is_e5_model("some/e5-small") is True

    def test_is_e5_model_returns_false_for_non_e5(self):
        """Test E5 model detection returns False for non-E5 models."""
        wrapper = QdrantClientWrapper.__new__(QdrantClientWrapper)
        assert wrapper.is_e5_model("BAAI/bge-small-en-v1.5") is False
        assert wrapper.is_e5_model("jinaai/jina-embeddings-v2-base-code") is False

    def test_is_e5_model_returns_false_for_bge(self):
        """Test E5 model detection returns False for BGE models."""
        wrapper = QdrantClientWrapper.__new__(QdrantClientWrapper)
        assert wrapper.is_e5_model("BAAI/bge-large-en-v1.5") is False


class TestEmbeddingModelCaching:
    """Tests for embedding model caching."""

    def test_default_embedding_model_set(self):
        """Test that default embedding model is set from settings."""
        with patch("qmcp.client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                embedding_model="BAAI/bge-small-en-v1.5",
                embedding_cache_dir=None,
            )
            wrapper = QdrantClientWrapper()
            assert wrapper._default_embedding_model == "BAAI/bge-small-en-v1.5"

    def test_embedding_model_cache_initialized_empty(self):
        """Test that embedding model cache is initialized as empty dict."""
        with patch("qmcp.client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                embedding_model="BAAI/bge-small-en-v1.5",
                embedding_cache_dir=None,
            )
            wrapper = QdrantClientWrapper()
            assert wrapper._embedding_model_cache == {}

    def test_get_embedding_model_instance_from_cache(self):
        """Test getting embedding model instance from cache."""
        with patch("qmcp.client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                embedding_model="BAAI/bge-small-en-v1.5",
                embedding_cache_dir=None,
            )
            wrapper = QdrantClientWrapper()

            mock_model = Mock()
            wrapper._embedding_model_cache["BAAI/bge-small-en-v1.5"] = mock_model

            result = wrapper._get_embedding_model_instance("BAAI/bge-small-en-v1.5")
            assert result is mock_model


class TestCreateCollection:
    """Tests for create_collection method."""

    @patch("qmcp.client.QdrantClient")
    def test_create_collection_stores_embedding_model_in_metadata(self, mock_qdrant_client):
        """Test that create_collection stores embedding model in metadata."""
        with patch("qmcp.client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                embedding_model="BAAI/bge-small-en-v1.5",
                embedding_cache_dir=None,
            )

            mock_client_instance = Mock()
            mock_qdrant_client.return_value = mock_client_instance
            mock_client_instance.get_collections.return_value = Mock(collections=[])

            # Mock get_embedding_size
            mock_client_instance.get_embedding_size.return_value = 384

            wrapper = QdrantClientWrapper()
            wrapper.connect()

            wrapper.create_collection(
                "test-collection", embedding_model="jinaai/jina-embeddings-v2-base-code"
            )

            # Verify set_collection_metadata was called with the model
            mock_client_instance.set_collection_metadata.assert_called_once_with(
                collection_name="test-collection",
                metadata={"embedding_model": "jinaai/jina-embeddings-v2-base-code"},
            )


class TestGetCollectionInfo:
    """Tests for get_collection_info method."""

    @patch("qmcp.client.QdrantClient")
    def test_get_collection_info_returns_embedding_model(self, mock_qdrant_client):
        """Test that get_collection_info returns embedding model from metadata."""
        with patch("qmcp.client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                embedding_model="BAAI/bge-small-en-v1.5",
                embedding_cache_dir=None,
            )

            mock_client_instance = Mock()
            mock_qdrant_client.return_value = mock_client_instance
            mock_client_instance.get_collections.return_value = Mock(collections=[])

            # Mock get_collection response
            mock_info = Mock()
            mock_info.points_count = 100
            mock_info.indexed_vectors_count = 100
            mock_info.status.name = "green"
            mock_info.config.params.size = 384
            mock_client_instance.get_collection.return_value = mock_info

            # Mock get_collection_metadata response
            mock_client_instance.get_collection_metadata.return_value = {
                "embedding_model": "jinaai/jina-embeddings-v2-base-code"
            }

            wrapper = QdrantClientWrapper()
            wrapper.connect()

            result = wrapper.get_collection_info("test-collection")

            assert result["embedding_model"] == "jinaai/jina-embeddings-v2-base-code"
            assert result["name"] == "test-collection"
            assert result["points_count"] == 100

    @patch("qmcp.client.QdrantClient")
    def test_get_collection_info_returns_none_for_old_collections(self, mock_qdrant_client):
        """Test that get_collection_info returns None for old collections without metadata."""
        with patch("qmcp.client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                embedding_model="BAAI/bge-small-en-v1.5",
                embedding_cache_dir=None,
            )

            mock_client_instance = Mock()
            mock_qdrant_client.return_value = mock_client_instance
            mock_client_instance.get_collections.return_value = Mock(collections=[])

            mock_info = Mock()
            mock_info.points_count = 100
            mock_info.indexed_vectors_count = 100
            mock_info.status.name = "green"
            mock_info.config.params.size = 384
            mock_client_instance.get_collection.return_value = mock_info

            # Mock get_collection_metadata raising exception (no metadata)
            mock_client_instance.get_collection_metadata.side_effect = Exception("No metadata")

            wrapper = QdrantClientWrapper()
            wrapper.connect()

            result = wrapper.get_collection_info("old-collection")

            assert result["embedding_model"] is None


class TestGetEmbeddingModelForCollection:
    """Tests for get_embedding_model_for_collection method."""

    @patch("qmcp.client.QdrantClient")
    def test_get_embedding_model_for_collection_from_metadata(self, mock_qdrant_client):
        """Test getting embedding model from collection metadata."""
        with patch("qmcp.client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                embedding_model="BAAI/bge-small-en-v1.5",
                embedding_cache_dir=None,
            )

            mock_client_instance = Mock()
            mock_qdrant_client.return_value = mock_client_instance
            mock_client_instance.get_collections.return_value = Mock(
                collections=[Mock(name="test-col")]
            )

            mock_info = Mock()
            mock_info.points_count = 100
            mock_info.indexed_vectors_count = 100
            mock_info.status.name = "green"
            mock_info.config.params.size = 384
            mock_client_instance.get_collection.return_value = mock_info
            mock_client_instance.get_collection_metadata.return_value = {
                "embedding_model": "intfloat/multilingual-e5-large"
            }

            wrapper = QdrantClientWrapper()
            wrapper.connect()

            # Patch collection_exists to avoid get_collections complexity
            with patch.object(wrapper, "collection_exists", return_value=True):
                result = wrapper.get_embedding_model_for_collection("test-col")

            assert result == "intfloat/multilingual-e5-large"

    @patch("qmcp.client.QdrantClient")
    def test_get_embedding_model_for_collection_falls_back_to_default(self, mock_qdrant_client):
        """Test fallback to default model when collection has no metadata."""
        with patch("qmcp.client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                embedding_model="BAAI/bge-small-en-v1.5",
                embedding_cache_dir=None,
            )

            mock_client_instance = Mock()
            mock_qdrant_client.return_value = mock_client_instance
            mock_client_instance.get_collections.return_value = Mock(
                collections=[Mock(name="old-col")]
            )

            mock_info = Mock()
            mock_info.points_count = 100
            mock_info.indexed_vectors_count = 100
            mock_info.status.name = "green"
            mock_info.config.params.size = 384
            mock_client_instance.get_collection.return_value = mock_info
            mock_client_instance.get_collection_metadata.side_effect = Exception("No metadata")

            wrapper = QdrantClientWrapper()
            wrapper.connect()

            # Patch collection_exists to avoid get_collections complexity
            with patch.object(wrapper, "collection_exists", return_value=True):
                result = wrapper.get_embedding_model_for_collection("old-col")

            assert result == "BAAI/bge-small-en-v1.5"

    @patch("qmcp.client.QdrantClient")
    def test_get_embedding_model_for_collection_raises_for_nonexistent(self, mock_qdrant_client):
        """Test that ValueError is raised for nonexistent collection."""
        with patch("qmcp.client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                embedding_model="BAAI/bge-small-en-v1.5",
                embedding_cache_dir=None,
            )

            mock_client_instance = Mock()
            mock_qdrant_client.return_value = mock_client_instance
            mock_client_instance.get_collections.return_value = Mock(collections=[])

            wrapper = QdrantClientWrapper()
            wrapper.connect()

            with pytest.raises(ValueError, match="does not exist"):
                wrapper.get_embedding_model_for_collection("nonexistent")


class TestSearchMany:
    """Tests for search_many method."""

    @patch("qmcp.client.QdrantClient")
    def test_search_many_merges_results_from_multiple_collections(self, mock_qdrant_client):
        """Test that search_many merges and sorts results from multiple collections."""
        with patch("qmcp.client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                embedding_model="BAAI/bge-small-en-v1.5",
                embedding_cache_dir=None,
            )

            mock_client_instance = Mock()
            mock_qdrant_client.return_value = mock_client_instance
            mock_client_instance.get_collections.return_value = Mock(collections=[])

            # Mock get_collection response
            mock_info = Mock()
            mock_info.points_count = 10
            mock_info.indexed_vectors_count = 10
            mock_info.status.name = "green"
            mock_info.config.params.size = 384
            mock_client_instance.get_collection.return_value = mock_info
            mock_client_instance.get_collection_metadata.return_value = {
                "embedding_model": "BAAI/bge-small-en-v1.5"
            }

            # Mock query_points for two collections
            mock_client_instance.query_points.side_effect = [
                Mock(
                    points=[
                        Mock(
                            score=0.9,
                            payload={
                                "file_path": "file1.py",
                                "content": "content1",
                                "type": "function_def",
                                "line_start": 1,
                                "line_end": 10,
                                "signature": None,
                                "symbol_names": [],
                                "imports": [],
                                "language": "python",
                            },
                        ),
                    ]
                ),
                Mock(
                    points=[
                        Mock(
                            score=0.7,
                            payload={
                                "file_path": "file2.py",
                                "content": "content2",
                                "type": "class_def",
                                "line_start": 20,
                                "line_end": 30,
                                "signature": None,
                                "symbol_names": [],
                                "imports": [],
                                "language": "python",
                            },
                        ),
                    ]
                ),
            ]

            wrapper = QdrantClientWrapper()
            wrapper.connect()

            # Mock the search method behavior
            def mock_search(collection, query, limit, score_threshold, **kwargs):
                if collection == "col1":
                    return [
                        {
                            "score": 0.9,
                            "file_path": "file1.py",
                            "content": "content1",
                            "type": "function_def",
                            "collection": "col1",
                        }
                    ]
                else:
                    return [
                        {
                            "score": 0.7,
                            "file_path": "file2.py",
                            "content": "content2",
                            "type": "class_def",
                            "collection": "col2",
                        }
                    ]

            wrapper.search = mock_search

            results = wrapper.search_many(
                ["col1", "col2"], "test query", limit=10, score_threshold=0.5
            )

            assert len(results) == 2
            # Results should be sorted by score descending
            assert results[0]["score"] == 0.9
            assert results[0]["collection"] == "col1"
            assert results[1]["score"] == 0.7
            assert results[1]["collection"] == "col2"

    @patch("qmcp.client.QdrantClient")
    def test_search_many_handles_empty_results(self, mock_qdrant_client):
        """Test that search_many handles empty results gracefully."""
        with patch("qmcp.client.get_settings") as mock_settings:
            mock_settings.return_value = Mock(
                qdrant_url="http://localhost:6333",
                qdrant_api_key=None,
                embedding_model="BAAI/bge-small-en-v1.5",
                embedding_cache_dir=None,
            )

            mock_client_instance = Mock()
            mock_qdrant_client.return_value = mock_client_instance
            mock_client_instance.get_collections.return_value = Mock(collections=[])

            mock_info = Mock()
            mock_info.points_count = 0
            mock_info.indexed_vectors_count = 0
            mock_info.status.name = "green"
            mock_info.config.params.size = 384
            mock_client_instance.get_collection.return_value = mock_info
            mock_client_instance.get_collection_metadata.return_value = {
                "embedding_model": "BAAI/bge-small-en-v1.5"
            }

            wrapper = QdrantClientWrapper()
            wrapper.connect()

            def mock_search(collection, query, limit, score_threshold, **kwargs):
                return []

            wrapper.search = mock_search

            results = wrapper.search_many(
                ["col1", "col2"], "test query", limit=10, score_threshold=0.5
            )

            assert len(results) == 0
