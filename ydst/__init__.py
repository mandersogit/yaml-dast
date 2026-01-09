"""ydst — YAML data-structure templates.

This package provides:

- A YAML loader (PyYAML-based) that understands templating tags (e.g., !var, !if).
- A renderer that evaluates templates into concrete Python data structures.
- Optional include resolvers and a simple CLI.

See README.md for usage examples.
"""

from .engine import TemplateEngine
from .api import (
    load_template,
    load_template_text,
    load_template_file,
    render,
    safe_engine,
    safe_render,
)
from .render import RenderOptions, TraceEvent
from .normalize import to_jsonable
from .nodes import (
    SourceMark,
    TemplateNode,
    Omit,
    OMIT,
    UNSET,
    Var,
    Default,
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
from .validate import validate_template, collect_variables
from .analysis import (
    collect_expressions,
    collect_calls,
    collect_includes,
    collect_pipe_stage_strings,
    analyze_dependencies,
    Dependencies,
)
from .registry import (
    FunctionRegistry,
    default_registry,
    safe_registry,
    minimal_registry,
    extended_registry,
    DictFunctionRegistry,
    chain_registries,
)

__all__ = [
    # Engine / API
    "TemplateEngine",
    "load_template",
    "load_template_text",
    "load_template_file",
    "render",
    "safe_engine",
    "safe_render",
    "to_jsonable",
    # Render primitives
    "RenderOptions",
    "TraceEvent",
    # Validation / analysis
    "validate_template",
    "collect_variables",
    "collect_expressions",
    "collect_calls",
    "collect_includes",
    "collect_pipe_stage_strings",
    "analyze_dependencies",
    "Dependencies",
    # Nodes / sentinels
    "SourceMark",
    "TemplateNode",
    "Omit",
    "OMIT",
    "UNSET",
    "Var",
    "Default",
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
    "DictFunctionRegistry",
    "chain_registries",
    "minimal_registry",
    "safe_registry",
    "default_registry",
    "extended_registry",
]
