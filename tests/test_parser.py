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

from qmcp.parser import MarkdownParser, PythonParser, find_parser


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
        func_chunk = next((c for c in chunks if c.chunk_type == "function_def"), None)
        assert func_chunk is not None
        assert func_chunk.name == "hello"
        assert "def hello" in func_chunk.content
        # Check new metadata fields
        assert func_chunk.signature == "def hello(name: str) -> str"
        assert "hello" in func_chunk.symbol_names
        assert "name" in func_chunk.symbol_names
        assert func_chunk.language == "python"

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

        class_chunk = next((c for c in chunks if c.chunk_type == "class_def"), None)
        assert class_chunk is not None
        assert class_chunk.name == "User"
        # Check new metadata fields
        assert class_chunk.signature == "class User"
        assert "User" in class_chunk.symbol_names
        assert class_chunk.language == "python"

    def test_parse_async_function(self):
        """Test parsing async function."""
        parser = PythonParser()
        content = '''
async def fetch_data(url: str) -> dict:
    """Fetch data from URL."""
    return {}
'''
        chunks = parser.parse_content(content, "test.py")

        func_chunk = next((c for c in chunks if c.chunk_type == "async_function_def"), None)
        assert func_chunk is not None
        assert func_chunk.name == "fetch_data"
        assert func_chunk.signature == "async def fetch_data(url: str) -> dict"

    def test_parse_function_with_imports(self):
        """Test that imports are extracted."""
        parser = PythonParser()
        content = '''
from typing import List, Dict
import json

def process(data: List[str]) -> Dict[str, int]:
    """Process data."""
    return {}
'''
        chunks = parser.parse_content(content, "test.py")

        func_chunk = next((c for c in chunks if c.chunk_type == "function_def"), None)
        assert func_chunk is not None
        # Check imports are extracted (as separate items per alias)
        assert "from typing import List" in func_chunk.imports
        assert "from typing import Dict" in func_chunk.imports
        assert "import json" in func_chunk.imports


class TestMarkdownParser:
    """Tests for Markdown parser section chunking."""

    @staticmethod
    def _make_content(sections: list[tuple[str, str]], paragraph_lines: int = 8) -> str:
        """Build markdown content from (header, body) pairs.

        Args:
            sections: List of (header_line, body_text) tuples; body text is
                padded with extra lines to exceed the min section size
            paragraph_lines: Number of filler lines added to each body

        Returns:
            Markdown text where every section is long enough to stand alone
        """
        parts = []
        for header, body in sections:
            parts.append(header)
            parts.append(body)
            parts.extend(f"Filler line {i} with some words." for i in range(paragraph_lines))
        return "\n".join(parts)

    def test_can_parse_markdown_file(self):
        """Test that parser recognizes Markdown files."""
        parser = MarkdownParser()
        assert parser.can_parse(Path("doc.md"))
        assert parser.can_parse(Path("doc.mdx"))
        assert not parser.can_parse(Path("doc.txt"))

    def test_sections_produce_chunks_with_exact_lines(self):
        """Headers split the file into chunks with precise line ranges."""
        parser = MarkdownParser()
        content = self._make_content(
            [
                ("# Title", "Intro paragraph."),
                ("## Install", "How to install."),
                ("### Advanced", "Advanced setup."),
            ]
        )
        chunks = parser.parse_content(content, "doc.md")

        assert len(chunks) >= 3
        section_chunks = [c for c in chunks if c.chunk_type == "section"]
        install = next(c for c in section_chunks if c.name == "Install")
        advanced = next(c for c in section_chunks if c.name == "Advanced")

        # Exact boundaries: section starts at its header line
        lines = content.split("\n")
        assert lines[install.line_start - 1].startswith("## Install")
        assert lines[advanced.line_start - 1].startswith("### Advanced")
        assert install.line_end == advanced.line_start - 1

        # Parents: nearest parent header goes to docstring and symbol_names
        assert advanced.docstring == "Install"
        assert "Install" in advanced.symbol_names
        assert "Advanced" in advanced.symbol_names
        assert all(c.language == "markdown" for c in chunks)

        # Coverage: chunks tile the file without gaps or overlaps
        ranges = sorted((c.line_start, c.line_end) for c in chunks)
        assert ranges[0][0] == 1
        assert ranges[-1][1] == len(lines)
        for (_, prev_end), (next_start, _) in zip(ranges, ranges[1:]):
            assert next_start == prev_end + 1

    def test_file_without_headers_single_document_chunk(self):
        """File without headers produces one document chunk."""
        parser = MarkdownParser()
        content = "\n".join(f"Plain line {i} of text." for i in range(20))

        chunks = parser.parse_content(content, "plain.md")

        assert len(chunks) == 1
        assert chunks[0].chunk_type == "document"
        assert chunks[0].name == "plain"
        assert chunks[0].line_start == 1
        assert chunks[0].line_end == len(content.split("\n"))

    def test_headers_inside_code_blocks_ignored(self):
        """Header-looking lines inside fenced code blocks do not split."""
        parser = MarkdownParser()
        content = self._make_content(
            [
                ("# Title", "Intro."),
                ("## Real Section", "Body."),
            ]
        )
        # Append a code block containing fake headers
        content += "\n## Fake\n```python\n# not a header\nfake = 1\n```\n"
        chunks = parser.parse_content(content, "doc.md")

        names = [c.name for c in chunks]
        assert "Real Section" in names
        assert "Fake" not in names

    def test_oversized_section_split_by_paragraphs(self):
        """Section longer than max_section_chars is split into several chunks."""
        parser = MarkdownParser()
        paragraph = "word " * 40  # ~200 chars
        long_body = "\n".join(paragraph for _ in range(40))  # ~8000+ chars
        content = f"# Title\n\n## Long Section\n\n{long_body}\n"

        chunks = parser.parse_content(content, "doc.md")

        section_chunks = [c for c in chunks if c.name == "Long Section"]
        assert len(section_chunks) > 1
        # All pieces keep the section name and stay within the size cap
        for chunk in section_chunks:
            assert chunk.chunk_type == "section"
            assert len(chunk.content) <= parser.max_section_chars + 200

    def test_short_sections_merged_into_previous(self):
        """Sections below min_section_chars are merged into the previous chunk."""
        parser = MarkdownParser()
        content = (
            "# Title\n\nIntro paragraph.\n\n"
            "## Big Section\n" + ("text " * 60) + "\n\n"
            "## Tiny\nsmall\n\n"
            "## Another Big\n" + ("more " * 60) + "\n"
        )
        chunks = parser.parse_content(content, "doc.md")

        names = [c.name for c in chunks]
        assert "Tiny" not in names
        # Tiny content was absorbed into the preceding chunk
        big = next(c for c in chunks if c.name == "Big Section")
        assert "small" in big.content

    def test_imports_contain_code_block_languages_only(self):
        """imports holds opener languages, not first words of block lines."""
        parser = MarkdownParser()
        content = (
            "# Title\n\n## Section\n\n"
            "```bash\nhelm install vm operator\nanother command line\n```\n\n"
            "```python\nx = 1\n```\n" + ("text " * 60)
        )
        chunks = parser.parse_content(content, "doc.md")

        section = next(c for c in chunks if c.name == "Section")
        assert section.imports == ["bash", "python"]
        # First words of inner lines must not leak in
        assert "helm" not in section.imports
        assert "another" not in section.imports

    def test_empty_content_returns_no_chunks(self):
        """Empty or whitespace-only content produces no chunks."""
        parser = MarkdownParser()
        assert parser.parse_content("", "doc.md") == []
        assert parser.parse_content("\n\n", "doc.md") == []


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

    def test_find_parser_for_markdown(self):
        """Test finding Markdown parser."""
        parser = find_parser(Path("doc.md"))
        assert parser is not None
        assert isinstance(parser, MarkdownParser)
