# CLI

ydst includes a small CLI for rendering templates.

Install (editable):

```bash
pip install -e .
```

## Render

Basic:

```bash
ydst render template.yaml --context-file ctx.json --registry-tier safe
```

Write output to a file:

```bash
ydst render template.yaml --context-file ctx.json --registry-tier safe --output-file out.json
```

Enable a JSONL trace of render events (written to stderr by default):

```bash
ydst render template.yaml --context-file ctx.json --registry-tier safe --trace
```

Or write trace to a file:

```bash
ydst render template.yaml --context-file ctx.json --registry-tier safe --trace-file trace.jsonl
```

Read template from stdin:

```bash
cat template.yaml | ydst render - --context-file ctx.json --registry-tier safe
```

## Context input

JSON:

- `--context-file ctx.json`
- `--context '{"name": "Alice"}'`

YAML:

- `--context-yaml-file ctx.yaml`
- `--context-yaml 'name: Alice'`

## Output formats

- `--output json` (default)
- `--output yaml`

When producing JSON, sets are converted to sorted lists for JSON compatibility.

## Includes

```bash
ydst render template.yaml --context-file ctx.json --registry-tier safe --include-path .
```

Disable load-time includes (`!include`) even if include paths are configured:

```bash
ydst render template.yaml --context-file ctx.json --registry-tier safe --include-path . --disable-load-includes
```

Hardening options:

- `--include-disallow-absolute` disallows absolute include targets
- `--include-enforce-roots` requires resolved includes to remain within the configured `--include-path` roots
- `--max-include-depth N` limits include nesting depth (load-time includes)

## YAML loader

- default: `yaml.SafeLoader`
- `--full-loader` uses `yaml.FullLoader`

## Modes and strictness

- `--mode trusted|expr_safe|locked_down`
- `--non-strict` toggles global strictness off

`locked_down` is a restrictive preset:

- disables `!call`
- disables render-time includes (`!include_rt`)
- disables registry-based string stages in `!pipe`
- disables attribute access and function calls inside `!expr`

Duplicate dict keys during rendering:

- `--dict-key-conflict auto|error|last|first`

## Pipe behavior

By default, unknown string stages in `!pipe` are treated as an error (recommended to catch typos).

To allow unknown string stages to be treated as literal values:

```bash
ydst render template.yaml --context-file ctx.json --registry-tier safe --pipe-unknown literal
```

To disallow registry string stages in `!pipe` entirely:

```bash
ydst render template.yaml --context-file ctx.json --registry-tier safe --no-pipe-registry-calls
```

To allow callable pipe stages (advanced; disabled by default):

```bash
ydst render template.yaml --context-file ctx.json --registry-tier safe --callable-pipe-stages
```

## Registries

Built-in tiers:

- `--registry-tier none` (default)
- `--registry-tier minimal`
- `--registry-tier safe`
- `--registry-tier extended`

Custom registries:

```bash
ydst render template.yaml --context-file ctx.json --registry-module mypkg.reg --registry-tier safe
```

The module must define `REGISTRY` or `registry`.

## Debugging

- `--raw-exceptions` disables ydst exception wrapping
- `--max-depth` and `--max-nodes` provide evaluation limits
- `--debug` prints a traceback on errors

## Exit codes

- `0` success
- `2` ydst error (template load/render/validation)
- `1` unexpected error
