"""ydst — YAML data-structure templates.

This package provides:

- A YAML loader (PyYAML-based) that understands templating tags (e.g., !var, !if).
- A renderer that evaluates templates into concrete Python data structures.
- Optional include resolvers and a simple CLI.

See README.md for usage examples.
"""

from __future__ import annotations

import ydst.analysis as analysis_mod
import ydst.api as api_mod
import ydst.engine as engine_mod
import ydst.errors as errors_mod
import ydst.include as include_mod
import ydst.nodes as nodes_mod
import ydst.normalize as normalize_mod
import ydst.registry as registry_mod
import ydst.render as render_mod
import ydst.validate as validate_mod

# Engine / API
TemplateEngine = engine_mod.TemplateEngine
load_template = api_mod.load_template
load_template_text = api_mod.load_template_text
load_template_file = api_mod.load_template_file
render = api_mod.render
safe_engine = api_mod.safe_engine
safe_render = api_mod.safe_render
to_jsonable = normalize_mod.to_jsonable

# Render primitives
RenderOptions = render_mod.RenderOptions
TraceEvent = render_mod.TraceEvent

# Nodes / sentinels
SourceMark = nodes_mod.SourceMark
TemplateNode = nodes_mod.TemplateNode
Omit = nodes_mod.Omit
OMIT = nodes_mod.OMIT
UNSET = nodes_mod.UNSET

Var = nodes_mod.Var
Default = nodes_mod.Default
If = nodes_mod.If
ForEach = nodes_mod.ForEach
Expr = nodes_mod.Expr
Call = nodes_mod.Call
Pipe = nodes_mod.Pipe
IncludeRuntime = nodes_mod.IncludeRuntime
SetDefault = nodes_mod.SetDefault
Python = nodes_mod.Python
PythonModule = nodes_mod.PythonModule

# Errors
YdstError = errors_mod.YdstError
TemplateLoadError = errors_mod.TemplateLoadError
TemplateValidationError = errors_mod.TemplateValidationError
RenderError = errors_mod.RenderError
MissingVariableError = errors_mod.MissingVariableError
RootOmitError = errors_mod.RootOmitError
ExpressionError = errors_mod.ExpressionError
FunctionNotFoundError = errors_mod.FunctionNotFoundError
FunctionCallError = errors_mod.FunctionCallError
IncludeError = errors_mod.IncludeError
IncludeCycleError = errors_mod.IncludeCycleError
PythonError = errors_mod.PythonError
PythonEmitError = errors_mod.PythonEmitError

# Includes
IncludeResolver = include_mod.IncludeResolver
FileIncludeResolver = include_mod.FileIncludeResolver
IncludeResult = include_mod.IncludeResult

# Validation / analysis
validate_template = validate_mod.validate_template
collect_variables = validate_mod.collect_variables

collect_expressions = analysis_mod.collect_expressions
collect_calls = analysis_mod.collect_calls
collect_includes = analysis_mod.collect_includes
collect_pipe_stage_strings = analysis_mod.collect_pipe_stage_strings
analyze_dependencies = analysis_mod.analyze_dependencies
Dependencies = analysis_mod.Dependencies

# Registry
FunctionRegistry = registry_mod.FunctionRegistry
default_registry = registry_mod.default_registry
safe_registry = registry_mod.safe_registry
minimal_registry = registry_mod.minimal_registry
extended_registry = registry_mod.extended_registry
DictFunctionRegistry = registry_mod.DictFunctionRegistry
chain_registries = registry_mod.chain_registries

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
    "SetDefault",
    "Python",
    "PythonModule",
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
    "PythonError",
    "PythonEmitError",
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
