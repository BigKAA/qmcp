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
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedChunk:
    """Represents a parsed code chunk."""

    file_path: str
    content: str
    chunk_type: str  # function, class, method, etc.
    name: str
    line_start: int
    line_end: int
    docstring: str = ""


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

    def parse_content(self, content: str) -> list[ParsedChunk]:
        """Parse file content directly.

        Default implementation reads from file.
        Override for content-based parsing.
        """
        raise NotImplementedError("Override parse_file or parse_content")
