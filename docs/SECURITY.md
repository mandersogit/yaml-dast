# Security notes

ydst is intended for **trusted templates** (configuration authored by your team).

It provides a restricted expression evaluator and a function allowlist model, but it is **not** a hardened sandbox for arbitrary untrusted code or templates.

## Primary risk areas

- **Includes** (`!include`, `!include_rt`): filesystem access and path traversal if targets are user-controlled.
- **Function registries**: any callable you expose can have side effects.
- **Callable pipe stages**: if enabled, any callable injected via context may be invoked by `!pipe`.
- **Expressions**: even restricted expressions can leak information or trigger expensive computations if you expose large objects or heavy functions.

## Recommended practices

- Treat templates as trusted inputs.
- Prefer `!call` over complex `!expr` logic; keep registries small.
- Keep `RenderOptions(allow_callable_pipe_stages=False)` unless you explicitly need callable stages.
- If you need to evaluate templates from partially untrusted sources:
  - use `RenderOptions(mode="safe")` to disable attribute access and expression calls **inside `!expr`**
    - note: this does **not** disable `!call`/`!pipe` or includes; those are controlled by what registries/resolvers you provide
  - do not provide filesystem include resolvers, or provide a resolver with explicit allowlists
  - cap work using `max_nodes` and `max_depth`

## Explicit non-goal

ydst does not attempt to safely execute arbitrary Python embedded in YAML. If you need that, run evaluation in a separate hardened environment and treat the result as untrusted until validated.
