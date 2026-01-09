# CLI

ydst includes a small CLI for rendering templates.

Install (editable):

```bash
pip install -e .
```

## Render

```bash
ydst render template.yaml --context-file ctx.json --default-registry
```
Write output to a file:

```bash
ydst render template.yaml --context-file ctx.json --output-file out.json
```

Enable a JSONL trace of render events (written to stderr by default):

```bash
ydst render template.yaml --context-file ctx.json --trace
```

Or write trace to a file:

```bash
ydst render template.yaml --context-file ctx.json --trace-file trace.jsonl
```


Read template from stdin:

```bash
cat template.yaml | ydst render - --context-file ctx.json --default-registry
```

### Context input

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

In non-strict mode (`--non-strict`), a root-level `!omit` renders as JSON/YAML `null` in the CLI (the library API still returns the `OMIT` sentinel).

## Includes

```bash
ydst render template.yaml --context-file ctx.json --include-path . --default-registry
```

Disable load-time includes (`!include`) even if include paths are configured:

```bash
ydst render template.yaml --context-file ctx.json --include-path . --disable-load-includes
```

Hardening options:

- `--include-disallow-absolute` disallows absolute include targets
- `--include-enforce-roots` requires resolved includes to remain within the configured `--include-path` roots

## YAML loader

- default: `yaml.SafeLoader`
- `--full-loader` uses `yaml.FullLoader`

## Modes and strictness

- `--mode trusted|expr_safe|locked_down` (alias: `safe` is accepted but deprecated)
- `--non-strict` toggles global strictness off

`locked_down` is intended as a safer preset: it disables `!call`, disables render-time includes, and disables string-to-registry resolution in `!pipe`.

Duplicate dict keys during rendering:

- `--dict-key-conflict auto|error|last|first`

## Debugging

- `--raw-exceptions` disables ydst exception wrapping
- `--max-depth` and `--max-nodes` provide evaluation limits
- `--debug` prints a traceback on errors

## Registries

Built-in tiers:

- `--default-registry` (legacy convenience tier)
- `--registry-tier minimal|safe|default|extended`

Custom registries:

```bash
ydst render template.yaml --context-file ctx.json --registry-module mypkg.reg --default-registry
```

The module must define `REGISTRY` or `registry`.

## Exit codes

- `0` success
- `2` ydst error (template load/render/validation)
- `1` unexpected error
