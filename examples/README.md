# ydst examples

These examples are designed to be runnable with the `ydst` CLI and readable as copy/paste blocks.

Assuming you are in the repository root (the directory containing `pyproject.toml`):

```bash
pip install -e .
```

Then:

```bash
cd examples
```

> Note: examples that use `!include` / `!include_rt` require include search paths; the commands below include `--include-path .`.

---

## 01 — Basic `!var`, `!expr`, `!foreach`

Template: `01-basic.yaml`

```yaml
model: gpt-5
params:
  temperature: !var temperature
  max_tokens: !expr "base_tokens + bonus_tokens"

tools: !foreach
  var: t
  in: !var enabled_tools
  template:
    name: !expr "t"
    enabled: true
```

Context: `01-basic.json`

```json
{
  "temperature": 0.2,
  "base_tokens": 1000,
  "bonus_tokens": 500,
  "enabled_tools": ["search", "calc"]
}
```

Run:

```bash
ydst render 01-basic.yaml --context-file 01-basic.json --default-registry
```

---

## 02 — Conditional keys with `!if` + `!omit`

Template: `02-if-omit.yaml`

```yaml
mode: !var mode

params:
  temperature: !if
    test: !expr "mode == 'creative'"
    then: 0.8
    else: 0.2

  reasoning: !if
    test: !expr "mode == 'creative'"
    then: high
```

Run (creative):

```bash
ydst render 02-if-omit.yaml --context-file 02-if-omit-creative.json --default-registry
```

Run (normal):

```bash
ydst render 02-if-omit.yaml --context-file 02-if-omit-normal.json --default-registry
```

---

## 03 — `!foreach` into a dict

Template: `03-foreach-dict.yaml`

```yaml
users_by_id: !foreach
  var: u
  in: !var users
  into: dict
  key: !expr "u.id"
  value:
    name: !expr "u.name"
    is_admin: !expr "u.role == 'admin'"
```

Context: `03-foreach-dict.json`

Run:

```bash
ydst render 03-foreach-dict.yaml --context-file 03-foreach-dict.json --default-registry
```

---

## 04 — `!pipe` + `!call`

Template: `04-pipe-call.yaml`

```yaml
title: !var title

slug: !pipe
  - !var title
  - !call {fn: slugify, kwargs: {max_len: 20}}

payload_json: !pipe
  -
    title: !var title
    slug: !pipe
      - !var title
      - !call {fn: slugify}
  - !call {fn: json_dumps}
```

Run:

```bash
ydst render 04-pipe-call.yaml --context-file 04-pipe-call.json --default-registry
```

---

## 05 — Load-time include (`!include`)

Template: `05-include-load.yaml`

```yaml
meta: !include includes/common.yaml

service:
  name: demo
  owner: !expr "meta.owner"
  labels: !expr "meta.labels"
```

Run:

```bash
ydst render 05-include-load.yaml --context-file 05-include-load.json --default-registry --include-path .
```

---

## 06 — Render-time include (`!include_rt`)

Template: `06-include-runtime.yaml`

```yaml
profile: !var profile

settings: !include_rt
  target: !expr "'profiles/' + profile + '.yaml'"
  required: true
```

Run (dev):

```bash
ydst render 06-include-runtime.yaml --context-file 06-include-runtime-dev.json --default-registry --include-path .
```

Run (prod):

```bash
ydst render 06-include-runtime.yaml --context-file 06-include-runtime-prod.json --default-registry --include-path .
```

---

## 07 — Layer then render

See `07-layer-then-render.md` plus `layer_base.yaml` and `layer_override.yaml`.

---

## 08 — `!default` (coalesce / fallback)

Template: `08-default.yaml`

```yaml
model: !default
  - !var {name: model, required: false}
  - "gpt-5"

timeout_seconds: !default
  value: !var {name: timeout_seconds, required: false}
  default: 30
  treat_none_as_missing: false

raw_timeout_seconds: !var {name: timeout_seconds, required: false}
```

Context: `08-default.json`

```json
{
  "timeout_seconds": null
}
```

Run:

```bash
ydst render 08-default.yaml --context-file 08-default.json --default-registry
```
