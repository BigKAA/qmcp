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

"""Tests for parsers."""

from pathlib import Path

from qmcp.parser import PythonParser, find_parser


class TestPythonParser:
    """Tests for Python parser."""

    def test_can_parse_python_file(self):
        """Test that parser recognizes Python files."""
        parser = PythonParser()
        assert parser.can_parse(Path("test.py"))
        assert parser.can_parse(Path("test.pyi"))
        assert not parser.can_parse(Path("test.js"))

    def test_parse_simple_function(self):
        """Test parsing a simple function."""
        parser = PythonParser()
        content = '''
def hello(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"
'''
        chunks = parser.parse_content(content, "test.py")

        assert len(chunks) >= 1
        func_chunk = next((c for c in chunks if c.chunk_type == "function"), None)
        assert func_chunk is not None
        assert func_chunk.name == "hello"
        assert "def hello" in func_chunk.content

    def test_parse_class(self):
        """Test parsing a class."""
        parser = PythonParser()
        content = '''
class User:
    """A user model."""

    def __init__(self, name: str):
        self.name = name
'''
        chunks = parser.parse_content(content, "test.py")

        class_chunk = next((c for c in chunks if c.chunk_type == "class"), None)
        assert class_chunk is not None
        assert class_chunk.name == "User"

    def test_parse_async_function(self):
        """Test parsing async function."""
        parser = PythonParser()
        content = '''
async def fetch_data(url: str) -> dict:
    """Fetch data from URL."""
    return {}
'''
        chunks = parser.parse_content(content, "test.py")

        func_chunk = next((c for c in chunks if c.chunk_type == "function"), None)
        assert func_chunk is not None
        assert func_chunk.name == "fetch_data"


class TestParserRegistry:
    """Tests for parser registry."""

    def test_find_parser_for_python(self):
        """Test finding Python parser."""
        parser = find_parser(Path("test.py"))
        assert parser is not None
        assert isinstance(parser, PythonParser)

    def test_find_parser_for_unknown(self):
        """Test unknown file type."""
        parser = find_parser(Path("test.unknown"))
        assert parser is None
