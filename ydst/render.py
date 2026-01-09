from __future__ import annotations

from collections import ChainMap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from .errors import (
    ErrorContext,
    ExpressionError,
    FunctionCallError,
    FunctionNotFoundError,
    IncludeCycleError,
    IncludeError,
    MissingVariableError,
    RenderError,
    RootOmitError,
)
from .expr import ExprPolicy, ExpressionEvaluator
from .include import IncludeResolver
from .nodes import (
    Call,
    Expr,
    ForEach,
    If,
    IncludeRuntime,
    Omit,
    OMIT,
    SourceMark,
    TemplateNode,
    Var,
)
from .registry import FunctionRegistry


@dataclass(frozen=True)
class TraceEvent:
    path: Tuple[Any, ...]
    node_type: str
    mark: Optional[SourceMark]
    before: Any
    after: Any


TraceSink = Callable[[TraceEvent], None]


@dataclass
class RenderOptions:
    """Rendering options.

    Notes
    -----
    - `strict` controls missing variables and root-omit behavior.
    - `dict_key_conflict='auto'` means:
        strict=True  -> error
        strict=False -> last-wins
      You can force last-wins while still strict by setting dict_key_conflict='last'.

    Security note:
    - `mode='safe'` only affects what is permitted inside `!expr`.
      It does **not** prevent registry functions from being invoked via `!call` / `!pipe`,
      and it does not disable file includes.
    """

    mode: str = "trusted"  # "trusted" | "safe"
    strict: bool = True

    allow_attribute_access_in_expr: bool = True
    allow_function_calls_in_expr: bool = True
    allow_method_calls_in_expr: bool = False

    max_depth: int = 200
    max_nodes: Optional[int] = None

    dict_key_conflict: str = "auto"  # auto|error|last|first

    # If True, wrap exceptions with RenderError subclasses preserving causes.
    # If False, raw exceptions from registry/expr propagate (useful for debugging).
    wrap_exceptions: bool = True

    trace: Optional[TraceSink] = None

    def normalized(self) -> "RenderOptions":
        """Normalize options based on mode."""
        o = RenderOptions(**self.__dict__)
        if o.mode == "safe":
            # In safe mode, do not allow attribute/method/calls in expressions.
            o.allow_attribute_access_in_expr = False
            o.allow_function_calls_in_expr = False
            o.allow_method_calls_in_expr = False
        return o

    def dict_conflict_policy(self) -> str:
        if self.dict_key_conflict == "auto":
            return "error" if self.strict else "last"
        return self.dict_key_conflict


@dataclass
class RenderContext:
    context: Mapping[str, Any]
    scope: ChainMap
    registry: Optional[FunctionRegistry]
    options: RenderOptions
    engine: Any = None  # TemplateEngine (optional)

    include_resolver: Optional[IncludeResolver] = None

    path: list[Any] = None  # type: ignore[assignment]
    depth: int = 0
    nodes_visited: int = 0
    include_stack: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.path is None:
            self.path = []
        if self.include_stack is None:
            self.include_stack = []


def render_template(
    template: Any,
    *,
    context: Optional[Mapping[str, Any]] = None,
    registry: Optional[FunctionRegistry] = None,
    options: Optional[RenderOptions] = None,
    engine: Any = None,
    include_resolver: Optional[IncludeResolver] = None,
) -> Any:
    ctx = RenderContext(
        context=context or {},
        scope=ChainMap({}, context or {}),
        registry=registry,
        options=(options or RenderOptions()).normalized(),
        engine=engine,
        include_resolver=include_resolver,
    )
    result = _render_any(template, ctx)

    if result is OMIT or isinstance(result, Omit):
        if ctx.options.strict:
            raise RootOmitError(
                "Template rendered to !omit at root",
                ctx=ErrorContext(path=tuple(ctx.path), node_type="Omit"),
            )
        return result
    return result


def _bump(ctx: RenderContext) -> None:
    ctx.nodes_visited += 1
    if ctx.options.max_nodes is not None and ctx.nodes_visited > ctx.options.max_nodes:
        raise RenderError(
            f"Render node limit exceeded (max_nodes={ctx.options.max_nodes})",
            ctx=ErrorContext(path=tuple(ctx.path), node_type="Limit"),
        )


def _render_any(value: Any, ctx: RenderContext) -> Any:
    _bump(ctx)

    # Depth limiting is applied to *all* recursive traversal, not just template nodes.
    ctx.depth += 1
    try:
        if ctx.depth > ctx.options.max_depth:
            raise RenderError(
                f"Maximum render depth exceeded (max_depth={ctx.options.max_depth})",
                ctx=ErrorContext(path=tuple(ctx.path), node_type="Depth"),
            )

        # Template nodes
        if isinstance(value, TemplateNode):
            before = value
            try:
                after = _render_node(value, ctx)
            except RenderError:
                raise
            except Exception as e:
                if ctx.options.wrap_exceptions:
                    raise RenderError(
                        str(e),
                        ctx=ErrorContext(
                            path=tuple(ctx.path),
                            mark=getattr(value, "mark", None),
                            node_type=type(value).__name__,
                        ),
                        cause=e,
                    )
                raise

            if ctx.options.trace is not None:
                ctx.options.trace(
                    TraceEvent(
                        path=tuple(ctx.path),
                        node_type=type(value).__name__,
                        mark=getattr(value, "mark", None),
                        before=before,
                        after=after,
                    )
                )
            return after

        # Containers
        if isinstance(value, Mapping):
            out: dict[Any, Any] = {}
            conflict = ctx.options.dict_conflict_policy()
            for k, v in value.items():
                # Templated/dynamic keys are not supported because YAML mappings must have
                # hashable keys at load time; use `!foreach into:dict` instead.
                if isinstance(k, TemplateNode):
                    raise RenderError(
                        "Templated mapping keys are not supported (use !foreach into:dict)",
                        ctx=ErrorContext(path=tuple(ctx.path), node_type="MappingKey", mark=getattr(k, "mark", None)),
                    )

                # Ensure keys are hashable so we can build a Python dict.
                try:
                    hash(k)
                except Exception as e:
                    raise RenderError(
                        "Mapping keys must be hashable values",
                        ctx=ErrorContext(path=tuple(ctx.path), node_type="MappingKey"),
                        cause=e if ctx.options.wrap_exceptions else None,
                    )

                # Render value
                ctx.path.append(k)
                try:
                    rv = _render_any(v, ctx)
                finally:
                    ctx.path.pop()

                if rv is OMIT or isinstance(rv, Omit):
                    continue

                if k in out:
                    if conflict == "error":
                        raise RenderError(
                            f"Duplicate key during render: {k!r}",
                            ctx=ErrorContext(path=tuple(ctx.path) + (k,), node_type="MappingKey"),
                        )
                    if conflict == "first":
                        continue
                    # last-wins
                out[k] = rv
            return out

        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            out_list: list[Any] = []
            for i, item in enumerate(value):
                ctx.path.append(i)
                try:
                    ri = _render_any(item, ctx)
                finally:
                    ctx.path.pop()

                if ri is OMIT or isinstance(ri, Omit):
                    continue
                out_list.append(ri)
            return out_list

        # Scalars
        return value

    finally:
        ctx.depth -= 1


def _render_node(node: TemplateNode, ctx: RenderContext) -> Any:
    if isinstance(node, Omit):
        return OMIT

    if isinstance(node, Var):
        return _render_var(node, ctx)

    if isinstance(node, If):
        return _render_if(node, ctx)

    if isinstance(node, ForEach):
        return _render_foreach(node, ctx)

    if isinstance(node, Expr):
        return _render_expr(node, ctx)

    if isinstance(node, Call):
        return _render_call(node, ctx)

    from .nodes import Pipe

    if isinstance(node, Pipe):
        return _render_pipe(node, ctx)

    if isinstance(node, IncludeRuntime):
        return _render_include_runtime(node, ctx)

    raise RenderError(
        f"Unknown template node type: {type(node).__name__}",
        ctx=ErrorContext(path=tuple(ctx.path), mark=getattr(node, "mark", None), node_type=type(node).__name__),
    )


def _render_var(node: Var, ctx: RenderContext) -> Any:
    name = node.name
    if name in ctx.scope:
        return ctx.scope[name]
    if node.required and ctx.options.strict:
        raise MissingVariableError(
            f"Missing required variable: {name}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Var"),
        )

    # Only the singleton sentinel OMIT means "no default specified".
    # If the default is an actual `!omit` node, render it so the enclosing container drops it.
    if node.default is not OMIT:
        return _render_any(node.default, ctx)

    return None


def _render_if(node: If, ctx: RenderContext) -> Any:
    ctx.path.append("test")
    try:
        test_val = _render_any(node.test, ctx)
    finally:
        ctx.path.pop()

    branch = node.then if test_val else node.else_
    return _render_any(branch, ctx)


def _materialize_iterable(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)):
        raise TypeError("Cannot iterate over string/bytes in !foreach")
    return list(value)


def _render_foreach(node: ForEach, ctx: RenderContext) -> Any:
    ctx.path.append("in")
    try:
        seq_val = _render_any(node.in_, ctx)
    finally:
        ctx.path.pop()

    try:
        items = _materialize_iterable(seq_val)
    except Exception as e:
        raise RenderError(
            f"!foreach 'in' is not iterable: {e}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
            cause=e if ctx.options.wrap_exceptions else None,
        )

    into = (node.into or "list").lower()
    if into == "list":
        out_list: list[Any] = []
    elif into == "dict":
        out_dict: dict[Any, Any] = {}
        conflict = ctx.options.dict_conflict_policy()
    elif into == "set":
        out_set: set[Any] = set()
    else:
        raise RenderError(
            f"Unsupported !foreach output type: {into}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
        )

    for idx, item in enumerate(items):
        frame: dict[str, Any] = {node.var: item}
        if node.index:
            frame[node.index] = idx

        old_scope = ctx.scope
        ctx.scope = ctx.scope.new_child(frame)
        try:
            if node.when is not None:
                ctx.path.append("when")
                try:
                    cond = _render_any(node.when, ctx)
                finally:
                    ctx.path.pop()
                if not cond:
                    continue

            if into == "list":
                ctx.path.append(idx)
                try:
                    rendered = _render_any(node.template, ctx)
                finally:
                    ctx.path.pop()
                if rendered is OMIT or isinstance(rendered, Omit):
                    continue
                out_list.append(rendered)

            elif into == "set":
                ctx.path.append(idx)
                try:
                    rendered = _render_any(node.template, ctx)
                finally:
                    ctx.path.pop()
                if rendered is OMIT or isinstance(rendered, Omit):
                    continue
                try:
                    out_set.add(rendered)
                except TypeError as e:
                    raise RenderError(
                        f"!foreach into:set produced unhashable element: {rendered!r}",
                        ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
                        cause=e if ctx.options.wrap_exceptions else None,
                    )

            else:  # dict
                ctx.path.append(idx)
                try:
                    rk = _render_any(node.key, ctx)
                    rv = _render_any(node.value, ctx)
                finally:
                    ctx.path.pop()

                if rk is OMIT or isinstance(rk, Omit) or rv is OMIT or isinstance(rv, Omit):
                    continue
                try:
                    hash(rk)
                except Exception as e:
                    raise RenderError(
                        f"!foreach into:dict produced unhashable key: {rk!r}",
                        ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
                        cause=e if ctx.options.wrap_exceptions else None,
                    )

                if rk in out_dict:
                    if conflict == "error":
                        raise RenderError(
                            f"Duplicate key produced by !foreach into:dict: {rk!r}",
                            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
                        )
                    if conflict == "first":
                        continue
                    # last-wins
                out_dict[rk] = rv
        finally:
            ctx.scope = old_scope

    if into == "list":
        return out_list
    if into == "set":
        return out_set
    return out_dict  # type: ignore[return-value]


def _build_expr_env(ctx: RenderContext) -> dict[str, Any]:
    env: dict[str, Any] = {}
    # ChainMap maps are ordered from most local to most global. We want the later ones
    # overwritten by earlier ones, so update from global->local.
    for m in reversed(ctx.scope.maps):
        env.update(m)
    return env


def _render_expr(node: Expr, ctx: RenderContext) -> Any:
    policy = ExprPolicy(
        allow_attribute_access=ctx.options.allow_attribute_access_in_expr,
        allow_function_calls=ctx.options.allow_function_calls_in_expr,
        allow_method_calls=ctx.options.allow_method_calls_in_expr,
    )

    env = _build_expr_env(ctx)

    def _fn_resolver(name: str) -> Optional[Callable[..., Any]]:
        if ctx.registry is None:
            return None
        fn = ctx.registry.get(name)
        return fn if callable(fn) else None

    evaluator = ExpressionEvaluator(policy=policy, function_resolver=_fn_resolver)
    compiled = node._compiled
    if compiled is None:
        try:
            compiled = evaluator.compile(
                node.expr,
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
            )
        except Exception as e:
            raise ExpressionError(
                f"Invalid expression: {node.expr}",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
                cause=e if ctx.options.wrap_exceptions else None,
            )
        node._compiled = compiled

    try:
        return evaluator.eval(compiled, env)
    except NameError as e:
        if not node.strict or not ctx.options.strict:
            if node.default is not OMIT:
                return _render_any(node.default, ctx)
            return None
        raise MissingVariableError(
            f"Missing name in !expr: {e.args[0]}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
            cause=e if ctx.options.wrap_exceptions else None,
        )
    except PermissionError as e:
        raise ExpressionError(
            str(e),
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
            cause=e if ctx.options.wrap_exceptions else None,
        )
    except Exception as e:
        if ctx.options.wrap_exceptions:
            raise ExpressionError(
                str(e),
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
                cause=e,
            )
        raise


def _render_call(node: Call, ctx: RenderContext, *, pipe_input: Any = None, include_pipe_input: bool = False) -> Any:
    fn_val = (
        _render_any(node.fn, ctx)
        if isinstance(node.fn, TemplateNode) or isinstance(node.fn, (Mapping, Sequence))
        else node.fn
    )
    if not isinstance(fn_val, str) or not fn_val:
        raise RenderError(
            f"!call function name must render to a non-empty string (got {fn_val!r})",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Call"),
        )

    if ctx.registry is None:
        raise FunctionNotFoundError(
            f"No registry provided; cannot resolve function '{fn_val}'",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Call"),
        )

    fn = ctx.registry.get(fn_val)
    if fn is None:
        raise FunctionNotFoundError(
            f"Function not found in registry: {fn_val}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Call"),
        )

    args = []
    if include_pipe_input:
        args.append(pipe_input)

    for i, a in enumerate(node.args):
        ctx.path.append(f"args[{i}]")
        try:
            args.append(_render_any(a, ctx))
        finally:
            ctx.path.pop()

    kwargs = {}
    for k, v in node.kwargs.items():
        ctx.path.append(f"kwargs[{k}]")
        try:
            kwargs[k] = _render_any(v, ctx)
        finally:
            ctx.path.pop()

    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if ctx.options.wrap_exceptions:
            raise FunctionCallError(
                f"Function '{fn_val}' raised: {e}",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Call"),
                cause=e,
            )
        raise


def _render_pipe(node: Any, ctx: RenderContext) -> Any:
    steps = list(getattr(node, "steps", []) or [])
    if not steps:
        return OMIT

    ctx.path.append("pipe[0]")
    try:
        value = _render_any(steps[0], ctx)
    finally:
        ctx.path.pop()

    if value is OMIT or isinstance(value, Omit):
        return OMIT

    for i, stage in enumerate(steps[1:], start=1):
        ctx.path.append(f"pipe[{i}]")
        try:
            if isinstance(stage, Call):
                value = _render_call(stage, ctx, pipe_input=value, include_pipe_input=True)
                continue

            rendered_stage = _render_any(stage, ctx)

            if isinstance(rendered_stage, str) and ctx.registry is not None:
                fn = ctx.registry.get(rendered_stage)
                if fn is None:
                    raise FunctionNotFoundError(
                        f"Pipeline stage function not found: {rendered_stage}",
                        ctx=ErrorContext(path=tuple(ctx.path), node_type="Pipe"),
                    )
                value = fn(value)
                continue

            if callable(rendered_stage):
                value = rendered_stage(value)
                continue

            value = rendered_stage
        finally:
            ctx.path.pop()

    return value


def _render_include_runtime(node: IncludeRuntime, ctx: RenderContext) -> Any:
    resolver = ctx.include_resolver
    if resolver is None and ctx.engine is not None:
        resolver = getattr(ctx.engine, "include_resolver", None)

    if resolver is None:
        if node.required and ctx.options.strict:
            raise IncludeError(
                "!include_rt requires an include_resolver",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
            )
        if node.default is not OMIT:
            return _render_any(node.default, ctx)
        return None

    target_val = _render_any(node.target, ctx)
    if not isinstance(target_val, str) or not target_val:
        raise IncludeError(
            f"!include_rt target must render to a non-empty string (got {target_val!r})",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
        )

    try:
        res = resolver.resolve(target_val, from_source=(node.mark.source if node.mark else None))
    except Exception as e:
        if ctx.options.wrap_exceptions:
            raise IncludeError(
                f"Include resolution failed for target {target_val!r}: {e}",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
                cause=e,
            )
        raise

    if res.content is None:
        if node.required and ctx.options.strict:
            raise IncludeError(
                f"Include target not found: {target_val}",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
            )
        if node.default is not OMIT:
            return _render_any(node.default, ctx)
        return None

    if res.key in ctx.include_stack:
        raise IncludeCycleError(
            f"Include cycle detected at '{res.key}'",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
        )

    if ctx.engine is None:
        raise IncludeError(
            "Render-time includes require a TemplateEngine instance (pass engine=... to render)",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
        )

    ctx.include_stack.append(res.key)
    try:
        included_tmpl = ctx.engine.load_template(res.content, source_name=res.source_name)
        return _render_any(included_tmpl, ctx)
    finally:
        ctx.include_stack.pop()
