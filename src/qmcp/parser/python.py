"""Python parser using AST."""

import ast
from pathlib import Path

from .base import BaseParser, ParsedChunk


class PythonParser(BaseParser):
    """Parser for Python files using AST."""

    extensions = [".py", ".pyi"]

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix in self.extensions

    def parse_file(self, file_path: Path) -> list[ParsedChunk]:
        """Parse Python file using AST."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return []

        return self.parse_content(content, str(file_path))

    def parse_content(self, content: str, file_path: str) -> list[ParsedChunk]:
        """Parse Python content using AST."""
        chunks = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        # Get module docstring
        module_docstring = ast.get_docstring(tree) or ""

        # Parse functions and classes
        for node in ast.walk(tree):
            chunk = self._extract_chunk(node, content, file_path, module_docstring)
            if chunk:
                chunks.append(chunk)

        return chunks

    def _extract_chunk(
        self,
        node: ast.AST,
        source: str,
        file_path: str,
        module_doc: str,
    ) -> ParsedChunk | None:
        """Extract a single chunk from AST node."""
        if isinstance(node, ast.FunctionDef):
            return self._parse_function(node, source, file_path)
        elif isinstance(node, ast.AsyncFunctionDef):
            return self._parse_function(node, source, file_path, is_async=True)
        elif isinstance(node, ast.ClassDef):
            return self._parse_class(node, source, file_path)
        return None

    def _parse_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        source: str,
        file_path: str,
        is_async: bool = False,
    ) -> ParsedChunk:
        """Parse a function definition."""
        # Get function source
        func_source = ast.get_source_segment(source, node)
        if func_source is None:
            func_source = ""

        # Get docstring
        docstring = ast.get_docstring(node) or ""

        return ParsedChunk(
            file_path=file_path,
            content=func_source,
            chunk_type="function",
            name=node.name,
            line_start=node.lineno or 0,
            line_end=node.end_lineno or 0,
            docstring=docstring,
        )

    def _parse_class(
        self,
        node: ast.ClassDef,
        source: str,
        file_path: str,
    ) -> ParsedChunk:
        """Parse a class definition."""
        # Get class source
        class_source = ast.get_source_segment(source, node)
        if class_source is None:
            class_source = ""

        # Get docstring
        docstring = ast.get_docstring(node) or ""

        return ParsedChunk(
            file_path=file_path,
            content=class_source,
            chunk_type="class",
            name=node.name,
            line_start=node.lineno or 0,
            line_end=node.end_lineno or 0,
            docstring=docstring,
        )

    def _get_base_name(self, node: ast.expr) -> str:
        """Get name from base class node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_base_name(node.value) + "." + node.attr
        return "Unknown"
