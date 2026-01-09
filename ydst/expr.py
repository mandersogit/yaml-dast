from __future__ import annotations

import ast as _ast
import collections.abc as _abc
import dataclasses as _dataclasses
import operator as _operator
import typing as _typing

import ydst.errors as errors


@_dataclasses.dataclass(frozen=True, slots=True)
class ExprPolicy:
    """Policy controls for the restricted expression evaluator.

    Notes
    -----
    This evaluator is intended for convenience and predictability, not as a
    security sandbox. "Safe mode" in ydst only restricts certain syntactic
    constructs (notably function calls and attribute access) inside `!expr`.
    """

    allow_attribute_access: bool = True
    allow_function_calls: bool = True
    allow_subscripts: bool = True

    # If False, calling obj.method(...) is disallowed even if attribute access is enabled.
    allow_method_calls: bool = False

    # If False, any attribute starting with '_' or containing '__' is rejected.
    allow_private_attributes: bool = False


class _ExprValidator(_ast.NodeVisitor):
    def __init__(self, *, policy: ExprPolicy, ctx: errors.ErrorContext):
        self.policy = policy
        self.ctx = ctx

    def generic_visit(self, node: _ast.AST) -> _typing.Any:
        raise errors.TemplateValidationError(
            f"Disallowed expression construct: {node.__class__.__name__}",
            ctx=self.ctx,
        )

    # Allowed top-level
    def visit_Expression(self, node: _ast.Expression) -> _typing.Any:
        self.visit(node.body)

    # Literals and containers
    def visit_Constant(self, node: _ast.Constant) -> _typing.Any:
        return None

    def visit_Name(self, node: _ast.Name) -> _typing.Any:
        return None

    def visit_Tuple(self, node: _ast.Tuple) -> _typing.Any:
        for e in node.elts:
            self.visit(e)

    def visit_List(self, node: _ast.List) -> _typing.Any:
        for e in node.elts:
            self.visit(e)

    def visit_Set(self, node: _ast.Set) -> _typing.Any:
        for e in node.elts:
            self.visit(e)

    def visit_Dict(self, node: _ast.Dict) -> _typing.Any:
        # Dict unpacking (**mapping) appears as a Dict with a `None` key.
        # We do not support this because it's easy to get subtly wrong.
        if any(k is None for k in node.keys):
            raise errors.TemplateValidationError("Dict unpacking (**mapping) is not allowed", ctx=self.ctx)

        for k in node.keys:
            # k is never None here
            self.visit(k)  # type: ignore[arg-type]
        for v in node.values:
            self.visit(v)

    # Operators / control
    def visit_UnaryOp(self, node: _ast.UnaryOp) -> _typing.Any:
        if not isinstance(node.op, (_ast.Not, _ast.UAdd, _ast.USub)):
            raise errors.TemplateValidationError(f"Disallowed unary operator: {node.op.__class__.__name__}", ctx=self.ctx)
        self.visit(node.operand)

    def visit_BinOp(self, node: _ast.BinOp) -> _typing.Any:
        if not isinstance(
            node.op,
            (
                _ast.Add,
                _ast.Sub,
                _ast.Mult,
                _ast.Div,
                _ast.FloorDiv,
                _ast.Mod,
                _ast.Pow,
            ),
        ):
            raise errors.TemplateValidationError(f"Disallowed binary operator: {node.op.__class__.__name__}", ctx=self.ctx)
        self.visit(node.left)
        self.visit(node.right)

    def visit_BoolOp(self, node: _ast.BoolOp) -> _typing.Any:
        if not isinstance(node.op, (_ast.And, _ast.Or)):
            raise errors.TemplateValidationError(f"Disallowed boolean operator: {node.op.__class__.__name__}", ctx=self.ctx)
        for v in node.values:
            self.visit(v)

    def visit_Compare(self, node: _ast.Compare) -> _typing.Any:
        for op in node.ops:
            if not isinstance(
                op,
                (_ast.Eq, _ast.NotEq, _ast.Lt, _ast.LtE, _ast.Gt, _ast.GtE, _ast.In, _ast.NotIn, _ast.Is, _ast.IsNot),
            ):
                raise errors.TemplateValidationError(f"Disallowed comparison operator: {op.__class__.__name__}", ctx=self.ctx)
        self.visit(node.left)
        for c in node.comparators:
            self.visit(c)

    def visit_IfExp(self, node: _ast.IfExp) -> _typing.Any:
        self.visit(node.test)
        self.visit(node.body)
        self.visit(node.orelse)

    # Indexing
    def visit_Subscript(self, node: _ast.Subscript) -> _typing.Any:
        if not self.policy.allow_subscripts:
            raise errors.TemplateValidationError("Subscript access is disabled by policy", ctx=self.ctx)
        self.visit(node.value)
        self.visit(node.slice)

    def visit_Slice(self, node: _ast.Slice) -> _typing.Any:
        if node.lower:
            self.visit(node.lower)
        if node.upper:
            self.visit(node.upper)
        if node.step:
            self.visit(node.step)

    # Attribute access
    def visit_Attribute(self, node: _ast.Attribute) -> _typing.Any:
        if not self.policy.allow_attribute_access:
            raise errors.TemplateValidationError("Attribute access is disabled by policy", ctx=self.ctx)
        if not self.policy.allow_private_attributes:
            if node.attr.startswith("_") or "__" in node.attr:
                raise errors.TemplateValidationError("Private/dunder attributes are not allowed", ctx=self.ctx)
        self.visit(node.value)

    # Function calls
    def visit_Call(self, node: _ast.Call) -> _typing.Any:
        if not self.policy.allow_function_calls:
            raise errors.TemplateValidationError("Function calls are disabled by policy", ctx=self.ctx)

        # Only allow calling names or (optionally) attribute lookups
        if isinstance(node.func, _ast.Attribute) and not self.policy.allow_method_calls:
            raise errors.TemplateValidationError("Method calls are disabled by policy", ctx=self.ctx)
        if not isinstance(node.func, (_ast.Name, _ast.Attribute)):
            raise errors.TemplateValidationError(
                "Only direct function names (and optionally methods) may be called",
                ctx=self.ctx,
            )

        self.visit(node.func)
        for a in node.args:
            self.visit(a)
        for kw in node.keywords:
            if kw.arg is None:
                raise errors.TemplateValidationError("**kwargs expansion is not allowed", ctx=self.ctx)
            self.visit(kw.value)


_BINOPS: dict[type, _typing.Callable[[_typing.Any, _typing.Any], _typing.Any]] = {
    _ast.Add: _operator.add,
    _ast.Sub: _operator.sub,
    _ast.Mult: _operator.mul,
    _ast.Div: _operator.truediv,
    _ast.FloorDiv: _operator.floordiv,
    _ast.Mod: _operator.mod,
    _ast.Pow: _operator.pow,
}

_UNARYOPS: dict[type, _typing.Callable[[_typing.Any], _typing.Any]] = {
    _ast.Not: _operator.not_,
    _ast.UAdd: _operator.pos,
    _ast.USub: _operator.neg,
}

_CMP: dict[type, _typing.Callable[[_typing.Any, _typing.Any], bool]] = {
    _ast.Eq: _operator.eq,
    _ast.NotEq: _operator.ne,
    _ast.Lt: _operator.lt,
    _ast.LtE: _operator.le,
    _ast.Gt: _operator.gt,
    _ast.GtE: _operator.ge,
    _ast.Is: _operator.is_,
    _ast.IsNot: _operator.is_not,
    _ast.In: lambda a, b: a in b,
    _ast.NotIn: lambda a, b: a not in b,
}


class ExpressionEvaluator:
    """Restricted AST-based expression evaluator.

    This is designed for convenience and predictability, **not** as a sandbox.
    Treat templates and their expressions as trusted inputs.

    The evaluator supports an optional function whitelist mechanism:

    - `allowed_functions`: explicit mapping from allowed function names to callables.
    - `function_resolver`: callable `(name) -> callable|None` used when
      `allowed_functions` is not provided.

    Importantly, function call resolution is *not* based on variable lookup in `env`.
    This avoids accidentally allowing arbitrary callables that appear in the render
    context, and avoids overwriting user variables by injecting registry functions into
    the evaluation environment.
    """

    def __init__(
        self,
        *,
        policy: ExprPolicy | None = None,
        allowed_functions: _abc.Mapping[str, _typing.Callable[..., _typing.Any]] | None = None,
        function_resolver: _typing.Callable[[str], _typing.Callable[..., _typing.Any] | None] | None = None,
    ):
        self.policy = policy or ExprPolicy()
        self.allowed_functions = dict(allowed_functions or {})
        self.function_resolver = function_resolver

    def compile(self, expr: str, *, ctx: errors.ErrorContext | None = None) -> _ast.Expression:
        ctx = ctx or errors.ErrorContext()
        try:
            parsed = _ast.parse(expr, mode="eval")
        except SyntaxError as e:
            raise errors.TemplateValidationError(f"Invalid expression syntax: {e.msg}", ctx=ctx, cause=e)

        _ExprValidator(policy=self.policy, ctx=ctx).visit(parsed)
        return parsed  # type: ignore[return-value]

    def eval(self, compiled: _ast.Expression, env: _abc.Mapping[str, _typing.Any]) -> _typing.Any:
        return self._eval_node(compiled.body, env)

    def _resolve_function(self, name: str) -> _typing.Callable[..., _typing.Any] | None:
        if name in self.allowed_functions:
            return self.allowed_functions[name]
        if self.function_resolver is not None:
            try:
                fn = self.function_resolver(name)
            except Exception:
                # Resolver errors are not swallowed: propagate.
                raise
            if fn is not None and callable(fn):
                return fn
        return None

    def _eval_node(self, node: _ast.AST, env: _abc.Mapping[str, _typing.Any]) -> _typing.Any:
        if isinstance(node, _ast.Constant):
            return node.value
        if isinstance(node, _ast.Name):
            if node.id in env:
                return env[node.id]
            raise NameError(node.id)
        if isinstance(node, _ast.Tuple):
            return tuple(self._eval_node(e, env) for e in node.elts)
        if isinstance(node, _ast.List):
            return [self._eval_node(e, env) for e in node.elts]
        if isinstance(node, _ast.Set):
            return {self._eval_node(e, env) for e in node.elts}
        if isinstance(node, _ast.Dict):
            if any(k is None for k in node.keys):
                raise ValueError("Dict unpacking (**mapping) is not supported")
            # All keys are non-None after the check above.
            return {self._eval_node(k, env): self._eval_node(v, env) for k, v in zip(node.keys, node.values) if k is not None}
        if isinstance(node, _ast.UnaryOp):
            unary_op = _UNARYOPS[type(node.op)]
            return unary_op(self._eval_node(node.operand, env))
        if isinstance(node, _ast.BinOp):
            bin_op = _BINOPS[type(node.op)]
            return bin_op(self._eval_node(node.left, env), self._eval_node(node.right, env))
        if isinstance(node, _ast.BoolOp):
            if isinstance(node.op, _ast.And):
                and_val: _typing.Any = False
                for v in node.values:
                    and_val = self._eval_node(v, env)
                    if not and_val:
                        return and_val
                return and_val
            if isinstance(node.op, _ast.Or):
                or_val: _typing.Any = False
                for v in node.values:
                    or_val = self._eval_node(v, env)
                    if or_val:
                        return or_val
                return or_val
        if isinstance(node, _ast.Compare):
            left = self._eval_node(node.left, env)
            for cmp_op, comp in zip(node.ops, node.comparators):
                right = self._eval_node(comp, env)
                cmp_fn = _CMP[type(cmp_op)]
                if not cmp_fn(left, right):
                    return False
                left = right
            return True
        if isinstance(node, _ast.IfExp):
            test = self._eval_node(node.test, env)
            return self._eval_node(node.body if test else node.orelse, env)
        if isinstance(node, _ast.Subscript):
            if not self.policy.allow_subscripts:
                raise ValueError("Subscripts disabled by policy")
            val = self._eval_node(node.value, env)
            sl = self._eval_slice(node.slice, env)
            return val[sl]
        if isinstance(node, _ast.Attribute):
            if not self.policy.allow_attribute_access:
                raise ValueError("Attribute access disabled by policy")
            base = self._eval_node(node.value, env)
            attr = node.attr
            if not self.policy.allow_private_attributes:
                if attr.startswith("_") or "__" in attr:
                    raise AttributeError(attr)

            # Mapping convenience: allow x.key for dict-like objects
            if isinstance(base, _abc.Mapping) and attr in base:
                return base[attr]
            return getattr(base, attr)
        if isinstance(node, _ast.Call):
            if not self.policy.allow_function_calls:
                raise ValueError("Function calls disabled by policy")

            # Direct name calls (whitelisted)
            if isinstance(node.func, _ast.Name):
                func_name = node.func.id
                resolved_fn = self._resolve_function(func_name)
                if resolved_fn is None:
                    raise PermissionError(f"Function '{func_name}' is not allowed")

                call_args = [self._eval_node(a, env) for a in node.args]
                call_kwargs = {kw.arg: self._eval_node(kw.value, env) for kw in node.keywords if kw.arg is not None}
                return resolved_fn(*call_args, **call_kwargs)

            # Method calls (explicitly gated)
            if isinstance(node.func, _ast.Attribute):
                if not self.policy.allow_method_calls:
                    raise PermissionError("Method calls are not allowed")
                method_fn = self._eval_node(node.func, env)
                if not callable(method_fn):
                    raise TypeError(f"Attribute is not callable: {node.func.attr}")
                method_args = [self._eval_node(a, env) for a in node.args]
                method_kwargs = {kw.arg: self._eval_node(kw.value, env) for kw in node.keywords if kw.arg is not None}
                return method_fn(*method_args, **method_kwargs)

            raise ValueError("Unsupported call form")

        raise ValueError(f"Unsupported expression node: {node.__class__.__name__}")

    def _eval_slice(self, node: _ast.AST, env: _abc.Mapping[str, _typing.Any]) -> _typing.Any:
        if isinstance(node, _ast.Slice):
            lower = self._eval_node(node.lower, env) if node.lower else None
            upper = self._eval_node(node.upper, env) if node.upper else None
            step = self._eval_node(node.step, env) if node.step else None
            return slice(lower, upper, step)
        # Python 3.9+ uses Index as an alias, but keep compatibility
        if isinstance(node, _ast.Index):  # type: ignore[attr-defined]
            return self._eval_node(node.value, env)  # type: ignore[attr-defined]
        return self._eval_node(node, env)
