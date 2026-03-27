.PHONY: help install dev test build run clean lint format

help:
	@echo "QMCP - QDrant MCP Server for OpenCode"
	@echo ""
	@echo "Available targets:"
	@echo "  install  - Install dependencies"
	@echo "  dev      - Install in development mode"
	@echo "  test     - Run tests"
	@echo "  build    - Build Docker image"
	@echo "  run      - Run locally"
	@echo "  clean    - Clean up"
	@echo "  lint     - Run linter"
	@echo "  format   - Format code"

install:
	uv sync

dev:
	uv sync --dev
	uv pip install -e .

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ --cov=src --cov-report=html --cov-report=term

build:
	docker build -t qmcp:latest .

run:
	export QDRANT_URL=http://192.168.218.190:6333
	uv run python -m qmcp.server

run-local:
	uv run python -m qmcp.server

clean:
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
