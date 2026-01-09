# CLI

ydst includes a small CLI for rendering templates with JSON context.

Install:

```bash
pip install -e .
```

Basic render:

```bash
ydst render template.yaml --context-file ctx.json --default-registry
```

Read template from stdin:

```bash
cat template.yaml | ydst render - --context-file ctx.json --default-registry
```

Output formats:

- `--output json` (default)
- `--output yaml`

Includes:

```bash
ydst render template.yaml --context-file ctx.json --include-path . --default-registry
```

YAML loader:

- default: `yaml.SafeLoader`
- `--full-loader` uses `yaml.FullLoader`

Modes and strictness:

- `--mode trusted|safe`
- `--non-strict` toggles global strictness off

Duplicate dict keys during rendering:

- `--dict-key-conflict auto|error|last|first`

Debugging:

- `--raw-exceptions` disables ydst exception wrapping
- `--max-depth` and `--max-nodes` provide evaluation limits

Custom registries:

```bash
ydst render template.yaml --context-file ctx.json --registry-module mypkg.reg --default-registry
```

The module must define `REGISTRY` or `registry`.
