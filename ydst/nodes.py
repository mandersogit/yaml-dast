from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


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

    pass


# Public singleton sentinel used by the renderer.
OMIT = Omit()


@dataclass
class Var(TemplateNode):
    """Variable substitution.

    YAML forms:
      - !var NAME
      - !var {name: NAME, default: <template>, required: true|false}
    """

    name: str = ""
    default: Any = field(default_factory=lambda: OMIT)
    required: bool = True


@dataclass
class If(TemplateNode):
    """Conditional selection.

    YAML form:
      !if {test: <template>, then: <template>, else: <template?>}
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
    """

    expr: str = ""
    strict: bool = True
    default: Any = field(default_factory=lambda: OMIT)

    # Internal cache (filled by loader/validator) - do not rely on this field externally.
    _compiled: Any = field(default=None, repr=False, compare=False)


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
        * if stage renders to a string and registry contains such a function, call it with current value
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
    default: Any = field(default_factory=lambda: OMIT)
