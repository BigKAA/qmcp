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


class MarkdownParser(BaseParser):
    """Parser for Markdown documentation files."""

    extensions = [".md", ".mdx"]
    language = "markdown"

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
        """Parse Markdown content."""
        chunks = []
        lines = content.split("\n")

        # Extract title
        title = ""
        for line in lines[:10]:
            if line.strip().startswith("# "):
                title = line.strip()[2:]
                break

        # Extract code blocks for additional metadata
        code_blocks = []
        in_code_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
            elif in_code_block:
                # Extract language from code block
                lang = line.strip().split()[0] if line.strip() else ""
                if lang:
                    code_blocks.append(lang)

        # Create single chunk for the file
        chunks.append(
            ParsedChunk(
                file_path=file_path or "unknown",
                content=content[:10000],  # Limit size
                chunk_type="document",
                name=title or Path(file_path or "unknown").stem,
                line_start=1,
                line_end=len(lines),
                docstring=title,
                signature=None,
                symbol_names=[title] if title else [],
                imports=code_blocks,  # Code block languages as "imports"
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
