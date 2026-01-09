# Template analysis helpers

ydst includes small static analysis helpers that walk a loaded template graph and collect
information that is useful for tooling (linting, CI checks, prewarming include caches, etc.).

These functions operate on the *already-loaded* template object graph.

Important limitation: **load-time includes (`!include`) are inlined during load**, so the original include edges are not visible to post-load analysis.

## Functions

- `collect_variables(template)` — returns a `set[str]` of variable names referenced by `!var` nodes.
- `collect_expressions(template)` — returns a `set[str]` of expression strings referenced by `!expr` nodes.
- `collect_calls(template)` — returns a `set[str]` of function names referenced by `!call` nodes.
- `collect_includes(template)` — returns a `set[str]` of *static* render-time include targets (`!include_rt`) when the target is a literal string.
- `analyze_dependencies(template, registry=None)` — returns a `Dependencies` record combining the above, plus a small amount of metadata.

## Example

```python
from ydst import TemplateEngine, analyze_dependencies, default_registry

engine = TemplateEngine()

tmpl = engine.load_template(
    """
model: !default
  - !var {name: model, required: false}
  - gpt-5

transformed: !pipe
  - !var text
  - strip
  - lower

settings: !include_rt
  target: "profiles/dev.yaml"
  required: false
  default: {}
""",
    source_name="inline.yaml",
)

deps = analyze_dependencies(tmpl, registry=default_registry())
print(deps.variables)
print(deps.calls)
print(deps.pipe_registry_functions)
print(deps.includes)
```
