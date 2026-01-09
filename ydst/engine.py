from __future__ import annotations

import collections.abc as _abc
import io as _io
import pathlib as _pathlib
import typing as _typing

import yaml as _yaml

import ydst.errors as errors
import ydst.include as include
import ydst.loader as loader_mod
import ydst.nodes as nodes
import ydst.render as render_mod
import ydst.registry as registry_mod
import ydst.template as template_mod


SourceInput = str | bytes | _pathlib.Path | _typing.IO[str]


def _is_filelike(obj: _typing.Any) -> bool:
    return hasattr(obj, "read") and callable(getattr(obj, "read"))


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
        include_resolver: include.IncludeResolver | None = None,
        allow_load_time_includes: bool = True,
        base_loader: type[_yaml.Loader] = _yaml.SafeLoader,  # type: ignore[assignment]
        max_include_depth: int | None = None,
        options: render_mod.RenderOptions | None = None,
        registry: registry_mod.FunctionRegistry | None = None,
    ):
        self.include_resolver = include_resolver
        self.allow_load_time_includes = allow_load_time_includes
        self.base_loader = base_loader
        self.max_include_depth = max_include_depth
        self._loader_class = self._make_loader_class(base_loader)
        self._custom_tags: dict[str, _typing.Callable[..., _typing.Any]] = {}
        self._options = options if options is not None else render_mod.RenderOptions()
        self._registry = registry if registry is not None else registry_mod.safe_registry()

    def _make_loader_class(self, base: type[_yaml.Loader]) -> type[_yaml.Loader]:
        # Create a per-engine loader class so constructor registration is isolated.
        cls = type("YdstLoader", (loader_mod.TemplateLoaderMixin, base), {})
        cls.add_ydst_constructors()  # type: ignore[attr-defined]
        return cls

    @property
    def Loader(self) -> type[_yaml.Loader]:
        return self._loader_class

    @property
    def options(self) -> render_mod.RenderOptions:
        """The render options for this engine.

        Users can copy and modify for per-render customization::

            import dataclasses as _dataclasses

            my_opts = _dataclasses.replace(engine.options, allow_python=True)
            tmpl.render(context=ctx, options=my_opts)
        """
        return self._options

    @property
    def registry(self) -> registry_mod.FunctionRegistry:
        """The function registry for this engine.

        Users can extend for per-render customization::

            my_reg = engine.registry.copy()
            my_reg.register("my_func", my_func)
            tmpl.render(context=ctx, registry=my_reg)
        """
        return self._registry

    def register_tag(self, tag: str, constructor: _typing.Callable[..., _typing.Any]) -> None:
        """Register an additional YAML tag constructor on this engine's loader."""
        if not tag.startswith("!"):
            raise ValueError("YAML tag must start with '!'")
        self._custom_tags[tag] = constructor
        self._loader_class.add_constructor(tag, constructor)  # type: ignore[attr-defined]

    # ----------------------------
    # Raw Loading (returns node tree, not Template)
    # ----------------------------
    def load_yaml(self, source: SourceInput, *, source_name: str | None = None) -> nodes.NodeTree:
        """Load YAML and return the raw parse result.

        Returns whatever the YAML parser produces:
        - TemplateNode subclasses for tags (!var, !if, etc.)
        - dict/list/scalar for plain YAML
        - Mixed structures

        This is the low-level API. Most users should use load_template().

        Semantics
        ---------
        - If `source` is a `str` or `pathlib.Path`, it is treated as a **filesystem path**.
        - If `source` is bytes/bytearray, it is treated as UTF-8 YAML text.
        - If `source` is a file-like object, YAML is read from the stream.

        If you want to parse YAML from a Python string, use :meth:`load_yaml_text`.
        """
        include_stack: list[str] = []

        if isinstance(source, str):
            p = _pathlib.Path(source)
            return self._load_template_internal(p, source_name=source_name or str(p), include_stack=include_stack)

        if isinstance(source, _pathlib.Path):
            return self._load_template_internal(
                source,
                source_name=source_name or str(source),
                include_stack=include_stack,
            )

        return self._load_template_internal(source, source_name=source_name, include_stack=include_stack)

    def load_yaml_text(self, text: str, *, source_name: str | None = None) -> nodes.NodeTree:
        """Load YAML from a string, return raw result."""
        include_stack: list[str] = []
        return self._load_template_internal(text, source_name=source_name, include_stack=include_stack)

    def load_yaml_path(self, path: str | _pathlib.Path) -> nodes.NodeTree:
        """Load YAML from a filesystem path, return raw result."""
        p = _pathlib.Path(path)
        return self.load_yaml(p, source_name=str(p))

    def load_yaml_stream(self, stream: _typing.IO[str], *, source_name: str | None = None) -> nodes.NodeTree:
        """Load YAML from an IO stream (file handle, StringIO, etc.), return raw result."""
        include_stack: list[str] = []
        return self._load_template_internal(stream, source_name=source_name, include_stack=include_stack)

    # ----------------------------
    # Template Loading (returns Template wrapper)
    # ----------------------------
    def load_template(
        self, source: SourceInput, *, source_name: str | None = None
    ) -> "template_mod.Template":
        """Load a template and return a Template object.

        This is the primary API for loading templates.

        Semantics
        ---------
        - If `source` is a `str` or `pathlib.Path`, it is treated as a **filesystem path**.
        - If `source` is bytes/bytearray, it is treated as UTF-8 YAML text.
        - If `source` is a file-like object, YAML is read from the stream.

        If you want to parse YAML from a Python string, use :meth:`load_template_text`.
        """
        # Determine source name for path inputs
        effective_source_name = source_name
        if effective_source_name is None:
            if isinstance(source, str):
                effective_source_name = source
            elif isinstance(source, _pathlib.Path):
                effective_source_name = str(source)

        root = self.load_yaml(source, source_name=source_name)
        return template_mod.Template(root=root, engine=self, source_name=effective_source_name)

    def load_template_text(
        self, text: str, *, source_name: str | None = None
    ) -> "template_mod.Template":
        """Load a template from a string."""
        root = self.load_yaml_text(text, source_name=source_name)
        return template_mod.Template(root=root, engine=self, source_name=source_name)

    def load_template_path(self, path: str | _pathlib.Path) -> "template_mod.Template":
        """Load a template from a filesystem path."""
        p = _pathlib.Path(path)
        root = self.load_yaml_path(p)
        return template_mod.Template(root=root, engine=self, source_name=str(p))

    def load_template_stream(
        self, stream: _typing.IO[str], *, source_name: str | None = None
    ) -> "template_mod.Template":
        """Load a template from an IO stream (file handle, StringIO, etc.)."""
        root = self.load_yaml_stream(stream, source_name=source_name)
        return template_mod.Template(root=root, engine=self, source_name=source_name)

    def _load_template_internal(
        self,
        source: SourceInput,
        *,
        source_name: str | None,
        include_stack: list[str],
    ) -> nodes.NodeTree:
        if isinstance(source, _pathlib.Path):
            try:
                text = source.read_text(encoding="utf-8")
            except Exception as e:
                raise errors.TemplateLoadError(
                    f"Failed to read template file: {source}: {e}",
                    ctx=errors.ErrorContext(mark=nodes.SourceMark(source=str(source)), node_type="File"),
                    cause=e,
                )
            return self._load_from_text(text, source_name=source_name or str(source), include_stack=include_stack)

        if isinstance(source, (bytes, bytearray)):
            try:
                text = source.decode("utf-8")
            except Exception as e:
                raise errors.TemplateLoadError(
                    f"Failed to decode template bytes: {e}",
                    ctx=errors.ErrorContext(mark=nodes.SourceMark(source=source_name), node_type="Bytes"),
                    cause=e,
                )
            return self._load_from_text(text, source_name=source_name, include_stack=include_stack)

        if isinstance(source, str):
            # Here `source` is YAML text (not a path) because path strings are handled in load_template(...).
            return self._load_from_text(source, source_name=source_name, include_stack=include_stack)

        if _is_filelike(source):
            return self._load_from_stream(source, source_name=source_name, include_stack=include_stack)

        raise TypeError(f"Unsupported source type: {type(source)!r}")

    def _load_from_text(self, text: str, *, source_name: str | None, include_stack: list[str]) -> nodes.NodeTree:
        return self._load_with_loader(_io.StringIO(text), source_name=source_name, include_stack=include_stack)

    def _load_from_stream(
        self,
        stream: _typing.IO[str],
        *,
        source_name: str | None,
        include_stack: list[str],
    ) -> nodes.NodeTree:
        return self._load_with_loader(stream, source_name=source_name, include_stack=include_stack)

    def _load_with_loader(
        self,
        stream: _typing.IO[str],
        *,
        source_name: str | None,
        include_stack: list[str],
    ) -> nodes.NodeTree:
        loader = self.Loader(stream)
        setattr(loader, "_ydst_engine", self)
        setattr(loader, "_ydst_source_name", source_name)
        setattr(loader, "_ydst_include_resolver", self.include_resolver)
        setattr(loader, "_ydst_include_stack", include_stack)

        try:
            data = loader.get_single_data()  # type: ignore[attr-defined]
        except errors.TemplateLoadError:
            raise
        except Exception as e:
            # Attempt to preserve YAML location info for syntax/scan errors.
            mark = nodes.SourceMark(source=source_name)
            ym = getattr(e, "problem_mark", None) or getattr(e, "context_mark", None) or getattr(e, "mark", None)
            if ym is not None:
                try:
                    line = getattr(ym, "line", None)
                    col = getattr(ym, "column", None)
                    src = source_name or getattr(ym, "name", None)
                    mark = nodes.SourceMark(
                        source=src,
                        line=(line + 1) if isinstance(line, int) else None,
                        column=(col + 1) if isinstance(col, int) else None,
                    )
                except Exception:
                    mark = nodes.SourceMark(source=source_name)

            raise errors.TemplateLoadError(
                str(e),
                ctx=errors.ErrorContext(mark=mark, node_type="YAML"),
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
        from_source: str | None,
        mark: nodes.SourceMark,
        include_stack: list[str] | None = None,
        required: bool = True,
        default: _typing.Any = nodes.UNSET,
    ) -> _typing.Any:
        if not self.allow_load_time_includes:
            if required:
                raise errors.TemplateLoadError(
                    "!include (load-time) is disabled by engine configuration",
                    ctx=errors.ErrorContext(mark=mark, node_type="Include"),
                )
            return None if default is nodes.UNSET else default

        resolver = self.include_resolver
        if resolver is None:
            if required:
                raise errors.TemplateLoadError(
                    "!include requires an include_resolver",
                    ctx=errors.ErrorContext(mark=mark, node_type="Include"),
                )
            return None if default is nodes.UNSET else default

        try:
            res = resolver.resolve(target, from_source=from_source)
        except Exception as e:
            raise errors.TemplateLoadError(
                f"Include resolution failed for target {target!r}: {e}",
                ctx=errors.ErrorContext(mark=mark, node_type="Include"),
                cause=e,
            )

        if res.content is None:
            if required:
                raise errors.TemplateLoadError(
                    f"Include target not found: {target}",
                    ctx=errors.ErrorContext(mark=mark, node_type="Include"),
                )
            return None if default is nodes.UNSET else default

        stack = include_stack if include_stack is not None else []

        # Optional depth limiting to prevent pathological include chains.
        if self.max_include_depth is not None and self.max_include_depth >= 0:
            if len(stack) >= self.max_include_depth:
                raise errors.TemplateLoadError(
                    f"Maximum include depth exceeded (max_include_depth={self.max_include_depth})",
                    ctx=errors.ErrorContext(mark=mark, node_type="Include"),
                )

        if res.key in stack:
            raise errors.TemplateLoadError(
                f"Include cycle detected at '{res.key}'",
                ctx=errors.ErrorContext(mark=mark, node_type="Include"),
            )

        stack.append(res.key)
        try:
            # Parse the included YAML using the *same* include stack for cycle detection.
            return self._load_template_internal(res.content, source_name=res.source_name, include_stack=stack)
        finally:
            stack.pop()

    # ----------------------------
    # Rendering (internal)
    # ----------------------------
    def _render_tree(
        self,
        tree: nodes.NodeTree,
        *,
        context: _abc.Mapping[str, _typing.Any] | None = None,
        registry: registry_mod.FunctionRegistry | None = None,
        options: render_mod.RenderOptions | None = None,
        include_resolver: include.IncludeResolver | None = None,
    ) -> _typing.Any:
        """Internal: render a node tree.

        Users should call Template.render() instead.

        Args:
            tree: Node tree to render (dict, list, TemplateNode, etc.)
            context: Variables available to the template.
            registry: Function registry (default: engine's registry).
            options: Render options (default: engine's options).
            include_resolver: Include resolver for !include_rt.
        """
        return render_mod.render_tree(
            tree,
            context=dict(context or {}),
            registry=registry if registry is not None else self._registry,
            options=options if options is not None else self._options,
            engine=self,
            include_resolver=include_resolver or self.include_resolver,
        )
