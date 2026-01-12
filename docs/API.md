---
title: API Reference
date: 2026-01-11
---

# API Reference

This document describes the public Python API for ydst.

## Core Classes

### `Template`

The primary user-facing class. Wraps a parsed YAML template and provides rendering.

```python
import ydst

tmpl = ydst.Template.from_text("name: !var user")
result = tmpl.render(context={"user": "Alice"})
```

#### Constructors (class methods)

| Method | Description |
|--------|-------------|
| `Template.from_text(text, *, engine=None, source_name=None)` | Load from a YAML string |
| `Template.from_path(path, *, engine=None)` | Load from a filesystem path |
| `Template.from_stream(stream, *, engine=None, source_name=None)` | Load from a file-like object |

All constructors use the module default engine if `engine` is not provided.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `root` | `NodeTree` | The parsed YAML structure (nodes, dicts, scalars) |
| `engine` | `TemplateEngine` | The engine that loaded this template |
| `source_name` | `str \| None` | Name for error messages (e.g., filename) |

#### Methods

**`render(context=None, *, options=None, registry=None) -> Any`**

Render the template with the given context.

- `context`: Dict of variables available to the template (default: empty)
- `options`: Override `RenderOptions` (default: engine's options)
- `registry`: Override `FunctionRegistry` (default: engine's registry)
- Returns: The rendered data structure
- Raises: `RenderError` on failure

**`render_safe(context=None, *, options=None) -> Any`**

Render with `mode="locked_down"` security settings. Disables `!call`, `!include_rt`, `!python`, etc.

**`validate(*, options=None, registry=None, allow_non_string_mapping_keys=False) -> None`**

Validate template structure. Raises `TemplateValidationError` on failure.

**`analyze_dependencies_with_registry(registry) -> Dependencies`**

Full dependency analysis with registry-aware pipe resolution. Use when you need `pipe_registry_functions` populated.

#### Analysis Properties (cached)

All analysis properties are computed via a single-pass traversal and cached.

| Property | Type | Description |
|----------|------|-------------|
| `variables` | `set[str]` | Variable names referenced by `!var` nodes |
| `required_variables` | `set[str]` | Variables without default values |
| `expressions` | `set[str]` | Expression strings from `!expr` nodes |
| `calls` | `set[str]` | Function names from `!call` nodes |
| `includes_rt` | `set[str]` | Static targets from `!include_rt` nodes |
| `pipe_stage_strings` | `set[str]` | Literal string stages from `!pipe` nodes |
| `setdefault_names` | `set[str]` | Variable names from `!setdefault` nodes |
| `python_block_count` | `int` | Count of `!python` blocks |
| `python_module_count` | `int` | Count of `!python_module` blocks |
| `has_dynamic_calls` | `bool` | True if any `!call` target is templated |
| `has_dynamic_includes` | `bool` | True if any `!include_rt` target is templated |
| `full_analysis` | `FullAnalysis` | Complete analysis dataclass (see `ydst.analysis`) |

---

### `TemplateEngine`

Configures YAML loading and provides engine-level defaults for rendering.

```python
import ydst

engine = ydst.TemplateEngine(
    include_resolver=ydst.FileIncludeResolver(search_paths=["./templates"]),
    options=ydst.RenderOptions(mode="locked_down"),
)
tmpl = engine.load_template_path("config.yaml")
```

#### Constructor

```python
TemplateEngine(
    *,
    include_resolver: IncludeResolver | None = None,
    allow_load_time_includes: bool = True,
    base_loader: type[yaml.Loader] = yaml.SafeLoader,
    max_include_depth: int | None = None,
    options: RenderOptions | None = None,
    registry: FunctionRegistry | None = None,
)
```

| Parameter | Description |
|-----------|-------------|
| `include_resolver` | Resolver for `!include` and `!include_rt` (default: None, disables includes) |
| `allow_load_time_includes` | Enable `!include` at load time (default: True) |
| `base_loader` | PyYAML loader class (default: `SafeLoader`) |
| `max_include_depth` | Maximum include nesting depth (default: None = unlimited) |
| `options` | Default `RenderOptions` for this engine |
| `registry` | Default `FunctionRegistry` for this engine (default: `safe_registry()`) |

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `options` | `RenderOptions` | Engine's default render options |
| `registry` | `FunctionRegistry` | Engine's default function registry |

#### Loading Methods (return `Template`)

| Method | Description |
|--------|-------------|
| `load_template_text(text, *, source_name=None)` | Load from YAML string |
| `load_template_path(path)` | Load from filesystem path |
| `load_template_stream(stream, *, source_name=None)` | Load from file-like object |

#### Raw Loading Methods (return node tree)

For introspection or custom processing:

| Method | Description |
|--------|-------------|
| `load_yaml_text(text, *, source_name=None)` | Load raw node tree from string |
| `load_yaml_path(path)` | Load raw node tree from path |
| `load_yaml_stream(stream, *, source_name=None)` | Load raw node tree from stream |

---

### `RenderOptions`

Controls rendering behavior. A frozen dataclass.

```python
import ydst

opts = ydst.RenderOptions(
    mode="trusted",
    strict=True,
    allow_python=True,
)
```

#### Key Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | `str` | `"trusted"` | Preset: `"trusted"`, `"expr_safe"`, or `"locked_down"` |
| `strict` | `bool` | `True` | Missing required vars raise errors |
| `max_depth` | `int` | `100` | Maximum recursion depth |
| `max_nodes` | `int \| None` | `None` | Maximum nodes to render |

#### Feature Toggles

| Field | Default | Description |
|-------|---------|-------------|
| `allow_calls` | `True` | Enable `!call` nodes |
| `allow_includes` | `True` | Enable `!include_rt` nodes |
| `allow_python` | `False` | Enable `!python` blocks |
| `allow_python_module` | `False` | Enable `!python_module` blocks |

#### Expression Controls

| Field | Default | Description |
|-------|---------|-------------|
| `allow_attribute_access_in_expr` | `True` | Allow `obj.attr` in `!expr` |
| `allow_function_calls_in_expr` | `True` | Allow `func()` in `!expr` |
| `allow_method_calls_in_expr` | `False` | Allow `obj.method()` in `!expr` |
| `allow_subscripts_in_expr` | `True` | Allow `obj[key]` in `!expr` |

#### Pipe Controls

| Field | Default | Description |
|-------|---------|-------------|
| `allow_pipe_registry_calls` | `True` | Allow registry lookups in `!pipe` |
| `strict_pipe_stages` | `True` | Error on unknown string stages |
| `allow_callable_pipe_stages` | `False` | Allow arbitrary callables as stages |

#### Modes

- **`trusted`**: Full power (default). All features enabled per individual flags.
- **`expr_safe`**: Disables attribute access and function calls in `!expr`.
- **`locked_down`**: Disables `!call`, `!include_rt`, `!python`, `!python_module`, and applies `expr_safe` restrictions.

---

### `FileIncludeResolver`

Filesystem-based include resolution for `!include` and `!include_rt`.

```python
import ydst

resolver = ydst.FileIncludeResolver(
    search_paths=["./templates", "./includes"],
    allow_absolute=False,
    enforce_roots=True,
)
```

#### Constructor

```python
FileIncludeResolver(
    *,
    search_paths: Sequence[str | Path] | None = None,
    encoding: str = "utf-8",
    max_bytes: int | None = None,
    cache: bool = False,
    cache_max: int | None = None,
    allow_absolute: bool = True,
    enforce_roots: bool = False,
    roots: Sequence[str | Path] | None = None,
)
```

| Parameter | Description |
|-----------|-------------|
| `search_paths` | Directories to search for includes |
| `max_bytes` | Maximum file size to read |
| `cache` | Enable caching of resolved includes |
| `allow_absolute` | Allow absolute paths in targets |
| `enforce_roots` | Require resolved paths to be under `roots` |
| `roots` | Allowed root directories (default: `search_paths`) |

---

## Factory Functions

### `safe_engine()`

Create a conservatively-configured engine.

```python
import ydst

engine = ydst.safe_engine(include_paths=["./templates"])
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `include_paths` | `None` | Directories for includes |
| `include_max_bytes` | `1_000_000` | Max include file size |
| `include_cache_max` | `256` | Include cache size |
| `max_include_depth` | `20` | Max include nesting |
| `allow_load_time_includes` | `False` | Disable `!include` by default |

### `full_engine()`

Create an engine with all features enabled. For trusted environments.

```python
import ydst.api as api

engine = api.full_engine()
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `include_paths` | `None` | Additional include directories |
| `include_cwd` | `True` | Add current directory to include paths |

Enables: `!python`, `!python_module`, attribute/method access in `!expr`, callable pipe stages, unrestricted includes.

---

## Module-Level Functions

### `get_default_engine() -> TemplateEngine`

Get or create the module-level singleton engine (thread-safe, lazy initialization).

### `set_default_engine(engine: TemplateEngine) -> None`

Set the module-level default engine.

```python
import ydst
import ydst.api as api

# Use full-power engine for all Template.from_*() calls
ydst.set_default_engine(api.full_engine())
```

---

## Registry

### `FunctionRegistry` (Protocol)

Protocol for function lookup. Only requires `.get(name) -> object | None`.

### `DictFunctionRegistry`

Dict-backed registry implementation.

```python
import ydst

reg = ydst.DictFunctionRegistry({"double": lambda x: x * 2})
```

### Registry Factory Functions

| Function | Description |
|----------|-------------|
| `safe_registry()` | Curated helpers, no I/O (default for engines) |
| `extended_registry()` | Includes `env()` for environment access |
| `ydst.registry.minimal_registry()` | Pure data helpers only |
| `ydst.registry.default_registry()` | Alias for `safe_registry()` |
| `ydst.registry.chain_registries(*regs)` | Combine multiple registries |

---

## Errors

All errors inherit from `YdstError`.

| Error | Description |
|-------|-------------|
| `YdstError` | Base error |
| `TemplateLoadError` | YAML parsing / loading failures |
| `TemplateValidationError` | Static validation failures |
| `RenderError` | Runtime rendering errors |
| `MissingVariableError` | Required variable not in context |
| `RootOmitError` | Template rendered to `!omit` at root |
| `ExpressionError` | `!expr` evaluation failure |
| `FunctionNotFoundError` | `!call` function not in registry |
| `FunctionCallError` | Registry function raised exception |
| `IncludeError` | Include resolution failure |
| `IncludeCycleError` | Circular include detected |
| `PythonError` | `!python` / `!python_module` execution error |
| `PythonEmitError` | `!python` didn't emit a value (strict mode) |

All contextual errors provide `.pretty()` for formatted messages with path/location info.

---

## Type Aliases

Defined in `ydst.nodes`:

| Alias | Definition | Description |
|-------|------------|-------------|
| `NodeTree` | `Any` | Parsed YAML structure (nodes, dicts, scalars) |
| `PathSegment` | `str \| int` | Single element of a render path |

