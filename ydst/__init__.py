"""ydst — YAML data-structure templates.

This package provides:

- A YAML loader (PyYAML-based) that understands templating tags (e.g., !var, !if).
- A renderer that evaluates templates into concrete Python data structures.
- Optional include resolvers and a simple CLI.

See README.md for usage examples.
"""

from .engine import TemplateEngine
from .api import load_template, render
from .nodes import (
    SourceMark,
    TemplateNode,
    Omit,
    OMIT,
    UNSET,
    Var,
    If,
    ForEach,
    Expr,
    Call,
    Pipe,
    IncludeRuntime,
)
from .errors import (
    YdstError,
    TemplateLoadError,
    TemplateValidationError,
    RenderError,
    MissingVariableError,
    RootOmitError,
    ExpressionError,
    FunctionNotFoundError,
    FunctionCallError,
    IncludeError,
    IncludeCycleError,
)
from .include import IncludeResolver, FileIncludeResolver, IncludeResult
from .registry import FunctionRegistry, default_registry, DictFunctionRegistry

__all__ = [
    # Engine / API
    "TemplateEngine",
    "load_template",
    "render",
    # Nodes / sentinels
    "SourceMark",
    "TemplateNode",
    "Omit",
    "OMIT",
    "UNSET",
    "Var",
    "If",
    "ForEach",
    "Expr",
    "Call",
    "Pipe",
    "IncludeRuntime",
    # Errors
    "YdstError",
    "TemplateLoadError",
    "TemplateValidationError",
    "RenderError",
    "MissingVariableError",
    "RootOmitError",
    "ExpressionError",
    "FunctionNotFoundError",
    "FunctionCallError",
    "IncludeError",
    "IncludeCycleError",
    # Includes
    "IncludeResolver",
    "FileIncludeResolver",
    "IncludeResult",
    # Registry
    "FunctionRegistry",
    "default_registry",
    "DictFunctionRegistry",
]
