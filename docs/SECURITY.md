# Security notes

ydst is intended for **trusted templates** (configuration authored by your team).

It provides a restricted expression evaluator and an explicit function allowlist model, but it is **not** a hardened sandbox for arbitrary untrusted code or templates.

## Primary risk areas

- **Includes** (`!include`, `!include_rt`): filesystem access and path traversal if targets are user-controlled.
- **Function registries**: any callable you expose can have side effects.
- **Callable pipe stages**: if enabled, any callable injected via context may be invoked by `!pipe`.
- **Expressions**: even restricted expressions can leak information or trigger expensive computations if you expose large objects or heavy functions.

## Rendering modes and policy toggles

ydst's `RenderOptions` includes both a coarse-grained `mode` and several explicit toggles:

- `mode="trusted"` (default)
  - expressions may use attribute access and function calls (subject to the registry you provide)
  - `!call` and `!include_rt` are permitted (again, only if you provided a registry/resolver)

- `mode="safe"` / `mode="expr_safe"`
  - restricts **only** `!expr` (no attribute access, no expression function calls)
  - does **not** automatically disable `!call`, `!pipe` registry calls, or runtime includes

- `mode="locked_down"`
  - disables `!call`, runtime includes (`!include_rt`), and pipe registry calls
  - also applies the `expr_safe` expression restrictions and disables callable pipe stages

If you need more precise control than `mode`, you can also set:

- `allow_calls` (controls `!call` and `!pipe` call nodes)
- `allow_includes` (controls `!include_rt`)
- `allow_pipe_registry_calls` (controls whether string stages in `!pipe` can resolve to registry functions)
- `allow_callable_pipe_stages` (controls direct invocation of callables in `!pipe`)

## Recommended practices

- Treat templates as trusted inputs.
- Prefer `!call` over complex `!expr` logic; keep registries small.
- Keep `RenderOptions(allow_callable_pipe_stages=False)` unless you explicitly need callable stages.
- If you need to evaluate templates from partially untrusted sources:
  - use `RenderOptions(mode="locked_down")` or explicitly disable calls/includes
  - do not provide a registry unless you need it; prefer `minimal_registry()`/`safe_registry()` when you do
  - cap work using `max_nodes` and `max_depth`
  - prefer `FileIncludeResolver(allow_absolute=False, enforce_roots=True, search_paths=[...])` when you must allow filesystem includes

## Explicit non-goal

ydst does not attempt to safely execute arbitrary Python embedded in YAML. If you need that, run evaluation in a separate hardened environment and treat the result as untrusted until validated.
