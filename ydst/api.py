from __future__ import annotations

from pathlib import Path
from typing import Any, IO, Mapping, Optional, Sequence, Union

import yaml

from .engine import TemplateEngine
from .include import IncludeResolver, FileIncludeResolver
from .render import RenderOptions
from .registry import FunctionRegistry, safe_registry


SourceInput = Union[str, bytes, Path, IO[str]]


def load_template(
    source: SourceInput,
    *,
    engine: TemplateEngine | None = None,
    includes: IncludeResolver | None = None,
    source_name: str | None = None,
) -> Any:
    """Convenience function: load a template using a default engine unless provided.

    Semantics
    ---------
    `ydst.load_template` forwards to :meth:`TemplateEngine.load_template`.

    - If `source` is a `str`, it is treated as a **filesystem path**.
    - If you want to parse YAML text from a Python string, use :func:`load_template_text`.

    Parameters
    ----------
    engine:
        A `TemplateEngine` instance to use.

    includes:
        Optional include resolver to install on the default engine (ignored if `engine` is provided).

    source_name:
        Optional source identifier for error reporting.
    """

    eng = engine or TemplateEngine(include_resolver=includes)
    return eng.load_template(source, source_name=source_name)


def load_template_text(
    text: str,
    *,
    engine: TemplateEngine | None = None,
    includes: IncludeResolver | None = None,
    source_name: str | None = None,
) -> Any:
    """Load a template from a YAML text string.

    This is equivalent to :func:`load_template` but makes it explicit that the input is YAML content.
    """

    eng = engine or TemplateEngine(include_resolver=includes)
    return eng.load_template_text(text, source_name=source_name)


def load_template_file(
    path: str | Path,
    *,
    engine: TemplateEngine | None = None,
    includes: IncludeResolver | None = None,
) -> Any:
    """Load a template from a filesystem path."""

    eng = engine or TemplateEngine(include_resolver=includes)
    return eng.load_template_file(path)


def render(
    template: Any,
    context: Mapping[str, Any] | None = None,
    *,
    registry: FunctionRegistry | None = None,
    options: RenderOptions | None = None,
    engine: TemplateEngine | None = None,
    include_resolver: IncludeResolver | None = None,
) -> Any:
    """Convenience function: render a template using a default engine unless provided."""

    eng = engine or TemplateEngine(include_resolver=include_resolver)
    return eng.render(
        template,
        context=dict(context or {}),
        registry=registry,
        options=options,
        include_resolver=include_resolver,
    )


def safe_engine(
    *,
    include_paths: Sequence[str | Path] | None = None,
    include_max_bytes: int = 1_000_000,
    include_cache_max: int = 256,
    max_include_depth: int | None = 20,
    allow_load_time_includes: bool = False,
) -> TemplateEngine:
    """Create a `TemplateEngine` configured with conservative defaults.

    - Uses `yaml.SafeLoader`
    - Disables load-time includes by default
    - If `include_paths` is provided, includes are constrained to those roots
      with an optional byte limit and caching enabled.
    """

    include_resolver = None
    if include_paths:
        include_resolver = FileIncludeResolver(
            search_paths=list(include_paths),
            allow_absolute=False,
            enforce_roots=True,
            max_bytes=include_max_bytes,
            cache=True,
            cache_max=include_cache_max,
        )

    return TemplateEngine(
        include_resolver=include_resolver,
        base_loader=yaml.SafeLoader,
        max_include_depth=max_include_depth,
        allow_load_time_includes=allow_load_time_includes,
    )


def safe_render(
    template: Any,
    context: Mapping[str, Any] | None = None,
    *,
    engine: TemplateEngine | None = None,
    include_paths: Sequence[str | Path] | None = None,
    registry: FunctionRegistry | None = None,
    options: RenderOptions | None = None,
) -> Any:
    """Render with defensive defaults (locked-down mode, strict by default).

    This is intended for situations where template inputs are not fully trusted.

    Notes:
      - `RenderOptions(mode="locked_down")` disables calls, includes, and most
        expression power.
      - A `safe` built-in registry is installed by default, but it is effectively
        unused under `locked_down` unless you explicitly loosen the mode.
    """

    eng = engine or safe_engine(include_paths=include_paths)
    opts = options or RenderOptions(mode="locked_down", strict=True)

    reg = registry if registry is not None else safe_registry()
    return eng.render(template, context=dict(context or {}), registry=reg, options=opts)
