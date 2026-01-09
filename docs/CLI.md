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

## Includes

```bash
ydst render template.yaml --context-file ctx.json --include-path . --default-registry
```

Hardening options:

- `--include-disallow-absolute` disallows absolute include targets
- `--include-enforce-roots` requires resolved includes to remain within the configured `--include-path` roots

## YAML loader

- default: `yaml.SafeLoader`
- `--full-loader` uses `yaml.FullLoader`

## Modes and strictness

- `--mode trusted|safe|expr_safe|locked_down`
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
