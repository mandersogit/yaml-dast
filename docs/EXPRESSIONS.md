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
- subscripts: `x[0]`, `x["k"]`, slices (configurable)
- attribute access: `obj.attr` (configurable)
- function calls: `fn(x)` (configurable; whitelisted)

Notes:

- Dict unpacking (`{**d}`) is **not** supported.

The validator rejects everything else (including comprehensions, lambdas, imports, assignments, and statement-level constructs).

## Attribute access

Attribute access is controlled by:

- `RenderOptions.allow_attribute_access_in_expr`
- `RenderOptions.mode` (`expr_safe` disables it)

Additional safety rules:

- By default, attributes starting with `_` or containing `__` are rejected.
- You can override this with `RenderOptions(allow_private_attributes_in_expr=True)`.
- For mapping-like objects, `x.key` will return `x["key"]` if that key exists (convenience for dict-backed context).

## Function calls

Function calls in expressions are controlled by:

- `RenderOptions.allow_function_calls_in_expr`
- `RenderOptions.mode` (`expr_safe` disables calls)

ydst only permits calling **whitelisted functions** obtained from the provided registry.

Function calls are resolved by name via `registry.get(name)`. The registry does not need to be enumerable (no `keys()` required). If `registry.get(name)` returns `None`, the call is rejected.

The render context environment is **not** used as a fallback for function call resolution. This avoids accidentally allowing arbitrary callables present in the context to be invoked from expressions.

### Method calls

Method calls (e.g., `obj.method()`) are disabled by default (`allow_method_calls_in_expr=False`). If enabled, method calls are not name-whitelisted (because the call target has no stable global name), so enabling this should be treated as a trusted-template-only capability.

## Subscripts

Subscripts (indexing and slices) are controlled by:

- `RenderOptions.allow_subscripts_in_expr`

This is enabled by default because it is fundamental for working with dictionaries/lists in configuration templates. If you are evaluating templates from partially untrusted sources, consider disabling it unless you explicitly need it.

## Missing names

- In strict mode (`RenderOptions.strict=True`), missing names raise.
- If a specific `!expr` node uses `strict: false` (or global non-strict), missing names return the rendered `default` if provided, else `null`.

## Recommendations

- Prefer `!call` for complex logic.
- Keep expressions short and side-effect free.
- If you need to evaluate templates from untrusted sources, use `mode="expr_safe"` or `mode="locked_down"` and avoid providing broad registries or filesystem include resolvers.
