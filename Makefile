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

.PHONY: help install dev test build-package run clean lint format mcp-dev mcp-install publish publish-test release

help:
	@echo "QMCP - QDrant MCP Server for OpenCode"
	@echo ""
	@echo "Available targets:"
	@echo "  install       - Install dependencies"
	@echo "  dev           - Install in development mode"
	@echo "  test          - Run tests"
	@echo "  build-package - Build PyPI package (dist/)"
	@echo "  publish-test  - Publish to Test PyPI"
	@echo "  publish       - Publish to PyPI"
	@echo "  clean         - Clean up"
	@echo "  lint          - Run linter"
	@echo "  format        - Format code"
	@echo "  mcp-dev       - Run with MCP inspector"
	@echo "  mcp-install   - Install as MCP server"

install:
	uv sync

dev:
	uv sync --dev
	uv pip install -e .

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ --cov=src --cov-report=html --cov-report=term

clean:
	rm -rf dist/
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	rm -rf .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

lint:
	uv run ruff check src/

format:
	uv run ruff format src/

mcp-dev:
	uv run mcp dev src/qmcp/server.py

mcp-install:
	uv run mcp install src/qmcp/server.py

# PyPI Publishing
build-package:
	rm -rf dist/
	uv build

publish-test:
	@echo "Publishing to Test PyPI..."
	uv publish --repository testpypi --trusted-publishing never

publish:
	@echo "Publishing to PyPI..."
	uv publish --trusted-publishing never

release:
	@echo "Usage: make release VERSION=X.Y.Z"
	@echo "This will:"
	@echo "  1. Update version in pyproject.toml"
	@echo "  2. Create git tag vX.Y.Z"
	@echo "  3. Build package"
	@echo "  4. Publish to PyPI"
	@echo ""
	@echo "To release, run manually:"
	@echo "  1. uv build"
	@echo "  2. uv publish --trusted-publishing never"
	@echo "  3. git tag -a vX.Y.Z -m 'Release vX.Y.Z'"
	@echo "  4. git push origin vX.Y.Z"
