from __future__ import annotations

import os as _os
import pathlib as _pathlib
import typing as _typing

import yaml as _yaml

import ydst.engine as engine_mod
import ydst.include as include_mod
import ydst.render as render_mod


def full_engine(
    *,
    include_paths: _typing.Sequence[str | _pathlib.Path] | None = None,
    include_cwd: bool = True,
) -> engine_mod.TemplateEngine:
    """Create a TemplateEngine with all features enabled.

    For trusted environments where template authors are trusted.

    Enables:
      - !python and !python_module tags
      - !call and !include_rt
      - Attribute/method access and function calls in !expr
      - Callable pipe stages
      - Load-time !include
      - Absolute paths in includes

    Args:
        include_paths: Directories to search for includes.
        include_cwd: If True (default), add current working directory to include paths.

    Example:
        # Full power, one line
        engine = ydst.api.full_engine()

        # Or set as default for the whole process
        ydst.set_default_engine(ydst.api.full_engine())
    """
    paths: list[str | _pathlib.Path] = list(include_paths or [])
    if include_cwd:
        paths.insert(0, _os.getcwd())

    include_resolver = include_mod.FileIncludeResolver(
        search_paths=paths,
        allow_absolute=True,
        enforce_roots=False,
    )

    options = render_mod.RenderOptions(
        mode="trusted",
        allow_python=True,
        allow_python_module=True,
        allow_callable_pipe_stages=True,
        allow_method_calls_in_expr=True,
        allow_private_attributes_in_expr=True,
    )

    return engine_mod.TemplateEngine(
        include_resolver=include_resolver,
        allow_load_time_includes=True,
        max_include_depth=None,  # No limit
        options=options,
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
