from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Optional, Set

from .errors import ErrorContext, TemplateValidationError
from .expr import ExprPolicy, ExpressionEvaluator
from .nodes import Expr, TemplateNode, Var, UNSET


def collect_variables(template: Any) -> Set[str]:
    """Collect variable names referenced by !var nodes."""
    out: Set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, Var):
            out.add(x.name)
            # default may contain vars too
            if x.default is not UNSET:
                walk(x.default)
            return
        if isinstance(x, Expr):
            # We do not attempt to extract names from expressions here, but we
            # *do* walk the default subtree because it may contain !var nodes.
            if x.default is not UNSET:
                walk(x.default)
            return
        if isinstance(x, TemplateNode):
            # generic node: walk its fields conservatively
            for v in x.__dict__.values():
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
) -> None:
    """Static validation.

    This function is intentionally *validation-only*.

    It currently validates:
      - !expr syntax and allowed constructs (per policy)
      - templated mapping keys are rejected (use !foreach into:dict)

    The template object graph is not mutated.
    """
    evaluator = ExpressionEvaluator(policy=policy or ExprPolicy())

    def walk(x: Any, path: tuple[Any, ...] = ()) -> None:
        if isinstance(x, Expr):
            ctx = ErrorContext(path=path, mark=x.mark, node_type="Expr")
            try:
                evaluator.compile(x.expr, ctx=ctx)
            except TemplateValidationError:
                raise
            except Exception as e:
                raise TemplateValidationError(str(e), ctx=ctx, cause=e)
            # Validate default subtree too
            if x.default is not UNSET:
                walk(x.default, path + ("default",))
            return

        if isinstance(x, TemplateNode):
            for k, v in x.__dict__.items():
                if k.startswith("_"):
                    continue
                walk(v, path + (k,))
            return

        from collections.abc import Mapping as _Mapping, Sequence as _Sequence

        if isinstance(x, _Mapping):
            for k, v in x.items():
                if isinstance(k, TemplateNode):
                    raise TemplateValidationError(
                        "Templated mapping keys are not supported (use !foreach into:dict)",
                        ctx=ErrorContext(path=path + ("<key>",), mark=getattr(k, "mark", None), node_type="MappingKey"),
                    )
                walk(k, path + ("<key>",))
                walk(v, path + (k,))
            return

        if isinstance(x, (set, frozenset)):
            for i, v in enumerate(x):
                walk(v, path + (i,))
            return

        if isinstance(x, _Sequence) and not isinstance(x, (str, bytes, bytearray)):
            for i, v in enumerate(x):
                walk(v, path + (i,))
            return

    walk(template)
