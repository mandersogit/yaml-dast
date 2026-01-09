from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Optional, Set

from .errors import ErrorContext, TemplateValidationError
from .expr import ExprPolicy, ExpressionEvaluator
from .nodes import (
    Call,
    Default,
    Expr,
    ForEach,
    IncludeRuntime,
    If,
    Pipe,
    TemplateNode,
    Var,
    UNSET,
    iter_template_node_items,
)

# RenderOptions is imported lazily (and only for optional validation rules) to
# keep this module usable in minimal contexts.
try:  # pragma: no cover
    from .render import RenderOptions
except Exception:  # pragma: no cover
    RenderOptions = None  # type: ignore[assignment]


def collect_variables(template: Any) -> Set[str]:
    """Collect variable names referenced by !var nodes.

    Notes
    -----
    - This does *not* attempt to parse names out of !expr strings.
    - It does walk into defaults and other subtrees to find nested !var nodes.
    """

    out: Set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, Var):
            out.add(x.name)
            if x.default is not UNSET:
                walk(x.default)
            return

        if isinstance(x, Expr):
            if x.default is not UNSET:
                walk(x.default)
            return

        if isinstance(x, TemplateNode):
            for _, v in iter_template_node_items(x):
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


def validate_template(
    template: Any,
    *,
    policy: Optional[ExprPolicy] = None,
    options: Optional["RenderOptions"] = None,
) -> None:
    """Validate a template graph.

    This is a *static* validation pass. It does not render the template.

    Validates
    ---------
    - !expr syntax and policy compliance
    - disallows templated mapping keys (TemplateNode keys)
    - validates basic structural invariants for core nodes (!foreach, !call, ...)
    - optionally enforces render-time restrictions when `options` is provided
      (e.g., in `locked_down` mode, !call and !include_rt should be rejected)

    Parameters
    ----------
    policy:
        Expression policy. If omitted and `options` is provided, a policy is derived
        from `options`.
    options:
        If provided, used to enforce template features that will be disabled during
        rendering (e.g. allow_calls/allow_includes).
    """

    opts = None
    if options is not None:
        # RenderOptions.normalized() validates values and canonicalizes mode aliases.
        try:
            opts = options.normalized()
        except Exception:
            # If a caller passes an object with a compatible interface but without
            # normalized(), we simply treat it as absent.
            opts = None

    if policy is None and opts is not None:
        policy = ExprPolicy(
            allow_attribute_access=opts.allow_attribute_access_in_expr,
            allow_function_calls=opts.allow_function_calls_in_expr,
            allow_subscripts=opts.allow_subscripts_in_expr,
            allow_method_calls=opts.allow_method_calls_in_expr,
            allow_private_attributes=opts.allow_private_attributes_in_expr,
        )

    evaluator = ExpressionEvaluator(policy=policy or ExprPolicy())

    def fail(msg: str, *, path: tuple[Any, ...], node: Any, node_type: str) -> None:
        raise TemplateValidationError(
            msg,
            ctx=ErrorContext(path=path, mark=getattr(node, "mark", None), node_type=node_type),
        )

    def walk(x: Any, path: tuple[Any, ...] = ()) -> None:
        # -----------------
        # Specific nodes
        # -----------------
        if isinstance(x, Var):
            if not isinstance(x.name, str) or not x.name:
                fail("Var: name must be a non-empty string", path=path, node=x, node_type="Var")
            if x.default is not UNSET:
                walk(x.default, path + ("default",))
            return

        if isinstance(x, Default):
            if x.default is UNSET:
                fail(
                    "Default: requires a fallback under key 'default' (or 'fallback')",
                    path=path,
                    node=x,
                    node_type="Default",
                )
            if not isinstance(x.treat_none_as_missing, bool):
                fail(
                    "Default: treat_none_as_missing must be boolean",
                    path=path,
                    node=x,
                    node_type="Default",
                )
            if not isinstance(x.treat_omit_as_missing, bool):
                fail(
                    "Default: treat_omit_as_missing must be boolean",
                    path=path,
                    node=x,
                    node_type="Default",
                )
            walk(x.value, path + ("value",))
            walk(x.default, path + ("default",))
            return

        if isinstance(x, If):
            if x.test is None:
                fail("!if requires 'test'", path=path, node=x, node_type="If")
            if x.then is None:
                fail("!if requires 'then'", path=path, node=x, node_type="If")
            walk(x.test, path + ("test",))
            walk(x.then, path + ("then",))
            walk(x.else_, path + ("else",))
            return

        if isinstance(x, ForEach):
            if not isinstance(x.var, str) or not x.var:
                fail("!foreach 'var' must be a non-empty string", path=path, node=x, node_type="ForEach")
            if x.in_ is None:
                fail("!foreach requires 'in'", path=path, node=x, node_type="ForEach")
            if x.into not in ("list", "dict", "set"):
                fail("!foreach 'into' must be one of: list, dict, set", path=path, node=x, node_type="ForEach")

            if x.into == "dict":
                if x.key is UNSET or x.value is UNSET:
                    # Note: YAML loader uses None for explicit null; UNSET is for missing.
                    fail("!foreach into:dict requires 'key' and 'value'", path=path, node=x, node_type="ForEach")
                walk(x.key, path + ("key",))
                walk(x.value, path + ("value",))
            else:
                if x.template is UNSET:
                    fail("!foreach requires 'template' (or use into:dict)", path=path, node=x, node_type="ForEach")
                walk(x.template, path + ("template",))

            if x.when is not None:
                walk(x.when, path + ("when",))

            walk(x.in_, path + ("in",))

            if x.index is not None and (not isinstance(x.index, str) or not x.index):
                fail("!foreach 'index' must be a non-empty string", path=path, node=x, node_type="ForEach")
            return

        if isinstance(x, Call):
            if opts is not None and not getattr(opts, "allow_calls", True):
                fail("!call is disabled by render options", path=path, node=x, node_type="Call")

            if x.args is None:
                fail("!call 'args' must be a list", path=path, node=x, node_type="Call")
            if not isinstance(x.args, (list, tuple)):
                fail("!call 'args' must be a list", path=path, node=x, node_type="Call")
            if x.kwargs is None:
                fail("!call 'kwargs' must be a mapping", path=path, node=x, node_type="Call")
            if not isinstance(x.kwargs, Mapping):
                fail("!call 'kwargs' must be a mapping", path=path, node=x, node_type="Call")

            walk(x.fn, path + ("fn",))
            for i, a in enumerate(x.args):
                walk(a, path + ("args", i))
            for k, v in x.kwargs.items():
                walk(v, path + ("kwargs", k))
            return

        if isinstance(x, IncludeRuntime):
            if opts is not None and not getattr(opts, "allow_includes", True):
                fail("!include_rt is disabled by render options", path=path, node=x, node_type="IncludeRuntime")
            if not isinstance(x.required, bool):
                fail("!include_rt 'required' must be boolean", path=path, node=x, node_type="IncludeRuntime")
            walk(x.target, path + ("target",))
            if x.default is not UNSET:
                walk(x.default, path + ("default",))
            return

        if isinstance(x, Pipe):
            if x.steps is None:
                fail("!pipe requires 'steps'", path=path, node=x, node_type="Pipe")
            if not isinstance(x.steps, (list, tuple)):
                fail("!pipe steps must be a sequence", path=path, node=x, node_type="Pipe")
            for i, step in enumerate(x.steps):
                walk(step, path + ("steps", i))
            return

        if isinstance(x, Expr):
            if not isinstance(x.expr, str) or not x.expr:
                fail("!expr requires a non-empty 'expr' string", path=path, node=x, node_type="Expr")

            # ExpressionEvaluator.compile already raises TemplateValidationError
            # with context for syntax/policy violations.
            evaluator.compile(
                x.expr,
                ctx=ErrorContext(path=path, mark=getattr(x, "mark", None), node_type="Expr"),
            )

            if x.default is not UNSET:
                walk(x.default, path + ("default",))
            return

        # -----------------
        # Containers and generic nodes
        # -----------------
        if isinstance(x, Mapping):
            for k, v in x.items():
                if isinstance(k, TemplateNode):
                    fail(
                        "TemplateNode keys are not allowed in mappings (keys must be concrete)",
                        path=path,
                        node=k,
                        node_type=type(k).__name__,
                    )
                walk(k, path + ("<key>",))
                walk(v, path + (k,))
            return

        if isinstance(x, (set, frozenset)):
            for i, v in enumerate(x):
                walk(v, path + (f"<set_item_{i}>",))
            return

        if isinstance(x, Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for i, v in enumerate(x):
                walk(v, path + (i,))
            return

        if isinstance(x, TemplateNode):
            # Unknown TemplateNode subclass: recurse into dataclass fields.
            for k, v in iter_template_node_items(x):
                walk(v, path + (k,))
            return

        # Scalars: nothing to validate.
        return

    walk(template)
