# Tag reference

This document describes the templating tags supported by ydst.

All tags create **template nodes** during load and are evaluated during render.

## `!var` / `!variable`

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

- Lookup order: loop scope → global context
- If missing:
  - strict + required → error
  - otherwise → render `default` if provided, else `null`

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
- At the root, `!omit` is an error in strict mode.

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

Scalar form:

```yaml
max_tokens: !expr "base_tokens + bonus"
```

Mapping form:

```yaml
max_tokens: !expr
  expr: "base_tokens + bonus"
  strict: true
  default: 2048
```

Notes:

- In strict mode, missing names raise.
- If `strict: false` (or global non-strict), missing names use `default` if present.
- Attribute access is enabled by default in trusted mode and disabled in safe mode.

See `EXPRESSIONS.md` for details on allowed constructs.

## `!call`

Call a named function from a registry.

Scalar form (rare; only useful for zero-arg functions):

```yaml
# e.g., if your registry provides a zero-arg function
value: !call some_zero_arg_fn
```

Mapping form (typical):

```yaml
user_id: !call
  fn: to_int
  args: [!var user_id_str]
  kwargs:
    default: 0
```

- The registry is provided by the caller (or `--default-registry` in CLI).
- Arguments are rendered before calling.

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
- A string stage (e.g., `slugify`) calls the named function **if present** in the registry.
  If the name is not present, the string is treated as a literal stage result.
- A callable stage is only invoked when `RenderOptions(allow_callable_pipe_stages=True)`.
  By default, callable stages raise an error (use `!call` or a registry string stage).

## `!include` (load-time include)

Scalar form:

```yaml
common: !include includes/common.yaml
```

Mapping form (explicit timing):

```yaml
common: !include
  target: includes/common.yaml
  timing: load       # load|render|runtime|rt
  required: true
  default: !omit
```

- Load-time includes are resolved and parsed immediately during `engine.load_template(...)`.
- When `required: false` and no `default` is provided, missing includes evaluate to `null` (`None`),
  not omission. Use `default: !omit` to omit keys/items.

## `!include_rt` / `!include_runtime` / `!include_render` (render-time include)

Scalar form:

```yaml
settings: !include_rt profiles/dev.yaml
```

Mapping form:

```yaml
settings: !include_rt
  target: !expr "'profiles/' + profile + '.yaml'"
  required: true
  default: {}
```

- Render-time includes are resolved during rendering.
- The include target can be templated (because `target` is rendered first).
- Render-time includes require a `TemplateEngine` instance during rendering.
