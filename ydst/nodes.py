from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SourceMark:
    """Source location information for a YAML node.

    Line/column are 1-based for human readability (matching most editor conventions).
    """

    source: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None


@dataclass
class TemplateNode:
    """Base class for all template nodes."""

    mark: Optional[SourceMark] = None


@dataclass
class Omit(TemplateNode):
    """A sentinel node that removes a key or list item from the rendered output."""

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


@dataclass
class Var(TemplateNode):
    """Variable substitution.

    YAML forms:
      - !var NAME
      - !var {name: NAME, default: <template>, required: true|false}

    Default handling:
      - if the variable is missing and `default` is UNSET, the value is `None`
      - if the variable is missing and `default` is OMIT / !omit, the key/item is omitted
    """

    name: str = ""
    default: Any = field(default_factory=lambda: UNSET)
    required: bool = True


@dataclass
class If(TemplateNode):
    """Conditional selection.

    YAML form:
      !if {test: <template>, then: <template>, else: <template?>}

    If `else` is omitted, it defaults to !omit.
    """

    test: Any = None
    then: Any = None
    else_: Any = field(default_factory=lambda: OMIT)


@dataclass
class ForEach(TemplateNode):
    """Iteration / collection generation.

    List form (default):
      !foreach {var: x, in: <template>, template: <template>, when: <template?>, index: i?}

    Dict form:
      !foreach {var: x, in: <template>, into: dict, key: <template>, value: <template>}

    Set form:
      !foreach {var: x, in: <template>, into: set, template: <template>}
    """

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


@dataclass
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

    expr: str = ""
    strict: bool = True
    default: Any = field(default_factory=lambda: UNSET)


@dataclass
class Call(TemplateNode):
    """Call a named function from a registry.

    YAML forms:
      - !call fn_name
      - !call {fn: fn_name, args: [...], kwargs: {...}}

    `fn` may itself be templated; it is rendered to a string at runtime.
    """

    fn: Any = ""
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Pipe(TemplateNode):
    """Pipeline composition.

    YAML form:
      !pipe [<stage1>, <stage2>, ...]

    Semantics:
      - first stage is rendered to a value
      - subsequent stages are applied to the current value
        * if stage is a Call node, it is invoked with the current value as the first arg
        * if stage renders to a string and the registry contains a callable with that name,
          call it with the current value
        * otherwise the stage result becomes the new value (a pass-through value)

    Note
    ----
    By default, stages that render to arbitrary Python callables are *not* invoked.
    Enable this with RenderOptions(allow_callable_pipe_stages=True) if you need it.
    """

    steps: list[Any] = field(default_factory=list)


@dataclass
class IncludeRuntime(TemplateNode):
    """Render-time include.

    YAML forms:
      - !include_rt "other.yaml"
      - !include_rt {target: <template>, required: true|false, default: <template?>}

    The `target` is rendered at runtime to a string and resolved via an IncludeResolver.
    """

    target: Any = ""
    required: bool = True
    default: Any = field(default_factory=lambda: UNSET)
