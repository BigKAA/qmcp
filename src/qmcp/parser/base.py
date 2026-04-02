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

"""Base parser interface for code parsing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedChunk:
    """Represents a parsed code chunk with metadata for structured filtering.

    Attributes:
        file_path: Absolute path to the source file
        content: Raw code content of the chunk
        chunk_type: Type of code construct (function_def, class_def, import_stmt, etc.)
        name: Name of the symbol (function name, class name, etc.)
        line_start: Starting line number (1-indexed)
        line_end: Ending line number (1-indexed)
        docstring: Associated docstring/comment if present
        signature: Function/class signature for matching (e.g., "def foo(a: int) -> str")
        symbol_names: List of all symbol names referenced/defined in this chunk
        imports: List of import statements in the chunk or file
        language: Programming language (python, go, js, etc.)
    """

    file_path: str
    content: str
    chunk_type: str  # function_def, class_def, import_stmt, etc.
    name: str
    line_start: int
    line_end: int
    docstring: str = ""
    signature: str | None = None  # e.g., "def get_user(user_id: int) -> User"
    symbol_names: list[str] = field(default_factory=list)  # ["get_user", "validate"]
    imports: list[str] = field(default_factory=list)  # ["from typing import User"]
    language: str = "unknown"  # python, go, js, etc.


class BaseParser(ABC):
    """Abstract base class for code parsers."""

    extensions: list[str] = []

    @abstractmethod
    def parse_file(self, file_path: Path) -> list[ParsedChunk]:
        """Parse a single file and return code chunks.

        Args:
            file_path: Path to the file

        Returns:
            List of parsed code chunks
        """
        pass

    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to check

        Returns:
            True if parser can handle this file
        """
        pass

    def parse_content(self, content: str, file_path: str | None = None) -> list[ParsedChunk]:
        """Parse file content directly.

        Default implementation reads from file.
        Override for content-based parsing.

        Args:
            content: Source code content to parse
            file_path: Optional file path for context (used in error messages, etc.)
        """
        raise NotImplementedError("Override parse_file or parse_content")
