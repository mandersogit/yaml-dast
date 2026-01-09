"""Template wrapper class for ergonomic template usage."""
from __future__ import annotations

import dataclasses as _dataclasses
import pathlib as _pathlib
import threading as _threading
import typing as _typing

import ydst.nodes as _nodes_mod

if _typing.TYPE_CHECKING:
    import ydst.engine as _engine_mod
    import ydst.registry as _registry_mod
    import ydst.render as _render_mod


# Module-level default engine (singleton, thread-safe initialization)
_default_engine: _engine_mod.TemplateEngine | None = None
_default_engine_lock = _threading.Lock()


def get_default_engine() -> _engine_mod.TemplateEngine:
    """Get or create the default engine (singleton).

    The default engine is created lazily on first use with default settings.
    Use set_default_engine() to configure a custom default.
    """
    global _default_engine
    if _default_engine is None:
        with _default_engine_lock:
            # Double-check after acquiring lock
            if _default_engine is None:
                import ydst.engine as engine_mod

                _default_engine = engine_mod.TemplateEngine()
    return _default_engine


def set_default_engine(engine: _engine_mod.TemplateEngine) -> None:
    """Set the default engine.

    Args:
        engine: The engine to use as the module default.
    """
    global _default_engine
    with _default_engine_lock:
        _default_engine = engine


def _summarize_root(root: _typing.Any) -> str:
    """Create a summary string for Template repr."""
    if isinstance(root, dict):
        return f"<dict with {len(root)} keys>"
    if isinstance(root, list):
        return f"<list with {len(root)} items>"
    if isinstance(root, tuple):
        return f"<tuple with {len(root)} items>"
    type_name = type(root).__name__
    return f"<{type_name}>"


@_dataclasses.dataclass(frozen=True)
class Template:
    """A loaded template bound to an engine.

    Template is immutable by convention. The dataclass is frozen (attributes
    cannot be reassigned), but the `root` contents may be mutable Python
    objects (dicts, lists). Users should not mutate root contents.

    The same Template can be rendered multiple times with different contexts.

    Attributes:
        root: The parsed YAML structure (nodes, dicts, scalars, etc.)
        engine: The engine that loaded this template (required for rendering)
        source_name: Optional name for error messages (e.g., filename)
    """

    root: _nodes_mod.NodeTree
    engine: _engine_mod.TemplateEngine
    source_name: str | None = None

    def __repr__(self) -> str:
        """Show source_name and root type/size, not full root."""
        root_summary = _summarize_root(self.root)
        if self.source_name:
            return f"Template(source_name={self.source_name!r}, root={root_summary})"
        return f"Template(root={root_summary})"

    def render(
        self,
        context: dict[str, _typing.Any] | None = None,
        *,
        options: _render_mod.RenderOptions | None = None,
        registry: _registry_mod.FunctionRegistry | None = None,
    ) -> _typing.Any:
        """Render the template with the given context.

        Args:
            context: Variables available to the template (default: empty)
            options: Override render options (default: engine's options).
                     To tweak, use dataclasses.replace():
                         opts = _dataclasses.replace(tmpl.engine.options, allow_python=True)
                         tmpl.render(context=ctx, options=opts)
            registry: Override function registry (default: engine's registry).
                      To extend, copy and add:
                          reg = tmpl.engine.registry.copy()
                          reg.register("my_func", my_func)
                          tmpl.render(context=ctx, registry=reg)

        Returns:
            The rendered data structure.

        Raises:
            RenderError: If rendering fails.
        """
        return self.engine._render_tree(
            self.root,
            context=context,
            options=options,
            registry=registry,
        )

    def render_safe(
        self,
        context: dict[str, _typing.Any] | None = None,
        *,
        options: _render_mod.RenderOptions | None = None,
    ) -> _typing.Any:
        """Render with locked-down security options.

        Equivalent to render() with mode="locked_down".
        """
        import ydst.render as _render_module

        safe_options = _render_module.RenderOptions(mode="locked_down")
        if options:
            # Merge, but locked_down wins on security settings
            safe_options = _dataclasses.replace(
                safe_options,
                **{
                    k: v
                    for k, v in _dataclasses.asdict(options).items()
                    if not k.startswith("allow_")
                },
            )
        return self.render(context=context, options=safe_options)

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        engine: _engine_mod.TemplateEngine | None = None,
        source_name: str | None = None,
    ) -> Template:
        """Create a template from a text string.

        Args:
            text: YAML template source
            engine: Engine to use (default: module default engine)
            source_name: Name for error messages

        Example:
            tmpl = Template.from_text("x: !var foo")
            result = tmpl.render(context={"foo": 42})
        """
        if engine is None:
            engine = get_default_engine()
        return engine.load_template_text(text, source_name=source_name)

    @classmethod
    def from_path(
        cls,
        path: str | _pathlib.Path,
        *,
        engine: _engine_mod.TemplateEngine | None = None,
    ) -> Template:
        """Create a template from a filesystem path.

        Args:
            path: Path to YAML template (str or pathlib.Path)
            engine: Engine to use (default: module default engine)
        """
        if engine is None:
            engine = get_default_engine()
        return engine.load_template_path(path)

    @classmethod
    def from_stream(
        cls,
        stream: _typing.IO[str],
        *,
        engine: _engine_mod.TemplateEngine | None = None,
        source_name: str | None = None,
    ) -> Template:
        """Create a template from an IO stream (file handle, StringIO, etc.).

        Args:
            stream: IO object to read YAML from
            engine: Engine to use (default: module default engine)
            source_name: Name for error messages (e.g., original filename)
        """
        if engine is None:
            engine = get_default_engine()
        return engine.load_template_stream(stream, source_name=source_name)


# Convenience one-shot rendering functions


def render_text(
    source: str,
    context: dict[str, _typing.Any] | None = None,
    *,
    engine: _engine_mod.TemplateEngine | None = None,
    options: _render_mod.RenderOptions | None = None,
    registry: _registry_mod.FunctionRegistry | None = None,
) -> _typing.Any:
    """One-shot render: load YAML text and render in a single call.

    For repeated rendering of the same template, use Template.from_text()
    and call .render() multiple times.

    Example:
        result = ydst.render_text("x: !var foo", context={"foo": 42})
    """
    tmpl = Template.from_text(source, engine=engine)
    return tmpl.render(context=context, options=options, registry=registry)


def render_path(
    path: str | _pathlib.Path,
    context: dict[str, _typing.Any] | None = None,
    *,
    engine: _engine_mod.TemplateEngine | None = None,
    options: _render_mod.RenderOptions | None = None,
    registry: _registry_mod.FunctionRegistry | None = None,
) -> _typing.Any:
    """One-shot render from a filesystem path."""
    tmpl = Template.from_path(path, engine=engine)
    return tmpl.render(context=context, options=options, registry=registry)


def render_stream(
    stream: _typing.IO[str],
    context: dict[str, _typing.Any] | None = None,
    *,
    engine: _engine_mod.TemplateEngine | None = None,
    options: _render_mod.RenderOptions | None = None,
    registry: _registry_mod.FunctionRegistry | None = None,
    source_name: str | None = None,
) -> _typing.Any:
    """One-shot render from an IO stream."""
    tmpl = Template.from_stream(stream, engine=engine, source_name=source_name)
    return tmpl.render(context=context, options=options, registry=registry)



