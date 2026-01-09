from __future__ import annotations

import ast as _ast
import collections as _collections
import collections.abc as _abc
import dataclasses as _dataclasses
import typing as _typing

import ydst.errors as errors
import ydst.expr as expr_mod
import ydst.include as include_mod
import ydst.nodes as nodes
import ydst.registry as registry_mod

# Local aliases for readability (no `from ... import ...`).
ChainMap = _collections.ChainMap
OrderedDict = _collections.OrderedDict

TemplateNode = nodes.TemplateNode
Omit = nodes.Omit
OMIT = nodes.OMIT
UNSET = nodes.UNSET

Var = nodes.Var
Default = nodes.Default
If = nodes.If
ForEach = nodes.ForEach
Expr = nodes.Expr
Call = nodes.Call
Pipe = nodes.Pipe
IncludeRuntime = nodes.IncludeRuntime
SetDefault = nodes.SetDefault
Python = nodes.Python
PythonModule = nodes.PythonModule

ErrorContext = errors.ErrorContext
TemplateValidationError = errors.TemplateValidationError
RenderError = errors.RenderError
MissingVariableError = errors.MissingVariableError
RootOmitError = errors.RootOmitError
ExpressionError = errors.ExpressionError
FunctionNotFoundError = errors.FunctionNotFoundError
FunctionCallError = errors.FunctionCallError
IncludeError = errors.IncludeError
IncludeCycleError = errors.IncludeCycleError
PythonError = errors.PythonError
PythonEmitError = errors.PythonEmitError


class _PythonEmitSignal(BaseException):
    """Internal signal used by !python and !python_module to emit a value."""

    def __init__(self, value: _typing.Any = None) -> None:
        self.value = value
        super().__init__()


@_dataclasses.dataclass(frozen=True, slots=True)
class TraceEvent:
    """A trace event emitted when rendering a node."""

    path: tuple[_typing.Any, ...]
    node_type: str
    mark: nodes.SourceMark | None
    before: _typing.Any
    after: _typing.Any


TraceSink = _abc.Callable[[TraceEvent], None]


@_dataclasses.dataclass(slots=True)
class RenderOptions:
    """Rendering controls.

    `mode` applies conservative presets:
      - trusted: defaults (full power, but still structured)
      - expr_safe: disable attribute access and function calls in !expr
      - locked_down: disable !call, !include_rt, !python, !python_module;
        and apply expr_safe restrictions (note: !setdefault is always allowed)
    """

    # General
    strict: bool = True
    max_depth: int = 100
    max_nodes: int | None = None

    # Node features
    allow_calls: bool = True
    allow_includes: bool = True

    # Pipes
    allow_pipe_registry_calls: bool = True
    strict_pipe_stages: bool = True
    allow_callable_pipe_stages: bool = False

    # Dict behavior
    dict_key_conflict: str = "auto"  # auto|error|first|last

    # Error handling
    wrap_exceptions: bool = True

    # Opt-in power tags (except setdefault which is always allowed)
    allow_setdefault: bool = True  # Safe: cannot override caller-provided values
    allow_python: bool = False
    allow_python_module: bool = False

    # Python execution
    python_strict_emit: bool = False

    # Expression evaluator controls
    mode: str = "trusted"  # trusted|expr_safe|locked_down
    allow_attribute_access_in_expr: bool = True
    allow_function_calls_in_expr: bool = True
    allow_method_calls_in_expr: bool = False
    allow_subscripts_in_expr: bool = True
    allow_private_attributes_in_expr: bool = False

    # Runtime include caching
    cache_runtime_includes: bool = True
    runtime_include_cache_max: int | None = 128

    # Optional tracing hook
    trace: TraceSink | None = None

    def normalized(self) -> "RenderOptions":
        opts = _dataclasses.replace(self)
        mode = (opts.mode or "trusted").lower().strip()
        if mode not in ("trusted", "expr_safe", "locked_down"):
            raise ValueError(f"Unknown render mode: {opts.mode!r}")

        if mode in ("expr_safe", "locked_down"):
            opts.allow_attribute_access_in_expr = False
            opts.allow_function_calls_in_expr = False
            opts.allow_method_calls_in_expr = False
            # Subscripts remain enabled by default in safe modes.

        if mode == "locked_down":
            opts.allow_calls = False
            opts.allow_includes = False
            opts.allow_pipe_registry_calls = False
            opts.allow_callable_pipe_stages = False

            # Power tags are disabled in locked-down mode (except setdefault which is safe).
            opts.allow_python = False
            opts.allow_python_module = False

        return opts

    def dict_conflict_policy(self) -> str:
        mode = self.dict_key_conflict.lower().strip()
        if mode not in ("auto", "error", "first", "last"):
            raise ValueError("dict_key_conflict must be one of: auto, error, first, last")
        if mode == "auto":
            return "error" if self.strict else "last"
        return mode

    def expr_policy(self) -> expr_mod.ExprPolicy:
        return expr_mod.ExprPolicy(
            allow_attribute_access=self.allow_attribute_access_in_expr,
            allow_function_calls=self.allow_function_calls_in_expr,
            allow_subscripts=self.allow_subscripts_in_expr,
            allow_method_calls=self.allow_method_calls_in_expr,
            allow_private_attributes=self.allow_private_attributes_in_expr,
        )


@_dataclasses.dataclass(slots=True)
class RenderContext:
    """Mutable render context used during rendering."""

    # Fixed configuration / dependencies
    options: RenderOptions
    registry: registry_mod.FunctionRegistry | None
    include_resolver: include_mod.IncludeResolver | None
    engine: _typing.Any  # TemplateEngine (kept loose to avoid import cycles)
    trace_sink: TraceSink | None

    # Scope layers
    context: dict[str, _typing.Any]
    root_scope: dict[str, _typing.Any]
    python_module: dict[str, _typing.Any]
    scope: ChainMap

    # Runtime state
    path: list[_typing.Any] = _dataclasses.field(default_factory=list)
    depth: int = 0
    node_count: int = 0

    # Runtime include cache (key -> loaded template object)
    runtime_include_cache: OrderedDict[str, _typing.Any] = _dataclasses.field(default_factory=OrderedDict)

    # Expression evaluator and per-render compile cache
    expr_evaluator: expr_mod.ExpressionEvaluator | None = None
    expr_compile_cache: dict[str, _ast.Expression] = _dataclasses.field(default_factory=dict)

    # Runtime include stack to detect cycles (keys from IncludeResult.key)
    include_stack: list[str] = _dataclasses.field(default_factory=list)


def render_template(
    template: _typing.Any,
    *,
    context: _abc.Mapping[str, _typing.Any] | None = None,
    registry: registry_mod.FunctionRegistry | None = None,
    options: RenderOptions | None = None,
    include_resolver: include_mod.IncludeResolver | None = None,
    engine: _typing.Any = None,
    runtime_include_cache: OrderedDict[str, _typing.Any] | None = None,
    path_prefix: list[_typing.Any] | None = None,
    depth: int = 0,
    node_count: int = 0,
) -> _typing.Any:
    """Render a template object into concrete Python data."""

    opts = (options or RenderOptions()).normalized()

    ctx_context = dict(context or {})
    root_scope: dict[str, _typing.Any] = {}
    python_module: dict[str, _typing.Any] = {}

    scope = ChainMap(root_scope, ctx_context, python_module)

    # Chain python module dict ahead of the base registry so python module helper functions are resolvable.
    python_module_registry = registry_mod.DictFunctionRegistry(python_module)
    if registry is not None:
        effective_registry: registry_mod.FunctionRegistry | None = registry_mod.chain_registries(
            python_module_registry,
            registry,
        )
    elif opts.allow_python_module:
        # Allow python-module-defined helper functions even without an external registry.
        effective_registry = python_module_registry
    else:
        effective_registry = None

    effective_include_resolver = include_resolver
    if effective_include_resolver is None and engine is not None:
        effective_include_resolver = getattr(engine, "include_resolver", None)

    trace_sink = opts.trace

    ctx = RenderContext(
        options=opts,
        registry=effective_registry,
        include_resolver=effective_include_resolver,
        engine=engine,
        trace_sink=trace_sink,
        context=ctx_context,
        root_scope=root_scope,
        python_module=python_module,
        scope=scope,
        path=list(path_prefix or []),
        depth=depth,
        node_count=node_count,
        runtime_include_cache=runtime_include_cache if runtime_include_cache is not None else OrderedDict(),
    )

    # Expr evaluator.
    def _resolve_allowed_fn(name: str) -> _typing.Callable[..., _typing.Any] | None:
        if ctx.registry is None:
            return None
        fn = ctx.registry.get(name)
        if fn is None or not callable(fn):
            return None
        return fn

    ctx.expr_evaluator = expr_mod.ExpressionEvaluator(
        policy=ctx.options.expr_policy(),
        function_resolver=_resolve_allowed_fn,
    )

    out = _render_any(template, ctx)

    if out is OMIT or isinstance(out, Omit):
        raise RootOmitError("Template rendered to !omit at the document root", ctx=ErrorContext(path=tuple(ctx.path)))

    # Propagate cache and counters back to caller if they pass them through.
    return out


def _emit_trace(ctx: RenderContext, node: TemplateNode, before: _typing.Any, after: _typing.Any) -> None:
    if ctx.trace_sink is None:
        return
    try:
        ctx.trace_sink(
            TraceEvent(
                path=tuple(ctx.path),
                node_type=node.__class__.__name__,
                mark=getattr(node, "mark", None),
                before=before,
                after=after,
            )
        )
    except Exception:
        # Tracing must not affect rendering.
        return


def _bump(ctx: RenderContext) -> None:
    ctx.node_count += 1
    if ctx.options.max_nodes is not None and ctx.node_count > ctx.options.max_nodes:
        raise RenderError(
            f"Exceeded max_nodes={ctx.options.max_nodes}",
            ctx=ErrorContext(path=tuple(ctx.path)),
        )


def _push_depth(ctx: RenderContext) -> None:
    ctx.depth += 1
    if ctx.depth > ctx.options.max_depth:
        raise RenderError(
            f"Exceeded max_depth={ctx.options.max_depth}",
            ctx=ErrorContext(path=tuple(ctx.path)),
        )


def _pop_depth(ctx: RenderContext) -> None:
    ctx.depth -= 1


class _PathGuard:
    def __init__(self, ctx: RenderContext, seg: _typing.Any):
        self._ctx = ctx
        self._seg = seg

    def __enter__(self) -> RenderContext:
        self._ctx.path.append(self._seg)
        return self._ctx

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: _typing.Any) -> None:
        self._ctx.path.pop()


def _path(ctx: RenderContext, seg: _typing.Any) -> _PathGuard:
    return _PathGuard(ctx, seg)


def _render_any(value: _typing.Any, ctx: RenderContext) -> _typing.Any:
    _bump(ctx)

    if isinstance(value, TemplateNode):
        _push_depth(ctx)
        try:
            before = value
            out = _render_node(value, ctx)
            _emit_trace(ctx, value, before=before, after=out)
            return out
        finally:
            _pop_depth(ctx)

    if isinstance(value, dict):
        _push_depth(ctx)
        try:
            return _render_dict(value, ctx)
        finally:
            _pop_depth(ctx)

    if isinstance(value, (list, tuple)):
        _push_depth(ctx)
        try:
            rendered: list[_typing.Any] = []
            for i, v in enumerate(value):
                with _path(ctx, i):
                    rv = _render_any(v, ctx)
                    if rv is OMIT or isinstance(rv, Omit):
                        continue
                    rendered.append(rv)
            if isinstance(value, tuple):
                return tuple(rendered)
            return rendered
        finally:
            _pop_depth(ctx)

    if isinstance(value, (set, frozenset)):
        _push_depth(ctx)
        try:
            rendered_set: set[_typing.Any] = set()
            for i, v in enumerate(value):
                with _path(ctx, i):
                    rv = _render_any(v, ctx)
                    if rv is OMIT or isinstance(rv, Omit):
                        continue
                    rendered_set.add(rv)
            if isinstance(value, frozenset):
                return frozenset(rendered_set)
            return rendered_set
        finally:
            _pop_depth(ctx)

    return value

def _render_dict(value: dict[_typing.Any, _typing.Any], ctx: RenderContext) -> dict[_typing.Any, _typing.Any]:
    out: dict[_typing.Any, _typing.Any] = {}
    policy = ctx.options.dict_conflict_policy()

    for k, v in value.items():
        with _path(ctx, "<key>"):
            rk = _render_any(k, ctx)
        with _path(ctx, k):
            rv = _render_any(v, ctx)

        if rv is OMIT or isinstance(rv, Omit):
            continue

        if rk in out:
            if policy == "error":
                raise RenderError(f"Duplicate dict key: {rk!r}", ctx=ErrorContext(path=tuple(ctx.path)))
            if policy == "first":
                continue
            # "last": overwrite
        out[rk] = rv

    return out

def _render_node(node: TemplateNode, ctx: RenderContext) -> _typing.Any:
    if isinstance(node, Omit):
        return OMIT

    if isinstance(node, Var):
        return _render_var(node, ctx)

    if isinstance(node, Default):
        return _render_default(node, ctx)

    if isinstance(node, If):
        return _render_if(node, ctx)

    if isinstance(node, ForEach):
        return _render_foreach(node, ctx)

    if isinstance(node, Expr):
        return _render_expr(node, ctx)

    if isinstance(node, Call):
        return _render_call(node, ctx)

    if isinstance(node, Pipe):
        return _render_pipe(node, ctx)

    if isinstance(node, IncludeRuntime):
        return _render_include_rt(node, ctx)

    if isinstance(node, SetDefault):
        return _render_setdefault(node, ctx)

    if isinstance(node, PythonModule):
        return _render_python_module(node, ctx)

    if isinstance(node, Python):
        return _render_python(node, ctx)

    raise RenderError(
        f"Unknown template node: {node.__class__.__name__}",
        ctx=ErrorContext(path=tuple(ctx.path), mark=getattr(node, "mark", None), node_type=node.__class__.__name__),
    )


def _render_var(node: Var, ctx: RenderContext) -> _typing.Any:
    name = node.name
    if name in ctx.scope:
        return ctx.scope[name]

    # Missing
    if node.required:
        raise MissingVariableError(
            f"Missing required variable: {name}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Var"),
        )

    if node.default is UNSET:
        return None
    with _path(ctx, "default"):
        return _render_any(node.default, ctx)

def _render_default(node: Default, ctx: RenderContext) -> _typing.Any:
    missing = False
    try:
        with _path(ctx, "value"):
            val = _render_any(node.value, ctx)
    except (MissingVariableError, IncludeError):
        missing = True
        val = None
    else:
        if node.treat_none_as_missing and val is None:
            missing = True
        if node.treat_omit_as_missing and (val is OMIT or isinstance(val, Omit)):
            missing = True

    if not missing:
        return val

    if node.default is UNSET:
        return None
    with _path(ctx, "default"):
        return _render_any(node.default, ctx)

def _render_if(node: If, ctx: RenderContext) -> _typing.Any:
    with _path(ctx, "test"):
        test_val = _render_any(node.test, ctx)

    if test_val:
        with _path(ctx, "then"):
            return _render_any(node.then, ctx)

    with _path(ctx, "else"):
        return _render_any(node.else_, ctx)

def _render_foreach(node: ForEach, ctx: RenderContext) -> _typing.Any:
    into = (node.into or "list").lower()
    if into not in {"list", "dict", "set"}:
        raise RenderError(
            f"!foreach invalid 'into': {node.into!r}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
        )

    if into in {"list", "set"} and node.template is UNSET:
        raise RenderError(
            "!foreach requires 'template' when into is 'list' or 'set'",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
        )

    if into == "dict" and (node.key is UNSET or node.value is UNSET):
        raise RenderError(
            "!foreach into:'dict' requires both 'key' and 'value'",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
        )

    with _path(ctx, "in"):
        iterable = _render_any(node.in_, ctx)

    if iterable is None:
        items: list[_typing.Any] = []
    elif isinstance(iterable, dict):
        items = list(iterable.items())
    else:
        try:
            items = list(iterable)
        except TypeError as e:
            raise RenderError(
                f"!foreach expected an iterable for 'in', got {type(iterable).__name__}",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
                cause=e,
            )

    if into == "dict":
        out_dict: dict[_typing.Any, _typing.Any] = {}
        policy = ctx.options.dict_conflict_policy()

        for idx, item in enumerate(items):
            frame: dict[str, _typing.Any] = {node.var: item}
            if node.index:
                frame[node.index] = idx

            with _path(ctx, idx):
                # when
                if node.when is not None:
                    ctx.scope = ctx.scope.new_child(frame)
                    try:
                        with _path(ctx, "when"):
                            when_val = _render_any(node.when, ctx)
                    finally:
                        ctx.scope = ctx.scope.parents
                    if not when_val:
                        continue

                ctx.scope = ctx.scope.new_child(frame)
                try:
                    with _path(ctx, "key"):
                        rk = _render_any(node.key, ctx)
                    with _path(ctx, "value"):
                        rv = _render_any(node.value, ctx)
                finally:
                    ctx.scope = ctx.scope.parents

                if rv is OMIT or isinstance(rv, Omit):
                    continue

                if rk in out_dict:
                    if policy == "error":
                        with _path(ctx, "key"):
                            raise RenderError(
                                f"Duplicate dict key in !foreach into:dict: {rk!r}",
                                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
                            )
                    if policy == "first":
                        continue
                out_dict[rk] = rv
        return out_dict

    if into == "set":
        out_set: set[_typing.Any] = set()
        for idx, item in enumerate(items):
            frame = {node.var: item}
            if node.index:
                frame[node.index] = idx

            with _path(ctx, idx):
                # when
                if node.when is not None:
                    ctx.scope = ctx.scope.new_child(frame)
                    try:
                        with _path(ctx, "when"):
                            when_val = _render_any(node.when, ctx)
                    finally:
                        ctx.scope = ctx.scope.parents
                    if not when_val:
                        continue

                ctx.scope = ctx.scope.new_child(frame)
                try:
                    with _path(ctx, "template"):
                        val = _render_any(node.template, ctx)
                finally:
                    ctx.scope = ctx.scope.parents

                if val is OMIT or isinstance(val, Omit):
                    continue
                out_set.add(val)
        return out_set

    # into == "list"
    out_list: list[_typing.Any] = []
    for idx, item in enumerate(items):
        frame = {node.var: item}
        if node.index:
            frame[node.index] = idx

        with _path(ctx, idx):
            # when
            if node.when is not None:
                ctx.scope = ctx.scope.new_child(frame)
                try:
                    with _path(ctx, "when"):
                        when_val = _render_any(node.when, ctx)
                finally:
                    ctx.scope = ctx.scope.parents
                if not when_val:
                    continue

            ctx.scope = ctx.scope.new_child(frame)
            try:
                with _path(ctx, "template"):
                    val = _render_any(node.template, ctx)
            finally:
                ctx.scope = ctx.scope.parents

            if val is OMIT or isinstance(val, Omit):
                continue
            out_list.append(val)
    return out_list

def _build_expr_env(ctx: RenderContext) -> _abc.Mapping[str, _typing.Any]:
    # ChainMap implements Mapping and reflects dynamic changes (e.g. !setdefault).
    return ctx.scope


def _render_expr(node: Expr, ctx: RenderContext) -> _typing.Any:
    if ctx.expr_evaluator is None:
        raise RenderError("Internal error: no expression evaluator configured", ctx=ErrorContext(path=tuple(ctx.path)))

    compiled = ctx.expr_compile_cache.get(node.expr)
    if compiled is None:
        try:
            compiled = ctx.expr_evaluator.compile(
                node.expr,
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
            )
        except TemplateValidationError:
            # Preserve the raw validation error when wrapping is disabled.
            if not ctx.options.wrap_exceptions:
                raise
            raise ExpressionError(
                "Invalid !expr syntax",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
            )
        ctx.expr_compile_cache[node.expr] = compiled

    env = _build_expr_env(ctx)
    try:
        return ctx.expr_evaluator.eval(compiled, env)
    except NameError as e:
        # Missing name in the evaluation environment.
        if not node.strict:
            if node.default is UNSET:
                return None
            with _path(ctx, "default"):
                return _render_any(node.default, ctx)

        if not ctx.options.wrap_exceptions:
            raise

        name = getattr(e, "name", None) or str(e)
        raise MissingVariableError(
            f"Missing name in !expr: {name}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
            cause=e,
        )
    except PermissionError as e:
        if not ctx.options.wrap_exceptions:
            raise
        raise ExpressionError(
            str(e),
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
            cause=e,
        )
    except Exception as e:
        if not ctx.options.wrap_exceptions:
            raise
        raise ExpressionError(
            f"Error evaluating expression: {e}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
            cause=e,
        )

def _render_call(node: Call, ctx: RenderContext) -> _typing.Any:
    if not ctx.options.allow_calls:
        raise RenderError(
            "!call is disabled (enable with RenderOptions(allow_calls=True) or avoid mode='locked_down')",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Call"),
        )

    if ctx.registry is None:
        raise RenderError(
            "No registry provided for !call",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Call"),
        )

    with _path(ctx, "fn"):
        fn_name = _render_any(node.fn, ctx)
    if not isinstance(fn_name, str) or not fn_name:
        raise RenderError(
            "!call 'fn' must render to a non-empty string",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Call"),
        )

    fn = ctx.registry.get(fn_name)
    if fn is None or not callable(fn):
        available: list[str] = []
        keys = getattr(ctx.registry, "keys", None)
        if callable(keys):
            try:
                available = sorted(list(keys()))
            except Exception:
                available = []
        hint = f" Available: {available}" if available else ""
        raise FunctionNotFoundError(
            f"Function not found: {fn_name!r}.{hint}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Call"),
        )

    args: list[_typing.Any] = []
    for i, a in enumerate(node.args):
        with _path(ctx, ("args", i)):
            args.append(_render_any(a, ctx))

    kwargs: dict[str, _typing.Any] = {}
    for k, v in node.kwargs.items():
        with _path(ctx, ("kwargs", k)):
            kwargs[k] = _render_any(v, ctx)

    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if not ctx.options.wrap_exceptions:
            raise
        raise FunctionCallError(
            f"Error calling function {fn_name!r}: {e}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Call"),
            cause=e,
        )

def _render_pipe(node: Pipe, ctx: RenderContext) -> _typing.Any:
    if not node.steps:
        return None

    with _path(ctx, ("pipe", 0)):
        value = _render_any(node.steps[0], ctx)

    for i, stage in enumerate(node.steps[1:], start=1):
        with _path(ctx, ("pipe", i)):
            # Special case: stage is a !call node => call with value as first arg
            if isinstance(stage, Call):
                if not ctx.options.allow_calls:
                    raise RenderError(
                        "!call is disabled (enable with RenderOptions(allow_calls=True) or avoid mode='locked_down')",
                        ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Pipe"),
                    )
                if ctx.registry is None:
                    raise RenderError(
                        "No registry provided for !call stage inside !pipe",
                        ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Pipe"),
                    )

                with _path(ctx, "fn"):
                    fn_name = _render_any(stage.fn, ctx)
                if not isinstance(fn_name, str) or not fn_name:
                    raise RenderError(
                        "!call stage 'fn' must render to a non-empty string",
                        ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Pipe"),
                    )

                fn = ctx.registry.get(fn_name)
                if fn is None or not callable(fn):
                    raise FunctionNotFoundError(
                        f"Function not found: {fn_name!r} (in !pipe)",
                        ctx=ErrorContext(path=tuple(ctx.path), mark=stage.mark, node_type="Call"),
                    )

                args: list[_typing.Any] = []
                for j, a in enumerate(stage.args):
                    with _path(ctx, ("args", j)):
                        args.append(_render_any(a, ctx))

                kwargs: dict[str, _typing.Any] = {}
                for k, v in stage.kwargs.items():
                    with _path(ctx, ("kwargs", k)):
                        kwargs[k] = _render_any(v, ctx)

                try:
                    value = fn(value, *args, **kwargs)
                except Exception as e:
                    if not ctx.options.wrap_exceptions:
                        raise
                    raise FunctionCallError(
                        f"Error calling function {fn_name!r} in !pipe: {e}",
                        ctx=ErrorContext(path=tuple(ctx.path), mark=stage.mark, node_type="Call"),
                        cause=e,
                    )
                continue

            rendered_stage = _render_any(stage, ctx)

            # Registry function stage: "trim" etc
            if ctx.options.allow_pipe_registry_calls and isinstance(rendered_stage, str) and ctx.registry is not None:
                fn = ctx.registry.get(rendered_stage)
                if fn is not None and callable(fn):
                    try:
                        value = fn(value)
                    except Exception as e:
                        if not ctx.options.wrap_exceptions:
                            raise
                        raise FunctionCallError(
                            f"Error calling function {rendered_stage!r} in !pipe: {e}",
                            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Pipe"),
                            cause=e,
                        )
                    continue

                if ctx.options.strict_pipe_stages:
                    raise FunctionNotFoundError(
                        f"Unknown pipe stage: {rendered_stage!r}",
                        ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Pipe"),
                    )

            # Callable stage: stage renders to a callable to apply
            if callable(rendered_stage):
                if not ctx.options.allow_callable_pipe_stages:
                    raise RenderError(
                        "Callable pipe stages are disabled (set allow_callable_pipe_stages=True to enable)",
                        ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Pipe"),
                    )
                try:
                    value = rendered_stage(value)
                except Exception as e:
                    if not ctx.options.wrap_exceptions:
                        raise
                    raise RenderError(
                        f"Error calling callable pipe stage: {e}",
                        ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Pipe"),
                        cause=e,
                    )
                continue

            # Otherwise, stage just becomes the new value
            value = rendered_stage

    return value

def _render_include_rt(node: IncludeRuntime, ctx: RenderContext) -> _typing.Any:
    if not ctx.options.allow_includes:
        raise RenderError(
            "!include_rt is disabled (enable with RenderOptions(allow_includes=True) or avoid mode='locked_down')",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
        )

    if ctx.engine is None:
        raise IncludeError(
            "No engine available for !include_rt",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
        )

    if ctx.include_resolver is None:
        if node.required:
            raise IncludeError(
                "!include_rt requires an include_resolver",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
            )
        if node.default is UNSET:
            return None
        with _path(ctx, "default"):
            return _render_any(node.default, ctx)

    with _path(ctx, "target"):
        target = _render_any(node.target, ctx)
    if not isinstance(target, str) or not target:
        raise IncludeError(
            "!include_rt target must render to a non-empty string",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
        )

    # We already checked that include_resolver is not None above.
    assert ctx.include_resolver is not None
    res = ctx.include_resolver.resolve(target, from_source=(node.mark.source if node.mark else None))
    if res.content is None:
        if node.required:
            raise IncludeError(
                f"Included template not found: {target!r}",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
            )
        if node.default is UNSET:
            return None
        with _path(ctx, "default"):
            return _render_any(node.default, ctx)

    # Cycle detection
    if res.key in ctx.include_stack:
        cycle = " -> ".join([*ctx.include_stack, res.key])
        raise IncludeCycleError(
            f"Include cycle detected: {cycle}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
        )

    ctx.include_stack.append(res.key)
    try:
        if ctx.options.cache_runtime_includes and res.key in ctx.runtime_include_cache:
            included_tmpl = ctx.runtime_include_cache[res.key]
            with _path(ctx, ("include", res.key)):
                return _render_any(included_tmpl, ctx)

        try:
            included_tmpl = ctx.engine.load_template_text(res.content, source_name=res.source_name)
        except Exception as e:
            raise IncludeError(
                f"Error loading included template {target!r}: {e}",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
                cause=e,
            )

        if ctx.options.cache_runtime_includes:
            ctx.runtime_include_cache[res.key] = included_tmpl
            if ctx.options.runtime_include_cache_max is not None and ctx.options.runtime_include_cache_max > 0:
                while len(ctx.runtime_include_cache) > ctx.options.runtime_include_cache_max:
                    ctx.runtime_include_cache.popitem(last=False)

        with _path(ctx, ("include", res.key)):
            return _render_any(included_tmpl, ctx)
    finally:
        ctx.include_stack.pop()

def _render_setdefault(node: SetDefault, ctx: RenderContext) -> _typing.Any:
    if not ctx.options.allow_setdefault:
        raise RenderError(
            "!setdefault is disabled (enable with RenderOptions(allow_setdefault=True))",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="SetDefault"),
        )

    for name, default_template in node.defaults.items():
        if not isinstance(name, str) or not name:
            raise RenderError(
                "!setdefault names must be non-empty strings",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="SetDefault"),
            )
        if name in ctx.scope:
            continue
        with _path(ctx, ("setdefault", name)):
            val = _render_any(default_template, ctx)
        ctx.root_scope[name] = val

    return OMIT

def _python_compile(code: str, *, filename: str, strict_emit: bool) -> _typing.Any:
    """Compile python code, optionally injecting an implicit emit(...) for a trailing expression."""

    if strict_emit:
        return compile(code, filename, "exec")

    try:
        module = _ast.parse(code, filename=filename, mode="exec")
    except SyntaxError:
        # Re-raise; caller wraps.
        raise

    if module.body and isinstance(module.body[-1], _ast.Expr):
        last_expr = module.body[-1].value
        module.body[-1] = _ast.Expr(
            value=_ast.Call(
                func=_ast.Name(id="emit", ctx=_ast.Load()),
                args=[last_expr],
                keywords=[],
            )
        )
        _ast.fix_missing_locations(module)

    return compile(module, filename, "exec")


def _render_python_module(node: PythonModule, ctx: RenderContext) -> _typing.Any:
    if not ctx.options.allow_python_module:
        raise RenderError(
            "!python_module is disabled (enable with RenderOptions(allow_python_module=True) or --allow-python-module)",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="PythonModule"),
        )

    code = node.code
    if not isinstance(code, str) or not code.strip():
        raise RenderError(
            "!python_module requires non-empty code",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="PythonModule"),
        )

    def emit(value: _typing.Any = None) -> _typing.NoReturn:
        raise _PythonEmitSignal(value)

    filename = "<ydst:python_module>"
    if node.mark and node.mark.source:
        filename = f"<ydst:python_module {node.mark.source}:{node.mark.line}:{node.mark.column}>"

    # Execute in the persistent module globals.
    g = ctx.python_module
    g.setdefault("__name__", "<ydst_python_module>")
    g.setdefault("OMIT", OMIT)
    g.setdefault("UNSET", UNSET)

    # Expose helpers. These are left in globals (trusted-only feature).
    g["emit"] = emit
    g["ctx"] = ctx
    g["scope"] = ctx.scope
    if ctx.registry is not None:
        g["registry"] = ctx.registry

    try:
        exec(compile(code, filename, "exec"), g, g)
    except _PythonEmitSignal:
        # Explicit early exit is allowed; result is always OMIT.
        return OMIT
    except Exception as e:
        raise PythonError(
            f"Error executing !python_module: {e}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="PythonModule"),
            cause=e,
        )

    return OMIT


def _render_python(node: Python, ctx: RenderContext) -> _typing.Any:
    if not ctx.options.allow_python:
        raise RenderError(
            "!python is disabled (enable with RenderOptions(allow_python=True) or --allow-python)",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Python"),
        )

    code = node.code
    if not isinstance(code, str) or not code.strip():
        raise RenderError(
            "!python requires non-empty code",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Python"),
        )

    strict_emit = node.strict_emit if node.strict_emit is not None else ctx.options.python_strict_emit

    def emit(value: _typing.Any = None) -> _typing.NoReturn:
        raise _PythonEmitSignal(value)

    filename = "<ydst:python>"
    if node.mark and node.mark.source:
        filename = f"<ydst:python {node.mark.source}:{node.mark.line}:{node.mark.column}>"

    try:
        code_obj = _python_compile(code, filename=filename, strict_emit=strict_emit)
    except SyntaxError as e:
        raise PythonError(
            f"Invalid python code: {e.msg}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Python"),
            cause=e,
        )

    # Globals: persistent python module dict so helper functions/constants are available.
    g = ctx.python_module
    g.setdefault("__name__", "<ydst_python_module>")
    g.setdefault("OMIT", OMIT)
    g.setdefault("UNSET", UNSET)

    # Locals: snapshot of current scope + helpers (does not persist back into module globals unless `global` is used).
    local_vars: dict[str, _typing.Any] = dict(ctx.scope)
    local_vars.update(
        {
            "emit": emit,
            "ctx": ctx,
            "scope": ctx.scope,
            "OMIT": OMIT,
            "UNSET": UNSET,
        }
    )
    if ctx.registry is not None:
        local_vars["registry"] = ctx.registry

    try:
        exec(code_obj, g, local_vars)
    except _PythonEmitSignal as e:
        return e.value
    except Exception as e:
        raise PythonError(
            f"Error executing !python: {e}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Python"),
            cause=e,
        )

    if strict_emit:
        raise PythonEmitError(
            "!python block completed without calling emit(...)",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Python"),
        )

    # No emit, no trailing expression -> implicit None
    return None
