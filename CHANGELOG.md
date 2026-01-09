# Changelog

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
