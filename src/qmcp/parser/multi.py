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

"""Multi-language parser using tree-sitter."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Parser

from .base import BaseParser, ParsedChunk
from .python import PythonParser

# Language configurations
LANGUAGE_CONFIGS = {
    ".go": {
        "language": "go",
        "extensions": [".go"],
        "function_query": """
            (function_declaration
                name: (identifier) @func_name
                body: (block) @body)
            (method_declaration
                name: (field_identifier) @func_name
                body: (block) @body)
        """,
        "class_query": "(type_declaration (type_spec (identifier) @class_name))",
        "import_query": "(import_declaration (import_spec (string_literal) @import))",
    },
    ".js": {
        "language": "javascript",
        "extensions": [".js", ".jsx", ".mjs"],
        "function_query": """
            (function_declaration
                name: (identifier) @func_name
                body: (block_statement) @body)
            (arrow_function) @func
            (method_definition
                name: (property_identifier) @func_name
                body: (block_statement) @body)
        """,
        "class_query": "(class_declaration (identifier) @class_name)",
        "import_query": "(import_statement (_ (string_literal) @import))",
    },
    ".ts": {
        "language": "typescript",
        "extensions": [".ts", ".tsx", ".mts", ".cts"],
        "function_query": """
            (function_declaration
                name: (identifier) @func_name
                body: (block_statement) @body)
            (method_definition
                name: (property_identifier) @func_name
                body: (block_statement) @body)
        """,
        "class_query": "(class_declaration (identifier) @class_name)",
        "import_query": "(import_statement (_ (string_literal) @import))",
    },
    ".java": {
        "language": "java",
        "extensions": [".java"],
        "function_query": """
            (method_declaration
                type: (void_type)? @return_type
                name: (identifier) @func_name
                parameters: (formal_parameters) @params
                body: (block) @body)
            (constructor_declaration
                name: (identifier) @func_name
                parameters: (formal_parameters) @params
                body: (block) @body)
        """,
        "class_query": """
            (class_declaration
                name: (identifier) @class_name
                body: (class_body) @body)
        """,
        "import_query": "(import_declaration (scoped_identifier) @import)",
    },
    ".cs": {
        "language": "csharp",
        "extensions": [".cs"],
        "function_query": """
            (method_declaration
                type: (predefined_type)? @return_type
                name: (identifier) @func_name
                parameters: (parameter_list) @params
                body: (block) @body)
            (constructor_declaration
                name: (identifier) @func_name
                parameters: (parameter_list) @params
                body: (block) @body)
        """,
        "class_query": """
            (class_declaration
                name: (identifier) @class_name
                body: (class_body) @body)
        """,
        "import_query": "(using_directive (qualified_identifier) @import)",
    },
}


class MultiLanguageParser(BaseParser):
    """Parser for multiple languages using tree-sitter.

    Currently provides basic file-level chunking with metadata.
    Full tree-sitter AST traversal is available but requires
    language bindings to be installed.
    """

    def __init__(self):
        self._parsers: dict[str, Parser] = {}
        self._loaded_languages: set[str] = set()

    def _get_parser(self, lang: str) -> Parser:
        """Get or create parser for language."""
        if lang not in self._parsers:
            parser = Parser()
            # Language will be loaded dynamically
            self._parsers[lang] = parser
        return self._parsers[lang]

    def can_parse(self, file_path: Path) -> bool:
        suffix = file_path.suffix.lower()
        return suffix in LANGUAGE_CONFIGS

    def parse_file(self, file_path: Path) -> list[ParsedChunk]:
        """Parse file using tree-sitter."""
        suffix = file_path.suffix.lower()
        config = LANGUAGE_CONFIGS.get(suffix)

        if not config:
            return []

        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return []

        return self.parse_content_by_lang(content, str(file_path), config["language"])

    def parse_content(self, content: str, file_path: str | None = None) -> list[ParsedChunk]:
        """Not implemented - use parse_content_by_lang."""
        raise NotImplementedError("Use parse_content_by_lang")

    def parse_content_by_lang(
        self,
        content: str,
        file_path: str,
        language: str,
    ) -> list[ParsedChunk]:
        """Parse content for a specific language.

        Extracts file-level chunk with metadata. For full AST-based
        extraction, tree-sitter language bindings need to be initialized.
        """
        chunks = []
        lines = content.split("\n")

        if not lines:
            return chunks

        # Determine file extension for chunk_type
        suffix = Path(file_path).suffix.lower()
        lang_config = LANGUAGE_CONFIGS.get(suffix, {})
        lang_name = lang_config.get("language", language)

        # Extract imports using simple regex patterns (fallback when tree-sitter unavailable)
        imports = self._extract_imports_simple(content, suffix)

        # Create a file-level chunk with metadata
        chunks.append(
            ParsedChunk(
                file_path=file_path,
                content=content[:5000],  # Limit content size
                chunk_type="file",
                name=Path(file_path).stem,
                line_start=1,
                line_end=len(lines),
                docstring="",
                signature=None,
                symbol_names=[Path(file_path).stem],
                imports=imports,
                language=lang_name,
            )
        )

        return chunks

    def _extract_imports_simple(self, content: str, suffix: str) -> list[str]:
        """Extract imports using simple patterns (fallback).

        This is a simplified version that works without tree-sitter.
        For full accuracy, use tree-sitter queries.
        """
        imports = []
        import_prefixes = {
            ".go": ("import", '"'),
            ".js": ("import", "'"),
            ".ts": ("import", "'"),
            ".java": ("import", ";"),
            ".cs": ("using", ";"),
        }

        prefix, _ = import_prefixes.get(suffix, (None, None))
        if not prefix:
            return imports

        for line in content.split("\n"):
            line = line.strip()
            if line.startswith(prefix):
                # Extract import path
                if '"' in line:
                    start = line.index('"') + 1
                    end = line.rindex('"')
                    imports.append(line[start:end])
                elif "'" in line:
                    start = line.index("'") + 1
                    end = line.rindex("'")
                    imports.append(line[start:end])
                elif ";" in line and suffix == ".java":
                    # Java import without quotes
                    parts = line.replace("import", "").replace(";", "").strip()
                    if parts:
                        imports.append(parts)

        return imports


# Markdown header line, e.g. "## Section title" (trailing "#" decorations are stripped)
_MD_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


@dataclass
class _MarkdownSection:
    """Intermediate markdown section produced during splitting.

    Attributes:
        start: First line index of the section (0-based, inclusive)
        end: Last line index of the section (0-based, inclusive)
        title: Section header text (empty for the preamble chunk)
        parents: Titles of enclosing higher-level headers, outermost first
        kind: Either "section" (starts at a header) or "document" (preamble)
    """

    start: int
    end: int
    title: str
    parents: list[str] = field(default_factory=list)
    kind: str = "section"


class MarkdownParser(BaseParser):
    """Parser for Markdown documentation files.

    Files are split into sections by ATX headers (levels between
    ``section_min_level`` and ``section_max_level``, by default ``##`` and
    ``###``). Sections longer than ``max_section_chars`` are further split by
    paragraph boundaries, never inside a fenced code block. A file without
    matching headers falls back to a single ``document`` chunk, also
    paragraph-split when oversized.

    Headers inside fenced code blocks are ignored. Short sections below
    ``min_section_chars`` are merged into the previous chunk.
    """

    extensions = [".md", ".mdx"]
    language = "markdown"

    # Configurable chunking parameters (override per instance or per subclass)
    section_min_level: int = 2
    section_max_level: int = 3
    min_section_chars: int = 200
    max_section_chars: int = 8000
    max_code_langs: int = 5

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.extensions

    def parse_file(self, file_path: Path) -> list[ParsedChunk]:
        """Parse Markdown file."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return []

        return self.parse_content(content, str(file_path))

    def parse_content(self, content: str, file_path: str | None = None) -> list[ParsedChunk]:
        """Parse Markdown content into per-section chunks.

        Args:
            content: Raw markdown text
            file_path: Path of the source file (used for chunk metadata)

        Returns:
            One ``section`` chunk per header section plus a ``document`` chunk
            for the preamble, or a single ``document`` chunk for files without
            headers
        """
        resolved_path = file_path or "unknown"
        lines = content.split("\n")

        if not any(line.strip() for line in lines):
            return []

        sections = self._split_into_sections(lines)
        merged = self._merge_short_sections(sections, lines)

        chunks: list[ParsedChunk] = []
        for section in merged:
            chunks.extend(self._section_to_chunks(section, lines, resolved_path))
        return chunks

    def _is_code_fence(self, line: str) -> bool:
        """Check whether the line opens or closes a fenced code block."""
        stripped = line.lstrip()
        return stripped.startswith("```") or stripped.startswith("~~~")

    def _find_headers(self, lines: list[str]) -> list[tuple[int, int, str]]:
        """Find ATX headers outside fenced code blocks.

        Args:
            lines: File lines

        Returns:
            List of ``(line_index, level, title)`` tuples
        """
        headers: list[tuple[int, int, str]] = []
        in_code_block = False

        for index, line in enumerate(lines):
            if self._is_code_fence(line):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            match = _MD_HEADER_RE.match(line)
            if match:
                headers.append((index, len(match.group(1)), match.group(2).strip()))

        return headers

    def _split_into_sections(self, lines: list[str]) -> list[_MarkdownSection]:
        """Split file lines into preamble and header sections.

        Args:
            lines: File lines

        Returns:
            Ordered sections covering every line of the file; empty list when
            the file has no headers at split levels
        """
        headers = self._find_headers(lines)

        # Document title: nearest H1 or the first header of any level
        doc_title = ""
        for _, level, title in headers:
            if level == 1:
                doc_title = title
                break
        if not doc_title and headers:
            doc_title = headers[0][2]

        split_headers = [
            (index, level, title)
            for index, level, title in headers
            if self.section_min_level <= level <= self.section_max_level
        ]

        sections: list[_MarkdownSection] = []

        # Preamble before the first split-level header becomes a document chunk
        first_split = split_headers[0][0] if split_headers else len(lines)
        if first_split > 0:
            sections.append(
                _MarkdownSection(start=0, end=first_split - 1, title=doc_title, kind="document")
            )

        # Track the nearest header title seen at each level to build parents
        current_by_level: dict[int, str] = {1: doc_title} if doc_title else {}

        for position, (index, level, title) in enumerate(split_headers):
            end = (
                split_headers[position + 1][0] - 1
                if position + 1 < len(split_headers)
                else len(lines) - 1
            )
            parents = [current_by_level[lvl] for lvl in sorted(current_by_level) if lvl < level]
            sections.append(_MarkdownSection(start=index, end=end, title=title, parents=parents))
            current_by_level[level] = title

        return sections

    def _merge_short_sections(
        self, sections: list[_MarkdownSection], lines: list[str]
    ) -> list[_MarkdownSection]:
        """Merge sections shorter than ``min_section_chars`` into the previous one.

        A short preamble is absorbed into the following section instead, so a
        tiny preamble never produces a near-empty chunk.

        Args:
            sections: Sections produced by ``_split_into_sections``
            lines: File lines (for length measurement)

        Returns:
            Filtered list of sections with adjusted boundaries
        """
        if not sections:
            return sections

        def section_len(section: _MarkdownSection) -> int:
            return sum(len(line) for line in lines[section.start : section.end + 1])

        result: list[_MarkdownSection] = []

        for section in sections:
            if result and section_len(section) < self.min_section_chars:
                # Absorb into the previous chunk: extend its range and keep
                # its title/parents so the merged chunk stays addressable
                result[-1].end = section.end
                continue
            result.append(section)

        # Short preamble merges forward into the first section
        if (
            len(result) > 1
            and result[0].kind == "document"
            and section_len(result[0]) < (self.min_section_chars)
        ):
            preamble = result.pop(0)
            result[0].start = preamble.start

        return result

    def _paragraph_ranges(self, lines: list[str]) -> list[tuple[int, int]]:
        """Split line range into paragraph-boundary ranges.

        Break points are blank lines outside fenced code blocks. Blank lines
        attach to the preceding range so the ranges tile the input exactly.

        Args:
            lines: Lines to split

        Returns:
            List of contiguous ``(start, end)`` line-index ranges (inclusive)
        """
        break_after: set[int] = set()
        in_code_block = False

        for index, line in enumerate(lines):
            if self._is_code_fence(line):
                in_code_block = not in_code_block
                continue
            if not in_code_block and not line.strip():
                break_after.add(index)

        ranges: list[tuple[int, int]] = []
        start = 0

        for index in range(len(lines)):
            # Break only after the last blank line of a blank run
            is_blank = index in break_after
            next_blank = index + 1 in break_after
            if is_blank and not next_blank and index + 1 < len(lines):
                ranges.append((start, index))
                start = index + 1

        if start < len(lines):
            ranges.append((start, len(lines) - 1))

        return ranges

    def _split_oversized(self, start: int, end: int, lines: list[str]) -> list[tuple[int, int]]:
        """Split an oversized line range into pieces within ``max_section_chars``.

        Greedily packs paragraph ranges; a single paragraph longer than the
        limit is hard-split by lines.

        Args:
            start: First line index of the range (inclusive)
            end: Last line index of the range (inclusive)
            lines: File lines

        Returns:
            List of ``(start, end)`` ranges covering the input range
        """
        section_lines = lines[start : end + 1]
        if sum(len(line) for line in section_lines) <= self.max_section_chars:
            return [(start, end)]

        pieces: list[tuple[int, int]] = []
        current_start: int | None = None
        current_len = 0

        def flush(bound: int) -> None:
            nonlocal current_start, current_len
            if current_start is not None:
                pieces.append((current_start, bound))
            current_start = None
            current_len = 0

        for range_start, range_end in self._paragraph_ranges(section_lines):
            absolute_start = start + range_start
            absolute_end = start + range_end
            piece_len = sum(len(line) for line in lines[absolute_start : absolute_end + 1])

            if piece_len > self.max_section_chars:
                # Single oversized paragraph: hard-split by lines.
                # flush() is a no-op when nothing has been accumulated yet.
                flush(absolute_start - 1)
                line_start = absolute_start
                running = 0
                for line_index in range(absolute_start, absolute_end + 1):
                    running += len(lines[line_index])
                    if running >= self.max_section_chars:
                        pieces.append((line_start, line_index))
                        line_start = line_index + 1
                        running = 0
                if line_start <= absolute_end:
                    current_start = line_start
                    current_len = sum(len(line) for line in lines[line_start : absolute_end + 1])
                continue

            if current_start is None:
                current_start = absolute_start
                current_len = piece_len
            elif current_len + piece_len <= self.max_section_chars:
                current_len += piece_len
            else:
                flush(absolute_start - 1)
                current_start = absolute_start
                current_len = piece_len

        if current_start is not None:
            flush(end)

        return pieces or [(start, end)]

    def _extract_code_langs(self, lines: list[str]) -> list[str]:
        """Extract unique code-block languages from fence opener lines.

        Only the language token of opening fences (e.g. `````bash``) is
        collected, never the first word of every line inside the block.

        Args:
            lines: Chunk lines

        Returns:
            Unique languages in order of appearance, capped at
            ``max_code_langs``
        """
        langs: list[str] = []
        in_code_block = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                if not in_code_block:
                    info = stripped.lstrip("`~").strip()
                    lang = info.split()[0] if info else ""
                    if lang and lang not in langs:
                        if len(langs) >= self.max_code_langs:
                            break
                        langs.append(lang)
                in_code_block = not in_code_block

        return langs

    def _section_to_chunks(
        self, section: _MarkdownSection, lines: list[str], file_path: str
    ) -> list[ParsedChunk]:
        """Convert one section into one or more addressable chunks.

        Args:
            section: Section boundaries and metadata
            lines: File lines
            file_path: Source file path for chunk metadata

        Returns:
            One chunk, or several when the section exceeds
            ``max_section_chars``
        """
        symbol_names = [*section.parents, section.title] if section.title else list(section.parents)
        if not symbol_names:
            symbol_names = [Path(file_path).stem]

        chunks: list[ParsedChunk] = []
        for piece_start, piece_end in self._split_oversized(section.start, section.end, lines):
            piece_lines = lines[piece_start : piece_end + 1]
            if not any(line.strip() for line in piece_lines):
                continue

            chunks.append(
                ParsedChunk(
                    file_path=file_path,
                    content="\n".join(piece_lines),
                    chunk_type=section.kind,
                    name=section.title or Path(file_path).stem,
                    line_start=piece_start + 1,
                    line_end=piece_end + 1,
                    docstring=section.parents[-1] if section.parents else section.title,
                    signature=None,
                    symbol_names=symbol_names,
                    imports=self._extract_code_langs(piece_lines),
                    language=self.language,
                )
            )

        return chunks


# Registry of all parsers
PARSERS: list[type[BaseParser]] = [
    PythonParser,
    MultiLanguageParser,
    MarkdownParser,
]


def get_parsers() -> list[BaseParser]:
    """Get list of parser instances."""
    return [parser_class() for parser_class in PARSERS]


def find_parser(file_path: Path) -> BaseParser | None:
    """Find appropriate parser for file."""
    for parser in get_parsers():
        if parser.can_parse(file_path):
            return parser
    return None
