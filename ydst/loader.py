from __future__ import annotations

from typing import Any, Optional

import yaml

from .errors import ErrorContext, TemplateLoadError
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
    UNSET,
    Var,
)


def _mark_from_node(loader: yaml.Loader, node: yaml.Node) -> SourceMark:
    """Extract a best-effort SourceMark from a PyYAML node."""

    # PyYAML marks are 0-based; expose as 1-based.
    try:
        line = getattr(node.start_mark, "line", None)
        col = getattr(node.start_mark, "column", None)
        src = getattr(loader, "_ydst_source_name", None) or getattr(node.start_mark, "name", None)
        return SourceMark(
            source=src,
            line=(line + 1) if isinstance(line, int) else None,
            column=(col + 1) if isinstance(col, int) else None,
        )
    except Exception:
        return SourceMark()


def _ctx(mark: SourceMark, node_type: str) -> ErrorContext:
    return ErrorContext(mark=mark, node_type=node_type)


def _require_bool(m: dict[str, Any], key: str, default: bool, *, mark: SourceMark, node_type: str) -> bool:
    val = m.get(key, default)
    if not isinstance(val, bool):
        raise TemplateLoadError(
            f"{node_type}: '{key}' must be a boolean (got {type(val).__name__})",
            ctx=_ctx(mark, node_type),
        )
    return val


class TemplateLoaderMixin:
    """Mixin that adds ydst templating constructors to a PyYAML Loader class.

    Engines typically create a fresh subclass combining this mixin with a concrete PyYAML loader
    (e.g., yaml.SafeLoader, yaml.FullLoader).

    The engine sets the following attributes per loader instance prior to parsing:
      - _ydst_engine
      - _ydst_source_name
      - _ydst_include_resolver
      - _ydst_include_stack
    """

    _ydst_engine: Any
    _ydst_source_name: Optional[str]
    _ydst_include_resolver: Optional[IncludeResolver]
    _ydst_include_stack: list[str]

    @classmethod
    def add_ydst_constructors(cls) -> None:
        # Variable tags
        for t in ("!var", "!variable"):
            cls.add_constructor(t, _construct_var)

        cls.add_constructor("!if", _construct_if)
        cls.add_constructor("!foreach", _construct_foreach)

        for t in ("!omit",):
            cls.add_constructor(t, _construct_omit)

        cls.add_constructor("!expr", _construct_expr)

        cls.add_constructor("!call", _construct_call)
        cls.add_constructor("!pipe", _construct_pipe)

        # Includes: load-time include uses !include; render-time include uses !include_rt/!include_runtime.
        cls.add_constructor("!include", _construct_include)
        for t in ("!include_rt", "!include_runtime", "!include_render"):
            cls.add_constructor(t, _construct_include_rt)


def _construct_var(loader: yaml.Loader, node: yaml.Node) -> Var:
    mark = _mark_from_node(loader, node)
    if isinstance(node, yaml.ScalarNode):
        name = loader.construct_scalar(node)
        return Var(name=str(name), mark=mark)

    if isinstance(node, yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        name = m.get("name")
        if not isinstance(name, str) or not name:
            raise TemplateLoadError(
                "!var mapping form requires a non-empty 'name' string",
                ctx=_ctx(mark, "Var"),
            )
        required = _require_bool(m, "required", True, mark=mark, node_type="Var")
        default = m.get("default", UNSET)
        return Var(name=name, required=required, default=default, mark=mark)

    raise TemplateLoadError("Unsupported YAML node form for !var", ctx=_ctx(mark, "Var"))


def _construct_if(loader: yaml.Loader, node: yaml.Node) -> If:
    mark = _mark_from_node(loader, node)
    if not isinstance(node, yaml.MappingNode):
        raise TemplateLoadError(
            "!if requires mapping form: {test: ..., then: ..., else: ...}",
            ctx=_ctx(mark, "If"),
        )
    m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
    if "test" not in m or "then" not in m:
        raise TemplateLoadError("!if requires 'test' and 'then' keys", ctx=_ctx(mark, "If"))
    else_ = m.get("else", OMIT)
    return If(test=m["test"], then=m["then"], else_=else_, mark=mark)


def _construct_foreach(loader: yaml.Loader, node: yaml.Node) -> ForEach:
    mark = _mark_from_node(loader, node)
    if not isinstance(node, yaml.MappingNode):
        raise TemplateLoadError("!foreach requires mapping form", ctx=_ctx(mark, "ForEach"))

    m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]

    # NOTE: use key *presence* rather than truthiness so values like "" don't silently fall back.
    if "var" in m:
        var = m.get("var")
    elif "as" in m:
        var = m.get("as")
    else:
        var = "item"

    if not isinstance(var, str) or not var:
        raise TemplateLoadError("!foreach requires 'var' as a non-empty string", ctx=_ctx(mark, "ForEach"))

    # Distinguish missing from explicit null.
    if "in" not in m:
        raise TemplateLoadError("!foreach requires 'in'", ctx=_ctx(mark, "ForEach"))
    in_ = m.get("in")

    template = m.get("template")

    into_raw = m.get("into", "list")
    if not isinstance(into_raw, str) or not into_raw:
        raise TemplateLoadError("!foreach 'into' must be a non-empty string", ctx=_ctx(mark, "ForEach"))
    into = into_raw.lower()

    index = m.get("index")
    when = m.get("when")
    key = m.get("key")
    value = m.get("value")

    if into not in ("list", "dict", "set"):
        raise TemplateLoadError(
            "!foreach 'into' must be one of: list, dict, set",
            ctx=_ctx(mark, "ForEach"),
        )

    if into == "dict":
        # Require both key and value.
        if key is None or value is None:
            raise TemplateLoadError(
                "!foreach into:dict requires 'key' and 'value'",
                ctx=_ctx(mark, "ForEach"),
            )
    else:
        if template is None:
            raise TemplateLoadError(
                "!foreach requires 'template' (or use into:dict with key/value)",
                ctx=_ctx(mark, "ForEach"),
            )

    if index is not None and (not isinstance(index, str) or not index):
        raise TemplateLoadError("!foreach 'index' must be a non-empty string", ctx=_ctx(mark, "ForEach"))

    return ForEach(
        var=var,
        in_=in_,
        template=template,
        index=index,
        when=when,
        into=into,
        key=key,
        value=value,
        mark=mark,
    )


def _construct_omit(loader: yaml.Loader, node: yaml.Node) -> Omit:
    mark = _mark_from_node(loader, node)
    return Omit(mark=mark)


def _construct_expr(loader: yaml.Loader, node: yaml.Node) -> Expr:
    mark = _mark_from_node(loader, node)

    if isinstance(node, yaml.ScalarNode):
        expr = loader.construct_scalar(node)
        return Expr(expr=str(expr), mark=mark)

    if isinstance(node, yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        expr = m.get("expr")
        if not isinstance(expr, str) or not expr:
            raise TemplateLoadError(
                "!expr mapping form requires non-empty 'expr'",
                ctx=_ctx(mark, "Expr"),
            )
        strict = _require_bool(m, "strict", True, mark=mark, node_type="Expr")
        default = m.get("default", UNSET)
        return Expr(expr=expr, strict=strict, default=default, mark=mark)

    raise TemplateLoadError("Unsupported YAML node form for !expr", ctx=_ctx(mark, "Expr"))


def _construct_call(loader: yaml.Loader, node: yaml.Node) -> Call:
    mark = _mark_from_node(loader, node)

    if isinstance(node, yaml.ScalarNode):
        fn = loader.construct_scalar(node)
        return Call(fn=str(fn), mark=mark)

    if isinstance(node, yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        fn = m.get("fn") or m.get("name")
        if fn is None:
            raise TemplateLoadError("!call requires 'fn'", ctx=_ctx(mark, "Call"))

        args = m.get("args", [])
        kwargs = m.get("kwargs", {})
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}

        if not isinstance(args, list):
            raise TemplateLoadError("!call 'args' must be a list", ctx=_ctx(mark, "Call"))
        if not isinstance(kwargs, dict):
            raise TemplateLoadError("!call 'kwargs' must be a mapping", ctx=_ctx(mark, "Call"))

        return Call(fn=fn, args=args, kwargs=kwargs, mark=mark)

    raise TemplateLoadError("Unsupported YAML node form for !call", ctx=_ctx(mark, "Call"))


def _construct_pipe(loader: yaml.Loader, node: yaml.Node) -> Any:
    mark = _mark_from_node(loader, node)

    if isinstance(node, yaml.SequenceNode):
        steps = loader.construct_sequence(node, deep=True)  # type: ignore[attr-defined]
        from .nodes import Pipe

        return Pipe(steps=list(steps), mark=mark)

    # Allow scalar as a single-step pipeline.
    if isinstance(node, yaml.ScalarNode):
        step = loader.construct_scalar(node)
        from .nodes import Pipe

        return Pipe(steps=[step], mark=mark)

    raise TemplateLoadError("!pipe requires a sequence", ctx=_ctx(mark, "Pipe"))


def _construct_include(loader: yaml.Loader, node: yaml.Node) -> Any:
    """Load-time include by default; can be configured to return a runtime include node."""

    mark = _mark_from_node(loader, node)

    def _as_runtime(target: Any, required: bool = True, default: Any = UNSET) -> IncludeRuntime:
        return IncludeRuntime(target=target, required=required, default=default, mark=mark)

    # Scalar form: !include "file.yaml" (load-time include).
    if isinstance(node, yaml.ScalarNode):
        target = loader.construct_scalar(node)
        if not isinstance(target, str) or not target:
            raise TemplateLoadError("!include requires a non-empty string target", ctx=_ctx(mark, "Include"))
        return _resolve_load_time_include(loader, target, mark)

    if isinstance(node, yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]

        timing_val = m.get("timing", "load")
        if not isinstance(timing_val, str) or not timing_val:
            raise TemplateLoadError("!include 'timing' must be a non-empty string", ctx=_ctx(mark, "Include"))
        timing = timing_val.lower()

        target = m.get("target") or m.get("path") or m.get("file")
        if target is None:
            raise TemplateLoadError("!include mapping form requires 'target'", ctx=_ctx(mark, "Include"))

        required = _require_bool(m, "required", True, mark=mark, node_type="Include")
        default = m.get("default", UNSET)

        if timing in ("render", "runtime", "rt"):
            # Render-time includes may be templated.
            return _as_runtime(target=target, required=required, default=default)

        if timing not in ("load", "parse"):
            raise TemplateLoadError(
                "!include 'timing' must be one of: load, render",
                ctx=_ctx(mark, "Include"),
            )

        # Load-time include requires a literal target string (no templating).
        if not isinstance(target, str) or not target:
            raise TemplateLoadError(
                "!include load-time form requires 'target' to be a non-empty string",
                ctx=_ctx(mark, "Include"),
            )

        return _resolve_load_time_include(loader, target, mark, required=required, default=default)

    raise TemplateLoadError("Unsupported YAML node form for !include", ctx=_ctx(mark, "Include"))


def _construct_include_rt(loader: yaml.Loader, node: yaml.Node) -> IncludeRuntime:
    mark = _mark_from_node(loader, node)

    if isinstance(node, yaml.ScalarNode):
        target = loader.construct_scalar(node)
        if not isinstance(target, str) or not target:
            raise TemplateLoadError("!include_rt requires a non-empty string target", ctx=_ctx(mark, "IncludeRuntime"))
        return IncludeRuntime(target=target, mark=mark)

    if isinstance(node, yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        target = m.get("target") or m.get("path") or m.get("file")
        if target is None:
            raise TemplateLoadError("!include_rt requires 'target'", ctx=_ctx(mark, "IncludeRuntime"))
        required = _require_bool(m, "required", True, mark=mark, node_type="IncludeRuntime")
        default = m.get("default", UNSET)
        return IncludeRuntime(target=target, required=required, default=default, mark=mark)

    raise TemplateLoadError("Unsupported YAML node form for !include_rt", ctx=_ctx(mark, "IncludeRuntime"))


def _resolve_load_time_include(
    loader: yaml.Loader,
    target: str,
    mark: SourceMark,
    *,
    required: bool = True,
    default: Any = UNSET,
) -> Any:
    engine = getattr(loader, "_ydst_engine", None)
    resolver = getattr(loader, "_ydst_include_resolver", None)

    if engine is None:
        raise TemplateLoadError(
            "Internal error: loader has no engine for !include",
            ctx=_ctx(mark, "Include"),
        )

    if resolver is None:
        if required:
            raise TemplateLoadError("!include requires an include_resolver", ctx=_ctx(mark, "Include"))
        return None if default is UNSET else default

    return engine._load_time_include(
        target,
        from_source=getattr(loader, "_ydst_source_name", None),
        mark=mark,
        include_stack=getattr(loader, "_ydst_include_stack", None),
        required=required,
        default=default,
    )
