# Example 07 — Layer then render

This example demonstrates the intended integration pattern with an external deep-merge / layering system:

1. load multiple YAML files into **template graphs**
2. merge those graphs (treating template nodes as atomic leaves)
3. render once at the end

Files:

- `layer_base.yaml`
- `layer_override.yaml`

## Sketch (no external dependencies)

```python
from copy import deepcopy
from ydst import TemplateEngine, default_registry

def deep_merge(a, b):
    # A minimal deep-merge for demonstration purposes:
    # - dicts merge recursively
    # - lists concatenate
    # - everything else: b overwrites a
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, bv in b.items():
            if k in out:
                out[k] = deep_merge(out[k], bv)
            else:
                out[k] = bv
        return out
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    return b

engine = TemplateEngine()
base = engine.load_template_file("layer_base.yaml")
override = engine.load_template_file("layer_override.yaml")

merged_template = deep_merge(base, override)

rendered = engine.render(
    merged_template,
    context={"temperature": 0.7},
    registry=default_registry(),
)

print(rendered)
```

Notes:

- This merge function is intentionally simplistic; use your project's real deep-merge/layering approach.
- The important part is merging **templates** (which may contain `ydst` nodes) before calling `render`.
