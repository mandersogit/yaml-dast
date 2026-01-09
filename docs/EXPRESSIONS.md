# Expressions

`!expr` evaluates a restricted Python expression using `ast.parse(..., mode="eval")` plus a whitelist validator and a small evaluator.

This system is designed for **predictability and ergonomics**, not as a hardened sandbox. Treat templates and expressions as trusted inputs.

## Allowed constructs

The expression validator allows:

- constants (`1`, `3.14`, `"x"`, `true/false/null` are YAML, but inside `!expr` use Python `True/False/None`)
- names (`foo`, `bar`)
- list/tuple/set/dict literals
- unary ops: `not`, unary `+`/`-`
- binary ops: `+`, `-`, `*`, `/`, `//`, `%`, `**`
- boolean ops: `and`, `or`
- comparisons: `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`, `is`, `is not`
- ternary expressions: `a if cond else b`
- subscripts: `x[0]`, `x["k"]`, slices
- attribute access: `obj.attr` (configurable)
- function calls: `fn(x)` (configurable; whitelisted)

The validator rejects everything else (including comprehensions, lambdas, imports, assignments, and statement-level constructs).

## Attribute access

Attribute access is controlled by:

- `RenderOptions.allow_attribute_access_in_expr`
- `RenderOptions.mode` (`safe` disables it)

Additional safety rules:

- By default, attributes starting with `_` or containing `__` are rejected.
- For mapping-like objects, `x.key` will return `x["key"]` if that key exists (convenience for dict-backed context).

## Function calls

Function calls in expressions are controlled by:

- `RenderOptions.allow_function_calls_in_expr`
- `RenderOptions.mode` (`safe` disables calls)

ydst only permits calling **whitelisted functions** derived from the provided registry.

**Important implementation detail:** the renderer can only whitelist functions if the registry supports `keys()` iteration (e.g., `DictFunctionRegistry`). If your registry only implements `get(name)` and not `keys()`, expression calls will not be enabled.

This is intentional: it avoids a world where “any callable injected into the environment” can be invoked from expressions without an explicit allowlist.

### Method calls

Method calls (e.g., `obj.method()`) are disabled by default (`allow_method_calls_in_expr=False`). If enabled, method calls are not name-whitelisted (because the call target has no stable global name), so enabling this should be treated as a trusted-template-only capability.

## Missing names

- In strict mode (`RenderOptions.strict=True`), missing names raise.
- If a specific `!expr` node uses `strict: false` (or global non-strict), missing names return the rendered `default` if provided, else `null`.

## Recommendations

- Prefer `!call` for complex logic.
- Keep expressions short and side-effect free.
- If you need to evaluate templates from untrusted sources, use `mode="safe"` and avoid providing broad registries or filesystem include resolvers.
