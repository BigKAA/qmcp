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

"""Python parser using AST."""

import ast
from pathlib import Path

from .base import BaseParser, ParsedChunk


class PythonParser(BaseParser):
    """Parser for Python files using AST.

    Extracts code chunks with rich metadata including signatures,
    symbol names, and import statements for structured filtering.
    """

    extensions = [".py", ".pyi"]
    language = "python"

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix in self.extensions

    def parse_file(self, file_path: Path) -> list[ParsedChunk]:
        """Parse Python file using AST."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return []

        return self.parse_content(content, str(file_path))

    def parse_content(self, content: str, file_path: str | None = None) -> list[ParsedChunk]:
        """Parse Python content using AST and extract metadata.

        Extracts functions, classes, and imports with full metadata
        including signatures, symbol names, and line ranges.
        """
        chunks = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        # Extract file-level imports first
        file_imports = self._extract_imports(tree, content)

        # Parse functions and classes
        for node in ast.walk(tree):
            chunk = self._extract_chunk(node, content, file_path or "unknown", file_imports)
            if chunk:
                chunks.append(chunk)

        return chunks

    def _extract_imports(self, tree: ast.AST, source: str) -> list[str]:
        """Extract all import statements from AST.

        Args:
            tree: Parsed AST tree
            source: Source code for extracting import text

        Returns:
            List of import statement strings
        """
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        imports.append(f"import {alias.name} as {alias.asname}")
                    else:
                        imports.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    if alias.asname:
                        imports.append(f"from {module} import {alias.name} as {alias.asname}")
                    else:
                        imports.append(f"from {module} import {alias.name}")
        return imports

    def _extract_chunk(
        self,
        node: ast.AST,
        source: str,
        file_path: str,
        file_imports: list[str],
    ) -> ParsedChunk | None:
        """Extract a single chunk from AST node with full metadata."""
        if isinstance(node, ast.FunctionDef):
            return self._parse_function(node, source, file_path, file_imports)
        elif isinstance(node, ast.AsyncFunctionDef):
            return self._parse_function(node, source, file_path, file_imports, is_async=True)
        elif isinstance(node, ast.ClassDef):
            return self._parse_class(node, source, file_path, file_imports)
        return None

    def _build_signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        is_async: bool = False,
    ) -> str:
        """Build a signature string for a function or class.

        Args:
            node: AST node for function or class
            is_async: Whether the function is async

        Returns:
            Signature string like "def foo(a: int, b: str) -> None"
        """
        parts = []

        # Function or class keyword
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parts.append("async " if is_async else "")
            parts.append("def ")
            parts.append(node.name)
        elif isinstance(node, ast.ClassDef):
            parts.append("class ")
            parts.append(node.name)
            # Classes don't have parameters in their signature definition
            return "".join(parts)

        # For functions only: build parameters list
        # Parameters
        params = []
        for arg in node.args.args:
            param_str = arg.arg
            if arg.annotation:
                # Try to get annotation name
                annotation = self._get_annotation_name(arg.annotation)
                param_str += f": {annotation}"
            params.append(param_str)

        # Add *args and **kwargs
        if node.args.vararg:
            vararg = node.args.vararg.arg
            if node.args.vararg.annotation:
                vararg += f": {self._get_annotation_name(node.args.vararg.annotation)}"
            params.append(f"*{vararg}")
        if node.args.kwarg:
            kwarg = node.args.kwarg.arg
            if node.args.kwarg.annotation:
                kwarg += f": {self._get_annotation_name(node.args.kwarg.annotation)}"
            params.append(f"**{kwarg}")

        # Add positional-only and keyword-only args
        if node.args.posonlyargs:
            posonly = []
            for arg in node.args.posonlyargs:
                param_str = arg.arg
                if arg.annotation:
                    param_str += f": {self._get_annotation_name(arg.annotation)}"
                posonly.append(param_str)
            params = posonly + params

        if node.args.kwonlyargs:
            kwonly = []
            for arg in node.args.kwonlyargs:
                param_str = arg.arg
                if arg.annotation:
                    param_str += f": {self._get_annotation_name(arg.annotation)}"
                kwonly.append(param_str)
            params.extend(kwonly)

        parts.append("(" + ", ".join(params) + ")")

        # Return type for functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
            parts.append(" -> ")
            parts.append(self._get_annotation_name(node.returns))

        return "".join(parts)

    def _get_annotation_name(self, annotation: ast.expr) -> str:
        """Get a string representation of a type annotation.

        Args:
            annotation: AST expression representing a type

        Returns:
            String representation of the type annotation
        """
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Attribute):
            value = self._get_annotation_name(annotation.value)
            return f"{value}.{annotation.attr}"
        elif isinstance(annotation, ast.Subscript):
            base = self._get_annotation_name(annotation.value)
            # Handle subscript like List[int], Dict[str, Any]
            if isinstance(annotation.slice, ast.Tuple):
                args = ", ".join(self._get_annotation_name(elt) for elt in annotation.slice.elts)
            else:
                args = self._get_annotation_name(annotation.slice)
            return f"{base}[{args}]"
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value)
        elif isinstance(annotation, ast.BinOp):
            # Handle Union types with |
            left = self._get_annotation_name(annotation.left)
            right = self._get_annotation_name(annotation.right)
            op = " | " if isinstance(annotation.op, ast.BitOr) else " | "
            return f"({left}{op}{right})"
        return "Any"

    def _parse_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        source: str,
        file_path: str,
        file_imports: list[str],
        is_async: bool = False,
    ) -> ParsedChunk:
        """Parse a function definition with full metadata.

        Args:
            node: AST function node
            source: Source code
            file_path: Path to the file
            file_imports: List of imports from the file
            is_async: Whether this is an async function

        Returns:
            ParsedChunk with extracted metadata
        """
        # Get function source
        func_source = ast.get_source_segment(source, node)
        if func_source is None:
            func_source = ""

        # Get docstring
        docstring = ast.get_docstring(node) or ""

        # Build signature
        signature = self._build_signature(node, is_async)

        # Collect symbol names (function name + parameter names)
        symbol_names = [node.name]
        for arg in node.args.args:
            symbol_names.append(arg.arg)
        for arg in node.args.kwonlyargs:
            symbol_names.append(arg.arg)
        if node.args.vararg:
            symbol_names.append(node.args.vararg.arg)
        if node.args.kwarg:
            symbol_names.append(node.args.kwarg.arg)

        # Determine chunk_type
        chunk_type = "async_function_def" if is_async else "function_def"

        return ParsedChunk(
            file_path=file_path,
            content=func_source,
            chunk_type=chunk_type,
            name=node.name,
            line_start=node.lineno or 0,
            line_end=node.end_lineno or 0,
            docstring=docstring,
            signature=signature,
            symbol_names=symbol_names,
            imports=file_imports,
            language=self.language,
        )

    def _parse_class(
        self,
        node: ast.ClassDef,
        source: str,
        file_path: str,
        file_imports: list[str],
    ) -> ParsedChunk:
        """Parse a class definition with full metadata.

        Args:
            node: AST class node
            source: Source code
            file_path: Path to the file
            file_imports: List of imports from the file

        Returns:
            ParsedChunk with extracted metadata
        """
        # Get class source
        class_source = ast.get_source_segment(source, node)
        if class_source is None:
            class_source = ""

        # Get docstring
        docstring = ast.get_docstring(node) or ""

        # Build signature (class name + base classes)
        signature = self._build_signature(node)

        # Collect symbol names (class name + base class names)
        symbol_names = [node.name]
        for base in node.bases:
            base_name = self._get_base_name(base)
            if base_name != "Unknown":
                symbol_names.append(base_name)

        return ParsedChunk(
            file_path=file_path,
            content=class_source,
            chunk_type="class_def",
            name=node.name,
            line_start=node.lineno or 0,
            line_end=node.end_lineno or 0,
            docstring=docstring,
            signature=signature,
            symbol_names=symbol_names,
            imports=file_imports,
            language=self.language,
        )

    def _get_base_name(self, node: ast.expr) -> str:
        """Get name from base class node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_base_name(node.value) + "." + node.attr
        return "Unknown"
