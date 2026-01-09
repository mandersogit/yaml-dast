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
from ydst import TemplateEngine, FileIncludeResolver, default_registry

engine = TemplateEngine(
    include_resolver=FileIncludeResolver(search_paths=["."]),
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

result = engine.render(
    tmpl,
    context={"temperature": 0.2, "base_tokens": 1000, "bonus_tokens": 500},
    registry=default_registry(),
)

print(result)
```

### Switching YAML loader

The engine defaults to `yaml.SafeLoader` but can be constructed with `yaml.FullLoader`:

```python
import yaml
from ydst import TemplateEngine

engine = TemplateEngine(base_loader=yaml.FullLoader)
```

## Convenience functions

The top-level functions are thin wrappers:

```python
from ydst import load_template_text, render, default_registry

tmpl = load_template_text("temperature: !var temperature")
out = render(tmpl, {"temperature": 0.2}, registry=default_registry())
```

For explicitness (and to avoid ambiguity where a string might look like a file path),
you can use:

```python
from ydst import load_template_text, load_template_file

tmpl1 = load_template_text("temperature: !var temperature")
tmpl2 = load_template_file("template.yaml")
```

Note: `load_template(...)` interprets a Python `str` as a **filesystem path**.
Use `load_template_text(...)` for YAML text.

If you use render-time includes (`!include_rt`), prefer `TemplateEngine.render(...)` so the renderer has access to the engine instance.

### Security-oriented convenience profiles

ydst provides convenience helpers for defensive defaults when ingesting template inputs that are not fully trusted:

```python
from ydst import load_template_text, safe_engine, safe_render

eng = safe_engine(include_paths=["."])  # optional
tmpl = load_template_text("temperature: !var temperature", engine=eng)

# Locked down by default (no calls, no includes)
out = safe_render(tmpl, {"temperature": 0.2}, engine=eng)
```

These helpers are intentionally conservative. If you need more capability, instantiate
`TemplateEngine` and `RenderOptions` directly and be explicit about which features you
enable.

## Render options

Rendering behavior is controlled by :class:`ydst.RenderOptions`.

```python
from ydst import RenderOptions

options = RenderOptions(
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
from ydst import RenderOptions

events = []

def trace(ev):
    events.append(ev)

options = RenderOptions(trace=trace)
out = engine.render(tmpl, context=ctx, registry=reg, options=options)
```

Trace events include:

- `path`: tuple path within the output being rendered
- `node_type`: e.g., `Var`, `Expr`, `ForEach`
- `mark`: best-effort source location (file/line/col)
- `before` / `after`: node instance and rendered value
