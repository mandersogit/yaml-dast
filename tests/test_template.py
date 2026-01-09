"""Tests for the Template wrapper class."""
import io as _io
import tempfile as _tempfile
import pathlib as _pathlib

import pytest as _pytest

import ydst as _ydst
import ydst.nodes as _nodes


class TestTemplateBasic:
    """Basic Template functionality."""

    def test_template_from_text(self) -> None:
        tmpl = _ydst.Template.from_text("x: !var foo")
        result = tmpl.render(context={"foo": 42})
        assert result == {"x": 42}

    def test_template_from_path(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            td_path = _pathlib.Path(td)
            (td_path / "test.yaml").write_text("x: !var foo\n", encoding="utf-8")
            tmpl = _ydst.Template.from_path(td_path / "test.yaml")
            result = tmpl.render(context={"foo": 42})
            assert result == {"x": 42}
            assert tmpl.source_name == str(td_path / "test.yaml")

    def test_template_from_stream(self) -> None:
        stream = _io.StringIO("x: !var foo")
        tmpl = _ydst.Template.from_stream(stream, source_name="test_stream")
        result = tmpl.render(context={"foo": 42})
        assert result == {"x": 42}
        assert tmpl.source_name == "test_stream"

    def test_template_reuse(self) -> None:
        tmpl = _ydst.Template.from_text("x: !var val")
        r1 = tmpl.render(context={"val": 1})
        r2 = tmpl.render(context={"val": 2})
        assert r1 == {"x": 1}
        assert r2 == {"x": 2}

    def test_template_repr(self) -> None:
        tmpl = _ydst.Template.from_text("x: 1", source_name="test.yaml")
        r = repr(tmpl)
        assert "test.yaml" in r
        assert "dict" in r

    def test_template_repr_no_source_name(self) -> None:
        tmpl = _ydst.Template.from_text("x: 1")
        r = repr(tmpl)
        assert "Template(" in r
        assert "dict" in r

    def test_template_is_frozen(self) -> None:
        tmpl = _ydst.Template.from_text("x: 1")
        with _pytest.raises(AttributeError):
            tmpl.root = {"y": 2}  # type: ignore[misc]


class TestTemplateRenderSafe:
    """Template.render_safe() functionality."""

    def test_render_safe_uses_locked_down(self) -> None:
        tmpl = _ydst.Template.from_text('x: !python "emit(42)"')
        # render_safe uses locked_down which disables !python
        with _pytest.raises(_ydst.RenderError) as cm:
            tmpl.render_safe()
        assert "disabled" in str(cm.value).lower()

    def test_render_safe_allows_setdefault(self) -> None:
        # !setdefault is always allowed, even in locked_down
        tmpl = _ydst.Template.from_text("""
- !setdefault {x: 10}
- !var x
""")
        result = tmpl.render_safe()
        # OMIT is filtered, so we get [10]
        assert result == [10]


class TestEngineProperties:
    """Engine options and registry properties."""

    def test_engine_options_property(self) -> None:
        eng = _ydst.TemplateEngine()
        opts = eng.options
        assert isinstance(opts, _ydst.RenderOptions)

    def test_engine_registry_property(self) -> None:
        eng = _ydst.TemplateEngine()
        reg = eng.registry
        # FunctionRegistry is a Protocol, can't use isinstance - check it has get method
        assert hasattr(reg, "get") and callable(reg.get)

    def test_engine_with_custom_options(self) -> None:
        opts = _ydst.RenderOptions(allow_python=True)
        eng = _ydst.TemplateEngine(options=opts)
        assert eng.options.allow_python is True

    def test_engine_options_used_in_render(self) -> None:
        opts = _ydst.RenderOptions(allow_python=True)
        eng = _ydst.TemplateEngine(options=opts)
        tmpl = eng.load_template_text('x: !python "emit(42)"')
        # Should work because engine options allow python
        result = tmpl.render()
        assert result == {"x": 42}


class TestLoadYamlRaw:
    """Raw loading methods (load_yaml_*)."""

    def test_load_yaml_text_returns_raw(self) -> None:
        eng = _ydst.TemplateEngine()
        raw = eng.load_yaml_text("x: !var foo")
        # Should be a dict containing a Var node, not a Template
        assert isinstance(raw, dict)
        assert "x" in raw
        assert isinstance(raw["x"], _nodes.Var)

    def test_load_yaml_path_returns_raw(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            td_path = _pathlib.Path(td)
            (td_path / "test.yaml").write_text("x: !var foo\n", encoding="utf-8")
            eng = _ydst.TemplateEngine()
            raw = eng.load_yaml_path(td_path / "test.yaml")
            assert isinstance(raw, dict)
            assert "x" in raw

    def test_load_yaml_stream_returns_raw(self) -> None:
        eng = _ydst.TemplateEngine()
        stream = _io.StringIO("x: !var foo")
        raw = eng.load_yaml_stream(stream)
        assert isinstance(raw, dict)
        assert isinstance(raw["x"], _nodes.Var)


class TestModuleLevelFunctions:
    """Module-level convenience functions."""

    def test_render_text_one_shot(self) -> None:
        result = _ydst.render_text("x: !var foo", context={"foo": 42})
        assert result == {"x": 42}

    def test_render_path(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            td_path = _pathlib.Path(td)
            (td_path / "test.yaml").write_text("x: !var foo\n", encoding="utf-8")
            result = _ydst.render_path(td_path / "test.yaml", context={"foo": 42})
            assert result == {"x": 42}

    def test_render_stream(self) -> None:
        stream = _io.StringIO("x: !var foo")
        result = _ydst.render_stream(stream, context={"foo": 42})
        assert result == {"x": 42}


class TestDefaultEngine:
    """Default engine singleton."""

    def test_get_default_engine(self) -> None:
        eng1 = _ydst.get_default_engine()
        eng2 = _ydst.get_default_engine()
        assert eng1 is eng2  # Same instance

    def test_set_default_engine(self) -> None:
        original = _ydst.get_default_engine()
        try:
            custom = _ydst.TemplateEngine(options=_ydst.RenderOptions(allow_python=True))
            _ydst.set_default_engine(custom)
            assert _ydst.get_default_engine() is custom
        finally:
            _ydst.set_default_engine(original)


class TestRawNodeTreeRendering:
    """Raw node trees must be wrapped in Template to render."""

    def test_render_raw_by_wrapping_in_template(self) -> None:
        eng = _ydst.TemplateEngine()
        raw = eng.load_yaml_text("x: !var foo")
        # Wrap raw tree in Template, then render
        tmpl = _ydst.Template(root=raw, engine=eng)
        result = tmpl.render(context={"foo": 42})
        assert result == {"x": 42}

    def test_template_render_is_only_public_api(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("x: !var foo")
        # Template.render() is the only public way to render
        result = tmpl.render(context={"foo": 42})
        assert result == {"x": 42}


class TestTemplateWithCustomEngine:
    """Template classmethods with explicit engine parameter."""

    def test_from_text_with_custom_engine(self) -> None:
        custom_opts = _ydst.RenderOptions(allow_python=True)
        custom_eng = _ydst.TemplateEngine(options=custom_opts)
        tmpl = _ydst.Template.from_text('x: !python "emit(42)"', engine=custom_eng)
        # Should use custom engine which allows python
        result = tmpl.render()
        assert result == {"x": 42}
        assert tmpl.engine is custom_eng

    def test_from_path_with_custom_engine(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            td_path = _pathlib.Path(td)
            (td_path / "test.yaml").write_text("x: !var foo\n", encoding="utf-8")
            custom_eng = _ydst.TemplateEngine()
            tmpl = _ydst.Template.from_path(td_path / "test.yaml", engine=custom_eng)
            assert tmpl.engine is custom_eng


class TestTemplateEquality:
    """Template dataclass equality."""

    def test_same_root_same_engine_equal(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl1 = eng.load_template_text("x: 1")
        tmpl2 = eng.load_template_text("x: 1")
        # Same content, same engine -> equal
        assert tmpl1 == tmpl2

    def test_different_root_not_equal(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl1 = eng.load_template_text("x: 1")
        tmpl2 = eng.load_template_text("x: 2")
        assert tmpl1 != tmpl2

    def test_different_engine_not_equal(self) -> None:
        eng1 = _ydst.TemplateEngine()
        eng2 = _ydst.TemplateEngine()
        tmpl1 = eng1.load_template_text("x: 1")
        tmpl2 = eng2.load_template_text("x: 1")
        # Same content but different engine instances
        assert tmpl1 != tmpl2


class TestPerRenderCustomization:
    """The documented pattern for per-render option/registry overrides."""

    def test_replace_options_pattern(self) -> None:
        import dataclasses as _dataclasses

        # Engine with python disabled (default)
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('x: !python "emit(42)"')

        # Should fail with default options
        with _pytest.raises(_ydst.RenderError):
            tmpl.render()

        # Use replace() pattern to enable python for this render
        opts = _dataclasses.replace(eng.options, allow_python=True)
        result = tmpl.render(options=opts)
        assert result == {"x": 42}

    def test_engine_defaults_used_when_none(self) -> None:
        # Engine configured with python enabled
        opts = _ydst.RenderOptions(allow_python=True)
        eng = _ydst.TemplateEngine(options=opts)
        tmpl = eng.load_template_text('x: !python "emit(42)"')

        # render() without options should use engine defaults
        result = tmpl.render()
        assert result == {"x": 42}


class TestInternalRenderTree:
    """Engine._render_tree() is internal - Template.render() is public API."""

    def test_internal_render_tree_exists(self) -> None:
        eng = _ydst.TemplateEngine()
        # _render_tree is internal, but exists for Template.render() to use
        assert hasattr(eng, "_render_tree")

    def test_users_should_use_template_render(self) -> None:
        eng = _ydst.TemplateEngine()
        # Load returns Template
        tmpl = eng.load_template_text("x: !var foo")
        # Use Template.render() - the one obvious way
        result = tmpl.render(context={"foo": 42})
        assert result == {"x": 42}


class TestLoadTemplateStream:
    """engine.load_template_stream() method."""

    def test_load_template_stream_returns_template(self) -> None:
        eng = _ydst.TemplateEngine()
        stream = _io.StringIO("x: !var foo")
        tmpl = eng.load_template_stream(stream, source_name="test_stream")
        assert isinstance(tmpl, _ydst.Template)
        assert tmpl.source_name == "test_stream"
        result = tmpl.render(context={"foo": 42})
        assert result == {"x": 42}

