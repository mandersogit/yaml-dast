from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Optional, Set

from .nodes import Call, Expr, IncludeRuntime, Pipe, TemplateNode, Var, UNSET
from .registry import FunctionRegistry
from .validate import collect_variables


def collect_expressions(template: Any) -> Set[str]:
    """Collect expression strings referenced by !expr nodes."""

    out: Set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, Expr):
            out.add(x.expr)
            if x.default is not UNSET:
                walk(x.default)
            return
        if isinstance(x, TemplateNode):
            for v in x.__dict__.values():
                walk(v)
            return
        if isinstance(x, Mapping):
            for k, v in x.items():
                walk(k)
                walk(v)
            return
        if isinstance(x, (set, frozenset)):
            for v in x:
                walk(v)
            return
        if isinstance(x, Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk(v)
            return

    walk(template)
    return out


def collect_calls(template: Any) -> Set[str]:
    """Collect explicitly named registry function calls.

    This collects `!call` nodes whose `fn` is a literal string.

    Note: this does not attempt to infer which `!pipe` string stages will call the registry
    at runtime, since that depends on the registry.
    """

    out: Set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, Call):
            if isinstance(x.fn, str) and x.fn:
                out.add(x.fn)
            # Walk into subtrees in case `fn` is templated or args contain nodes.
            walk(x.fn)
            for a in x.args:
                walk(a)
            for v in x.kwargs.values():
                walk(v)
            return
        if isinstance(x, TemplateNode):
            for v in x.__dict__.values():
                walk(v)
            return
        if isinstance(x, Mapping):
            for k, v in x.items():
                walk(k)
                walk(v)
            return
        if isinstance(x, (set, frozenset)):
            for v in x:
                walk(v)
            return
        if isinstance(x, Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk(v)
            return

    walk(template)
    return out


def collect_includes(template: Any) -> Set[str]:
    """Collect render-time include targets that are literal strings."""

    out: Set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, IncludeRuntime):
            if isinstance(x.target, str) and x.target:
                out.add(x.target)
            walk(x.target)
            if x.default is not UNSET:
                walk(x.default)
            return
        if isinstance(x, TemplateNode):
            for v in x.__dict__.values():
                walk(v)
            return
        if isinstance(x, Mapping):
            for k, v in x.items():
                walk(k)
                walk(v)
            return
        if isinstance(x, (set, frozenset)):
            for v in x:
                walk(v)
            return
        if isinstance(x, Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk(v)
            return

    walk(template)
    return out


def collect_pipe_stage_strings(template: Any) -> Set[str]:
    """Collect literal string stages used in !pipe nodes.

    These strings *may* correspond to registry functions (depending on `registry` and render options).
    """

    out: Set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, Pipe):
            for s in x.steps:
                if isinstance(s, str):
                    out.add(s)
                walk(s)
            return
        if isinstance(x, TemplateNode):
            for v in x.__dict__.values():
                walk(v)
            return
        if isinstance(x, Mapping):
            for k, v in x.items():
                walk(k)
                walk(v)
            return
        if isinstance(x, (set, frozenset)):
            for v in x:
                walk(v)
            return
        if isinstance(x, Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk(v)
            return

    walk(template)
    return out



@dataclass(frozen=True)
class Dependencies:
    """A coarse static dependency summary for a template graph."""

    variables: Set[str]
    expressions: Set[str]
    calls: Set[str]
    includes_rt: Set[str]
    pipe_stage_strings: Set[str]
    pipe_registry_functions: Set[str]
    has_dynamic_calls: bool
    has_dynamic_includes: bool


def analyze_dependencies(template: Any, *, registry: Optional[FunctionRegistry] = None) -> Dependencies:
    """Analyze a template graph and return a coarse dependency summary.

    Parameters
    ----------
    registry:
        If provided, `pipe_registry_functions` will include those `!pipe` string stages
        that resolve to callables in the registry.
    """

    vars_ = collect_variables(template)
    exprs = collect_expressions(template)
    calls = collect_calls(template)
    includes = collect_includes(template)
    pipe_strings = collect_pipe_stage_strings(template)

    # Detect dynamic patterns conservatively.
    has_dynamic_calls = False
    has_dynamic_includes = False

    def walk_dyn(x: Any) -> None:
        nonlocal has_dynamic_calls, has_dynamic_includes
        if isinstance(x, Call):
            if not (isinstance(x.fn, str) and x.fn):
                has_dynamic_calls = True
            walk_dyn(x.fn)
            for a in x.args:
                walk_dyn(a)
            for v in x.kwargs.values():
                walk_dyn(v)
            return
        if isinstance(x, IncludeRuntime):
            if not (isinstance(x.target, str) and x.target):
                has_dynamic_includes = True
            walk_dyn(x.target)
            if x.default is not UNSET:
                walk_dyn(x.default)
            return
        if isinstance(x, TemplateNode):
            for v in x.__dict__.values():
                walk_dyn(v)
            return
        if isinstance(x, Mapping):
            for k, v in x.items():
                walk_dyn(k)
                walk_dyn(v)
            return
        if isinstance(x, (set, frozenset)):
            for v in x:
                walk_dyn(v)
            return
        if isinstance(x, Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk_dyn(v)
            return

    walk_dyn(template)

    pipe_registry_functions: Set[str] = set()
    if registry is not None:
        for s in pipe_strings:
            fn = registry.get(s) if hasattr(registry, "get") else None
            if fn is not None and callable(fn):
                pipe_registry_functions.add(s)

    return Dependencies(
        variables=vars_,
        expressions=exprs,
        calls=calls,
        includes_rt=includes,
        pipe_stage_strings=pipe_strings,
        pipe_registry_functions=pipe_registry_functions,
        has_dynamic_calls=has_dynamic_calls,
        has_dynamic_includes=has_dynamic_includes,
    )
