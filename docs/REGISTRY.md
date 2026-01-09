# Function registry

`!call` and (optionally) function calls inside `!expr` rely on a registry provided by the application.

## Interface

A registry must provide:

```python
class FunctionRegistry(Protocol):
    def get(self, name: str) -> Callable[..., Any] | None: ...
```

An optional `keys()` method may be provided for introspection/tooling, but it is not required.
Expression calls resolve functions via `registry.get(name)` and therefore work with any object implementing the `FunctionRegistry` protocol.

## Registry tiers

ydst provides several optional, built-in registries. None are enabled by default; you must opt in.

- `minimal_registry()` — pure data helpers only (no environment access, no Python builtins)
- `safe_registry()` — `minimal_registry()` plus a small set of deterministic builtins
- `extended_registry()` — `safe_registry()` plus additional convenience functions that may be undesirable in locked-down environments (currently: `env()`)

`default_registry()` is an alias for `safe_registry()` in v0.2.0. The intent is: if you are “just getting started” and want a sane default, use `default_registry()`; if you want to signal a more security-conscious stance, use `safe_registry()` explicitly.

In security-sensitive scenarios, prefer `minimal_registry()` or `safe_registry()` and keep `RenderOptions.allow_function_calls_in_expr=False`.

## Built-in function set

The exact set may evolve in early versions, but currently:

### Minimal

- `get_in(obj, path, default=None)` — nested dict/list access (supports dot-path strings with escaping)
- `coalesce(*values, default=None)` — first non-`None`/non-`!omit`
- `slugify(value, max_len=None)` — simple slug function
- `to_int(value, default=None)` / `to_float(value, default=None)`
- `json_dumps(value, sort_keys=True)` — JSON serialize

### Safe

Safe adds a small set of basic builtins:

- `len`, `min`, `max`, `sum`, `sorted`, `str`, `int`, `float`, `bool`, `round`, `abs`

### Extended

Extended adds:

- `env(name, default=None)` — environment variable lookup

## Providing a custom registry

The simplest approach is a dict wrapped in `DictFunctionRegistry`:

```python
from ydst import DictFunctionRegistry

REGISTRY = DictFunctionRegistry({
    "my_fn": lambda x: x,
})
```

Or define your own object implementing `.get(name)`.

## CLI registry modules

The CLI accepts `--registry-module mypkg.registry_module`, which must provide `REGISTRY` or `registry` at module scope.

Example:

```bash
ydst render template.yaml --context-file ctx.json --registry-tier safe --registry-module mypkg.registry_module
```
