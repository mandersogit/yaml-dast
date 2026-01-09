from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Callable, Dict, IO, Optional, Type, Union

import yaml

from .errors import ErrorContext, IncludeCycleError, TemplateLoadError
from .include import IncludeResolver
from .loader import TemplateLoaderMixin
from .nodes import SourceMark
from .render import RenderOptions, render_template
from .registry import FunctionRegistry

SourceInput = Union[str, bytes, Path, IO[str]]


def _is_filelike(obj: Any) -> bool:
    return hasattr(obj, "read") and callable(obj.read)


class TemplateEngine:
    """The primary entry point for loading and rendering templates.

    The engine owns:
      - a per-engine YAML Loader class (mixin + base loader)
      - the ydst tag set (and any custom tags registered on this engine)
      - an optional include resolver
    """

    def __init__(
        self,
        *,
        include_resolver: Optional[IncludeResolver] = None,
        base_loader: Type[yaml.Loader] = yaml.SafeLoader,
    ):
        self.include_resolver = include_resolver
        self.base_loader = base_loader
        self._loader_class = self._make_loader_class(base_loader)
        self._custom_tags: Dict[str, Callable[..., Any]] = {}

    def _make_loader_class(self, base: Type[yaml.Loader]) -> Type[yaml.Loader]:
        # Create a per-engine loader class so constructor registration is isolated.
        cls = type("YdstLoader", (TemplateLoaderMixin, base), {})
        cls.add_ydst_constructors()  # type: ignore[attr-defined]
        return cls

    @property
    def Loader(self) -> Type[yaml.Loader]:
        return self._loader_class

    def register_tag(self, tag: str, constructor: Callable[..., Any]) -> None:
        """Register an additional YAML tag constructor on this engine's loader."""
        if not tag.startswith("!"):
            raise ValueError("YAML tag must start with '!'")
        self._custom_tags[tag] = constructor
        self._loader_class.add_constructor(tag, constructor)  # type: ignore[attr-defined]

    # ----------------------------
    # Loading
    # ----------------------------
    def load_template(self, source: SourceInput, *, source_name: Optional[str] = None) -> Any:
        """Load YAML and return a template object graph (plain values + TemplateNodes).

        `source` is treated as YAML content if it's a string. For filesystem paths, pass a Path.
        """
        include_stack: list[str] = []
        return self._load_template_internal(source, source_name=source_name, include_stack=include_stack)

    def load_template_file(self, path: Union[str, Path]) -> Any:
        p = Path(path)
        return self.load_template(p, source_name=str(p))

    def _load_template_internal(self, source: SourceInput, *, source_name: Optional[str], include_stack: list[str]) -> Any:
        if isinstance(source, Path):
            text = source.read_text(encoding="utf-8")
            return self._load_from_text(text, source_name=source_name or str(source), include_stack=include_stack)

        if isinstance(source, (bytes, bytearray)):
            text = source.decode("utf-8")
            return self._load_from_text(text, source_name=source_name, include_stack=include_stack)

        if isinstance(source, str):
            return self._load_from_text(source, source_name=source_name, include_stack=include_stack)

        if _is_filelike(source):
            return self._load_from_stream(source, source_name=source_name, include_stack=include_stack)

        raise TypeError(f"Unsupported source type: {type(source)!r}")

    def _load_from_text(self, text: str, *, source_name: Optional[str], include_stack: list[str]) -> Any:
        return self._load_with_loader(io.StringIO(text), source_name=source_name, include_stack=include_stack)

    def _load_from_stream(self, stream: IO[str], *, source_name: Optional[str], include_stack: list[str]) -> Any:
        return self._load_with_loader(stream, source_name=source_name, include_stack=include_stack)

    def _load_with_loader(self, stream: IO[str], *, source_name: Optional[str], include_stack: list[str]) -> Any:
        loader = self.Loader(stream)
        setattr(loader, "_ydst_engine", self)
        setattr(loader, "_ydst_source_name", source_name)
        setattr(loader, "_ydst_include_resolver", self.include_resolver)
        setattr(loader, "_ydst_include_stack", include_stack)
        try:
            data = loader.get_single_data()  # type: ignore[attr-defined]
        except TemplateLoadError:
            raise
        except Exception as e:
            raise TemplateLoadError(
                str(e),
                ctx=ErrorContext(mark=SourceMark(source=source_name), node_type="YAML"),
                cause=e,
            )
        finally:
            try:
                loader.dispose()  # type: ignore[attr-defined]
            except Exception:
                pass
        return data

    def _load_time_include(
        self,
        target: str,
        *,
        from_source: Optional[str],
        mark: SourceMark,
        include_stack: Optional[list[str]] = None,
        required: bool = True,
        default: Any = None,
    ) -> Any:
        resolver = self.include_resolver
        if resolver is None:
            if required:
                raise TemplateLoadError(
                    "!include requires an include_resolver",
                    ctx=ErrorContext(mark=mark, node_type="Include"),
                )
            return default

        res = resolver.resolve(target, from_source=from_source)
        if not res.content:
            if required:
                raise TemplateLoadError(
                    f"Include target not found: {target}",
                    ctx=ErrorContext(mark=mark, node_type="Include"),
                )
            return default

        stack = include_stack if include_stack is not None else []
        if res.key in stack:
            raise IncludeCycleError(
                f"Include cycle detected at '{res.key}'",
                ctx=ErrorContext(mark=mark, node_type="Include"),
            )

        stack.append(res.key)
        try:
            # Parse the included YAML using the *same* include stack for cycle detection.
            return self._load_template_internal(res.content, source_name=res.source_name, include_stack=stack)
        finally:
            stack.pop()

    # ----------------------------
    # Rendering
    # ----------------------------
    def render(
        self,
        template: Any,
        *,
        context: Optional[dict[str, Any]] = None,
        registry: Optional[FunctionRegistry] = None,
        options: Optional[RenderOptions] = None,
        include_resolver: Optional[IncludeResolver] = None,
    ) -> Any:
        return render_template(
            template,
            context=context or {},
            registry=registry,
            options=options,
            engine=self,
            include_resolver=include_resolver or self.include_resolver,
        )
