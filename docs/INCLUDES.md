# Includes

ydst supports two forms of includes:

1. **Load-time include** (`!include`): resolves and inlines YAML during parsing.
2. **Render-time include** (`!include_rt`): resolves YAML during rendering (target may be templated).

## Include resolver

Both include forms rely on an `IncludeResolver`:

```python
class IncludeResolver(Protocol):
    def resolve(self, target: str, *, from_source: str | None = None) -> IncludeResult: ...
```

The resolver returns:

- `content`: YAML text (`None` means "not found"; empty string is a valid empty file)
- `source_name`: a human-readable name (usually a file path)
- `key`: a stable identity used for cycle detection

## FileIncludeResolver

ydst includes a basic filesystem resolver:

```python
import ydst

resolver = ydst.FileIncludeResolver(search_paths=[".", "./configs"])

# Optional (in-resolver) caching for repeated resolves in long-running processes:
# - caches both hits and misses
# - LRU-ish eviction via cache_max
cached_resolver = FileIncludeResolver(search_paths=[".", "./configs"], cache=True, cache_max=256)

# Optional: bound the maximum file size read by the resolver.
bounded_resolver = FileIncludeResolver(search_paths=[".", "./configs"], max_bytes=1_000_000)
```

Hardening options (useful if include targets are partially user-controlled):

```python
# Disallow absolute paths and require includes to resolve within the provided search_paths
resolver = FileIncludeResolver(
    search_paths=[".", "./configs"],
    allow_absolute=False,
    enforce_roots=True,
)
```

Resolution rules:

- absolute paths are used as-is (unless `allow_absolute=False`)
- relative paths are resolved relative to the including file when possible
- otherwise, `search_paths` are searched in order
- when `enforce_roots=True`, resolved includes must be within the configured roots (by default, the `search_paths`)

## Load-time include (`!include`)

When you load a template file, `!include` is resolved immediately and the included YAML content is parsed into the template graph.

Example:

```yaml
common: !include includes/common.yaml
service:
  owner: !expr "common.owner"
```

Load-time include requires that the engine be configured with a resolver:

```python
engine = TemplateEngine(include_resolver=resolver)
```

You can explicitly disable load-time includes even if a resolver is present:

```python
engine = TemplateEngine(include_resolver=resolver, allow_load_time_includes=False)
```

Note: `RenderOptions(..., allow_includes=...)` only affects `!include_rt` (render-time includes).


Default behavior for missing load-time includes:

- If `required: true` (default), missing includes raise `TemplateLoadError`.
- If `required: false` and no `default:` is provided, missing includes evaluate to `null` (`None`).
- Use `default: !omit` to omit keys/items when an include is missing.

Cycle detection is enforced by tracking include keys during a single load operation.

If you need to guard against pathological include chains, you can also configure a maximum include depth:

```python
engine = TemplateEngine(include_resolver=resolver, max_include_depth=32)
```

## Render-time include (`!include_rt`)

Render-time includes are resolved during rendering. This is useful when the include target depends on context:

```yaml
profile: !var profile
settings: !include_rt
  target: !expr "'profiles/' + profile + '.yaml'"
  required: true
```

Notes:

- You must use `TemplateEngine.render(...)` so the renderer can load and evaluate the included YAML.
- Cycle detection is enforced during rendering.
- `required: false` and `default:` are supported.
- Parsed templates for render-time includes are cached **within a single render invocation** by default.
  You can control this via:
  - `RenderOptions(cache_runtime_includes=...)`
  - `RenderOptions(runtime_include_cache_max=...)`

The default `runtime_include_cache_max` is `128` (set to `None` for unbounded caching).

The default `runtime_include_cache_max` is 128 to keep memory bounded.

## Security note

Includes are a common attack surface when templates or include targets are not trusted.

- Treat templates as trusted inputs.
- If you must handle untrusted includes, consider a resolver that enforces an allowlist of locations and rejects path traversal.
