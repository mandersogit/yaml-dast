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

- `mode="expr_safe"`
  - restricts **only** `!expr` (no attribute access, no expression function calls)
  - does **not** automatically disable `!call`, `!pipe` registry calls, runtime includes, or load-time includes

- `mode="locked_down"`
  - disables `!call`, runtime includes (`!include_rt`), and pipe registry calls
  - also applies the `expr_safe` expression restrictions and disables callable pipe stages

If you need more precise control than `mode`, you can also set:

- `allow_calls` (controls `!call` and `!pipe` call nodes)
- `allow_includes` (controls `!include_rt`)
- `allow_pipe_registry_calls` (controls whether string stages in `!pipe` can resolve to registry functions)
- `allow_callable_pipe_stages` (controls direct invocation of callables in `!pipe`)

Expression surface controls:

- `allow_subscripts_in_expr` (controls `x[...]` access in `!expr`)
- `allow_private_attributes_in_expr` (controls access to `_private` / `__dunder__` attributes when attribute access is enabled)


### Load-time includes are not controlled by RenderOptions

`!include` (load-time) is resolved during `engine.load_template(...)`, before any call to `render(...)`.

- Render-time controls (`RenderOptions.allow_includes`, `mode=...`) affect `!include_rt` only.
- To disable load-time includes entirely, construct your engine with:

```python
engine = TemplateEngine(include_resolver=resolver, allow_load_time_includes=False)
```

Or avoid configuring an `include_resolver` if you do not need `!include`.

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


### Embedded Python

Ydst includes two **power tags** that can execute code:

- `!python` — executes embedded Python and emits a value
- `!python_module` — executes embedded Python in a shared module scope (for helper definitions)

These tags are **disabled by default** and are also disabled by `RenderOptions(mode="locked_down")`.

If you enable them (`allow_python=True` / `allow_python_module=True`), you should treat templates as
equivalent to running Python code from that source.
