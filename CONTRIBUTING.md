# Contributing to ydst

## Development Setup

This project uses a local virtual environment at `./local.venv/`.

```bash
# Create the virtual environment (Python 3.11+ required)
python3 -m venv local.venv

# Install in editable mode with dev dependencies
./local.venv/bin/pip install -e ".[dev]"
```

The Makefile and scripts automatically use `./local.venv/bin/python` when available.

## Running Tests and Checks

```bash
make all         # Run lint + typecheck + tests
make test        # Run tests only
make lint        # Run ruff linter
make typecheck   # Run mypy
```

Or directly:

```bash
./local.venv/bin/python -m pytest tests/ -v
./local.venv/bin/python -m ruff check ydst/ tests/
./local.venv/bin/python -m mypy ydst/ tests/
```

## Coding Standards

### Import Style

**Always use qualified imports.** Never import symbols directly into the namespace.

```python
# ❌ FORBIDDEN
from pathlib import Path
from typing import Any

# ✅ CORRECT - external packages get underscore prefix
import pathlib as _pathlib
import typing as _typing

# ✅ CORRECT - internal ydst packages have no underscore
import ydst.engine as engine
```

- **External** (stdlib, third-party): underscore prefix (`_pathlib`, `_click`)
- **Internal** (ydst.*): no underscore (`engine`, `render`)

### Type Hints

Always use type hints for function signatures.

### Docstrings

Use Google-style docstrings.

## Commit Workflow

This project uses **commit plans** instead of direct `git commit`. Plans are YAML files that describe a series of commits.

```bash
# Preview a commit plan (safe, read-only)
./scripts/commit-helper.py workflow/commit-plans/plan.yaml

# Execute commits (requires explicit request)
./scripts/commit-helper.py workflow/commit-plans/plan.yaml --execute
```

See `.cursor/rules/commit-plans.mdc` for the full workflow.

## Project Structure

```
ydst/           # Main package source
tests/          # Test suite
docs/           # User-facing documentation
scripts/        # Development scripts
workflow/       # Planning docs, commit plans (gitignored)
examples/       # Example templates
```

## IDE Setup (Cursor/VS Code)

For proper Python analysis, ensure your IDE uses `./local.venv/bin/python` as the interpreter.

In Cursor/VS Code: `Cmd+Shift+P` → "Python: Select Interpreter" → choose `local.venv`.

