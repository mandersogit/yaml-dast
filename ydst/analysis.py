from __future__ import annotations

import collections.abc as _abc
import dataclasses as _dataclasses
import typing as _typing

import ydst.nodes as nodes
import ydst.registry as registry_mod

if _typing.TYPE_CHECKING:
    import ydst.template as _template_mod


def collect_variables(template: _template_mod.Template) -> set[str]:
    """Collect variable names referenced by !var nodes."""
    out: set[str] = set()

    def walk(x: _typing.Any) -> None:
        if isinstance(x, nodes.Var):
            out.add(x.name)
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

    walk(template.root)
    return out


def collect_required_variables(template: _template_mod.Template) -> set[str]:
    """Collect variable names that have no default (must be provided in context)."""
    required: set[str] = set()
    has_default: set[str] = set()

    def walk(x: _typing.Any) -> None:
        if isinstance(x, nodes.Var):
            if x.default is nodes.UNSET:
                required.add(x.name)
            else:
                has_default.add(x.name)
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

    walk(template.root)
    # A variable is required only if it appears without a default
    # and never appears with a default elsewhere
    return required - has_default


def collect_expressions(template: _template_mod.Template) -> set[str]:
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

    walk(template.root)
    return out


def collect_calls(template: _template_mod.Template) -> set[str]:
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

    walk(template.root)
    return out


def collect_includes(template: _template_mod.Template) -> set[str]:
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

    walk(template.root)
    return out


def collect_pipe_stage_strings(template: _template_mod.Template) -> set[str]:
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

    walk(template.root)
    return out


def collect_setdefault_names(template: _template_mod.Template) -> set[str]:
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

    walk(template.root)
    return out


def count_python_blocks(template: _template_mod.Template) -> tuple[int, int]:
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

    walk(template.root)
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


def analyze_dependencies(
    template: _template_mod.Template,
    *,
    registry: registry_mod.FunctionRegistry | None = None,
) -> Dependencies:
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

    walk_dyn(template.root)

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


# -----------------------------------------------------------------------------
# Single-pass comprehensive analysis
# -----------------------------------------------------------------------------


@_dataclasses.dataclass(frozen=True, slots=True)
class FullAnalysis:
    """Comprehensive template analysis from a single tree traversal.

    More efficient than calling individual analysis functions when you need
    multiple pieces of analysis data. All fields are populated in one pass.
    """

    @classmethod
    def from_template(cls, template: _template_mod.Template) -> FullAnalysis:
        """Create a FullAnalysis from a template (convenience constructor)."""
        return full_analysis(template)

    # Variable analysis
    variables: set[str]
    required_variables: set[str]
    variables_with_defaults: set[str]
    variable_usage_counts: dict[str, int]

    # Expression analysis
    expressions: set[str]
    if_conditions: set[str]

    # Call analysis
    calls: set[str]
    dynamic_call_count: int
    has_dynamic_calls: bool

    # Include analysis
    includes_rt: set[str]
    dynamic_include_count: int
    has_dynamic_includes: bool

    # Pipe analysis
    pipe_stage_strings: set[str]

    # Setdefault analysis
    setdefault_names: set[str]

    # Python analysis
    python_block_count: int
    python_module_count: int

    # Loop analysis
    foreach_vars: set[str]
    foreach_index_vars: set[str]

    # Structure metrics
    node_counts: dict[str, int]
    total_template_nodes: int
    max_depth: int


def full_analysis(template: _template_mod.Template) -> FullAnalysis:
    """Perform comprehensive template analysis in a single tree traversal.

    This is more efficient than calling individual analysis functions when
    you need multiple pieces of information about a template.

    Example:
        tmpl = ydst.Template.from_path("config.yaml")
        analysis = ydst.analysis.full_analysis(tmpl)
        print(f"Variables: {analysis.variables}")
        print(f"Max depth: {analysis.max_depth}")
        print(f"Node counts: {analysis.node_counts}")
    """
    # Accumulators
    variables: set[str] = set()
    required_variables: set[str] = set()
    variables_with_defaults: set[str] = set()
    variable_usage_counts: dict[str, int] = {}

    expressions: set[str] = set()
    if_conditions: set[str] = set()

    calls: set[str] = set()
    dynamic_call_count = 0

    includes: set[str] = set()
    dynamic_include_count = 0

    pipe_stage_strings: set[str] = set()
    setdefault_names: set[str] = set()

    python_count = 0
    python_module_count = 0

    foreach_vars: set[str] = set()
    foreach_index_vars: set[str] = set()

    node_counts: dict[str, int] = {}
    total_template_nodes = 0
    max_depth = 0

    def walk(x: _typing.Any, depth: int) -> None:
        nonlocal dynamic_call_count, dynamic_include_count
        nonlocal python_count, python_module_count
        nonlocal total_template_nodes, max_depth

        if depth > max_depth:
            max_depth = depth

        # Handle template nodes
        if isinstance(x, nodes.TemplateNode):
            total_template_nodes += 1
            node_type = x.__class__.__name__
            node_counts[node_type] = node_counts.get(node_type, 0) + 1

            # Node-specific collection
            if isinstance(x, nodes.Var):
                variables.add(x.name)
                variable_usage_counts[x.name] = variable_usage_counts.get(x.name, 0) + 1
                if x.default is nodes.UNSET:
                    required_variables.add(x.name)
                else:
                    variables_with_defaults.add(x.name)
                    walk(x.default, depth + 1)
                return

            if isinstance(x, nodes.Expr):
                expressions.add(x.expr)
                if x.default is not nodes.UNSET:
                    walk(x.default, depth + 1)
                return

            if isinstance(x, nodes.If):
                if isinstance(x.test, str):
                    if_conditions.add(x.test)
                else:
                    walk(x.test, depth + 1)
                walk(x.then, depth + 1)
                if x.else_ is not nodes.UNSET:
                    walk(x.else_, depth + 1)
                return

            if isinstance(x, nodes.Call):
                if isinstance(x.fn, str) and x.fn:
                    calls.add(x.fn)
                else:
                    dynamic_call_count += 1
                walk(x.fn, depth + 1)
                for a in x.args:
                    walk(a, depth + 1)
                for v in x.kwargs.values():
                    walk(v, depth + 1)
                return

            if isinstance(x, nodes.IncludeRuntime):
                if isinstance(x.target, str) and x.target:
                    includes.add(x.target)
                else:
                    dynamic_include_count += 1
                walk(x.target, depth + 1)
                if x.default is not nodes.UNSET:
                    walk(x.default, depth + 1)
                return

            if isinstance(x, nodes.Pipe):
                for s in x.steps:
                    if isinstance(s, str):
                        pipe_stage_strings.add(s)
                    walk(s, depth + 1)
                return

            if isinstance(x, nodes.SetDefault):
                setdefault_names.update(x.defaults.keys())
                for v in x.defaults.values():
                    walk(v, depth + 1)
                return

            if isinstance(x, nodes.Python):
                python_count += 1
                return

            if isinstance(x, nodes.PythonModule):
                python_module_count += 1
                return

            if isinstance(x, nodes.ForEach):
                if isinstance(x.var, str):
                    foreach_vars.add(x.var)
                if isinstance(x.index, str):
                    foreach_index_vars.add(x.index)
                # Walk all fields
                for _, v in nodes.iter_template_node_items(x):
                    walk(v, depth + 1)
                return

            # Generic template node - walk all fields
            for _, v in nodes.iter_template_node_items(x):
                walk(v, depth + 1)
            return

        # Handle containers
        if isinstance(x, _abc.Mapping):
            for k, v in x.items():
                walk(k, depth + 1)
                walk(v, depth + 1)
            return

        if isinstance(x, (set, frozenset)):
            for v in x:
                walk(v, depth + 1)
            return

        if isinstance(x, _abc.Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for v in x:
                walk(v, depth + 1)
            return

    walk(template.root, 0)

    # Post-process: required = those without defaults anywhere
    final_required = required_variables - variables_with_defaults

    return FullAnalysis(
        variables=variables,
        required_variables=final_required,
        variables_with_defaults=variables_with_defaults,
        variable_usage_counts=variable_usage_counts,
        expressions=expressions,
        if_conditions=if_conditions,
        calls=calls,
        dynamic_call_count=dynamic_call_count,
        has_dynamic_calls=dynamic_call_count > 0,
        includes_rt=includes,
        dynamic_include_count=dynamic_include_count,
        has_dynamic_includes=dynamic_include_count > 0,
        pipe_stage_strings=pipe_stage_strings,
        setdefault_names=setdefault_names,
        python_block_count=python_count,
        python_module_count=python_module_count,
        foreach_vars=foreach_vars,
        foreach_index_vars=foreach_index_vars,
        node_counts=node_counts,
        total_template_nodes=total_template_nodes,
        max_depth=max_depth,
    )
