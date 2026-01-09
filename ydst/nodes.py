from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Iterator, Optional


@dataclass(frozen=True, slots=True)
class SourceMark:
    """Source location information for a YAML node.

    Line/column are 1-based for human readability (matching most editor conventions).
    """

    source: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None


@dataclass(frozen=True, slots=True)
class TemplateNode:
    """Base class for all template nodes.

    Template nodes are treated as immutable. The renderer does not mutate nodes at runtime.
    """

    mark: Optional[SourceMark] = None

    # Important: do not allow TemplateNode objects to become usable as dict keys.
    # ydst intentionally forbids templated keys in mappings.
    __hash__ = None


def iter_template_node_items(node: TemplateNode) -> Iterator[tuple[str, Any]]:
    """Yield (field_name, value) for a TemplateNode.

    We use dataclass fields instead of `__dict__` so nodes can be `slots=True`.
    """

    for f in fields(node):
        yield f.name, getattr(node, f.name)


@dataclass(frozen=True, slots=True)
class Omit(TemplateNode):
    """A sentinel node that removes a key or list item from the rendered output."""

    __hash__ = None

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
UNSET: Any = object()


@dataclass(frozen=True, slots=True)
class Var(TemplateNode):
    """Variable substitution.

    YAML forms:
      - !var NAME
      - !var {name: NAME, default: <template>, required: true|false}

    Default handling:
      - if the variable is missing and `default` is UNSET, the value is `None`
      - if the variable is missing and `default` is OMIT / !omit, the key/item is omitted
    """

    __hash__ = None

    name: str = ""
    default: Any = field(default_factory=lambda: UNSET)
    required: bool = True


@dataclass(frozen=True, slots=True)
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

    __hash__ = None

    value: Any = None
    default: Any = field(default_factory=lambda: UNSET)
    treat_none_as_missing: bool = True
    treat_omit_as_missing: bool = True


@dataclass(frozen=True, slots=True)
class If(TemplateNode):
    """Conditional selection.

    YAML form:
      !if {test: <template>, then: <template>, else: <template?>}

    If `else` is omitted, it defaults to !omit.
    """

    __hash__ = None

    test: Any = None
    then: Any = None
    else_: Any = field(default_factory=lambda: OMIT)


@dataclass(frozen=True, slots=True)
class ForEach(TemplateNode):
    """Iteration / collection generation.

    List form (default):
      !foreach {var: x, in: <template>, template: <template>, when: <template?>, index: i?}

    Dict form:
      !foreach {var: x, in: <template>, into: dict, key: <template>, value: <template>}

    Set form:
      !foreach {var: x, in: <template>, into: set, template: <template>}
    """

    __hash__ = None

    var: str = "item"
    in_: Any = None
    template: Any = None

    # Optional additions
    index: Optional[str] = None
    when: Any = None

    # Output target: "list" (default), "dict", "set"
    into: str = "list"

    # Dict output fields
    key: Any = None
    value: Any = None


@dataclass(frozen=True, slots=True)
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

    __hash__ = None

    expr: str = ""
    strict: bool = True
    default: Any = field(default_factory=lambda: UNSET)


@dataclass(frozen=True, slots=True)
class Call(TemplateNode):
    """Call a named function from a registry.

    YAML forms:
      - !call fn_name
      - !call {fn: fn_name, args: [...], kwargs: {...}}

    `fn` may itself be templated; it is rendered to a string at runtime.
    """

    __hash__ = None

    fn: Any = ""
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
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

    __hash__ = None

    steps: list[Any] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class IncludeRuntime(TemplateNode):
    """Render-time include.

    YAML forms:
      - !include_rt "other.yaml"
      - !include_rt {target: <template>, required: true|false, default: <template?>}

    The `target` is rendered at runtime to a string and resolved via an IncludeResolver.
    """

    __hash__ = None

    target: Any = ""
    required: bool = True
    default: Any = field(default_factory=lambda: UNSET)
