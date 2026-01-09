from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional

from .errors import ErrorContext, TemplateValidationError
from .nodes import SourceMark


@dataclass(frozen=True)
class ExprPolicy:
    allow_attribute_access: bool = True
    allow_function_calls: bool = True
    allow_subscripts: bool = True

    # If False, calling obj.method(...) is disallowed even if attribute access is enabled.
    allow_method_calls: bool = False

    # If False, any attribute starting with '_' or containing '__' is rejected.
    allow_private_attributes: bool = False


class _ExprValidator(ast.NodeVisitor):
    def __init__(self, *, policy: ExprPolicy, ctx: ErrorContext):
        self.policy = policy
        self.ctx = ctx

    def generic_visit(self, node: ast.AST) -> Any:
        raise TemplateValidationError(
            f"Disallowed expression construct: {node.__class__.__name__}",
            ctx=self.ctx,
        )

    # Allowed top-level
    def visit_Expression(self, node: ast.Expression) -> Any:
        self.visit(node.body)

    # Literals and containers
    def visit_Constant(self, node: ast.Constant) -> Any:
        return None

    def visit_Name(self, node: ast.Name) -> Any:
        return None

    def visit_Tuple(self, node: ast.Tuple) -> Any:
        for e in node.elts:
            self.visit(e)

    def visit_List(self, node: ast.List) -> Any:
        for e in node.elts:
            self.visit(e)

    def visit_Set(self, node: ast.Set) -> Any:
        for e in node.elts:
            self.visit(e)

    def visit_Dict(self, node: ast.Dict) -> Any:
        for k in node.keys:
            if k is not None:
                self.visit(k)
        for v in node.values:
            self.visit(v)

    # Operators / control
    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        if not isinstance(node.op, (ast.Not, ast.UAdd, ast.USub)):
            raise TemplateValidationError(f"Disallowed unary operator: {node.op.__class__.__name__}", ctx=self.ctx)
        self.visit(node.operand)

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        if not isinstance(
            node.op,
            (
                ast.Add,
                ast.Sub,
                ast.Mult,
                ast.Div,
                ast.FloorDiv,
                ast.Mod,
                ast.Pow,
            ),
        ):
            raise TemplateValidationError(f"Disallowed binary operator: {node.op.__class__.__name__}", ctx=self.ctx)
        self.visit(node.left)
        self.visit(node.right)

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise TemplateValidationError(f"Disallowed boolean operator: {node.op.__class__.__name__}", ctx=self.ctx)
        for v in node.values:
            self.visit(v)

    def visit_Compare(self, node: ast.Compare) -> Any:
        for op in node.ops:
            if not isinstance(
                op, (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot)
            ):
                raise TemplateValidationError(f"Disallowed comparison operator: {op.__class__.__name__}", ctx=self.ctx)
        self.visit(node.left)
        for c in node.comparators:
            self.visit(c)

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        self.visit(node.test)
        self.visit(node.body)
        self.visit(node.orelse)

    # Indexing
    def visit_Subscript(self, node: ast.Subscript) -> Any:
        if not self.policy.allow_subscripts:
            raise TemplateValidationError("Subscript access is disabled by policy", ctx=self.ctx)
        self.visit(node.value)
        self.visit(node.slice)

    def visit_Slice(self, node: ast.Slice) -> Any:
        if node.lower:
            self.visit(node.lower)
        if node.upper:
            self.visit(node.upper)
        if node.step:
            self.visit(node.step)

    # Attribute access
    def visit_Attribute(self, node: ast.Attribute) -> Any:
        if not self.policy.allow_attribute_access:
            raise TemplateValidationError("Attribute access is disabled by policy", ctx=self.ctx)
        self.visit(node.value)

    # Function calls
    def visit_Call(self, node: ast.Call) -> Any:
        if not self.policy.allow_function_calls:
            raise TemplateValidationError("Function calls are disabled by policy", ctx=self.ctx)

        # Only allow calling names or (optionally) attribute lookups
        if isinstance(node.func, ast.Attribute) and not self.policy.allow_method_calls:
            raise TemplateValidationError("Method calls are disabled by policy", ctx=self.ctx)
        if not isinstance(node.func, (ast.Name, ast.Attribute)):
            raise TemplateValidationError("Only direct function names (and optionally methods) may be called", ctx=self.ctx)

        self.visit(node.func)
        for a in node.args:
            self.visit(a)
        for kw in node.keywords:
            if kw.arg is None:
                raise TemplateValidationError("**kwargs expansion is not allowed", ctx=self.ctx)
            self.visit(kw.value)


_BINOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARYOPS: dict[type, Callable[[Any], Any]] = {
    ast.Not: operator.not_,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_CMP: dict[type, Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


class ExpressionEvaluator:
    """Restricted AST-based expression evaluator.

    This is designed for convenience and predictability, not as a sandbox.
    Treat templates and their expressions as trusted inputs.
    """

    def __init__(
        self,
        *,
        policy: Optional[ExprPolicy] = None,
        allowed_functions: Optional[Mapping[str, Callable[..., Any]]] = None,
    ):
        self.policy = policy or ExprPolicy()
        self.allowed_functions = dict(allowed_functions or {})

    def compile(self, expr: str, *, ctx: Optional[ErrorContext] = None) -> ast.Expression:
        ctx = ctx or ErrorContext()
        try:
            parsed = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            raise TemplateValidationError(f"Invalid expression syntax: {e.msg}", ctx=ctx, cause=e)

        _ExprValidator(policy=self.policy, ctx=ctx).visit(parsed)
        return parsed  # type: ignore[return-value]

    def eval(self, compiled: ast.Expression, env: Mapping[str, Any]) -> Any:
        return self._eval_node(compiled.body, env)

    def _eval_node(self, node: ast.AST, env: Mapping[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            raise NameError(node.id)
        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(e, env) for e in node.elts)
        if isinstance(node, ast.List):
            return [self._eval_node(e, env) for e in node.elts]
        if isinstance(node, ast.Set):
            return {self._eval_node(e, env) for e in node.elts}
        if isinstance(node, ast.Dict):
            return {
                self._eval_node(k, env) if k is not None else None: self._eval_node(v, env)
                for k, v in zip(node.keys, node.values)
            }
        if isinstance(node, ast.UnaryOp):
            op = _UNARYOPS[type(node.op)]
            return op(self._eval_node(node.operand, env))
        if isinstance(node, ast.BinOp):
            op = _BINOPS[type(node.op)]
            return op(self._eval_node(node.left, env), self._eval_node(node.right, env))
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for v in node.values:
                    val = self._eval_node(v, env)
                    if not val:
                        return val
                return val  # type: ignore[has-type]
            if isinstance(node.op, ast.Or):
                for v in node.values:
                    val = self._eval_node(v, env)
                    if val:
                        return val
                return val  # type: ignore[has-type]
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, env)
            for op, comp in zip(node.ops, node.comparators):
                right = self._eval_node(comp, env)
                fn = _CMP[type(op)]
                if not fn(left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            test = self._eval_node(node.test, env)
            return self._eval_node(node.body if test else node.orelse, env)
        if isinstance(node, ast.Subscript):
            if not self.policy.allow_subscripts:
                raise ValueError("Subscripts disabled by policy")
            val = self._eval_node(node.value, env)
            sl = self._eval_slice(node.slice, env)
            return val[sl]
        if isinstance(node, ast.Attribute):
            if not self.policy.allow_attribute_access:
                raise ValueError("Attribute access disabled by policy")
            base = self._eval_node(node.value, env)
            attr = node.attr
            if not self.policy.allow_private_attributes:
                if attr.startswith("_") or "__" in attr:
                    raise AttributeError(attr)
            # Mapping convenience: allow x.key for dict-like objects
            try:
                from collections.abc import Mapping as _Mapping

                if isinstance(base, _Mapping) and attr in base:
                    return base[attr]
            except Exception:
                pass
            return getattr(base, attr)
        if isinstance(node, ast.Call):
            if not self.policy.allow_function_calls:
                raise ValueError("Function calls disabled by policy")

            if isinstance(node.func, ast.Attribute) and not self.policy.allow_method_calls:
                raise ValueError("Method calls disabled by policy")

            func = self._eval_node(node.func, env)
            # Policy: only allow calling functions that are explicitly whitelisted by name,
            # unless the caller provided callables directly in env and opted into that behavior.
            # We check by identity membership in allowed_functions when possible.
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name not in self.allowed_functions:
                    raise PermissionError(f"Function '{name}' is not allowed")
            else:
                # Attribute-based calls are only allowed if allow_method_calls is true.
                # There is no stable name, so we cannot whitelist; treat as forbidden unless explicitly enabled.
                if not self.policy.allow_method_calls:
                    raise PermissionError("Method calls are not allowed")

            args = [self._eval_node(a, env) for a in node.args]
            kwargs = {kw.arg: self._eval_node(kw.value, env) for kw in node.keywords if kw.arg is not None}
            return func(*args, **kwargs)

        raise ValueError(f"Unsupported expression node: {node.__class__.__name__}")

    def _eval_slice(self, node: ast.AST, env: Mapping[str, Any]) -> Any:
        if isinstance(node, ast.Slice):
            lower = self._eval_node(node.lower, env) if node.lower else None
            upper = self._eval_node(node.upper, env) if node.upper else None
            step = self._eval_node(node.step, env) if node.step else None
            return slice(lower, upper, step)
        # Python 3.9+ uses Index as an alias, but keep compatibility
        if isinstance(node, ast.Index):  # type: ignore[attr-defined]
            return self._eval_node(node.value, env)  # type: ignore[attr-defined]
        return self._eval_node(node, env)
