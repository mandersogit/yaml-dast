from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Type

import yaml

from .errors import ErrorContext, TemplateLoadError
from .nodes import (
    Call,
    Expr,
    ForEach,
    If,
    IncludeRuntime,
    Omit,
    OMIT,
    UNSET,
    SourceMark,
    Var,
)
from .include import IncludeResolver


def _mark_from_node(loader: yaml.Loader, node: yaml.Node) -> SourceMark:
    # PyYAML marks are 0-based; expose as 1-based
    try:
        line = getattr(node.start_mark, "line", None)
        col = getattr(node.start_mark, "column", None)
        src = getattr(loader, "_ydst_source_name", None) or getattr(node.start_mark, "name", None)
        return SourceMark(source=src, line=(line + 1) if isinstance(line, int) else None, column=(col + 1) if isinstance(col, int) else None)
    except Exception:
        return SourceMark()


class TemplateLoaderMixin:
    """Mixin that adds ydst templating constructors to a PyYAML Loader class.

    Engines typically create a fresh subclass combining this mixin with a concrete PyYAML loader
    (e.g., yaml.SafeLoader, yaml.FullLoader).
    """

    # The engine sets these attributes per loader instance prior to parsing.
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
            raise TemplateLoadError("!var mapping form requires a non-empty 'name' string", ctx=ErrorContext(mark=mark, node_type="Var"))
        required = bool(m.get("required", True))
        default = m.get("default", UNSET)
        return Var(name=name, required=required, default=default, mark=mark)

    raise TemplateLoadError("Unsupported YAML node form for !var", ctx=ErrorContext(mark=mark, node_type="Var"))


def _construct_if(loader: yaml.Loader, node: yaml.Node) -> If:
    mark = _mark_from_node(loader, node)
    if not isinstance(node, yaml.MappingNode):
        raise TemplateLoadError("!if requires mapping form: {test: ..., then: ..., else: ...}", ctx=ErrorContext(mark=mark, node_type="If"))
    m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
    if "test" not in m or "then" not in m:
        raise TemplateLoadError("!if requires 'test' and 'then' keys", ctx=ErrorContext(mark=mark, node_type="If"))
    else_ = m.get("else", OMIT)
    return If(test=m["test"], then=m["then"], else_=else_, mark=mark)


def _construct_foreach(loader: yaml.Loader, node: yaml.Node) -> ForEach:
    mark = _mark_from_node(loader, node)
    if not isinstance(node, yaml.MappingNode):
        raise TemplateLoadError("!foreach requires mapping form", ctx=ErrorContext(mark=mark, node_type="ForEach"))
    m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
    var = m.get("var") or m.get("as") or "item"
    if not isinstance(var, str) or not var:
        raise TemplateLoadError("!foreach requires 'var' as a non-empty string", ctx=ErrorContext(mark=mark, node_type="ForEach"))
    in_ = m.get("in")
    if in_ is None:
        raise TemplateLoadError("!foreach requires 'in'", ctx=ErrorContext(mark=mark, node_type="ForEach"))
    template = m.get("template")
    into = str(m.get("into", "list"))
    index = m.get("index")
    when = m.get("when")
    key = m.get("key")
    value = m.get("value")

    if into not in ("list", "dict", "set"):
        raise TemplateLoadError("!foreach 'into' must be one of: list, dict, set", ctx=ErrorContext(mark=mark, node_type="ForEach"))

    if into == "dict":
        if key is None or value is None:
            raise TemplateLoadError("!foreach into:dict requires 'key' and 'value'", ctx=ErrorContext(mark=mark, node_type="ForEach"))
    else:
        if template is None:
            raise TemplateLoadError("!foreach requires 'template' (or use into:dict with key/value)", ctx=ErrorContext(mark=mark, node_type="ForEach"))

    if index is not None and (not isinstance(index, str) or not index):
        raise TemplateLoadError("!foreach 'index' must be a non-empty string", ctx=ErrorContext(mark=mark, node_type="ForEach"))

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
    # no content needed
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
            raise TemplateLoadError("!expr mapping form requires non-empty 'expr'", ctx=ErrorContext(mark=mark, node_type="Expr"))
        strict = bool(m.get("strict", True))
        default = m.get("default", UNSET)
        return Expr(expr=expr, strict=strict, default=default, mark=mark)

    raise TemplateLoadError("Unsupported YAML node form for !expr", ctx=ErrorContext(mark=mark, node_type="Expr"))


def _construct_call(loader: yaml.Loader, node: yaml.Node) -> Call:
    mark = _mark_from_node(loader, node)
    if isinstance(node, yaml.ScalarNode):
        fn = loader.construct_scalar(node)
        return Call(fn=str(fn), mark=mark)

    if isinstance(node, yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        fn = m.get("fn") or m.get("name")
        if fn is None:
            raise TemplateLoadError("!call requires 'fn'", ctx=ErrorContext(mark=mark, node_type="Call"))
        args = m.get("args", [])
        kwargs = m.get("kwargs", {})
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        if not isinstance(args, list):
            raise TemplateLoadError("!call 'args' must be a list", ctx=ErrorContext(mark=mark, node_type="Call"))
        if not isinstance(kwargs, dict):
            raise TemplateLoadError("!call 'kwargs' must be a mapping", ctx=ErrorContext(mark=mark, node_type="Call"))
        return Call(fn=fn, args=args, kwargs=kwargs, mark=mark)

    raise TemplateLoadError("Unsupported YAML node form for !call", ctx=ErrorContext(mark=mark, node_type="Call"))


def _construct_pipe(loader: yaml.Loader, node: yaml.Node) -> Any:
    mark = _mark_from_node(loader, node)
    if isinstance(node, yaml.SequenceNode):
        steps = loader.construct_sequence(node, deep=True)  # type: ignore[attr-defined]
        from .nodes import Pipe

        return Pipe(steps=list(steps), mark=mark)

    # allow mapping/scalar? treat as single-step pipeline
    if isinstance(node, yaml.ScalarNode):
        step = loader.construct_scalar(node)
        from .nodes import Pipe

        return Pipe(steps=[step], mark=mark)

    raise TemplateLoadError("!pipe requires a sequence", ctx=ErrorContext(mark=mark, node_type="Pipe"))


def _construct_include(loader: yaml.Loader, node: yaml.Node) -> Any:
    """Load-time include by default; can be configured to return a runtime include node."""
    mark = _mark_from_node(loader, node)

    def _as_runtime(target: Any, required: bool = True, default: Any = UNSET) -> IncludeRuntime:
        return IncludeRuntime(target=target, required=required, default=default, mark=mark)

    # scalar form: !include "file.yaml" (load-time include)
    if isinstance(node, yaml.ScalarNode):
        target = loader.construct_scalar(node)
        return _resolve_load_time_include(loader, str(target), mark)

    if isinstance(node, yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        timing = str(m.get("timing", "load")).lower()
        target = m.get("target") or m.get("path") or m.get("file")
        if target is None:
            raise TemplateLoadError("!include mapping form requires 'target'", ctx=ErrorContext(mark=mark, node_type="Include"))
        required = bool(m.get("required", True))
        default = m.get("default", UNSET)

        if timing in ("render", "runtime", "rt"):
            return _as_runtime(target=target, required=required, default=default)
        return _resolve_load_time_include(loader, str(target), mark, required=required, default=default)

    raise TemplateLoadError("Unsupported YAML node form for !include", ctx=ErrorContext(mark=mark, node_type="Include"))


def _construct_include_rt(loader: yaml.Loader, node: yaml.Node) -> IncludeRuntime:
    mark = _mark_from_node(loader, node)
    if isinstance(node, yaml.ScalarNode):
        target = loader.construct_scalar(node)
        return IncludeRuntime(target=str(target), mark=mark)
    if isinstance(node, yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        target = m.get("target") or m.get("path") or m.get("file")
        if target is None:
            raise TemplateLoadError("!include_rt requires 'target'", ctx=ErrorContext(mark=mark, node_type="IncludeRuntime"))
        required = bool(m.get("required", True))
        default = m.get("default", UNSET)
        return IncludeRuntime(target=target, required=required, default=default, mark=mark)
    raise TemplateLoadError("Unsupported YAML node form for !include_rt", ctx=ErrorContext(mark=mark, node_type="IncludeRuntime"))


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
        raise TemplateLoadError("Internal error: loader has no engine for !include", ctx=ErrorContext(mark=mark, node_type="Include"))
    if resolver is None:
        if required:
            raise TemplateLoadError("!include requires an include_resolver", ctx=ErrorContext(mark=mark, node_type="Include"))
        return None if default is UNSET else default
    return engine._load_time_include(target, from_source=getattr(loader, "_ydst_source_name", None), mark=mark, include_stack=getattr(loader, "_ydst_include_stack", None), required=required, default=default)
