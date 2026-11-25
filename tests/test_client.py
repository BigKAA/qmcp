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

"""Tests for collection metadata handling in QdrantClientWrapper."""

from unittest.mock import Mock

from qdrant_client.http import models

from qmcp.client import QdrantClientWrapper


def _make_wrapper(
    vectors: models.VectorParams | dict[str, models.VectorParams] | None,
    sparse_vectors: dict[str, models.SparseVectorParams] | None = None,
) -> QdrantClientWrapper:
    """Build a wrapper returning real Qdrant models without a server.

    Args:
        vectors: Dense vector configuration returned by Qdrant
        sparse_vectors: Optional sparse vector configuration returned by Qdrant

    Returns:
        Wrapper with a mocked transport and a real CollectionInfo response
    """
    info = models.CollectionInfo.model_construct(
        status=models.CollectionStatus.GREEN,
        points_count=7,
        indexed_vectors_count=7,
        config=models.CollectionConfig.model_construct(
            params=models.CollectionParams(vectors=vectors, sparse_vectors=sparse_vectors)
        ),
    )
    wrapper = QdrantClientWrapper(url="http://localhost:6333")
    wrapper._client = Mock()
    wrapper._client.get_collection.return_value = info
    return wrapper


def _unnamed_vector(size: int = 384) -> models.VectorParams:
    """Create a real unnamed dense vector configuration."""
    return models.VectorParams(size=size, distance=models.Distance.COSINE)


def test_get_collection_info_reads_unnamed_vector_size():
    """Collection info reads size from VectorParams rather than CollectionParams."""
    wrapper = _make_wrapper(_unnamed_vector())

    assert wrapper.get_collection_info("docs") == {
        "name": "docs",
        "points_count": 7,
        "indexed_vectors_count": 7,
        "status": "GREEN",
        "vector_size": 384,
    }


def test_validate_collection_vectors_accepts_unnamed_vector():
    """Vector validation accepts a positive unnamed dense vector size."""
    wrapper = _make_wrapper(_unnamed_vector())

    assert wrapper.validate_collection_vectors("docs") == {
        "collection": "docs",
        "points_count": 7,
        "vector_size": 384,
        "is_valid": True,
        "warning": None,
    }


def test_collection_methods_preserve_named_vector_sizes():
    """Named vectors retain every name and size in both metadata responses."""
    wrapper = _make_wrapper(
        {
            "text": _unnamed_vector(384),
            "code": _unnamed_vector(768),
        }
    )

    assert wrapper.get_collection_info("code")["vector_size"] == {"text": 384, "code": 768}
    validation = wrapper.validate_collection_vectors("code")
    assert validation["vector_size"] == {"text": 384, "code": 768}
    assert validation["is_valid"] is True
    assert validation["warning"] is None


def test_collection_methods_accept_sparse_only_vectors():
    """Sparse-only collections are valid despite having no fixed dense size."""
    wrapper = _make_wrapper(None, sparse_vectors={"text": models.SparseVectorParams()})

    assert wrapper.get_collection_info("docs")["vector_size"] is None
    validation = wrapper.validate_collection_vectors("docs")
    assert validation["vector_size"] is None
    assert validation["is_valid"] is True
    assert validation["warning"] is None


def test_collection_methods_report_missing_vectors():
    """A collection without dense or sparse vectors fails validation cleanly."""
    wrapper = _make_wrapper(None)

    assert wrapper.get_collection_info("docs")["vector_size"] == 0
    validation = wrapper.validate_collection_vectors("docs")
    assert validation["vector_size"] == 0
    assert validation["is_valid"] is False
    assert validation["warning"] is not None


def test_validate_collection_vectors_rejects_zero_dimensions():
    """A dense vector configured with zero dimensions remains invalid."""
    wrapper = _make_wrapper(_unnamed_vector(0))

    validation = wrapper.validate_collection_vectors("docs")

    assert validation["vector_size"] == 0
    assert validation["is_valid"] is False
    assert "zero dimensions" in validation["warning"]


def test_validate_collection_vectors_rejects_any_invalid_named_vector():
    """Named dense vectors are valid only when every size is positive."""
    wrapper = _make_wrapper(
        {
            "text": _unnamed_vector(384),
            "broken": _unnamed_vector(0),
        }
    )

    validation = wrapper.validate_collection_vectors("code")

    assert validation["vector_size"] == {"text": 384, "broken": 0}
    assert validation["is_valid"] is False
    assert "zero dimensions" in validation["warning"]
