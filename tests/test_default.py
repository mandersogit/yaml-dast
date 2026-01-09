import unittest
from pathlib import Path
import tempfile

from ydst import TemplateEngine, FileIncludeResolver, default_registry, TemplateValidationError, ExpressionError, TemplateLoadError
from ydst.render import RenderOptions


class TestDefaultTag(unittest.TestCase):
    def test_default_fallback_for_missing_var_strict(self):
        eng = TemplateEngine()
        tmpl = eng.load_template_text(
            """
x: !default
  value: !var {name: missing, required: true}
  default: 123
"""
        )
        out = eng.render(tmpl, context={}, registry=default_registry())
        self.assertEqual(out, {"x": 123})

    def test_default_fallback_for_missing_var_non_strict_none(self):
        eng = TemplateEngine()
        tmpl = eng.load_template_text(
            """
x: !default
  value: !var {name: missing, required: false}
  default: 123
"""
        )
        out = eng.render(tmpl, context={}, registry=default_registry())
        self.assertEqual(out, {"x": 123})

    def test_default_treat_none_as_missing_toggle(self):
        eng = TemplateEngine()
        tmpl = eng.load_template_text(
            """
x: !default
  value: !var {name: v, required: false}
  default: 123
  treat_none_as_missing: false
"""
        )
        out = eng.render(tmpl, context={}, registry=default_registry())
        # missing var -> None; treat_none_as_missing false means keep None
        self.assertEqual(out, {"x": None})


class TestPolicyAndLoaderControls(unittest.TestCase):
    def test_expr_compile_wrap_exceptions_toggle(self):
        eng = TemplateEngine()
        tmpl = eng.load_template_text('x: !expr "1 +"\n')

        # Default: wrapped as ExpressionError
        with self.assertRaises(ExpressionError):
            eng.render(tmpl)

        # Debug: surface TemplateValidationError
        with self.assertRaises(TemplateValidationError):
            eng.render(tmpl, options=RenderOptions(wrap_exceptions=False))

    def test_disable_load_time_includes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "a.yaml").write_text("x: 1\n", encoding="utf-8")
            (p / "b.yaml").write_text("y: !include a.yaml\n", encoding="utf-8")

            resolver = FileIncludeResolver(search_paths=[p])
            eng = TemplateEngine(include_resolver=resolver, allow_load_time_includes=False)

            with self.assertRaises(TemplateLoadError):
                eng.load_template_file(p / "b.yaml")


if __name__ == "__main__":
    unittest.main()
