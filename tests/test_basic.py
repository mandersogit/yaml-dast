import unittest
from pathlib import Path
import tempfile

from ydst import TemplateEngine, FileIncludeResolver, default_registry, OMIT
from ydst.render import RenderOptions


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


if __name__ == "__main__":
    unittest.main()
