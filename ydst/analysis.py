from __future__ import annotations

import collections.abc as _abc
import dataclasses as _dataclasses
import typing as _typing

import ydst.nodes as nodes
import ydst.registry as registry_mod
import ydst.validate as validate_mod


def collect_expressions(template: _typing.Any) -> set[str]:
    """Collect expression strings referenced by !expr nodes."""

    out: set[str] = set()

    def walk(x: _typing.Any) -> None:
        if isinstance(x, nodes.Expr):
            out.add(x.expr)
            if x.default is not nodes.UNSET:
                walk(x.default)
            return
        if isinstance(x, nodes.TemplateNode):
            for _, v in nodes.iter_template_node_items(x):
                walk(v)
            return
        if isinstance(x, _abc.Mapping):
            for k, v in x.items():
                walk(k)
                walk(v)
            return
        if isinstance(x, (set, frozenset)):
            for v in x:
                walk(v)
            return
        if isinstance(x, _abc.Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk(v)
            return

    walk(template)
    return out


def collect_calls(template: _typing.Any) -> set[str]:
    """Collect explicitly named registry function calls.

    This collects `!call` nodes whose `fn` is a literal string.

    Note: this does not attempt to infer which `!pipe` string stages will call the registry
    at runtime, since that depends on the registry and render options.
    """

    out: set[str] = set()

    def walk(x: _typing.Any) -> None:
        if isinstance(x, nodes.Call):
            if isinstance(x.fn, str) and x.fn:
                out.add(x.fn)
            # Walk into subtrees in case `fn` is templated or args contain nodes.
            walk(x.fn)
            for a in x.args:
                walk(a)
            for v in x.kwargs.values():
                walk(v)
            return
        if isinstance(x, nodes.TemplateNode):
            for _, v in nodes.iter_template_node_items(x):
                walk(v)
            return
        if isinstance(x, _abc.Mapping):
            for k, v in x.items():
                walk(k)
                walk(v)
            return
        if isinstance(x, (set, frozenset)):
            for v in x:
                walk(v)
            return
        if isinstance(x, _abc.Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk(v)
            return

    walk(template)
    return out


def collect_includes(template: _typing.Any) -> set[str]:
    """Collect render-time include targets that are literal strings."""

    out: set[str] = set()

    def walk(x: _typing.Any) -> None:
        if isinstance(x, nodes.IncludeRuntime):
            if isinstance(x.target, str) and x.target:
                out.add(x.target)
            walk(x.target)
            if x.default is not nodes.UNSET:
                walk(x.default)
            return
        if isinstance(x, nodes.TemplateNode):
            for _, v in nodes.iter_template_node_items(x):
                walk(v)
            return
        if isinstance(x, _abc.Mapping):
            for k, v in x.items():
                walk(k)
                walk(v)
            return
        if isinstance(x, (set, frozenset)):
            for v in x:
                walk(v)
            return
        if isinstance(x, _abc.Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk(v)
            return

    walk(template)
    return out


def collect_pipe_stage_strings(template: _typing.Any) -> set[str]:
    """Collect literal string stages used in !pipe nodes.

    These strings *may* correspond to registry functions (depending on `registry` and render options).
    """

    out: set[str] = set()

    def walk(x: _typing.Any) -> None:
        if isinstance(x, nodes.Pipe):
            for s in x.steps:
                if isinstance(s, str):
                    out.add(s)
                walk(s)
            return
        if isinstance(x, nodes.TemplateNode):
            for _, v in nodes.iter_template_node_items(x):
                walk(v)
            return
        if isinstance(x, _abc.Mapping):
            for k, v in x.items():
                walk(k)
                walk(v)
            return
        if isinstance(x, (set, frozenset)):
            for v in x:
                walk(v)
            return
        if isinstance(x, _abc.Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk(v)
            return

    walk(template)
    return out


def collect_setdefault_names(template: _typing.Any) -> set[str]:
    """Collect variable names established via `!setdefault`."""

    out: set[str] = set()

    def walk(x: _typing.Any) -> None:
        if isinstance(x, nodes.SetDefault):
            out.update(x.defaults.keys())
            for v in x.defaults.values():
                walk(v)
            return
        if isinstance(x, nodes.TemplateNode):
            for _, v in nodes.iter_template_node_items(x):
                walk(v)
            return
        if isinstance(x, _abc.Mapping):
            for k, v in x.items():
                walk(k)
                walk(v)
            return
        if isinstance(x, (set, frozenset)):
            for v in x:
                walk(v)
            return
        if isinstance(x, _abc.Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk(v)
            return

    walk(template)
    return out


def count_python_blocks(template: _typing.Any) -> tuple[int, int]:
    """Return (python_count, python_module_count)."""

    python_count = 0
    python_module_count = 0

    def walk(x: _typing.Any) -> None:
        nonlocal python_count, python_module_count
        if isinstance(x, nodes.Python):
            python_count += 1
            return
        if isinstance(x, nodes.PythonModule):
            python_module_count += 1
            return
        if isinstance(x, nodes.TemplateNode):
            for _, v in nodes.iter_template_node_items(x):
                walk(v)
            return
        if isinstance(x, _abc.Mapping):
            for k, v in x.items():
                walk(k)
                walk(v)
            return
        if isinstance(x, (set, frozenset)):
            for v in x:
                walk(v)
            return
        if isinstance(x, _abc.Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk(v)
            return

    walk(template)
    return python_count, python_module_count


@_dataclasses.dataclass(frozen=True, slots=True)
class Dependencies:
    """A coarse static dependency summary for a template graph."""

    variables: set[str]
    expressions: set[str]
    calls: set[str]
    includes_rt: set[str]
    pipe_stage_strings: set[str]
    pipe_registry_functions: set[str]

    # Opt-in power tags
    setdefault_names: set[str]
    python_block_count: int
    python_module_count: int

    has_dynamic_calls: bool
    has_dynamic_includes: bool


def analyze_dependencies(template: _typing.Any, *, registry: registry_mod.FunctionRegistry | None = None) -> Dependencies:
    """Analyze a template graph and return a coarse dependency summary.

    Parameters
    ----------
    registry:
        If provided, `pipe_registry_functions` will include those `!pipe` string stages
        that resolve to callables in the registry.
    """

    vars_ = validate_mod.collect_variables(template)
    exprs = collect_expressions(template)
    calls = collect_calls(template)
    includes = collect_includes(template)
    pipe_strings = collect_pipe_stage_strings(template)
    setdefault_names = collect_setdefault_names(template)
    python_count, python_module_count = count_python_blocks(template)

    # Detect dynamic patterns conservatively.
    has_dynamic_calls = False
    has_dynamic_includes = False

    def walk_dyn(x: _typing.Any) -> None:
        nonlocal has_dynamic_calls, has_dynamic_includes
        if isinstance(x, nodes.Call):
            if not (isinstance(x.fn, str) and x.fn):
                has_dynamic_calls = True
            walk_dyn(x.fn)
            for a in x.args:
                walk_dyn(a)
            for v in x.kwargs.values():
                walk_dyn(v)
            return
        if isinstance(x, nodes.IncludeRuntime):
            if not (isinstance(x.target, str) and x.target):
                has_dynamic_includes = True
            walk_dyn(x.target)
            if x.default is not nodes.UNSET:
                walk_dyn(x.default)
            return
        if isinstance(x, nodes.TemplateNode):
            for _, v in nodes.iter_template_node_items(x):
                walk_dyn(v)
            return
        if isinstance(x, _abc.Mapping):
            for k, v in x.items():
                walk_dyn(k)
                walk_dyn(v)
            return
        if isinstance(x, (set, frozenset)):
            for v in x:
                walk_dyn(v)
            return
        if isinstance(x, _abc.Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk_dyn(v)
            return

    walk_dyn(template)

    pipe_registry_functions: set[str] = set()
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
        setdefault_names=setdefault_names,
        python_block_count=python_count,
        python_module_count=python_module_count,
        has_dynamic_calls=has_dynamic_calls,
        has_dynamic_includes=has_dynamic_includes,
    )
