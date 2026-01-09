import pytest as _pytest
import pathlib as _pathlib
import tempfile as _tempfile

import ydst as _ydst


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
        out = eng.render(tmpl, context={}, registry=_ydst.default_registry())
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
        out = eng.render(tmpl, context={}, registry=_ydst.default_registry())
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
        out = eng.render(tmpl, context={}, registry=_ydst.default_registry())
        # missing var -> None; treat_none_as_missing false means keep None
        assert out == {"x": None}


class TestPolicyAndLoaderControls:
    def test_expr_compile_wrap_exceptions_toggle(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('x: !expr "1 +"\n')

        # Default: wrapped as ExpressionError
        with _pytest.raises(_ydst.ExpressionError):
            eng.render(tmpl)

        # Debug: surface TemplateValidationError
        with _pytest.raises(_ydst.TemplateValidationError):
            eng.render(tmpl, options=_ydst.RenderOptions(wrap_exceptions=False))

    def test_disable_load_time_includes(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            p = _pathlib.Path(td)
            (p / "a.yaml").write_text("x: 1\n", encoding="utf-8")
            (p / "b.yaml").write_text("y: !include a.yaml\n", encoding="utf-8")

            resolver = _ydst.FileIncludeResolver(search_paths=[p])
            eng = _ydst.TemplateEngine(include_resolver=resolver, allow_load_time_includes=False)

            with _pytest.raises(_ydst.TemplateLoadError):
                eng.load_template_file(p / "b.yaml")


class TestProgrammaticTemplateValidation:
    def test_foreach_missing_template_is_validation_error(self) -> None:
        node = _ydst.ForEach(in_=[1, 2, 3])
        with _pytest.raises(_ydst.TemplateValidationError):
            _ydst.validate_template(node)

    def test_foreach_missing_template_is_render_error(self) -> None:
        node = _ydst.ForEach(in_=[1, 2, 3])
        eng = _ydst.TemplateEngine()
        with _pytest.raises(_ydst.RenderError):
            eng.render(node, context={})

    def test_foreach_dict_missing_key_value_is_validation_error(self) -> None:
        node = _ydst.ForEach(in_=[{"a": 1}], into="dict")
        with _pytest.raises(_ydst.TemplateValidationError):
            _ydst.validate_template(node)

    def test_foreach_dict_missing_key_value_is_render_error(self) -> None:
        node = _ydst.ForEach(in_=[{"a": 1}], into="dict")
        eng = _ydst.TemplateEngine()
        with _pytest.raises(_ydst.RenderError):
            eng.render(node, context={})
