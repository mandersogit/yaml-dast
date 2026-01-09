from __future__ import annotations

import pathlib as _pathlib
import typing as _typing

import yaml as _yaml

import ydst.engine as engine_mod
import ydst.include as include_mod
import ydst.render as render_mod
import ydst.registry as registry_mod


SourceInput = str | bytes | _pathlib.Path | _typing.IO[str]


def load_template(
    source: SourceInput,
    *,
    engine: engine_mod.TemplateEngine | None = None,
    includes: include_mod.IncludeResolver | None = None,
    source_name: str | None = None,
) -> _typing.Any:
    """Load a template using a default engine unless one is provided.

    Semantics
    ---------
    `ydst.load_template` forwards to :meth:`TemplateEngine.load_template`.

    - If `source` is a `str`, it is treated as a **filesystem path**.
    - If you want to parse YAML text from a Python string, use :func:`load_template_text`.
    """

    eng = engine or engine_mod.TemplateEngine(include_resolver=includes)
    return eng.load_template(source, source_name=source_name)


def load_template_text(
    text: str,
    *,
    engine: engine_mod.TemplateEngine | None = None,
    includes: include_mod.IncludeResolver | None = None,
    source_name: str | None = None,
) -> _typing.Any:
    """Load a template from a YAML text string."""

    eng = engine or engine_mod.TemplateEngine(include_resolver=includes)
    return eng.load_template_text(text, source_name=source_name)


def load_template_file(
    path: str | _pathlib.Path,
    *,
    engine: engine_mod.TemplateEngine | None = None,
    includes: include_mod.IncludeResolver | None = None,
) -> _typing.Any:
    """Load a template from a filesystem path."""

    eng = engine or engine_mod.TemplateEngine(include_resolver=includes)
    return eng.load_template_file(path)


def render(
    template: _typing.Any,
    context: _typing.Mapping[str, _typing.Any] | None = None,
    *,
    registry: registry_mod.FunctionRegistry | None = None,
    options: render_mod.RenderOptions | None = None,
    engine: engine_mod.TemplateEngine | None = None,
    include_resolver: include_mod.IncludeResolver | None = None,
) -> _typing.Any:
    """Render a template using a default engine unless provided."""

    eng = engine or engine_mod.TemplateEngine(include_resolver=include_resolver)
    return eng.render(
        template,
        context=dict(context or {}),
        registry=registry,
        options=options,
        include_resolver=include_resolver,
    )


def safe_engine(
    *,
    include_paths: _typing.Sequence[str | _pathlib.Path] | None = None,
    include_max_bytes: int = 1_000_000,
    include_cache_max: int = 256,
    max_include_depth: int | None = 20,
    allow_load_time_includes: bool = False,
) -> engine_mod.TemplateEngine:
    """Create a TemplateEngine configured with conservative defaults."""

    include_resolver = None
    if include_paths:
        include_resolver = include_mod.FileIncludeResolver(
            search_paths=list(include_paths),
            allow_absolute=False,
            enforce_roots=True,
            max_bytes=include_max_bytes,
            cache=True,
            cache_max=include_cache_max,
        )

    return engine_mod.TemplateEngine(
        include_resolver=include_resolver,
        base_loader=_yaml.SafeLoader,  # type: ignore[arg-type]
        max_include_depth=max_include_depth,
        allow_load_time_includes=allow_load_time_includes,
    )


def safe_render(
    template: _typing.Any,
    context: _typing.Mapping[str, _typing.Any] | None = None,
    *,
    engine: engine_mod.TemplateEngine | None = None,
    include_paths: _typing.Sequence[str | _pathlib.Path] | None = None,
    registry: registry_mod.FunctionRegistry | None = None,
    options: render_mod.RenderOptions | None = None,
) -> _typing.Any:
    """Render with defensive defaults (locked-down mode, strict by default)."""

    eng = engine or safe_engine(include_paths=include_paths)
    opts = options or render_mod.RenderOptions(mode="locked_down", strict=True)

    reg = registry if registry is not None else registry_mod.safe_registry()
    return eng.render(template, context=dict(context or {}), registry=reg, options=opts)
