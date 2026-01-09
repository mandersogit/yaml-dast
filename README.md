# ydst — YAML data-structure templates

`ydst` is a small Python library that loads YAML into a *template object graph* and renders it into a
concrete Python data structure (dict/list/scalars) using a minimal set of YAML tags.

This is **data-structure templating** (not text templating): the output preserves types.

## Core features

- `!var` / `!variable` — variable substitution from runtime context
- `!if` — conditional branches (with `else` defaulting to omission)
- `!foreach` — generate lists/dicts/sets by iteration
- `!omit` — remove keys/items from output
- `!expr` — evaluate restricted Python expressions (AST-based)
- `!call` — call named functions from a user-provided registry
- `!pipe` — compose transformations
- `!include` — **load-time include**: inlines another YAML file during parsing
- `!include_rt` / `!include_runtime` — **render-time include**: includes and renders another YAML file during rendering

## Quick start

```python
from ydst import TemplateEngine, FileIncludeResolver, default_registry

engine = TemplateEngine(
    include_resolver=FileIncludeResolver(search_paths=["."]),
)

tmpl = engine.load_template("""
model: gpt-5
params:
  temperature: !var temperature
tools: !foreach
  var: t
  in: !var enabled_tools
  template:
    name: !expr "t"
""", source_name="inline.yaml")

out = engine.render(
    tmpl,
    context={"temperature": 0.2, "enabled_tools": ["search", "calc"]},
    registry=default_registry(),
)

print(out)
```

## CLI

Render a template with a JSON context:

```bash
ydst render template.yaml --context-file ctx.json
```

Use the built-in default registry:

```bash
ydst render template.yaml --context-file ctx.json --default-registry
```

## Notes

- YAML anchors/aliases are supported by the YAML loader, but the renderer produces new dict/list objects,
  so alias identity is generally not preserved in the output.
- This library is **not** a sandbox for untrusted code; expression evaluation is restricted, but treat templates as trusted.
