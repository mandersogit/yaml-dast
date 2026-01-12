from __future__ import annotations

import collections.abc as _abc
import dataclasses as _dataclasses
import typing as _typing

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

NodeTree: _typing.TypeAlias = _typing.Any
"""A parsed YAML structure: dicts, lists, scalars, or TemplateNode instances.

This is the raw result of YAML parsing before being wrapped in a Template.
"""

PathSegment: _typing.TypeAlias = str | int | tuple[str, str | int]
"""A path segment: string key, integer index, or compound (e.g., ('args', 0))."""


# ---------------------------------------------------------------------------
# Source location
# ---------------------------------------------------------------------------


@_dataclasses.dataclass(frozen=True, slots=True)
class SourceMark:
    """Source location information for a YAML node.

    Line/column are 1-based for human readability (matching most editor conventions).
    """

    source: str | None = None
    line: int | None = None
    column: int | None = None


@_dataclasses.dataclass(frozen=True, slots=True)
class TemplateNode:
    """Base class for all template nodes.

    Template nodes are treated as immutable. The renderer does not mutate nodes at runtime.
    """

    mark: SourceMark | None = None

    # Important: do not allow TemplateNode objects to become usable as dict keys.
    # ydst intentionally forbids templated keys in mappings.
    __hash__ = None  # type: ignore[assignment]


def iter_template_node_items(node: TemplateNode) -> _abc.Iterator[tuple[str, _typing.Any]]:
    """Yield (field_name, value) for a TemplateNode.

    We use dataclass fields instead of `__dict__` so nodes can be `slots=True`.
    """

    for f in _dataclasses.fields(node):
        yield f.name, getattr(node, f.name)


@_dataclasses.dataclass(frozen=True, slots=True)
class Omit(TemplateNode):
    """A sentinel node that removes a key or list item from the rendered output."""

    __hash__ = None  # type: ignore[assignment]

    def __bool__(self) -> bool:  # pragma: no cover
        # Treat OMIT as falsy so it behaves naturally in conditionals (e.g. !if, !foreach when).
        return False


# Public singleton sentinel used by the renderer.
#
# IMPORTANT: this represents "omit" *in the rendered output*. It is not the same as
# "no default provided". Use UNSET for the latter.
OMIT = Omit()


# Public singleton sentinel representing "no default provided".
#
# This is distinct from OMIT so programmatic users can express:
#   - default omitted / unspecified -> UNSET
#   - default explicitly omit output -> OMIT (or Omit(...))
UNSET: _typing.Any = object()


@_dataclasses.dataclass(frozen=True, slots=True)
class Var(TemplateNode):
    """Variable substitution.

    YAML forms:
      - !var NAME
      - !var {name: NAME, default: <template>, required: true|false}

    Default handling:
      - if the variable is missing and `default` is UNSET, the value is `None`
      - if the variable is missing and `default` is OMIT / !omit, the key/item is omitted
    """

    __hash__ = None  # type: ignore[assignment]

    name: str = ""
    default: _typing.Any = _dataclasses.field(default_factory=lambda: UNSET)
    required: bool = True


@_dataclasses.dataclass(frozen=True, slots=True)
class Default(TemplateNode):
    """Coalesce / fallback.

    YAML forms:
      - !default {value: <template>, default: <template>}
      - !default [<value>, <default>]

    Semantics
    ---------
    Render `value`. If it:
      - raises a MissingVariableError / IncludeError during rendering, or
      - renders to None (when `treat_none_as_missing=True`), or
      - renders to !omit/OMIT (when `treat_omit_as_missing=True`)

    then render and return `default` instead.

    Notes
    -----
    This is designed for ergonomic composition; it is not an error-handling sandbox.
    """

    __hash__ = None  # type: ignore[assignment]

    value: _typing.Any = None
    default: _typing.Any = _dataclasses.field(default_factory=lambda: UNSET)
    treat_none_as_missing: bool = True
    treat_omit_as_missing: bool = True


@_dataclasses.dataclass(frozen=True, slots=True)
class If(TemplateNode):
    """Conditional selection.

    YAML form:
      !if {test: <template>, then: <template>, else: <template?>}

    If `else` is omitted, it defaults to !omit.
    """

    __hash__ = None  # type: ignore[assignment]

    test: _typing.Any = None
    then: _typing.Any = None
    else_: _typing.Any = _dataclasses.field(default_factory=lambda: OMIT)


@_dataclasses.dataclass(frozen=True, slots=True)
class ForEach(TemplateNode):
    """Iteration / collection generation.

    List form (default):
      !foreach {var: x, in: <template>, template: <template>, when: <template?>, index: i?}

    Dict form:
      !foreach {var: x, in: <template>, into: dict, key: <template>, value: <template>}

    Set form:
      !foreach {var: x, in: <template>, into: set, template: <template>}
    """

    __hash__ = None  # type: ignore[assignment]

    var: str = "item"
    in_: _typing.Any = None
    # Presence-sensitive. Use UNSET to represent "missing" so programmatic construction
    # can be validated consistently with YAML-loaded templates.
    template: _typing.Any = _dataclasses.field(default_factory=lambda: UNSET)

    # Optional additions
    index: str | None = None
    when: _typing.Any = None

    # Output target: "list" (default), "dict", "set"
    into: str = "list"

    # Dict output fields
    key: _typing.Any = _dataclasses.field(default_factory=lambda: UNSET)
    value: _typing.Any = _dataclasses.field(default_factory=lambda: UNSET)


@_dataclasses.dataclass(frozen=True, slots=True)
class Expr(TemplateNode):
    """Expression evaluation.

    YAML forms:
      - !expr "x + 1"
      - !expr {expr: "x + 1", strict: true|false, default: <template?>}

    Expressions are evaluated by an AST-based evaluator; this is not a sandbox.

    Default handling mirrors !var:
      - if a name is missing and `default` is UNSET, the value is `None` (when strict is false)
      - if `default` is OMIT / !omit, the key/item is omitted
    """

    __hash__ = None  # type: ignore[assignment]

    expr: str = ""
    strict: bool = True
    default: _typing.Any = _dataclasses.field(default_factory=lambda: UNSET)


@_dataclasses.dataclass(frozen=True, slots=True)
class Call(TemplateNode):
    """Call a named function from a registry.

    YAML forms:
      - !call fn_name
      - !call {fn: fn_name, args: [...], kwargs: {...}}

    `fn` may itself be templated; it is rendered to a string at runtime.
    """

    __hash__ = None  # type: ignore[assignment]

    fn: _typing.Any = ""
    args: list[_typing.Any] = _dataclasses.field(default_factory=list)
    kwargs: dict[str, _typing.Any] = _dataclasses.field(default_factory=dict)


@_dataclasses.dataclass(frozen=True, slots=True)
class Pipe(TemplateNode):
    """Pipeline composition.

    YAML form:
      !pipe [<stage1>, <stage2>, ...]

    Semantics:
      - stage 0 is rendered to a value
      - subsequent stages are applied to the current value
        * if the stage is a `!call` node, it is invoked with the current value as the first arg
        * if the stage renders to a string and `allow_pipe_registry_calls=True`, we attempt to
          resolve a registry function with that name and call it
        * if the stage renders to a callable and `allow_callable_pipe_stages=True`, we call it
          with the current value
        * otherwise the stage result becomes the new value

    Notes
    -----
    - By default, unknown string stages raise an error (`RenderOptions.strict_pipe_stages=True`).
      If you want the older "unknown strings become literal" behavior, set
      `RenderOptions.strict_pipe_stages=False`.
    - By default, stages that render to arbitrary Python callables are *not* invoked.
      Enable this with `RenderOptions(allow_callable_pipe_stages=True)` if you need it.
    """

    __hash__ = None  # type: ignore[assignment]

    steps: list[_typing.Any] = _dataclasses.field(default_factory=list)


@_dataclasses.dataclass(frozen=True, slots=True)
class IncludeRuntime(TemplateNode):
    """Render-time include.

    YAML forms:
      - !include_rt "other.yaml"
      - !include_rt {target: <template>, required: true|false, default: <template?>}

    The `target` is rendered at runtime to a string and resolved via an IncludeResolver.
    """

    __hash__ = None  # type: ignore[assignment]

    target: _typing.Any = ""
    required: bool = True
    default: _typing.Any = _dataclasses.field(default_factory=lambda: UNSET)


@_dataclasses.dataclass(frozen=True, slots=True)
class SetDefault(TemplateNode):
    """Set default variables for the remainder of a render.

    `!setdefault` is a side-effecting tag intended for templates that want to
    provide defaults for optional context values.

    YAML forms:
      - !setdefault [name, value]
      - !setdefault {name: NAME, value: <template>}  # or {name: NAME, default: <template>}
      - !setdefault {var1: <template>, var2: <template>, ...}

    Rendering semantics:
      - For each entry, if the name is not already present in scope, the value is
        rendered and assigned into the template-local scope.
      - The node itself renders to OMIT (so it can be used as "bookkeeping" without
        appearing in output).

    This tag is always enabled (it cannot override caller-provided context values).
    """

    __hash__ = None  # type: ignore[assignment]

    defaults: dict[str, _typing.Any] = _dataclasses.field(default_factory=dict)


@_dataclasses.dataclass(frozen=True, slots=True)
class Python(TemplateNode):
    """Execute a trusted Python snippet and emit a value.

    YAML forms:
      - !python |\n          # code
      - !python {code: "...", strict_emit: true|false}

    Semantics:
      - The snippet is executed at render time.
      - Use `emit(value)` to provide the node's value and terminate execution.
      - If `emit()` is not called and strict emit is disabled, the value of the
        final expression statement is used (or `None` if there is no final expression).

    This tag is disabled by default; enable it with `RenderOptions(allow_python=True)`.
    """

    __hash__ = None  # type: ignore[assignment]

    code: str = ""
    strict_emit: bool | None = None


@_dataclasses.dataclass(frozen=True, slots=True)
class PythonModule(TemplateNode):
    """Execute a trusted Python snippet to define reusable helpers.

    YAML forms:
      - !python_module |\n          # code
      - !python_module {code: "..."}

    Semantics:
      - Executed at render time.
      - Definitions made in the module scope are shared across subsequent `!python`
        nodes within the same render invocation.
      - The node always renders to OMIT.

    This tag is disabled by default; enable it with `RenderOptions(allow_python_module=True)`.
    """

    __hash__ = None  # type: ignore[assignment]

    code: str = ""
