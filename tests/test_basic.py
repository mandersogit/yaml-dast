import unittest
from pathlib import Path
import tempfile

from ydst import (
    TemplateEngine,
    FileIncludeResolver,
    default_registry,
    OMIT,
    RenderError,
    ExpressionError,
    TemplateLoadError,
)
from ydst.render import RenderOptions
from ydst.registry import chain_registries


class TestYdstBasic(unittest.TestCase):
    def test_var_and_if_and_omit(self):
        eng = TemplateEngine()
        tmpl = eng.load_template(
            """
a: 1
b: !var x
c: !if
  test: !expr "x > 1"
  then: "yes"
  else: !omit
"""
        )
        out = eng.render(tmpl, context={"x": 2}, registry=default_registry())
        self.assertEqual(out, {"a": 1, "b": 2, "c": "yes"})

        out2 = eng.render(tmpl, context={"x": 1}, registry=default_registry())
        self.assertEqual(out2, {"a": 1, "b": 1})

    def test_foreach_list(self):
        eng = TemplateEngine()
        tmpl = eng.load_template(
            """
items: !foreach
  var: t
  in: !var xs
  template: !expr "t * 2"
"""
        )
        out = eng.render(tmpl, context={"xs": [1, 2, 3]}, registry=default_registry())
        self.assertEqual(out["items"], [2, 4, 6])

    def test_foreach_dict(self):
        eng = TemplateEngine()
        tmpl = eng.load_template(
            """
m: !foreach
  var: t
  in: !var xs
  into: dict
  key: !expr "t"
  value: !expr "t * t"
"""
        )
        out = eng.render(tmpl, context={"xs": [1, 2, 3]}, registry=default_registry())
        self.assertEqual(out["m"], {1: 1, 2: 4, 3: 9})

    def test_call_and_pipe(self):
        eng = TemplateEngine()
        tmpl = eng.load_template(
            """
slug: !pipe
  - !var title
  - !call {fn: slugify}
  - !call {fn: truncate, kwargs: {max_len: 5}}
"""
        )

        # Custom registry for truncate
        reg = default_registry()
        reg.functions["truncate"] = lambda s, max_len=5: str(s)[:max_len]

        out = eng.render(tmpl, context={"title": "Hello, World"}, registry=reg)
        self.assertEqual(out["slug"], "hello")

    def test_load_time_include(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "a.yaml").write_text("x: 1\n", encoding="utf-8")
            (td / "b.yaml").write_text("y: !include a.yaml\n", encoding="utf-8")

            eng = TemplateEngine(include_resolver=FileIncludeResolver(search_paths=[td]))
            tmpl = eng.load_template_file(td / "b.yaml")
            out = eng.render(tmpl)
            self.assertEqual(out, {"y": {"x": 1}})

    def test_runtime_include(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "a.yaml").write_text("x: !var v\n", encoding="utf-8")
            (td / "b.yaml").write_text("y: !include_rt a.yaml\n", encoding="utf-8")

            eng = TemplateEngine(include_resolver=FileIncludeResolver(search_paths=[td]))
            tmpl = eng.load_template_file(td / "b.yaml")
            out = eng.render(tmpl, context={"v": 42})
            self.assertEqual(out, {"y": {"x": 42}})

    def test_dict_key_conflict_policy(self):
        eng = TemplateEngine()
        tmpl = eng.load_template("""m: {a: 1, a: 2}\n""")  # YAML parser will likely keep last anyway
        # For deterministic test, force conflict via foreach dict:
        tmpl = eng.load_template(
            """
m: !foreach
  var: t
  in: [1, 1]
  into: dict
  key: !expr "t"
  value: !expr "t"
"""
        )
        # strict with last-wins
        out = eng.render(tmpl, registry=default_registry(), options=RenderOptions(dict_key_conflict="last"))
        self.assertEqual(out["m"], {1: 1})

        # strict with error
        with self.assertRaises(Exception):
            eng.render(tmpl, registry=default_registry(), options=RenderOptions(dict_key_conflict="error"))

    def test_expr_calls_with_chained_registry(self):
        eng = TemplateEngine()
        tmpl = eng.load_template("n: !expr \"len(xs)\"\n")

        extra = default_registry()
        extra.functions = {"noop": lambda x: x}

        reg = chain_registries(extra, default_registry())
        out = eng.render(tmpl, context={"xs": [1, 2, 3]}, registry=reg)
        self.assertEqual(out["n"], 3)

    def test_expr_calls_with_get_only_registry(self):
        class _GetOnly:
            def __init__(self, funcs):
                self._funcs = dict(funcs)

            def get(self, name: str):
                return self._funcs.get(name)

        eng = TemplateEngine()
        tmpl = eng.load_template("n: !expr \"len(xs)\"\n")
        reg = _GetOnly({"len": len})
        out = eng.render(tmpl, context={"xs": [1, 2, 3]}, registry=reg)
        self.assertEqual(out["n"], 3)

    def test_expr_dict_unpacking_rejected(self):
        eng = TemplateEngine()
        tmpl = eng.load_template("x: !expr \"{**d}\"\n")
        with self.assertRaises(ExpressionError):
            eng.render(tmpl, context={"d": {"a": 1}}, registry=default_registry())

    def test_expr_private_attributes_rejected(self):
        eng = TemplateEngine()
        tmpl = eng.load_template("x: !expr \"obj.__class__\"\n")
        with self.assertRaises(ExpressionError):
            eng.render(tmpl, context={"obj": object()}, registry=default_registry())

    def test_safe_mode_disables_expr_calls(self):
        eng = TemplateEngine()
        tmpl = eng.load_template("n: !expr \"len(xs)\"\n")
        with self.assertRaises(ExpressionError):
            eng.render(
                tmpl,
                context={"xs": [1, 2, 3]},
                registry=default_registry(),
                options=RenderOptions(mode="safe"),
            )

    def test_max_depth_applies_to_containers(self):
        eng = TemplateEngine()
        tmpl = eng.load_template("""
a:
  b:
    c:
      d: 1
""")
        with self.assertRaises(RenderError):
            eng.render(tmpl, options=RenderOptions(max_depth=3))

    def test_default_omit_for_var_expr_include_rt(self):
        eng = TemplateEngine()

        tmpl_var = eng.load_template("""
a: !var
  name: missing
  required: false
  default: !omit
b: 1
""")
        out_var = eng.render(tmpl_var, registry=default_registry())
        self.assertEqual(out_var, {"b": 1})

        tmpl_expr = eng.load_template("""
a: !expr
  expr: missing_name
  strict: false
  default: !omit
b: 1
""")
        out_expr = eng.render(tmpl_expr, registry=default_registry())
        self.assertEqual(out_expr, {"b": 1})

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            eng2 = TemplateEngine(include_resolver=FileIncludeResolver(search_paths=[td]))
            tmpl_inc = eng2.load_template("""
a: !include_rt
  target: missing.yaml
  required: false
  default: !omit
b: 1
""")
            out_inc = eng2.render(tmpl_inc, registry=default_registry())
            self.assertEqual(out_inc, {"b": 1})

    def test_empty_include_file_is_not_missing(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "empty.yaml").write_text("", encoding="utf-8")
            (td / "main.yaml").write_text("x: !include empty.yaml\n", encoding="utf-8")

            (td / "rt.yaml").write_text("x: !include_rt empty.yaml\n", encoding="utf-8")

            eng = TemplateEngine(include_resolver=FileIncludeResolver(search_paths=[td]))
            tmpl = eng.load_template_file(td / "main.yaml")
            out = eng.render(tmpl)
            self.assertEqual(out, {"x": None})

            tmpl_rt = eng.load_template_file(td / "rt.yaml")
            out_rt = eng.render(tmpl_rt)
            self.assertEqual(out_rt, {"x": None})

            tmpl_rt = eng.load_template("x: !include_rt empty.yaml\n")
            out_rt = eng.render(tmpl_rt)
            self.assertEqual(out_rt, {"x": None})


    def test_pipe_unknown_string_stage_is_literal(self) -> None:
        eng = TemplateEngine()
        tmpl = eng.load_template(
            """x: !pipe
  - 1
  - not_a_function
"""
        )
        out = eng.render(tmpl, registry=default_registry())
        self.assertEqual(out, {"x": "not_a_function"})

    def test_pipe_callable_stage_requires_opt_in(self) -> None:
        eng = TemplateEngine()
        tmpl = eng.load_template(
            """x: !pipe
  - 1
  - !var f
"""
        )

        # Default: callable stages are disabled.
        with self.assertRaises(RenderError):
            eng.render(tmpl, context={"f": lambda x: x + 1})

        # Opt-in: allow callable stages.
        out = eng.render(tmpl, context={"f": lambda x: x + 1}, options=RenderOptions(allow_callable_pipe_stages=True))
        self.assertEqual(out, {"x": 2})

    def test_load_time_include_required_false_defaults_to_none(self) -> None:
        eng = TemplateEngine()  # no include_resolver
        tmpl = eng.load_template(
            """x: !include
  target: missing.yaml
  required: false
""",
            source_name="inline.yaml",
        )
        out = eng.render(tmpl)
        self.assertEqual(out, {"x": None})

    def test_yaml_parse_error_preserves_mark(self) -> None:
        eng = TemplateEngine()
        with self.assertRaises(TemplateLoadError) as cm:
            eng.load_template("a: [1, 2\n")  # missing closing bracket

        e = cm.exception
        self.assertIsNotNone(e.ctx)
        self.assertIsNotNone(e.ctx.mark)
        # Depending on the YAML parser error type, line/column should be present.
        self.assertIsInstance(e.ctx.mark.line, int)
        self.assertIsInstance(e.ctx.mark.column, int)
        self.assertGreaterEqual(e.ctx.mark.line or 0, 1)
        self.assertGreaterEqual(e.ctx.mark.column or 0, 1)



    def test_omit_is_falsy_in_if(self) -> None:
        eng = TemplateEngine()
        tmpl = eng.load_template("""
!if
  test: !omit
  then: "YES"
  else: "NO"
""")
        out = eng.render(tmpl)
        self.assertEqual(out, "NO")

    def test_omit_is_falsy_in_foreach_when(self) -> None:
        eng = TemplateEngine()
        tmpl = eng.load_template("""
!foreach
  in: [1, 2, 3]
  template: {v: !var item}
  when: !omit
""")
        out = eng.render(tmpl)
        self.assertEqual(out, [])

    def test_loader_validates_boolean_fields(self) -> None:
        eng = TemplateEngine()
        with self.assertRaises(TemplateLoadError):
            eng.load_template('!var {name: x, required: "false"}')

        with self.assertRaises(TemplateLoadError):
            eng.load_template('!include {timing: load, target: 123}')

    def test_foreach_var_must_be_non_empty_string(self) -> None:
        eng = TemplateEngine()
        with self.assertRaises(TemplateLoadError):
            eng.load_template('!foreach {in: [1], var: "", template: {x: 1}}')

    def test_load_time_include_cycle_is_template_load_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / 'a.yaml').write_text('!include b.yaml', encoding='utf-8')
            (p / 'b.yaml').write_text('!include a.yaml', encoding='utf-8')

            resolver = FileIncludeResolver(search_paths=[p])
            eng = TemplateEngine(include_resolver=resolver)

            with self.assertRaises(TemplateLoadError):
                eng.load_template_file(str(p / 'a.yaml'))

    def test_pipe_unknown_stage_strict_errors(self) -> None:
        eng = TemplateEngine()
        tmpl = eng.load_template('!pipe [a, unknown]')

        with self.assertRaises(RenderError):
            eng.render(tmpl, registry=default_registry(), options=RenderOptions(strict_pipe_stages=True))
if __name__ == "__main__":
    unittest.main()
