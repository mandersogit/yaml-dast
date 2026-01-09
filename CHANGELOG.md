# Changelog

## 0.1.3 (2026-01-02)

### Correctness

- `!pipe` string stages now only call registry functions **if** the registry contains a callable of that name.
  Otherwise, the string is treated as a literal stage result (matching the documented semantics).
- Load-time `!include` now matches `!var`/`!expr`/`!include_rt` default behavior:
  when `required: false` and no `default` is provided, missing includes produce `None` (not an omit sentinel).
- YAML load errors now preserve line/column information when available from PyYAML exceptions.

### API / ergonomics

- Added `UNSET` sentinel to distinguish "no default provided" from "omit".
  `Var.default`, `Expr.default`, and `IncludeRuntime.default` now default to `UNSET`.
- Added `RenderOptions.allow_callable_pipe_stages` (default: `False`) to prevent arbitrary callables
  from being invoked as `!pipe` stages. `mode="safe"` forces this off.
- Added a per-render runtime include template cache:
  - `RenderOptions.cache_runtime_includes` (default: `True`)
  - `RenderOptions.runtime_include_cache_max` (default: `None`, meaning unbounded per render)

### Performance

- `!expr` evaluation no longer copies the scope ChainMap into a new dict per expression.
- `ExpressionEvaluator` is now built once per render invocation and reused.
- `FileIncludeResolver` optionally caches include resolution results (`cache=...`, `cache_max=...`).

### Packaging

- Declared `requires-python >=3.10` (code uses `|` type union syntax).

### Documentation & tests

- Updated docs to describe the new pipe semantics, default handling, and caching options.
- Added tests covering the above.

## 0.1.2 (2026-01-02)

### Correctness

- `!expr` function calls no longer depend on registries implementing `keys()`.
  Functions are resolved by name via `registry.get(name)` at evaluation time, which also fixes
  failures when using `chain_registries(... )`.
- `!expr` now rejects dict unpacking (`{**d}`) at validation time and also defends at runtime.
- `max_depth` now constrains recursion for deep container-only templates (not just template nodes).
- `default: !omit` is now honored for `!var`, `!expr`, and `!include_rt`.
- Includes now distinguish "missing" from "empty file" (`IncludeResult.content: str | None`).

### API / ergonomics

- `ydst.api.load_template(...)` now accepts `engine=` as the primary parameter; `loader=` remains as an alias.
- `RenderError.__str__` now returns the contextualized `pretty()` form by default.

### Documentation

- Updated expression and include documentation to reflect the above behavior changes.
- Clarified the security posture of `mode="safe"` (it only affects `!expr`).
