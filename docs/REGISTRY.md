# Function registry

`!call` and (optionally) function calls inside `!expr` rely on a registry provided by the application.

## Interface

A registry must provide:

```python
class FunctionRegistry(Protocol):
    def get(self, name: str) -> Callable[..., Any] | None: ...
```

For expression call support, ydst also looks for an optional `keys()` iterator to build an allowlist of callable names.

The built-in `DictFunctionRegistry` supports both.

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
