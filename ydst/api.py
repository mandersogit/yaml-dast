from __future__ import annotations

from pathlib import Path
from typing import Any, IO, Mapping, Optional, Union

from .engine import TemplateEngine
from .include import IncludeResolver
from .render import RenderOptions
from .registry import FunctionRegistry


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
