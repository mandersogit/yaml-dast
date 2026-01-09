"""ydst — YAML data-structure templates.

This package provides:

- A YAML loader (PyYAML-based) that understands templating tags (e.g., !var, !if).
- A renderer that evaluates templates into concrete Python data structures.
- Optional include resolvers and a simple CLI.

See README.md for usage examples.

For advanced features, import from submodules:
- ydst.nodes: Node classes (Var, If, ForEach, etc.), sentinels (OMIT, UNSET)
- ydst.errors: Specific error classes (MissingVariableError, ExpressionError, etc.)
- ydst.analysis: Static analysis (collect_variables, analyze_dependencies, etc.)
- ydst.validate: Template validation
- ydst.registry: Registry utilities (chain_registries, minimal_registry, etc.)
- ydst.include: Include resolver protocol and utilities
"""

from __future__ import annotations

import ydst.api as _api_mod
import ydst.engine as _engine_mod
import ydst.errors as _errors_mod
import ydst.include as _include_mod
import ydst.registry as _registry_mod
import ydst.render as _render_mod
import ydst.template as _template_mod

# -----------------------------------------------------------------------------
# Core API
# -----------------------------------------------------------------------------

# Template class - the primary user-facing interface
Template = _template_mod.Template

# Engine - for customization and advanced usage
TemplateEngine = _engine_mod.TemplateEngine

# Configuration
RenderOptions = _render_mod.RenderOptions

# Factory for safe/sandboxed engines
safe_engine = _api_mod.safe_engine

# -----------------------------------------------------------------------------
# One-shot rendering (load + render in one call)
# -----------------------------------------------------------------------------

render_text = _template_mod.render_text
render_path = _template_mod.render_path
render_stream = _template_mod.render_stream

# -----------------------------------------------------------------------------
# Module-level default engine management
# -----------------------------------------------------------------------------

get_default_engine = _template_mod.get_default_engine
set_default_engine = _template_mod.set_default_engine

# -----------------------------------------------------------------------------
# Errors (base classes for exception handling)
# -----------------------------------------------------------------------------

YdstError = _errors_mod.YdstError
RenderError = _errors_mod.RenderError
TemplateLoadError = _errors_mod.TemplateLoadError
TemplateValidationError = _errors_mod.TemplateValidationError

# -----------------------------------------------------------------------------
# Registry (for custom functions in templates)
# -----------------------------------------------------------------------------

FunctionRegistry = _registry_mod.FunctionRegistry
DictFunctionRegistry = _registry_mod.DictFunctionRegistry
safe_registry = _registry_mod.safe_registry
extended_registry = _registry_mod.extended_registry

# -----------------------------------------------------------------------------
# Includes (for custom include resolution)
# -----------------------------------------------------------------------------

FileIncludeResolver = _include_mod.FileIncludeResolver

# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

__all__ = [
    # Core
    "Template",
    "TemplateEngine",
    "RenderOptions",
    "safe_engine",
    # One-shot rendering
    "render_text",
    "render_path",
    "render_stream",
    # Engine management
    "get_default_engine",
    "set_default_engine",
    # Errors
    "YdstError",
    "RenderError",
    "TemplateLoadError",
    "TemplateValidationError",
    # Registry
    "FunctionRegistry",
    "DictFunctionRegistry",
    "safe_registry",
    "extended_registry",
    # Includes
    "FileIncludeResolver",
]
