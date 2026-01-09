from __future__ import annotations

import warnings

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
    loader: TemplateEngine | None = None,
    includes: IncludeResolver | None = None,
    source_name: str | None = None,
) -> Any:
    """Convenience function: load a template using a default engine unless provided.

    Important ergonomics note
    -------------------------
    If `source` is a string, it is treated as YAML *content*, not a filesystem path.

    For filesystem paths, prefer:
      - :func:`ydst.load_template_file` / :meth:`TemplateEngine.load_template_file`, or
      - pass a :class:`pathlib.Path`.

    Parameters
    ----------
    engine:
        A `TemplateEngine` instance to use.

    loader:
        Backwards-compatible alias for `engine`.
        (Historically, this parameter was named `loader`, but it accepts a TemplateEngine.)

    includes:
        Optional include resolver to install on the default engine (ignored if `engine` is provided).

    source_name:
        Optional source identifier for error reporting.
    """

    if engine is not None and loader is not None:
        raise ValueError("Pass only one of: engine=..., loader=...")

    if loader is not None:
        warnings.warn(
            "`loader` is deprecated; use `engine` instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    eng = engine or loader or TemplateEngine(include_resolver=includes)
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
