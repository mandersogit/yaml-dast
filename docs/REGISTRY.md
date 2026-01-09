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

- `minimal_registry()` — pure data helpers only (no environment access, no builtins)
- `safe_registry()` — minimal helpers plus a small set of basic, deterministic builtins
- `default_registry()` — convenience registry (includes `env()` and additional helpers)
- `extended_registry()` — currently an alias for `default_registry()`; provided for clarity when you want to express tier intent

In security-sensitive scenarios, prefer `minimal_registry()` or `safe_registry()` and keep `RenderOptions.allow_function_calls_in_expr=False`.

## `default_registry()`

ydst provides an optional `default_registry()` for convenience. It is **not** enabled automatically; callers must opt in (or use `--default-registry` in CLI).

Included functions (subject to change in early versions):

- `get_in(obj, path, default=None)` — nested dict/list access (supports dot-path strings with escaping)
- `coalesce(*values, default=None)` — first non-`None`/non-`!omit`
- `slugify(value, max_len=None)` — simple slug function
- `env(name, default=None)` — environment variable lookup
- `to_int(value, default=None)` / `to_float(value, default=None)`
- `json_dumps(value, sort_keys=True)` — JSON serialize
- selected safe builtins: `len`, `min`, `max`, `sum`, `sorted`, `str`, `int`, `float`, `bool`, `round`, `abs`

## Providing a custom registry

The simplest approach is a dict wrapped in `DictFunctionRegistry`:

```python
from ydst import DictFunctionRegistry

REGISTRY = DictFunctionRegistry({
    "my_fn": lambda x: ...,
})
```

Or define your own object implementing `.get(name)`.

## CLI registry modules

The CLI accepts `--registry-module mypkg.registry_module`, which must provide `REGISTRY` or `registry` at module scope.
