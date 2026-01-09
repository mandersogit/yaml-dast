import pytest as _pytest
import pathlib as _pathlib
import tempfile as _tempfile

import ydst as _ydst
import ydst.errors as _errors
import ydst.nodes as _nodes
import ydst.registry as _registry
import ydst.validate as _validate


class TestDefaultTag:
    def test_default_fallback_for_missing_var_strict(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
x: !default
  value: !var {name: missing, required: true}
  default: 123
"""
        )
        out = tmpl.render(context={}, registry=_registry.default_registry())
        assert out == {"x": 123}

    def test_default_fallback_for_missing_var_non_strict_none(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
x: !default
  value: !var {name: missing, required: false}
  default: 123
"""
        )
        out = tmpl.render(context={}, registry=_registry.default_registry())
        assert out == {"x": 123}

    def test_default_treat_none_as_missing_toggle(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
x: !default
  value: !var {name: v, required: false}
  default: 123
  treat_none_as_missing: false
"""
        )
        out = tmpl.render(context={}, registry=_registry.default_registry())
        # missing var -> None; treat_none_as_missing false means keep None
        assert out == {"x": None}


class TestPolicyAndLoaderControls:
    def test_expr_compile_wrap_exceptions_toggle(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('x: !expr "1 +"\n')

        # Default: wrapped as ExpressionError
        with _pytest.raises(_errors.ExpressionError):
            tmpl.render()

        # Debug: surface TemplateValidationError
        with _pytest.raises(_ydst.TemplateValidationError):
            tmpl.render(options=_ydst.RenderOptions(wrap_exceptions=False))

    def test_disable_load_time_includes(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            p = _pathlib.Path(td)
            (p / "a.yaml").write_text("x: 1\n", encoding="utf-8")
            (p / "b.yaml").write_text("y: !include a.yaml\n", encoding="utf-8")

            resolver = _ydst.FileIncludeResolver(search_paths=[p])
            eng = _ydst.TemplateEngine(include_resolver=resolver, allow_load_time_includes=False)

            with _pytest.raises(_ydst.TemplateLoadError):
                eng.load_template_path(p / "b.yaml")


class TestProgrammaticTemplateValidation:
    def test_foreach_missing_template_is_validation_error(self) -> None:
        eng = _ydst.TemplateEngine()
        node = _nodes.ForEach(in_=[1, 2, 3])
        tmpl = _ydst.Template(root=node, engine=eng)
        with _pytest.raises(_ydst.TemplateValidationError):
            _validate.validate_template(tmpl)

    def test_foreach_missing_template_is_render_error(self) -> None:
        eng = _ydst.TemplateEngine()
        node = _nodes.ForEach(in_=[1, 2, 3])
        tmpl = _ydst.Template(root=node, engine=eng)
        with _pytest.raises(_ydst.RenderError):
            tmpl.render(context={})

    def test_foreach_dict_missing_key_value_is_validation_error(self) -> None:
        eng = _ydst.TemplateEngine()
        node = _nodes.ForEach(in_=[{"a": 1}], into="dict")
        tmpl = _ydst.Template(root=node, engine=eng)
        with _pytest.raises(_ydst.TemplateValidationError):
            _validate.validate_template(tmpl)

    def test_foreach_dict_missing_key_value_is_render_error(self) -> None:
        eng = _ydst.TemplateEngine()
        node = _nodes.ForEach(in_=[{"a": 1}], into="dict")
        tmpl = _ydst.Template(root=node, engine=eng)
        with _pytest.raises(_ydst.RenderError):
            tmpl.render(context={})
