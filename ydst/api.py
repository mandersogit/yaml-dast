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
    loader: TemplateEngine | None = None,
    includes: IncludeResolver | None = None,
    source_name: str | None = None,
) -> Any:
    """Convenience function: load a template using a default engine unless provided."""
    engine = loader or TemplateEngine(include_resolver=includes)
    return engine.load_template(source, source_name=source_name)


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
    return eng.render(template, context=dict(context or {}), registry=registry, options=options, include_resolver=include_resolver)
