from __future__ import annotations

import typing as _typing

import yaml as _yaml

import ydst.errors as errors
import ydst.include as include
import ydst.nodes as nodes


def _mark_from_node(loader: _yaml.Loader, node: _yaml.Node) -> nodes.SourceMark:
    """Extract a best-effort SourceMark from a PyYAML node."""

    # PyYAML marks are 0-based; expose as 1-based.
    try:
        line = getattr(node.start_mark, "line", None)
        col = getattr(node.start_mark, "column", None)
        src = getattr(loader, "_ydst_source_name", None) or getattr(node.start_mark, "name", None)
        return nodes.SourceMark(
            source=src,
            line=(line + 1) if isinstance(line, int) else None,
            column=(col + 1) if isinstance(col, int) else None,
        )
    except Exception:
        return nodes.SourceMark()


def _ctx(mark: nodes.SourceMark, node_type: str) -> errors.ErrorContext:
    return errors.ErrorContext(mark=mark, node_type=node_type)


def _require_bool(
    m: dict[_typing.Hashable, _typing.Any],
    key: str,
    default: bool,
    *,
    mark: nodes.SourceMark,
    node_type: str,
) -> bool:
    val = m.get(key, default)
    if not isinstance(val, bool):
        raise errors.TemplateLoadError(
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

    _ydst_engine: _typing.Any
    _ydst_source_name: str | None
    _ydst_include_resolver: include.IncludeResolver | None
    _ydst_include_stack: list[str]

    @classmethod
    def add_ydst_constructors(cls) -> None:
        # The add_constructor method comes from yaml.Loader when this mixin is combined with it.
        # Variable tags
        cls.add_constructor("!var", _construct_var)  # type: ignore[attr-defined]

        cls.add_constructor("!default", _construct_default)  # type: ignore[attr-defined]

        cls.add_constructor("!if", _construct_if)  # type: ignore[attr-defined]
        cls.add_constructor("!foreach", _construct_foreach)  # type: ignore[attr-defined]

        cls.add_constructor("!omit", _construct_omit)  # type: ignore[attr-defined]

        cls.add_constructor("!expr", _construct_expr)  # type: ignore[attr-defined]

        cls.add_constructor("!call", _construct_call)  # type: ignore[attr-defined]
        cls.add_constructor("!pipe", _construct_pipe)  # type: ignore[attr-defined]

        # Includes:
        #   - !include: load-time include
        #   - !include_rt: render-time include
        cls.add_constructor("!include", _construct_include)  # type: ignore[attr-defined]
        cls.add_constructor("!include_rt", _construct_include_rt)  # type: ignore[attr-defined]

        # Opt-in power tags:
        cls.add_constructor("!setdefault", _construct_setdefault)  # type: ignore[attr-defined]
        cls.add_constructor("!python", _construct_python)  # type: ignore[attr-defined]
        cls.add_constructor("!python_module", _construct_python_module)  # type: ignore[attr-defined]


def _construct_var(loader: _yaml.Loader, node: _yaml.Node) -> nodes.Var:
    mark = _mark_from_node(loader, node)
    if isinstance(node, _yaml.ScalarNode):
        scalar_name = loader.construct_scalar(node)
        return nodes.Var(name=str(scalar_name), mark=mark)

    if isinstance(node, _yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        name: _typing.Any = m.get("name")
        if not isinstance(name, str) or not name:
            raise errors.TemplateLoadError(
                "!var mapping form requires a non-empty 'name' string",
                ctx=_ctx(mark, "Var"),
            )
        required = _require_bool(m, "required", True, mark=mark, node_type="Var")
        default = m.get("default", nodes.UNSET)
        return nodes.Var(name=name, required=required, default=default, mark=mark)

    raise errors.TemplateLoadError("Unsupported YAML node form for !var", ctx=_ctx(mark, "Var"))


def _construct_default(loader: _yaml.Loader, node: _yaml.Node) -> nodes.Default:
    """Construct a !default node.

    Forms:
      - !default {value: <template>, default: <template>, treat_none_as_missing?: bool, treat_omit_as_missing?: bool}
      - !default [<value>, <default>]
    """

    mark = _mark_from_node(loader, node)

    if isinstance(node, _yaml.SequenceNode):
        seq = loader.construct_sequence(node, deep=True)  # type: ignore[attr-defined]
        if not isinstance(seq, list) or len(seq) != 2:
            raise errors.TemplateLoadError(
                "!default sequence form requires exactly 2 items: [value, default]",
                ctx=_ctx(mark, "Default"),
            )
        value, default = seq
        return nodes.Default(value=value, default=default, mark=mark)

    if isinstance(node, _yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]

        if "value" not in m and "val" not in m:
            raise errors.TemplateLoadError("!default requires 'value'", ctx=_ctx(mark, "Default"))
        value = m.get("value", m.get("val"))

        if "default" not in m and "fallback" not in m:
            raise errors.TemplateLoadError("!default requires 'default' (or 'fallback')", ctx=_ctx(mark, "Default"))
        default = m.get("default", m.get("fallback"))

        treat_none_as_missing = _require_bool(
            m,
            "treat_none_as_missing",
            True,
            mark=mark,
            node_type="Default",
        )
        treat_omit_as_missing = _require_bool(
            m,
            "treat_omit_as_missing",
            True,
            mark=mark,
            node_type="Default",
        )

        return nodes.Default(
            value=value,
            default=default,
            treat_none_as_missing=treat_none_as_missing,
            treat_omit_as_missing=treat_omit_as_missing,
            mark=mark,
        )

    raise errors.TemplateLoadError("Unsupported YAML node form for !default", ctx=_ctx(mark, "Default"))


def _construct_if(loader: _yaml.Loader, node: _yaml.Node) -> nodes.If:
    mark = _mark_from_node(loader, node)
    if not isinstance(node, _yaml.MappingNode):
        raise errors.TemplateLoadError(
            "!if requires mapping form: {test: ..., then: ..., else: ...}",
            ctx=_ctx(mark, "If"),
        )
    m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
    if "test" not in m or "then" not in m:
        raise errors.TemplateLoadError("!if requires 'test' and 'then' keys", ctx=_ctx(mark, "If"))
    else_ = m.get("else", nodes.OMIT)
    return nodes.If(test=m["test"], then=m["then"], else_=else_, mark=mark)


def _construct_foreach(loader: _yaml.Loader, node: _yaml.Node) -> nodes.ForEach:
    mark = _mark_from_node(loader, node)
    if not isinstance(node, _yaml.MappingNode):
        raise errors.TemplateLoadError("!foreach requires mapping form", ctx=_ctx(mark, "ForEach"))

    m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]

    # NOTE: use key *presence* rather than truthiness so values like "" don't silently fall back.
    if "var" in m:
        var = m.get("var")
    elif "as" in m:
        var = m.get("as")
    else:
        var = "item"

    if not isinstance(var, str) or not var:
        raise errors.TemplateLoadError("!foreach requires 'var' as a non-empty string", ctx=_ctx(mark, "ForEach"))

    # Distinguish missing from explicit null.
    if "in" not in m:
        raise errors.TemplateLoadError("!foreach requires 'in'", ctx=_ctx(mark, "ForEach"))
    in_ = m.get("in")

    # Distinguish missing from explicit null.
    has_template = "template" in m
    template = m.get("template")

    into_raw = m.get("into", "list")
    if not isinstance(into_raw, str) or not into_raw:
        raise errors.TemplateLoadError("!foreach 'into' must be a non-empty string", ctx=_ctx(mark, "ForEach"))
    into = into_raw.lower()

    index = m.get("index")
    when = m.get("when")
    # Distinguish missing from explicit null.
    has_key = "key" in m
    has_value = "value" in m
    key = m.get("key")
    value = m.get("value")

    if into not in ("list", "dict", "set"):
        raise errors.TemplateLoadError(
            "!foreach 'into' must be one of: list, dict, set",
            ctx=_ctx(mark, "ForEach"),
        )

    if into == "dict":
        # Require both key and value (presence, not truthiness).
        # YAML `null` is a valid value for key/value templates.
        if not has_key or not has_value:
            raise errors.TemplateLoadError(
                "!foreach into:dict requires 'key' and 'value'",
                ctx=_ctx(mark, "ForEach"),
            )
    else:
        # Require template presence (YAML `null` is valid).
        if not has_template:
            raise errors.TemplateLoadError(
                "!foreach requires 'template' (or use into:dict with key/value)",
                ctx=_ctx(mark, "ForEach"),
            )

    if index is not None and (not isinstance(index, str) or not index):
        raise errors.TemplateLoadError("!foreach 'index' must be a non-empty string", ctx=_ctx(mark, "ForEach"))

    return nodes.ForEach(
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


def _construct_omit(loader: _yaml.Loader, node: _yaml.Node) -> nodes.Omit:
    mark = _mark_from_node(loader, node)
    return nodes.Omit(mark=mark)


def _construct_expr(loader: _yaml.Loader, node: _yaml.Node) -> nodes.Expr:
    mark = _mark_from_node(loader, node)

    if isinstance(node, _yaml.ScalarNode):
        scalar_expr = loader.construct_scalar(node)
        return nodes.Expr(expr=str(scalar_expr), mark=mark)

    if isinstance(node, _yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        expr: _typing.Any = m.get("expr")
        if not isinstance(expr, str) or not expr:
            raise errors.TemplateLoadError(
                "!expr mapping form requires non-empty 'expr'",
                ctx=_ctx(mark, "Expr"),
            )
        strict = _require_bool(m, "strict", True, mark=mark, node_type="Expr")
        default = m.get("default", nodes.UNSET)
        return nodes.Expr(expr=expr, strict=strict, default=default, mark=mark)

    raise errors.TemplateLoadError("Unsupported YAML node form for !expr", ctx=_ctx(mark, "Expr"))


def _construct_call(loader: _yaml.Loader, node: _yaml.Node) -> nodes.Call:
    mark = _mark_from_node(loader, node)

    if isinstance(node, _yaml.ScalarNode):
        scalar_fn = loader.construct_scalar(node)
        return nodes.Call(fn=str(scalar_fn), mark=mark)

    if isinstance(node, _yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        fn: _typing.Any = m.get("fn") or m.get("name")
        if fn is None:
            raise errors.TemplateLoadError("!call requires 'fn'", ctx=_ctx(mark, "Call"))

        args = m.get("args", [])
        kwargs = m.get("kwargs", {})
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}

        if not isinstance(args, list):
            raise errors.TemplateLoadError("!call 'args' must be a list", ctx=_ctx(mark, "Call"))
        if not isinstance(kwargs, dict):
            raise errors.TemplateLoadError("!call 'kwargs' must be a mapping", ctx=_ctx(mark, "Call"))

        return nodes.Call(fn=fn, args=args, kwargs=kwargs, mark=mark)

    raise errors.TemplateLoadError("Unsupported YAML node form for !call", ctx=_ctx(mark, "Call"))


def _construct_pipe(loader: _yaml.Loader, node: _yaml.Node) -> nodes.Pipe:
    mark = _mark_from_node(loader, node)

    if isinstance(node, _yaml.SequenceNode):
        steps = loader.construct_sequence(node, deep=True)  # type: ignore[attr-defined]
        return nodes.Pipe(steps=list(steps), mark=mark)

    # Allow scalar as a single-step pipeline.
    if isinstance(node, _yaml.ScalarNode):
        step = loader.construct_scalar(node)
        return nodes.Pipe(steps=[step], mark=mark)

    raise errors.TemplateLoadError("!pipe requires a sequence", ctx=_ctx(mark, "Pipe"))


def _construct_include(loader: _yaml.Loader, node: _yaml.Node) -> _typing.Any:
    """Load-time include.

    Notes
    -----
    - `!include` is *load-time only*.
    - For render-time includes (templated targets), use `!include_rt`.
    """

    mark = _mark_from_node(loader, node)

    # Scalar form: !include "file.yaml" (load-time include).
    if isinstance(node, _yaml.ScalarNode):
        scalar_target = loader.construct_scalar(node)
        if not isinstance(scalar_target, str) or not scalar_target:
            raise errors.TemplateLoadError("!include requires a non-empty string target", ctx=_ctx(mark, "Include"))
        return _resolve_load_time_include(loader, scalar_target, mark)

    if isinstance(node, _yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]

        if "timing" in m:
            raise errors.TemplateLoadError(
                "!include no longer supports 'timing:'; use !include_rt for render-time includes",
                ctx=_ctx(mark, "Include"),
            )

        target: _typing.Any = m.get("target") or m.get("path") or m.get("file")
        if target is None:
            raise errors.TemplateLoadError("!include mapping form requires 'target'", ctx=_ctx(mark, "Include"))

        required = _require_bool(m, "required", True, mark=mark, node_type="Include")
        default = m.get("default", nodes.UNSET)

        # Load-time include requires a literal target string (no templating).
        if not isinstance(target, str) or not target:
            raise errors.TemplateLoadError(
                "!include requires 'target' to be a non-empty string (templated targets must use !include_rt)",
                ctx=_ctx(mark, "Include"),
            )

        return _resolve_load_time_include(loader, target, mark, required=required, default=default)

    raise errors.TemplateLoadError("Unsupported YAML node form for !include", ctx=_ctx(mark, "Include"))


def _construct_include_rt(loader: _yaml.Loader, node: _yaml.Node) -> nodes.IncludeRuntime:
    mark = _mark_from_node(loader, node)

    if isinstance(node, _yaml.ScalarNode):
        scalar_target = loader.construct_scalar(node)
        if not isinstance(scalar_target, str) or not scalar_target:
            raise errors.TemplateLoadError(
                "!include_rt requires a non-empty string target",
                ctx=_ctx(mark, "IncludeRuntime"),
            )
        return nodes.IncludeRuntime(target=scalar_target, mark=mark)

    if isinstance(node, _yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        target: _typing.Any = m.get("target") or m.get("path") or m.get("file")
        if target is None:
            raise errors.TemplateLoadError("!include_rt requires 'target'", ctx=_ctx(mark, "IncludeRuntime"))
        required = _require_bool(m, "required", True, mark=mark, node_type="IncludeRuntime")
        default = m.get("default", nodes.UNSET)
        return nodes.IncludeRuntime(target=target, required=required, default=default, mark=mark)

    raise errors.TemplateLoadError("Unsupported YAML node form for !include_rt", ctx=_ctx(mark, "IncludeRuntime"))


def _construct_setdefault(loader: _yaml.Loader, node: _yaml.Node) -> nodes.SetDefault:
    mark = _mark_from_node(loader, node)

    if isinstance(node, _yaml.SequenceNode):
        seq = loader.construct_sequence(node, deep=True)  # type: ignore[attr-defined]
        if not isinstance(seq, list) or len(seq) != 2:
            raise errors.TemplateLoadError(
                "!setdefault sequence form requires exactly 2 items: [name, value]",
                ctx=_ctx(mark, "SetDefault"),
            )
        name, value = seq
        if not isinstance(name, str) or not name:
            raise errors.TemplateLoadError(
                "!setdefault name must be a non-empty string",
                ctx=_ctx(mark, "SetDefault"),
            )
        return nodes.SetDefault(defaults={name: value}, mark=mark)

    if isinstance(node, _yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]

        # Explicit single-var mapping form: {name: ..., value/default: ...}
        if "name" in m or "var" in m:
            name = m.get("name", m.get("var"))
            if not isinstance(name, str) or not name:
                raise errors.TemplateLoadError(
                    "!setdefault 'name' must be a non-empty string",
                    ctx=_ctx(mark, "SetDefault"),
                )
            if "value" in m:
                value = m.get("value")
            elif "default" in m:
                value = m.get("default")
            else:
                raise errors.TemplateLoadError(
                    "!setdefault mapping form requires 'value' (or 'default')",
                    ctx=_ctx(mark, "SetDefault"),
                )
            return nodes.SetDefault(defaults={name: value}, mark=mark)

        # Multi-var mapping form: {var1: ..., var2: ...}
        defaults: dict[str, _typing.Any] = {}
        for k, v in m.items():
            if not isinstance(k, str) or not k:
                raise errors.TemplateLoadError(
                    "!setdefault multi-mapping form requires non-empty string keys",
                    ctx=_ctx(mark, "SetDefault"),
                )
            defaults[k] = v
        return nodes.SetDefault(defaults=defaults, mark=mark)

    raise errors.TemplateLoadError("Unsupported YAML node form for !setdefault", ctx=_ctx(mark, "SetDefault"))


def _construct_python(loader: _yaml.Loader, node: _yaml.Node) -> nodes.Python:
    mark = _mark_from_node(loader, node)

    if isinstance(node, _yaml.ScalarNode):
        scalar_code = loader.construct_scalar(node)
        if not isinstance(scalar_code, str) or not scalar_code.strip():
            raise errors.TemplateLoadError(
                "!python requires a non-empty code string",
                ctx=_ctx(mark, "Python"),
            )
        return nodes.Python(code=scalar_code, mark=mark)

    if isinstance(node, _yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        code: _typing.Any = m.get("code") or m.get("python") or m.get("py")
        if not isinstance(code, str) or not code.strip():
            raise errors.TemplateLoadError(
                "!python mapping form requires a non-empty 'code' string",
                ctx=_ctx(mark, "Python"),
            )
        strict_emit = m.get("strict_emit", None)
        if strict_emit is not None and not isinstance(strict_emit, bool):
            raise errors.TemplateLoadError(
                "Python: 'strict_emit' must be a boolean when provided",
                ctx=_ctx(mark, "Python"),
            )
        return nodes.Python(code=code, strict_emit=strict_emit, mark=mark)

    raise errors.TemplateLoadError("Unsupported YAML node form for !python", ctx=_ctx(mark, "Python"))


def _construct_python_module(loader: _yaml.Loader, node: _yaml.Node) -> nodes.PythonModule:
    mark = _mark_from_node(loader, node)

    if isinstance(node, _yaml.ScalarNode):
        code = loader.construct_scalar(node)
        if not isinstance(code, str) or not code.strip():
            raise errors.TemplateLoadError(
                "!python_module requires a non-empty code string",
                ctx=_ctx(mark, "PythonModule"),
            )
        return nodes.PythonModule(code=code, mark=mark)

    if isinstance(node, _yaml.MappingNode):
        m = loader.construct_mapping(node, deep=True)  # type: ignore[attr-defined]
        code_val: _typing.Any = m.get("code") or m.get("python") or m.get("py")
        if not isinstance(code_val, str) or not code_val.strip():
            raise errors.TemplateLoadError(
                "!python_module mapping form requires a non-empty 'code' string",
                ctx=_ctx(mark, "PythonModule"),
            )
        return nodes.PythonModule(code=code_val, mark=mark)

    raise errors.TemplateLoadError(
        "Unsupported YAML node form for !python_module",
        ctx=_ctx(mark, "PythonModule"),
    )


def _resolve_load_time_include(
    loader: _yaml.Loader,
    target: str,
    mark: nodes.SourceMark,
    *,
    required: bool = True,
    default: _typing.Any = nodes.UNSET,
) -> _typing.Any:
    engine = getattr(loader, "_ydst_engine", None)
    resolver = getattr(loader, "_ydst_include_resolver", None)

    if engine is None:
        raise errors.TemplateLoadError(
            "Internal error: loader has no engine for !include",
            ctx=_ctx(mark, "Include"),
        )

    if resolver is None:
        if required:
            raise errors.TemplateLoadError("!include requires an include_resolver", ctx=_ctx(mark, "Include"))
        return None if default is nodes.UNSET else default

    return engine._load_time_include(
        target,
        from_source=getattr(loader, "_ydst_source_name", None),
        mark=mark,
        include_stack=getattr(loader, "_ydst_include_stack", None),
        required=required,
        default=default,
    )
