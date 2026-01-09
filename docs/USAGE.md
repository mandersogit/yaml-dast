# Usage

## Installation

From a checkout/unpacked archive:

```bash
pip install -e .
```

ydst requires **PyYAML**.

## Core concepts

- **Template**: a YAML-derived object graph that may contain template nodes like `!var`, `!if`, `!foreach`, etc.
- **Render**: evaluation of a template into plain Python containers and scalars.
- **Context**: a mapping used to resolve variables and expressions.
- **Registry**: a mapping-like object used to resolve `!call` functions and (optionally) function calls inside `!expr`.

The two-phase model is intentional:

1. **Load**: YAML → template graph (no runtime evaluation)
2. **Render**: template graph + context → concrete structure

This separation makes it natural to combine ydst with independent deep-merge/layering systems.

## Recommended API: `TemplateEngine`

```python
import ydst
import ydst.registry as registry

engine = ydst.TemplateEngine(
    include_resolver=ydst.FileIncludeResolver(search_paths=["."]),
)

tmpl = engine.load_template_text(
    """
model: gpt-5
params:
  temperature: !var temperature
  max_tokens: !expr "base_tokens + bonus_tokens"
""",
    source_name="inline.yaml",
)

result = tmpl.render(
    context={"temperature": 0.2, "base_tokens": 1000, "bonus_tokens": 500},
    registry=registry.default_registry(),
)

print(result)
```

### Switching YAML loader

The engine defaults to `yaml.SafeLoader` but can be constructed with `yaml.FullLoader`:

```python
import yaml
import ydst

engine = ydst.TemplateEngine(base_loader=yaml.FullLoader)
```

## Module-level convenience functions

For one-shot loading and rendering (when you don't need to keep a reference to the template):

```python
import ydst

# One-shot: load from text and render
result = ydst.render_text(
    "temperature: !var temperature",
    context={"temperature": 0.2},
)

# One-shot: load from path and render
result = ydst.render_path("template.yaml", context={"temperature": 0.2})
```

These use a default engine. To customize engine settings, use `TemplateEngine` directly.

### Template class for reusable templates

When you want to render the same template multiple times:

```python
import ydst

# Load once
tmpl = ydst.Template.from_text("temperature: !var temperature")

# Render multiple times
out1 = tmpl.render(context={"temperature": 0.2})
out2 = tmpl.render(context={"temperature": 0.8})
```

Template classmethods:
- `Template.from_text(text)` — from YAML string
- `Template.from_path(path)` — from filesystem path
- `Template.from_stream(stream)` — from file-like object

### Security-oriented convenience profile

ydst provides `safe_engine()` for defensive defaults when ingesting template inputs that are not fully trusted:

```python
import ydst

eng = ydst.safe_engine(include_paths=["."])  # optional

# Templates loaded with this engine can use render_safe() for locked-down rendering
tmpl = eng.load_template_text("temperature: !var temperature")

# Locked down by default (no calls, no includes)
result = tmpl.render_safe(context={"temperature": 0.2})
```

This is intentionally conservative. If you need more capability, instantiate
`TemplateEngine` and `RenderOptions` directly and be explicit about which features you
enable.

## Render options

Rendering behavior is controlled by :class:`ydst.RenderOptions`.

```python
import ydst

options = ydst.RenderOptions(
    mode="trusted",         # "trusted" (default), "expr_safe", or "locked_down"
    strict=True,            # missing vars error; root !omit always errors
    dict_key_conflict="auto",
    wrap_exceptions=True,   # wrap errors into ydst exceptions with cause preserved
    max_depth=200,
    max_nodes=None,
)
```

Key fields:

- `strict` (default: `True`)
  - if `True`, missing required variables raise (unless a node provides a default).
  - if `False`, missing variables become `None` (or a node-specific default).
  - root-level `!omit` **always errors** (it has no sensible container semantics).
- `mode`
  - `"trusted"` (default): expression attribute access and expression function calls are enabled (subject to other flags).
  - `"expr_safe"`: disables expression attribute access and expression function calls (see `EXPRESSIONS.md`).
    Note: this only affects `!expr`; use the explicit policy toggles below to control `!call`, `!include_rt`, and `!pipe`.
  - `"locked_down"`: a more restrictive preset that disables `!call`, `!include_rt`, and registry-based string stages in `!pipe`, and applies the same expression restrictions as `"expr_safe"`.
- `dict_key_conflict`
  - `"auto"`: strict→error, non-strict→last-wins
  - `"error"`: always error on duplicates
  - `"last"` / `"first"`: deterministic override behavior
- `wrap_exceptions`
  - if `False`, raw exceptions from registry functions propagate (useful for debugging)
- `max_depth` / `max_nodes`
  - `max_nodes` is useful for bounding total work in templates with large loops.

Additional policy toggles:

- `allow_calls` (default: `True`)
- `allow_includes` (default: `True`)
- `allow_pipe_registry_calls` (default: `True`)
- `strict_pipe_stages` (default: `True`)
- `materialize_foreach_iterables` (default: `True`)

### Expression flags

Advanced:

- `allow_attribute_access_in_expr` (default: `True` in trusted mode)
- `allow_function_calls_in_expr` (default: `True` in trusted mode)
- `allow_method_calls_in_expr` (default: `False`)

Note: even with `allow_function_calls_in_expr=True`, ydst only allows calling *whitelisted* functions (derived from the provided registry). See `EXPRESSIONS.md`.

## Tracing

You can attach a trace callback to observe evaluation events for template nodes:

```python
import ydst

events = []

def trace(ev):
    events.append(ev)

options = ydst.RenderOptions(trace=trace)
out = tmpl.render(context=ctx, registry=reg, options=options)
```

Trace events include:

- `path`: tuple path within the output being rendered
- `node_type`: e.g., `Var`, `Expr`, `ForEach`
- `mark`: best-effort source location (file/line/col)
- `before` / `after`: node instance and rendered value
