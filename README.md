# yaml-dast — YAML Data Structure Templates

**Install:** `pip install yaml-dast` · **Import:** `import ydst`

A Python library that loads YAML into a *template object graph* and renders it into a
concrete Python data structure (dict/list/scalars) using a small set of YAML tags.

This is **data-structure templating** (not text templating): the output preserves types.

## Core features

- `!var` — variable substitution from runtime context
- `!if` — conditional branches (with `else` defaulting to omission)
- `!foreach` — generate lists/dicts/sets by iteration
- `!omit` — remove keys/items from output
- `!default` — coalesce-ish defaulting with configurable missingness semantics
- `!setdefault` — define default values for variables in the render scope
- `!expr` — evaluate restricted Python expressions (AST-based)
- `!call` — call named functions from a user-provided registry
- `!pipe` — compose transformations
- `!include` — **load-time include**: inlines another YAML file during parsing
- `!include_rt` — **render-time include**: includes and renders another YAML file during rendering

## Power features (opt-in)

These tags are **disabled by default** and intended for **trusted templates only**:

- `!python` — execute embedded Python and emit a value into the template output
- `!python_module` — define helper functions/constants in a shared module scope

Enable them via `RenderOptions(allow_python=True)` or CLI flags when you control the template source.

## Documentation

- Docs index: [`docs/README.md`](docs/README.md)
- Examples: [`examples/README.md`](examples/README.md)

## Quick start

```python
import ydst

# Load a template
tmpl = ydst.Template.from_path("config.yaml")

# Render with context
result = tmpl.render(context={"env": "production", "debug": False})

# Templates are reusable
dev = tmpl.render(context={"env": "development", "debug": True})
prod = tmpl.render(context={"env": "production", "debug": False})
```

For inline YAML:

```python
tmpl = ydst.Template.from_text("""
database:
  host: !var db_host
  port: !default [!var db_port, 5432]
""")
result = tmpl.render(context={"db_host": "localhost"})
# → {"database": {"host": "localhost", "port": 5432}}
```

### Custom engine (advanced)

For includes, custom options, or custom function registries:

```python
import ydst

engine = ydst.TemplateEngine(
    include_resolver=ydst.FileIncludeResolver(search_paths=["./templates"]),
)

tmpl = engine.load_template_path("config.yaml")
result = tmpl.render(context={"env": "production"})
```

## Loading templates

- `Template.from_text(yaml_string)` — load from a string
- `Template.from_path(path)` — load from a filesystem path
- `Template.from_stream(io_object)` — load from a file handle or StringIO

Or use the engine directly:
- `engine.load_template_text(text)` — returns `Template`
- `engine.load_template_path(path)` — returns `Template`
- `engine.load_yaml_text(text)` — returns raw node tree (for introspection)

## CLI

Render a template with a JSON context:

```bash
ydst render template.yaml --context-file ctx.json
```

The CLI enables the `safe` registry tier by default. To disable registries entirely:

```bash
ydst render template.yaml --context-file ctx.json --registry-tier none
```

Enable a built-in registry tier explicitly:

```bash
ydst render template.yaml --context-file ctx.json --registry-tier safe
```

Validate a template without rendering:

```bash
ydst validate template.yaml
```

Analyze static dependencies:

```bash
ydst deps template.yaml
```

## Notes

- Requires Python 3.11+.
- YAML anchors/aliases are supported by the YAML loader, but the renderer produces new dict/list objects,
  so alias identity is generally not preserved in the output.
- This library is **not** a sandbox for untrusted code; expression evaluation is restricted, but treat templates as trusted.
  If you need additional defense-in-depth, consider:
  - `RenderOptions(mode="locked_down")`
  - a reduced registry tier (e.g. `ydst.safe_registry()` or `ydst.registry.minimal_registry()`), or no registry
  - `FileIncludeResolver(..., allow_absolute=False, enforce_roots=True)`
