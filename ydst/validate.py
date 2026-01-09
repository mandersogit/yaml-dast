from __future__ import annotations

import collections.abc as _abc
import typing as _typing

import ydst.errors as errors
import ydst.nodes as nodes
import ydst.registry as registry_mod
import ydst.render as render_mod

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


def _validate_mapping_keys(
    m: _abc.Mapping[_typing.Any, _typing.Any],
    *,
    ctx: errors.ErrorContext,
    allow_non_string: bool,
) -> None:
    if allow_non_string:
        return
    for k in m.keys():
        if not isinstance(k, str):
            raise errors.TemplateValidationError(
                "Templated dict keys are not supported (use only string keys)",
                ctx=ctx,
            )


def _validate_foreach(node: nodes.ForEach, *, ctx: errors.ErrorContext) -> None:
    if not isinstance(node.var, str) or not node.var:
        raise errors.TemplateValidationError("!foreach 'var' must be a non-empty string", ctx=ctx)

    if node.into not in ("list", "dict", "set"):
        raise errors.TemplateValidationError("!foreach 'into' must be one of list, dict, set", ctx=ctx)

    if node.into == "dict":
        if node.key is nodes.UNSET or node.value is nodes.UNSET:
            raise errors.TemplateValidationError("!foreach into:dict requires key and value", ctx=ctx)
    else:
        if node.template is nodes.UNSET:
            raise errors.TemplateValidationError("!foreach requires 'template'", ctx=ctx)


def _validate_python_code(code: str, *, ctx: errors.ErrorContext) -> None:
    # Best-effort syntax validation. Runtime errors (imports, NameError, etc.) are not validated here.
    try:
        compile(code, "<ydst:python>", "exec")
    except SyntaxError as e:
        raise errors.TemplateValidationError(f"Invalid python code: {e.msg}", ctx=ctx, cause=e)


def validate_template(
    template: _template_mod.Template,
    *,
    options: render_mod.RenderOptions | None = None,
    registry: registry_mod.FunctionRegistry | None = None,
    allow_non_string_mapping_keys: bool = False,
) -> None:
    """Validate a template graph for static structural issues.

    This performs conservative checks:
      - mapping keys must be strings by default (templated keys are intentionally unsupported)
      - mode/options gates (calls, includes, python tags) are enforced
      - some node-specific structural invariants are checked
      - if a registry is provided, string-literal call targets are validated
    """
    opts = (options or render_mod.RenderOptions()).normalized()

    def walk(x: _typing.Any, path: tuple[nodes.PathSegment, ...]) -> None:
        ctx = errors.ErrorContext(path=path)

        if isinstance(x, nodes.TemplateNode):
            # Provide node type and mark if present.
            ctx = errors.ErrorContext(path=path, node_type=x.__class__.__name__, mark=getattr(x, "mark", None))

            # Option gates
            if isinstance(x, nodes.Call) and not opts.allow_calls:
                raise errors.TemplateValidationError("!call is disabled by render options", ctx=ctx)
            if isinstance(x, nodes.IncludeRuntime) and not opts.allow_includes:
                raise errors.TemplateValidationError("!include_rt is disabled by render options", ctx=ctx)
            if isinstance(x, nodes.SetDefault) and not opts.allow_setdefault:
                raise errors.TemplateValidationError("!setdefault is disabled by render options", ctx=ctx)
            if isinstance(x, nodes.Python) and not opts.allow_python:
                raise errors.TemplateValidationError("!python is disabled by render options", ctx=ctx)
            if isinstance(x, nodes.PythonModule) and not opts.allow_python_module:
                raise errors.TemplateValidationError("!python_module is disabled by render options", ctx=ctx)

            # Node-specific validations
            if isinstance(x, nodes.ForEach):
                _validate_foreach(x, ctx=ctx)
            elif isinstance(x, nodes.Python):
                if not isinstance(x.code, str) or not x.code.strip():
                    raise errors.TemplateValidationError("!python code must be a non-empty string", ctx=ctx)
                _validate_python_code(x.code, ctx=ctx)
            elif isinstance(x, nodes.PythonModule):
                if not isinstance(x.code, str) or not x.code.strip():
                    raise errors.TemplateValidationError("!python_module code must be a non-empty string", ctx=ctx)
                _validate_python_code(x.code, ctx=ctx)
            elif isinstance(x, nodes.SetDefault):
                for name in x.defaults.keys():
                    if not isinstance(name, str) or not name:
                        raise errors.TemplateValidationError("!setdefault names must be non-empty strings", ctx=ctx)

            # Registry checks for literal call targets
            if isinstance(x, nodes.Call):
                if registry is not None and isinstance(x.fn, str) and x.fn:
                    fn = registry.get(x.fn) if hasattr(registry, "get") else None
                    if fn is None or not callable(fn):
                        raise errors.TemplateValidationError(
                            f"!call references unknown function: {x.fn!r}",
                            ctx=ctx,
                        )

            # Recurse into fields
            for field_name, v in nodes.iter_template_node_items(x):
                walk(v, path + (field_name,))
            return

        # Non-node containers
        if isinstance(x, _abc.Mapping):
            _validate_mapping_keys(x, ctx=ctx, allow_non_string=allow_non_string_mapping_keys)
            for k, v in x.items():
                walk(k, path + ("<key>",))
                walk(v, path + (k,))
            return

        if isinstance(x, (set, frozenset)):
            for i, v in enumerate(x):
                walk(v, path + (i,))
            return

        if isinstance(x, _abc.Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for i, v in enumerate(x):
                walk(v, path + (i,))
            return

    walk(template.root, ())
