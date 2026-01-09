---
title: Quickstart - Python Usage Patterns
date: 2026-01-09
---

# Quickstart — Python Usage Patterns

This example shows the most common ways to use ydst from Python.

## 1. One-shot rendering

For quick, one-off template rendering:

```python
import ydst

# Render YAML text directly
result = ydst.render_text("""
user:
  name: !var name
  role: !var role
""", context={"name": "Alice", "role": "admin"})

print(result)
# {'user': {'name': 'Alice', 'role': 'admin'}}
```

Also available: `ydst.render_path()` and `ydst.render_stream()`.

## 2. Template reuse

When rendering the same template multiple times with different contexts:

```python
import ydst

# Load once
tmpl = ydst.Template.from_path("01-basic.yaml")

# Render many times
alice = tmpl.render(context={"message": "Hello, Alice!", "enabled": True})
bob = tmpl.render(context={"message": "Hello, Bob!", "enabled": False})
```

Also available: `Template.from_text()` and `Template.from_stream()`.

## 3. Custom engine configuration

For advanced scenarios (custom include paths, registries, options):

```python
import ydst
import ydst.registry as registry

# Configure engine
engine = ydst.TemplateEngine(
    include_resolver=ydst.FileIncludeResolver(search_paths=["./templates"]),
    options=ydst.RenderOptions(mode="locked_down"),
    registry=registry.safe_registry(),
)

# Load and render
tmpl = engine.load_template_path("config.yaml")
result = tmpl.render(context={"env": "production"})
```

## 4. Per-render customization

Override options or registry for a specific render:

```python
import dataclasses
import ydst

tmpl = ydst.Template.from_text("x: !var foo")

# Use engine defaults
result1 = tmpl.render(context={"foo": 1})

# Override options for this render only
custom_opts = dataclasses.replace(tmpl.engine.options, strict=False)
result2 = tmpl.render(context={}, options=custom_opts)
```

## 5. Safe rendering (untrusted templates)

For templates from untrusted sources:

```python
import ydst

tmpl = ydst.Template.from_text(untrusted_yaml_string)

# render_safe() uses mode="locked_down"
result = tmpl.render_safe(context={"foo": "bar"})
```

## Running the YAML examples

The numbered examples (01-08) are YAML templates with expected JSON outputs.

To render them from the command line:

```bash
# Render 01-basic.yaml with context
ydst render 01-basic.yaml --context '{"message": "Hello!", "enabled": true}'

# Compare with expected output
diff <(ydst render 01-basic.yaml --context '{"message": "Hello!", "enabled": true}') 01-basic.json
```

Or from Python:

```python
import ydst

tmpl = ydst.Template.from_path("01-basic.yaml")
result = tmpl.render(context={"message": "Hello!", "enabled": True})
print(result)
```

