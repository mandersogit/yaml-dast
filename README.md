# ydst — YAML data-structure templates

`ydst` is a small Python library that loads YAML into a *template object graph* and renders it into a
concrete Python data structure (dict/list/scalars) using a small set of YAML tags.

This is **data-structure templating** (not text templating): the output preserves types.

## Core features

- `!var` — variable substitution from runtime context
- `!if` — conditional branches (with `else` defaulting to omission)
- `!foreach` — generate lists/dicts/sets by iteration
- `!omit` — remove keys/items from output
- `!default` — coalesce-ish defaulting with configurable missingness semantics
- `!expr` — evaluate restricted Python expressions (AST-based)
- `!call` — call named functions from a user-provided registry
- `!pipe` — compose transformations
- `!include` — **load-time include**: inlines another YAML file during parsing
- `!include_rt` — **render-time include**: includes and renders another YAML file during rendering

## Documentation

- Docs index: [`docs/README.md`](docs/README.md)
- Examples: [`examples/README.md`](examples/README.md)

## Quick start

```python
from ydst import TemplateEngine, FileIncludeResolver, default_registry

engine = TemplateEngine(
    include_resolver=FileIncludeResolver(search_paths=["."]),
)

tmpl = engine.load_template_text(
    """
model: gpt-5
params:
  temperature: !var temperature
tools: !foreach
  var: t
  in: !var enabled_tools
  template:
    name: !expr "t"
""",
    source_name="inline.yaml",
)

out = engine.render(
    tmpl,
    context={"temperature": 0.2, "enabled_tools": ["search", "calc"]},
    registry=default_registry(),
)

print(out)
```

## Loading templates

- Use `load_template_file(path)` / `TemplateEngine.load_template_file(path)` for filesystem files.
- Use `load_template_text(text)` / `TemplateEngine.load_template_text(text)` for YAML text.
- `load_template(source)` / `TemplateEngine.load_template(source)` treats a `str` as a **filesystem path**.

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

- Requires Python 3.10+.
- YAML anchors/aliases are supported by the YAML loader, but the renderer produces new dict/list objects,
  so alias identity is generally not preserved in the output.
- This library is **not** a sandbox for untrusted code; expression evaluation is restricted, but treat templates as trusted.
  If you need additional defense-in-depth, consider:
  - `RenderOptions(mode="locked_down")`
  - a reduced registry tier (e.g. `safe_registry()` / `minimal_registry()`), or no registry
  - `FileIncludeResolver(..., allow_absolute=False, enforce_roots=True)`
