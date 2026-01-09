# Tag reference

This document describes the templating tags supported by ydst.

All tags create **template nodes** during load and are evaluated during render.

## `!var`

Inject a value from the runtime context (or loop scope).

### Scalar form

```yaml
temperature: !var temperature
```

### Mapping form

```yaml
temperature: !var
  name: temperature
  required: false
  default: 0.2
```

Semantics:

- Lookup order: loop scope → global context.
- If missing:
  - strict + required → error (`MissingVariableError`).
  - otherwise → render `default` if provided, else `null`.

Notes:

- `name` must be a non-empty string.

## `!default`

Coalesce / fallback.

Use this when you want "first non-missing" semantics without writing an `!expr`.

### Sequence form

```yaml
model: !default
  - !var {name: model, required: false}
  - "gpt-5"
```

### Mapping form

```yaml
timeout_seconds: !default
  value: !var {name: timeout_seconds, required: false}
  default: 30
  treat_none_as_missing: true
  treat_omit_as_missing: true
```

Semantics:

- Render `value`.
- If `value` raises a `MissingVariableError` or an `IncludeError`, render `default` instead.
- If `treat_none_as_missing` is true (default), a rendered `null` triggers the fallback.
- If `treat_omit_as_missing` is true (default), a rendered `!omit` triggers the fallback.

Notes:

- `!default` is intended for ergonomic composition; it does not catch arbitrary exceptions.

## `!if`

Conditional selection.

```yaml
reasoning: !if
  test: !expr "mode == 'creative'"
  then: "high"
  # else omitted => !omit
```

Semantics:

- `test` is rendered; truthy chooses `then`, falsy chooses `else`.
- If `else` is omitted, it defaults to `!omit`.

## `!omit`

Produces an omission sentinel.

- In mappings, a value that renders to `!omit` removes the key.
- In sequences, an element that renders to `!omit` is skipped.
- At the root, `!omit` is **always an error**.

Example:

```yaml
params:
  debug: !if
    test: !var debug
    then: true
    else: !omit
```

## `!foreach`

Generate a collection by iterating.

### List output (default)

```yaml
tools: !foreach
  var: t
  in: !var enabled_tools
  template:
    name: !expr "t"
    enabled: true
```

### Dict output

```yaml
user_map: !foreach
  var: u
  in: !var users
  into: dict
  key: !expr "u.id"
  value:
    name: !expr "u.name"
    role: !expr "u.role"
```

### Set output

```yaml
unique_roles: !foreach
  var: u
  in: !var users
  into: set
  template: !expr "u.role"
```

Optional fields:

- `index`: bind loop index to a variable name
- `when`: filter; iterations where `when` renders falsy are skipped

Duplicate keys (for `into: dict`) are governed by `RenderOptions.dict_key_conflict`.

## `!expr`

Evaluate a restricted Python expression (AST-based).

### Scalar form

```yaml
max_tokens: !expr "base_tokens + bonus"
```

### Mapping form

```yaml
max_tokens: !expr
  expr: "base_tokens + bonus"
  strict: true
  default: 2048
```

Notes:

- In strict mode, missing names raise.
- If `strict: false` (or global non-strict), missing names use `default` if present.
- Attribute access and function calls inside expressions are enabled by default in `trusted` mode and disabled in `expr_safe`.

See `EXPRESSIONS.md` for details on allowed constructs.

## `!call`

Call a named function from a registry.

### Scalar form (rare; only useful for zero-arg functions)

```yaml
value: !call some_zero_arg_fn
```

### Mapping form (typical)

```yaml
user_id: !call
  fn: to_int
  args: [!var user_id_str]
  kwargs:
    default: 0
```

Semantics:

- The registry is provided by the caller (e.g. `engine.render(..., registry=...)`).
- Arguments are rendered before calling.

CLI note:

- If your template uses `!call`, provide a registry via `ydst render --registry-tier ...` or `--registry-module ...`.

## `!pipe`

Compose transformations.

```yaml
slug: !pipe
  - !var title
  - !call {fn: slugify, kwargs: {max_len: 20}}
```

Pipeline stages:

- First stage is rendered to an initial value.
- A `!call` stage receives the prior value as its first positional argument.
- A **string stage** (e.g. `slugify`) is treated as a registry function name when `RenderOptions.allow_pipe_registry_calls=True`.
  - By default, unknown stage names are an error (`RenderOptions.strict_pipe_stages=True`).
  - If `strict_pipe_stages=False`, unknown string stages are treated as literal values.
- A **callable stage** is only invoked when `RenderOptions.allow_callable_pipe_stages=True`.
  By default, callable stages raise an error (use `!call` or a registry string stage).

CLI note:

- Use `ydst render --pipe-unknown literal` to allow unknown string stages to be treated as literal values.

## `!include` (load-time include)

Load-time includes are resolved and parsed during `engine.load_template_*`.

### Scalar form

```yaml
common: !include includes/common.yaml
```

### Mapping form

```yaml
common: !include
  target: includes/common.yaml
  required: true
  default: !omit
```

Notes:

- `!include` is **load-time only**.
- `target` must be a literal (non-empty) string.
- When `required: false` and no `default` is provided, missing includes evaluate to `null` (`None`), not omission.
  Use `default: !omit` to omit keys/items.

## `!include_rt` (render-time include)

Render-time includes are resolved during rendering.

### Scalar form

```yaml
settings: !include_rt profiles/dev.yaml
```

### Mapping form

```yaml
settings: !include_rt
  target: !expr "'profiles/' + profile + '.yaml'"
  required: true
  default: {}
```

Notes:

- The include target can be templated (because `target` is rendered first).
- To avoid repeated file I/O, set `RenderOptions(cache_runtime_includes=True)`.
