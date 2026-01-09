# yaml-dast Makefile
#
# Usage:
#   make test       - Run all tests
#   make test-cov   - Run tests with coverage report
#   make lint       - Run ruff linter
#   make typecheck  - Run mypy type checker
#   make all        - Run lint, typecheck, and tests
#   make clean      - Remove build artifacts
#
# Set PYTHON_EXE to override the Python interpreter (defaults to local.venv).

# Default to local.venv if PYTHON_EXE not set
PYTHON_EXE ?= $(CURDIR)/local.venv/bin/python

.PHONY: test test-cov lint typecheck all clean help

# Default target
help:
	@echo "yaml-dast Development Commands"
	@echo ""
	@echo "  make test       Run all tests"
	@echo "  make test-cov   Run tests with coverage report"
	@echo "  make lint       Run ruff linter"
	@echo "  make typecheck  Run mypy type checker"
	@echo "  make all        Run lint, typecheck, and tests"
	@echo "  make clean      Remove build artifacts"
	@echo ""
	@echo "Python:   $(PYTHON_EXE)"
	@echo "Override: PYTHON_EXE=/path/to/python make test"

# Run all tests
test:
	$(PYTHON_EXE) -m pytest tests/ -v

# Run tests with coverage
test-cov:
	$(PYTHON_EXE) -m pytest tests/ -v \
		--cov=ydst \
		--cov-report=term-missing \
		--cov-report=html:coverage_html

# Lint with ruff
lint:
	$(PYTHON_EXE) -m ruff check ydst/ tests/ scripts/

# Type check with mypy
typecheck:
	$(PYTHON_EXE) -m mypy ydst/ tests/ scripts/ --ignore-missing-imports

# Run all checks
all: lint typecheck test

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf coverage_html/
	rm -rf .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
