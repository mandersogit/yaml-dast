from __future__ import annotations

from collections import ChainMap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from .errors import (
    ErrorContext,
    TemplateValidationError,
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
    Default,
    Expr,
    ForEach,
    If,
    IncludeRuntime,
    Omit,
    OMIT,
    UNSET,
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
    - `strict` controls missing variables and other "required" behaviors.
    - `dict_key_conflict='auto'` means:
        strict=True  -> error
        strict=False -> last-wins
      You can force last-wins while still strict by setting dict_key_conflict='last'.

    Mode semantics
    --------------
    `mode` is a convenience preset; it simply sets other flags via `normalized()`.

    - `trusted`: no automatic restrictions.
    - `expr_safe`: disables attribute access and function calls inside `!expr`.
    - `locked_down`: a stricter preset intended for untrusted-ish templates. It disables:
        * `!expr` attribute access and calls
        * `!call`
        * registry calls from `!pipe` string stages
        * render-time includes (`!include_rt`)

    Security note
    -------------
    ydst is not a sandbox. These controls reduce footguns but do not make rendering
    arbitrary templates safe against malicious inputs.
    """

    mode: str = "trusted"  # trusted|expr_safe|locked_down
    strict: bool = True

    # -----------------
    # !expr policy
    # -----------------
    allow_attribute_access_in_expr: bool = True
    allow_function_calls_in_expr: bool = True
    allow_subscripts_in_expr: bool = True
    allow_method_calls_in_expr: bool = False

    # If True, allow attribute names that begin with '_' or contain '__'.
    # By default these are rejected even when attribute access is enabled.
    allow_private_attributes_in_expr: bool = False

    # -----------------
    # !call policy
    # -----------------
    allow_calls: bool = True

    # -----------------
    # !include_rt policy
    # -----------------
    allow_includes: bool = True

    # -----------------
    # !pipe policy
    # -----------------
    # If True, any pipeline stage that renders to a callable will be invoked with the
    # current value. If False, use `!call` (registry) or a string stage naming a registry function.
    allow_callable_pipe_stages: bool = False

    # If True, string stages are allowed to call registry functions (when present).
    # If False, string stages are treated as literal values.
    allow_pipe_registry_calls: bool = True

    # If True, unknown string stages (that are not registry functions) raise an error
    # instead of being treated as literal strings.
    strict_pipe_stages: bool = True

    # -----------------
    # !foreach policy
    # -----------------
    # If True, coerce the `in:` value to a list up front (preserves historical behavior).
    # If False, iterate streaming for iterators/generators (can reduce memory use).
    materialize_foreach_iterables: bool = True

    # -----------------
    # Structural limits
    # -----------------
    max_depth: int = 200
    max_nodes: Optional[int] = None

    # Mapping conflict policy for !foreach into:dict and templated mappings.
    dict_key_conflict: str = "auto"  # auto|error|last|first

    # Render-time include caching.
    # Caches parsed templates (not raw file content) within a single render invocation.
    cache_runtime_includes: bool = True
    # By default we keep a modest per-render cache to avoid repeatedly parsing the same
    # included templates while still bounding memory use for templates that include many
    # distinct targets.
    runtime_include_cache_max: Optional[int] = 128

    # If True, wrap foreign exceptions with RenderError subclasses preserving causes.
    # If False, raw exceptions from registry/expr/include-resolvers propagate (useful for debugging).
    wrap_exceptions: bool = True

    trace: Optional[TraceSink] = None

    def validate(self) -> None:
        """Validate option values (fail fast).

        This is primarily to surface configuration errors early for API users.
        The CLI already constrains many of these, but library users may not.
        """
        allowed_modes = {"trusted", "expr_safe", "locked_down"}
        if self.mode not in allowed_modes:
            raise ValueError(
                f"Invalid RenderOptions.mode={self.mode!r}. Expected one of: {sorted(allowed_modes)}"
            )

        if not isinstance(self.max_depth, int) or self.max_depth < 0:
            raise ValueError("RenderOptions.max_depth must be an int >= 0")

        if self.max_nodes is not None:
            if not isinstance(self.max_nodes, int) or self.max_nodes < 0:
                raise ValueError("RenderOptions.max_nodes must be None or an int >= 0")

        if self.runtime_include_cache_max is not None:
            if not isinstance(self.runtime_include_cache_max, int) or self.runtime_include_cache_max < 0:
                raise ValueError("RenderOptions.runtime_include_cache_max must be None or an int >= 0")

        allowed_conflicts = {"auto", "error", "last", "first"}
        if self.dict_key_conflict not in allowed_conflicts:
            raise ValueError(
                f"Invalid RenderOptions.dict_key_conflict={self.dict_key_conflict!r}. "
                f"Expected one of: {sorted(allowed_conflicts)}"
            )

        # Defensive: ensure cache max is consistent with cache enable flag.
        if self.cache_runtime_includes is False and self.runtime_include_cache_max not in (None, 0):
            # Not an error; just a no-op configuration.
            pass

    def normalized(self) -> "RenderOptions":
        """Normalize options based on mode."""
        o = RenderOptions(**self.__dict__)

        mode = (o.mode or "trusted").replace("-", "_").lower()

        if mode == "expr_safe":
            # "Safe" in ydst means: safe-ish *expressions*.
            o.allow_attribute_access_in_expr = False
            o.allow_function_calls_in_expr = False
            o.allow_method_calls_in_expr = False
            # When attribute access is disabled, private attribute policy is moot.
            o.allow_private_attributes_in_expr = False
            # Also disallow implicit callable stages in !pipe, since this bypasses the registry.
            o.allow_callable_pipe_stages = False

        if mode == "locked_down":
            # Start from expr-safe.
            o.allow_attribute_access_in_expr = False
            o.allow_function_calls_in_expr = False
            o.allow_method_calls_in_expr = False
            # Prefer a stricter expression surface by default.
            o.allow_private_attributes_in_expr = False
            o.allow_callable_pipe_stages = False

            # And additionally disable the main "escape hatches".
            o.allow_calls = False
            o.allow_includes = False
            o.allow_pipe_registry_calls = False

        # Preserve the normalized mode string.
        o.mode = mode
        o.validate()
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

    # Internal helpers/caches (filled by render_template).
    expr_evaluator: Optional[ExpressionEvaluator] = None
    expr_compile_cache: Optional[dict[str, Any]] = None
    runtime_include_cache: Optional[dict[str, Any]] = None

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

    # Build an expression evaluator once per render invocation.
    policy = ExprPolicy(
        allow_attribute_access=ctx.options.allow_attribute_access_in_expr,
        allow_function_calls=ctx.options.allow_function_calls_in_expr,
        allow_subscripts=ctx.options.allow_subscripts_in_expr,
        allow_method_calls=ctx.options.allow_method_calls_in_expr,
        allow_private_attributes=ctx.options.allow_private_attributes_in_expr,
    )

    def _fn_resolver(name: str) -> Optional[Callable[..., Any]]:
        if ctx.registry is None:
            return None
        fn = ctx.registry.get(name)
        return fn if callable(fn) else None

    ctx.expr_evaluator = ExpressionEvaluator(policy=policy, function_resolver=_fn_resolver)

    # Cache compiled expressions per render invocation (avoid mutating shared template nodes).
    ctx.expr_compile_cache = {}

    if ctx.options.cache_runtime_includes and (
        ctx.options.runtime_include_cache_max is None or ctx.options.runtime_include_cache_max > 0
    ):
        ctx.runtime_include_cache = {}

    result = _render_any(template, ctx)

    # Root-level !omit has no sensible container semantics. Reject it explicitly.
    if result is OMIT or isinstance(result, Omit):
        raise RootOmitError(
            "Template rendered to !omit at root",
            ctx=ErrorContext(path=tuple(ctx.path), node_type="Omit"),
        )
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

        # Sets / frozensets are treated as containers as well.
        # Note: sets are unordered; the numeric path index reflects iteration order.
        if isinstance(value, (set, frozenset)):
            out_set: set[Any] = set()
            for i, item in enumerate(value):
                ctx.path.append(i)
                try:
                    ri = _render_any(item, ctx)
                    if ri is OMIT or isinstance(ri, Omit):
                        continue
                    try:
                        out_set.add(ri)
                    except TypeError as e:
                        raise RenderError(
                            f"Set elements must be hashable (got {ri!r})",
                            ctx=ErrorContext(path=tuple(ctx.path), node_type="SetElement"),
                            cause=e if ctx.options.wrap_exceptions else None,
                        )
                finally:
                    ctx.path.pop()
            return out_set

        # Scalars
        return value

    finally:
        ctx.depth -= 1


def _render_node(node: TemplateNode, ctx: RenderContext) -> Any:
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

    # Default handling:
    #   - default UNSET -> missing optional var becomes None
    #   - default OMIT / !omit -> omit the key/item
    if node.default is not UNSET:
        return _render_any(node.default, ctx)

    return None



def _render_default(node: Default, ctx: RenderContext) -> Any:
    """Render a !default node."""

    if node.default is UNSET:
        # Programmatic templates may omit a fallback; YAML loader enforces presence.
        raise RenderError(
            "!default requires a 'default' value",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Default"),
        )

    try:
        val = _render_any(node.value, ctx)
    except (MissingVariableError, IncludeError):
        return _render_any(node.default, ctx)

    if node.treat_omit_as_missing and (val is OMIT or isinstance(val, Omit)):
        return _render_any(node.default, ctx)

    if node.treat_none_as_missing and val is None:
        return _render_any(node.default, ctx)

    return val


def _render_if(node: If, ctx: RenderContext) -> Any:
    ctx.path.append("test")
    try:
        test_val = _render_any(node.test, ctx)
    finally:
        ctx.path.pop()

    branch = node.then if test_val else node.else_
    return _render_any(branch, ctx)


def _iter_foreach_items(value: Any, *, materialize: bool) -> Any:
    """Coerce a !foreach input into an iterable.

    If `materialize` is True, iterators/generators are converted to a list up front.
    If False, we iterate streaming (useful for large or unbounded iterables).
    """

    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)):
        raise TypeError("Cannot iterate over string/bytes in !foreach")
    if not materialize:
        return value
    if isinstance(value, (list, tuple)):
        return value
    return list(value)


def _render_foreach(node: ForEach, ctx: RenderContext) -> Any:
    # Defensive validation for programmatic construction. YAML-loaded templates
    # should have been validated by the loader constructors.
    into = (node.into or "list").lower()
    if into in ("list", "set") and node.template is UNSET:
        raise RenderError(
            "!foreach requires 'template' for into:list/set",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
        )
    if into == "dict" and (node.key is UNSET or node.value is UNSET):
        raise RenderError(
            "!foreach requires both 'key' and 'value' for into:dict",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
        )

    ctx.path.append("in")
    try:
        seq_val = _render_any(node.in_, ctx)
    finally:
        ctx.path.pop()

    try:
        items = _iter_foreach_items(seq_val, materialize=ctx.options.materialize_foreach_iterables)
    except Exception as e:
        raise RenderError(
            f"!foreach 'in' is not iterable: {e}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
            cause=e if ctx.options.wrap_exceptions else None,
        )

    # `into` was already normalized above.
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
        # Keep the iteration index on the path for the entire per-item processing.
        # This materially improves error localization for duplicate keys and unhashable
        # outputs, and also makes `when:` failures point at the correct iteration.
        ctx.path.append(idx)
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
                rendered = _render_any(node.template, ctx)
                if rendered is OMIT or isinstance(rendered, Omit):
                    continue
                out_list.append(rendered)

            elif into == "set":
                rendered = _render_any(node.template, ctx)
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
                ctx.path.append("key")
                try:
                    rk = _render_any(node.key, ctx)
                finally:
                    ctx.path.pop()

                ctx.path.append("value")
                try:
                    rv = _render_any(node.value, ctx)
                finally:
                    ctx.path.pop()

                if rk is OMIT or isinstance(rk, Omit) or rv is OMIT or isinstance(rv, Omit):
                    continue

                # Ensure key is hashable; keep path pointing at the key.
                ctx.path.append("key")
                try:
                    hash(rk)
                except Exception as e:
                    raise RenderError(
                        f"!foreach into:dict produced unhashable key: {rk!r}",
                        ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="ForEach"),
                        cause=e if ctx.options.wrap_exceptions else None,
                    )
                finally:
                    ctx.path.pop()

                if rk in out_dict:
                    if conflict == "error":
                        raise RenderError(
                            f"Duplicate key produced by !foreach into:dict: {rk!r}",
                            ctx=ErrorContext(path=tuple(ctx.path) + ("key",), mark=node.mark, node_type="ForEach"),
                        )
                    if conflict == "first":
                        continue
                    # last-wins
                out_dict[rk] = rv
        finally:
            ctx.path.pop()
            ctx.scope = old_scope

    if into == "list":
        return out_list
    if into == "set":
        return out_set
    return out_dict  # type: ignore[return-value]


def _build_expr_env(ctx: RenderContext) -> Mapping[str, Any]:
    """Return the expression environment mapping.

    We use the ChainMap directly to avoid rebuilding a fresh dict for each `!expr`.
    """
    return ctx.scope


def _render_expr(node: Expr, ctx: RenderContext) -> Any:
    evaluator = ctx.expr_evaluator
    if evaluator is None:
        # Fallback (should not happen in normal usage): build an evaluator on demand.
        policy = ExprPolicy(
            allow_attribute_access=ctx.options.allow_attribute_access_in_expr,
            allow_function_calls=ctx.options.allow_function_calls_in_expr,
            allow_subscripts=ctx.options.allow_subscripts_in_expr,
            allow_method_calls=ctx.options.allow_method_calls_in_expr,
            allow_private_attributes=ctx.options.allow_private_attributes_in_expr,
        )

        def _fn_resolver(name: str) -> Optional[Callable[..., Any]]:
            if ctx.registry is None:
                return None
            fn = ctx.registry.get(name)
            return fn if callable(fn) else None

        evaluator = ExpressionEvaluator(policy=policy, function_resolver=_fn_resolver)
        ctx.expr_evaluator = evaluator

    env = _build_expr_env(ctx)

    cache = ctx.expr_compile_cache
    compiled = None
    if cache is not None:
        compiled = cache.get(node.expr)

    if compiled is None:
        try:
            compiled = evaluator.compile(
                node.expr,
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
            )
        except TemplateValidationError as e:
            if not ctx.options.wrap_exceptions:
                raise
            # Preserve the underlying reason (policy rejection / unsupported syntax) in the message.
            raise ExpressionError(
                f"Invalid expression: {node.expr!r}: {e.args[0]}",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
                cause=e,
            )
        except Exception as e:
            if not ctx.options.wrap_exceptions:
                raise
            raise ExpressionError(
                f"Invalid expression: {node.expr!r}: {e}",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
                cause=e,
            )
        if cache is not None:
            cache[node.expr] = compiled

    try:
        return evaluator.eval(compiled, env)
    except NameError as e:
        if not node.strict or not ctx.options.strict:
            if node.default is not UNSET:
                return _render_any(node.default, ctx)
            return None
        raise MissingVariableError(
            f"Missing name in !expr: {e.args[0]}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
            cause=e if ctx.options.wrap_exceptions else None,
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
        if ctx.options.wrap_exceptions:
            raise ExpressionError(
                str(e),
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Expr"),
                cause=e,
            )
        raise


def _render_call(node: Call, ctx: RenderContext, *, pipe_input: Any = None, include_pipe_input: bool = False) -> Any:
    if not ctx.options.allow_calls:
        raise RenderError(
            "!call is disabled by render options",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Call"),
        )

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
    if fn is None or not callable(fn):
        raise FunctionNotFoundError(
            f"Function not found (or not callable) in registry: {fn_val}",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Call"),
        )

    args = []
    if include_pipe_input:
        args.append(pipe_input)

    for i, a in enumerate(node.args):
        ctx.path.append("args")
        ctx.path.append(i)
        try:
            args.append(_render_any(a, ctx))
        finally:
            ctx.path.pop()
            ctx.path.pop()

    kwargs = {}
    for k, v in node.kwargs.items():
        ctx.path.append("kwargs")
        ctx.path.append(k)
        try:
            kwargs[k] = _render_any(v, ctx)
        finally:
            ctx.path.pop()
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

    ctx.path.append("pipe")
    ctx.path.append(0)
    try:
        value = _render_any(steps[0], ctx)
    finally:
        ctx.path.pop()
        ctx.path.pop()

    if value is OMIT or isinstance(value, Omit):
        return OMIT

    for i, stage in enumerate(steps[1:], start=1):
        ctx.path.append("pipe")
        ctx.path.append(i)
        try:
            if isinstance(stage, Call):
                value = _render_call(stage, ctx, pipe_input=value, include_pipe_input=True)
                continue

            rendered_stage = _render_any(stage, ctx)

            if isinstance(rendered_stage, str) and ctx.options.allow_pipe_registry_calls:
                # Treat strings as registry function names.
                if ctx.registry is None:
                    if ctx.options.strict_pipe_stages:
                        raise RenderError(
                            f"No registry provided; cannot resolve pipe stage function: {rendered_stage!r}",
                            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Pipe"),
                        )
                    value = rendered_stage
                    continue

                fn = ctx.registry.get(rendered_stage)
                if fn is not None and callable(fn):
                    try:
                        value = fn(value)
                    except Exception as e:
                        if ctx.options.wrap_exceptions:
                            raise FunctionCallError(
                                f"Function '{rendered_stage}' raised: {e}",
                                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Pipe"),
                                cause=e,
                            )
                        raise
                    continue

                if ctx.options.strict_pipe_stages:
                    avail: list[str] = []
                    keys_fn = getattr(ctx.registry, "keys", None)
                    if callable(keys_fn):
                        try:
                            avail = [str(k) for k in list(keys_fn())]
                        except Exception:
                            avail = []

                    msg = f"Unknown pipe stage function: {rendered_stage!r}"
                    if avail:
                        avail_sorted = sorted(avail)
                        sample = ", ".join(avail_sorted[:20])
                        if len(avail_sorted) > 20:
                            sample += f", ... (+{len(avail_sorted) - 20} more)"
                        msg += f" (available: {sample})"

                    raise RenderError(
                        msg,
                        ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Pipe"),
                    )

                # If the string is not a known registry function, treat it as a literal value.
                value = rendered_stage
                continue

            if callable(rendered_stage):
                if not ctx.options.allow_callable_pipe_stages:
                    raise RenderError(
                        "Callable pipe stages are disabled. Use !call or a string stage naming a registry function.",
                        ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Pipe"),
                    )
                try:
                    value = rendered_stage(value)
                except Exception as e:
                    if ctx.options.wrap_exceptions:
                        raise RenderError(
                            f"Callable pipe stage raised: {e}",
                            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="Pipe"),
                            cause=e,
                        )
                    raise
                continue

            value = rendered_stage
        finally:
            ctx.path.pop()
            ctx.path.pop()

    return value


def _render_include_runtime(node: IncludeRuntime, ctx: RenderContext) -> Any:
    if not ctx.options.allow_includes:
        raise IncludeError(
            "Render-time includes are disabled by render options",
            ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
        )

    resolver = ctx.include_resolver
    if resolver is None and ctx.engine is not None:
        resolver = getattr(ctx.engine, "include_resolver", None)

    if resolver is None:
        if node.required and ctx.options.strict:
            raise IncludeError(
                "!include_rt requires an include_resolver",
                ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
            )
        if node.default is not UNSET:
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
        if node.default is not UNSET:
            return _render_any(node.default, ctx)
        return None

    # Optional include depth limiting (mirrors TemplateEngine load-time includes).
    if ctx.engine is not None:
        max_depth = getattr(ctx.engine, "max_include_depth", None)
        if max_depth is not None and max_depth >= 0:
            if len(ctx.include_stack) >= max_depth:
                raise IncludeError(
                    f"Maximum include depth exceeded (max_include_depth={max_depth})",
                    ctx=ErrorContext(path=tuple(ctx.path), mark=node.mark, node_type="IncludeRuntime"),
                )

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
        included_tmpl: Any

        cache = ctx.runtime_include_cache
        if cache is not None:
            if res.key in cache:
                # LRU: bump to the end on access
                included_tmpl = cache.pop(res.key)
                cache[res.key] = included_tmpl
            else:
                included_tmpl = ctx.engine.load_template_text(res.content, source_name=res.source_name)
                cache[res.key] = included_tmpl

                maxn = ctx.options.runtime_include_cache_max
                if maxn is not None and maxn > 0:
                    while len(cache) > maxn:
                        # Evict the oldest entry (in insertion/LRU order).
                        oldest = next(iter(cache))
                        cache.pop(oldest, None)
        else:
            included_tmpl = ctx.engine.load_template_text(res.content, source_name=res.source_name)

        return _render_any(included_tmpl, ctx)
    finally:
        ctx.include_stack.pop()
