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

"""Tests for QdrantClientWrapper.search response shaping."""

from types import SimpleNamespace
from unittest.mock import Mock

from qmcp.client import QdrantClientWrapper


def _make_wrapper(points: list[dict]) -> QdrantClientWrapper:
    """Build a wrapper with mocked Qdrant client and embedding model.

    Args:
        points: Fake hit payloads (each gets score 0.9)

    Returns:
        Wrapper whose search() runs fully offline
    """
    wrapper = QdrantClientWrapper(url="http://localhost:6333")
    wrapper._client = Mock()
    wrapper._client.query_points.return_value = SimpleNamespace(
        points=[SimpleNamespace(score=0.9, payload=payload) for payload in points]
    )
    wrapper._embedding_model_instance = Mock()
    wrapper._embedding_model_instance.query_embed.return_value = [[0.1, 0.2, 0.3]]
    return wrapper


class TestSearchResponseShape:
    """Tests for the compact qdrant_search response."""

    def test_response_is_compact(self):
        """Response contains only pointer fields, no content/imports/symbol_names."""
        wrapper = _make_wrapper(
            [
                {
                    "file_path": "/docs/06-vm-operator.md",
                    "type": "section",
                    "name": "VMAuth",
                    "line_start": 900,
                    "line_end": 1010,
                    "language": "markdown",
                    "symbol_names": ["Title", "VMAuth"],
                    "imports": ["bash", "yaml"],
                    "content_hash": "abc",
                }
            ]
        )

        results = wrapper.search(collection="docs", query="vmauth")

        assert len(results) == 1
        assert results[0] == {
            "score": 0.9,
            "file_path": "/docs/06-vm-operator.md",
            "type": "section",
            "name": "VMAuth",
            "line_start": 900,
            "line_end": 1010,
            "language": "markdown",
        }
        # Bloat fields must not come back
        assert "content" not in results[0]
        assert "imports" not in results[0]
        assert "symbol_names" not in results[0]

    def test_markdown_hit_size_budget(self):
        """Acceptance: a markdown hit serializes to <= 300 characters."""
        wrapper = _make_wrapper(
            [
                {
                    "file_path": "/long/realistic/path/junior-03/06-vm-operator.md",
                    "type": "section",
                    "name": "VMAuth VMUser setup",
                    "line_start": 912,
                    "line_end": 1044,
                    "language": "markdown",
                }
            ]
        )

        results = wrapper.search(collection="docs", query="vmauth")

        import json

        assert len(json.dumps(results[0])) <= 300

    def test_signature_included_for_code_chunks(self):
        """Signature is kept when present (useful for code pointers)."""
        wrapper = _make_wrapper(
            [
                {
                    "file_path": "/src/app.py",
                    "type": "function_def",
                    "name": "get_user",
                    "line_start": 10,
                    "line_end": 20,
                    "language": "python",
                    "signature": "def get_user(user_id: int) -> User",
                }
            ]
        )

        results = wrapper.search(collection="code", query="get user")

        assert results[0]["signature"] == "def get_user(user_id: int) -> User"

    def test_file_path_pattern_glob_semantics(self):
        """file_path_pattern is a real glob matched against the full path."""
        wrapper = _make_wrapper(
            [
                {"file_path": "/src/app.py", "type": "function_def", "language": "python"},
                {"file_path": "/docs/guide.md", "type": "section", "language": "markdown"},
                {"file_path": "/src/util.py", "type": "function_def", "language": "python"},
            ]
        )

        # "*.py" works as a suffix filter (was broken with full-text matching)
        results = wrapper.search(collection="code", query="test", file_path_pattern="*.py")
        assert sorted(r["file_path"] for r in results) == ["/src/app.py", "/src/util.py"]

        # Directory prefix filtering
        results = wrapper.search(collection="code", query="test", file_path_pattern="/docs/*")
        assert [r["file_path"] for r in results] == ["/docs/guide.md"]

        # No match returns empty list
        results = wrapper.search(collection="code", query="test", file_path_pattern="*.java")
        assert results == []
