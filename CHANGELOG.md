# Changelog


## 0.4.0 (unreleased)

### Breaking changes

- **`!setdefault` is now enabled by default** and is no longer disabled by `mode="locked_down"`.
  The tag is safe (cannot override caller-provided context values) and appropriate for semi-trusted templates.
  - Removed `--allow-setdefault` CLI flag (no longer needed)
  - `RenderOptions.allow_setdefault` now defaults to `True`

- **Removed dict attribute convenience in `!expr`**: Previously, `x.key` on a dict-like object
  would return `x["key"]` if the key existed. This behavior has been removed because it could
  shadow dict methods (e.g., a key named `"items"` would shadow `.items()`).
  Use explicit subscript syntax: `x["key"]`.

### Fixed

- **OMIT values are now correctly filtered from lists and sets**: Previously, `!omit`, `!setdefault`,
  and `!python_module` (which all return OMIT) would appear as `Omit(mark=None)` in list output
  instead of being filtered. This now matches the documented behavior ("In sequences, an element
  that renders to `!omit` is skipped").

### Improved

- Error messages for disabled tags now include instructions on how to enable them.

### Added

- Comprehensive test coverage for `!python`, `!python_module`, and `!setdefault`.
- Documentation for stateful patterns using `!python` and `!python_module` together.
- Documentation for implicit emit limitations in `!python`.
- Documentation for mode precedence (modes override individual options).


## 0.3.1 (2026-01-08)

### Fixed
- Added missing `_PythonEmitSignal` exception class to `render.py` (was referenced but undefined).
- Fixed type annotations across codebase for mypy compliance.
- Fixed test imports to follow project coding standards (qualified imports).
- Renamed shadowed variables in `expr.py` and `loader.py` to satisfy mypy.

### Changed
- Makefile now defaults `PYTHON_EXE` to `local.venv/bin/python` instead of requiring it to be set.
- Extended `make lint` and `make typecheck` to cover `tests/` and `scripts/` directories.
- Renamed `scripts/commit-helper` to `scripts/commit-helper.py` for tooling compatibility.

### Added
- Added `types-PyYAML` to dev dependencies for type checking.
- Added PyPI classifiers, keywords, and project URLs to `pyproject.toml`.
- Added version validation to `commit-helper.py`: checks that tag `vX.Y.Z` matches `pyproject.toml` version.
- Added Python 3.11+ version check to `commit-helper.py` with helpful error message.


## 0.3.0 (2026-01-05)

### Breaking changes
- **Python >= 3.11 is now required.**

### Added
- New `!setdefault` tag for defining defaults into the render-time local scope (opt-in via `RenderOptions.allow_setdefault`).
- New `!python` tag for executing embedded Python and emitting a value (opt-in via `RenderOptions.allow_python`).  
  - Supports implicit emit of the trailing expression, unless `python_strict_emit`/`strict_emit` is enabled.
- New `!python_module` tag for defining helper functions/constants in a shared module scope (opt-in via `RenderOptions.allow_python_module`).  
  - Functions defined here are available to `!call`/`!pipe` registry lookups and `!expr` function calls.
- CLI: added `--allow-setdefault`, `--allow-python`, `--allow-python-module`, and `--python-strict-emit`.

### Notes
- These power features are disabled by default and are also disabled by `mode="locked_down"`.

## 0.2.1 (2026-01-03)

### Correctness

- `!foreach` nodes now default presence-sensitive fields (`template`, `key`, `value`) to `UNSET` for better consistency with validation when templates are constructed programmatically.
- Renderer now defensively errors if a programmatic `!foreach` is missing required fields (rather than rendering `UNSET` through to the output).
- Include root-enforcement now uses `Path.relative_to(...)` for cross-platform correctness.

### API

- Exported `RenderOptions` and `TraceEvent` at the package top level (`from ydst import RenderOptions`).
- Added `safe_engine(...)` and `safe_render(...)` convenience helpers for conservative defaults.

### CLI

- Default `--registry-tier` is now `safe` (use `--registry-tier none` to disable).
- Improved `--full-loader` help text to better communicate risk.
- Added `ydst validate` and `ydst deps` commands.

### Maintenance

- Removed an unused `warnings` import.
- Reduced duplication in error classes.


## 0.2.0 (2026-01-02)

### Breaking changes (pre-1.0 cleanup)

- **Loading semantics**: `TemplateEngine.load_template(...)` and `ydst.load_template(...)` now treat a `str` input as a **filesystem path**.
  - Use `load_template_text(...)` / `TemplateEngine.load_template_text(...)` for YAML text.
  - `load_template_file(...)` remains explicit and unchanged.
- **API cleanup**: removed the deprecated `loader=` parameter from `ydst.load_template(...)`; use `engine=`.
- **Modes**: removed `mode="safe"` and `mode="lockdown"` aliases.
  - Use `mode="expr_safe"` or `mode="locked_down"`.
- **Tag set cleanup**: removed tag aliases.
  - `!variable` → use `!var`.
  - `!include_runtime` / `!include_render` → use `!include_rt`.
- **Include syntax**: `!include` is now **load-time only** (no `timing:` field).
  - Render-time include is always `!include_rt`.
- **Registry tiers**: `default_registry()` is now the **safe-by-default** tier.
  - Use `extended_registry()` for environment access (`env`) and other extended helpers.
- **`!pipe` defaults**: unknown string stages now **error by default** (`RenderOptions.strict_pipe_stages=True`).
- **Root `!omit`**: rendering a root-level `!omit` now **always raises** `RootOmitError` (regardless of strictness).
- **Template nodes**: core node dataclasses are now `slots=True` + `frozen=True` (treated as immutable).

### CLI changes

- Removed `--default-registry`.
- `--registry-tier` values are now: `none`, `minimal`, `safe`, `extended`.
- `--mode` choices are now: `trusted`, `expr_safe`, `locked_down`.



## 0.1.6 (2026-01-02)

### Changes
- Added `TemplateEngine(allow_load_time_includes=...)` to explicitly disable load-time includes (`!include`), even if an include resolver is configured.
- Improved `RenderOptions` normalization:
  - `mode="safe"` is now a deprecated alias for `mode="expr_safe"`.
  - `RenderOptions.validate()` is called during normalization to catch invalid option values early.
- Improved expression compile error behavior:
  - When `wrap_exceptions=False`, compile-time errors now surface their original exception types (e.g., `TemplateValidationError`).
  - When wrapped, `ExpressionError` messages include the underlying reason.
- Added explicit top-level and engine convenience loaders:
  - `load_template_text(...)` and `load_template_file(...)` to avoid ambiguity when passing a `str`.
- Improved error path formatting for non-string keys (avoids misleading dotted paths like `$.None`).
- Expanded `validate_template(...)` to validate structural invariants for `!foreach`, `!call`, `!include_rt`, and `!default`, and to optionally enforce `RenderOptions` restrictions (e.g., `locked_down`).
- Added template analysis helpers (`collect_expressions`, `collect_calls`, `collect_includes`, `analyze_dependencies`).
- Added `to_jsonable(...)` helper for producing JSON-serializable outputs.
- CLI improvements:
  - `--output-file` to write rendered output to a file.
  - `--trace` / `--trace-file` for JSONL render traces.
  - `--disable-load-includes` to disable `!include`.
- Added `py.typed` marker for improved typing support.

## 0.1.5 (2026-01-02)

### Correctness

- `!foreach` now treats `template: null` (and `key: null` / `value: null`) as *present* instead of raising a load error.
- `!foreach` error contexts now retain the iteration index for `when:` evaluation and for `into:dict` / `into:set` post-render checks (duplicate keys, unhashable outputs).
- CLI `ydst render` now serializes a root-level `!omit` in non-strict mode as `null` (YAML/JSON), and the JSON conversion now handles `OMIT` defensively.

### API / ergonomics

- `RenderOptions` now exposes the remaining `ExprPolicy` controls: `allow_subscripts_in_expr` and `allow_private_attributes_in_expr`.
- `validate_template()` is now validation-only and does not mutate templates; the unused internal `Expr._compiled` cache was removed.
- Improved error paths for `!call` arguments/kwargs and `!pipe` stages (structured `$.args[0]` / `$.pipe[1]` paths).

### Security / hardening

- `FileIncludeResolver` now supports `max_bytes=...` to bound include file size.
- `TemplateEngine(max_include_depth=...)` (and render-time includes) can now enforce maximum include nesting depth.
- `runtime_include_cache_max` is now bounded by default (128) to avoid unbounded per-render caching.

## 0.1.4 (2026-01-02)

### Correctness

- `!omit` is now falsy, preventing surprising behavior when used in `!if` tests and `!foreach` when clauses.
- YAML constructors now validate boolean fields (`required`, `strict`, etc.) as booleans instead of coercing truthiness from non-bool values.
- `!foreach` loader now distinguishes missing keys from explicit `null` values and correctly handles `var:`/`as:` selection even when empty strings are supplied.
- Load-time `!include` now enforces `target` being a literal non-empty string (templated / non-string targets must use `!include_rt`).
- Load-time include cycle errors are now reported as `TemplateLoadError` (not a render-time error type).
- Improved error paths for `!foreach into: dict` by tagging key vs value evaluation in the path.

### API / ergonomics

- Added `mode="locked_down"` (and `mode="expr_safe"` alias) to make expression and execution policy clearer:
  - `locked_down` disables `!call`, `!include_rt`, registry-driven `!pipe` string stages, and callable pipe stages.
- Added `RenderOptions.allow_calls`, `allow_includes`, `allow_pipe_registry_calls`, `strict_pipe_stages`, and `materialize_foreach_iterables`.
- `TemplateLoadError` and `TemplateValidationError` now render contextualized messages via `__str__` (matching `RenderError`).
- `ydst.api.load_template(..., loader=...)` now emits a deprecation warning; prefer `engine=`.
- Exported `validate_template` and `collect_variables` from the top-level package.

### Security / hardening

- `FileIncludeResolver` now supports `allow_absolute=False` and `enforce_roots=True` to restrict include targets to an allowlisted directory set.
- Added registry tiers: `minimal_registry()`, `safe_registry()`, and `extended_registry()` (alias for the existing `default_registry()`).

### CLI

- CLI now supports YAML context via `--context-yaml` / `--context-yaml-file`.
- Improved CLI error handling and exit codes; `--debug` enables tracebacks.
- JSON output now handles sets (converted to stable lists) and non-JSON dict keys (stringified).

### Tests

- Added tests covering the above fixes and new options.

## 0.1.3 (2026-01-02)

### Correctness

- `!pipe` string stages now only call registry functions **if** the registry contains a callable of that name.
  Otherwise, the string is treated as a literal stage result (matching the documented semantics).
- Load-time `!include` now matches `!var`/`!expr`/`!include_rt` default behavior:
  when `required: false` and no `default` is provided, missing includes produce `None` (not an omit sentinel).
- YAML load errors now preserve line/column information when available from PyYAML exceptions.

### API / ergonomics

- Added `UNSET` sentinel to distinguish "no default provided" from "omit".
  `Var.default`, `Expr.default`, and `IncludeRuntime.default` now default to `UNSET`.
- Added `RenderOptions.allow_callable_pipe_stages` (default: `False`) to prevent arbitrary callables
  from being invoked as `!pipe` stages. `mode="safe"` forces this off.
- Added a per-render runtime include template cache:
  - `RenderOptions.cache_runtime_includes` (default: `True`)
  - `RenderOptions.runtime_include_cache_max` (default: `None`, meaning unbounded per render)

### Performance

- `!expr` evaluation no longer copies the scope ChainMap into a new dict per expression.
- `ExpressionEvaluator` is now built once per render invocation and reused.
- `FileIncludeResolver` optionally caches include resolution results (`cache=...`, `cache_max=...`).

### Packaging

- Declared `requires-python >=3.10` (code uses `|` type union syntax).

### Documentation & tests

- Updated docs to describe the new pipe semantics, default handling, and caching options.
- Added tests covering the above.

## 0.1.2 (2026-01-02)

### Correctness

- `!expr` function calls no longer depend on registries implementing `keys()`.
  Functions are resolved by name via `registry.get(name)` at evaluation time, which also fixes
  failures when using `chain_registries(... )`.
- `!expr` now rejects dict unpacking (`{**d}`) at validation time and also defends at runtime.
- `max_depth` now constrains recursion for deep container-only templates (not just template nodes).
- `default: !omit` is now honored for `!var`, `!expr`, and `!include_rt`.
- Includes now distinguish "missing" from "empty file" (`IncludeResult.content: str | None`).

### API / ergonomics

- `ydst.api.load_template(...)` now accepts `engine=` as the primary parameter; `loader=` remains as an alias.
- `RenderError.__str__` now returns the contextualized `pretty()` form by default.

### Documentation

- Updated expression and include documentation to reflect the above behavior changes.
- Clarified the security posture of `mode="safe"` (it only affects `!expr`).
