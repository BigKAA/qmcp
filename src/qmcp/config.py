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

"""Configuration management using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All settings can be overridden via environment variables.
    Defaults are defined for local development.

    Attributes:
        qdrant_url: URL of the Qdrant server
        qdrant_api_key: Optional API key for Qdrant authentication
        embedding_model: Model name for generating embeddings
        host: Server host address
        port: Server port number
        transport: MCP transport type (streamable-http, sse, etc.)
        batch_size: Number of vectors to batch when indexing
        debounce_seconds: Seconds to wait before processing file changes
        watch_paths: Comma-separated list of paths to watch for changes
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log output format (json, text)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Qdrant Configuration
    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="URL of the Qdrant server",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="Optional API key for Qdrant authentication",
    )
    embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="Model name for generating embeddings",
    )
    embedding_cache_dir: str | None = Field(
        default=None,
        description="Custom directory for embedding model cache. If not set, uses system default (/tmp/fastembed_cache)",
    )

    # Server Configuration
    host: str = Field(
        default="0.0.0.0",
        description="Server host address",
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Server port number",
    )
    transport: Literal["streamable-http", "sse", "stdio"] = Field(
        default="streamable-http",
        description="MCP transport type",
    )

    # Indexer Configuration
    batch_size: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Number of vectors to batch when indexing",
    )
    debounce_seconds: float = Field(
        default=5.0,
        ge=0.1,
        le=300.0,
        description="Seconds to wait before processing file changes",
    )

    # Watch Configuration
    watch_paths: list[str] = Field(
        default=["/data/repo"],
        description="List of paths to watch for changes",
    )

    # Logging Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )
    log_format: Literal["json", "text"] = Field(
        default="text",
        description="Log output format",
    )

    @field_validator("watch_paths", mode="before")
    @classmethod
    def parse_watch_paths(cls, v):
        """Parse watch_paths from comma-separated string or list."""
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v):
        """Ensure log level is uppercase."""
        if isinstance(v, str):
            return v.upper()
        return v


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Cached Settings instance (singleton pattern)
    """
    return Settings()
