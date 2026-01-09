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
from ydst import FileIncludeResolver
resolver = FileIncludeResolver(search_paths=[".", "./configs"])
```

Resolution rules:

- absolute paths are used as-is
- relative paths are resolved relative to the including file when possible
- otherwise, `search_paths` are searched in order

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

Cycle detection is enforced by tracking include keys during a single load operation.

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

## Security note

Includes are a common attack surface when templates or include targets are not trusted.

- Treat templates as trusted inputs.
- If you must handle untrusted includes, consider a resolver that enforces an allowlist of locations and rejects path traversal.
