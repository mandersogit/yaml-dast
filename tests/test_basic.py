import pathlib as _pathlib
import tempfile as _tempfile
import unittest as _unittest

import ydst as _ydst
import ydst.registry as _registry


class TestYdstBasic(_unittest.TestCase):
    def test_var_and_if_and_omit(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
a: 1
b: !var x
c: !if
  test: !expr "x > 1"
  then: "yes"
  else: !omit
"""
        )
        out = eng.render(tmpl, context={"x": 2}, registry=_ydst.default_registry())
        self.assertEqual(out, {"a": 1, "b": 2, "c": "yes"})

        out2 = eng.render(tmpl, context={"x": 1}, registry=_ydst.default_registry())
        self.assertEqual(out2, {"a": 1, "b": 1})

    def test_root_omit_is_error(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("!omit")
        with self.assertRaises(_ydst.RootOmitError):
            eng.render(tmpl, context={}, registry=_ydst.default_registry())

    def test_foreach_list(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
items: !foreach
  var: t
  in: !var xs
  template: !expr "t * 2"
"""
        )
        out = eng.render(tmpl, context={"xs": [1, 2, 3]}, registry=_ydst.default_registry())
        self.assertEqual(out["items"], [2, 4, 6])

    def test_foreach_dict(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
m: !foreach
  var: t
  in: !var xs
  into: dict
  key: !expr "t"
  value: !expr "t * t"
"""
        )
        out = eng.render(tmpl, context={"xs": [1, 2, 3]}, registry=_ydst.default_registry())
        self.assertEqual(out["m"], {1: 1, 2: 4, 3: 9})

    def test_foreach_allows_explicit_null_template_key_value(self) -> None:
        eng = _ydst.TemplateEngine()

        tmpl_list = eng.load_template_text(
            """
x: !foreach
  in: [1, 2, 3]
  template: null
"""
        )
        self.assertEqual(eng.render(tmpl_list), {"x": [None, None, None]})

        tmpl_set = eng.load_template_text(
            """
x: !foreach
  in: [1, 2]
  into: set
  template: null
"""
        )
        self.assertEqual(eng.render(tmpl_set), {"x": {None}})

        tmpl_dict = eng.load_template_text(
            """
x: !foreach
  in: [1]
  into: dict
  key: null
  value: null
"""
        )
        self.assertEqual(eng.render(tmpl_dict), {"x": {None: None}})

    def test_call_and_pipe(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
slug: !pipe
  - !var title
  - !call {fn: slugify}
  - !call {fn: truncate, kwargs: {max_len: 5}}
"""
        )

        # Custom registry for truncate
        reg = _ydst.default_registry()
        reg.functions["truncate"] = lambda s, max_len=5: str(s)[:max_len]

        out = eng.render(tmpl, context={"title": "Hello, World"}, registry=reg)
        self.assertEqual(out["slug"], "hello")

    def test_load_time_include(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            td_path = _pathlib.Path(td)
            (td_path / "a.yaml").write_text("x: 1\n", encoding="utf-8")
            (td_path / "b.yaml").write_text("y: !include a.yaml\n", encoding="utf-8")

            eng = _ydst.TemplateEngine(include_resolver=_ydst.FileIncludeResolver(search_paths=[td_path]))
            tmpl = eng.load_template_file(td_path / "b.yaml")
            out = eng.render(tmpl)
            self.assertEqual(out, {"y": {"x": 1}})

    def test_runtime_include(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            td_path = _pathlib.Path(td)
            (td_path / "a.yaml").write_text("x: !var v\n", encoding="utf-8")
            (td_path / "b.yaml").write_text("y: !include_rt a.yaml\n", encoding="utf-8")

            eng = _ydst.TemplateEngine(include_resolver=_ydst.FileIncludeResolver(search_paths=[td_path]))
            tmpl = eng.load_template_file(td_path / "b.yaml")
            out = eng.render(tmpl, context={"v": 42})
            self.assertEqual(out, {"y": {"x": 42}})

    def test_dict_key_conflict_policy(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("""m: {a: 1, a: 2}\n""")  # YAML parser will likely keep last anyway
        # For deterministic test, force conflict via foreach dict:
        tmpl = eng.load_template_text(
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
        out = eng.render(tmpl, registry=_ydst.default_registry(), options=_ydst.RenderOptions(dict_key_conflict="last"))
        self.assertEqual(out["m"], {1: 1})

        # strict with error
        with self.assertRaises(_ydst.RenderError) as cm:
            eng.render(tmpl, registry=_ydst.default_registry(), options=_ydst.RenderOptions(dict_key_conflict="error"))

        # Ensure the error path includes the iteration index that caused the conflict.
        self.assertIn("path=$.m[1].key", str(cm.exception))

    def test_expr_calls_with_chained_registry(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("n: !expr \"len(xs)\"\n")

        extra = _ydst.default_registry()
        extra.functions = {"noop": lambda x: x}

        reg = _registry.chain_registries(extra, _ydst.default_registry())
        out = eng.render(tmpl, context={"xs": [1, 2, 3]}, registry=reg)
        self.assertEqual(out["n"], 3)

    def test_expr_calls_with_get_only_registry(self) -> None:
        class _GetOnly:
            def __init__(self, funcs: dict) -> None:
                self._funcs = dict(funcs)

            def get(self, name: str):
                return self._funcs.get(name)

        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("n: !expr \"len(xs)\"\n")
        reg = _GetOnly({"len": len})
        out = eng.render(tmpl, context={"xs": [1, 2, 3]}, registry=reg)
        self.assertEqual(out["n"], 3)

    def test_expr_dict_unpacking_rejected(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("x: !expr \"{**d}\"\n")
        with self.assertRaises(_ydst.ExpressionError):
            eng.render(tmpl, context={"d": {"a": 1}}, registry=_ydst.default_registry())

    def test_expr_private_attributes_rejected(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("x: !expr \"obj.__class__.__name__\"\n")
        with self.assertRaises(_ydst.ExpressionError):
            eng.render(tmpl, context={"obj": object()}, registry=_ydst.default_registry())

        # Opt-in: allow private/dunder attribute access.
        out = eng.render(
            tmpl,
            context={"obj": object()},
            registry=_ydst.default_registry(),
            options=_ydst.RenderOptions(allow_private_attributes_in_expr=True),
        )
        self.assertEqual(out["x"], "object")

    def test_expr_subscripts_policy_toggle(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("x: !expr \"d['a']\"\n")

        with self.assertRaises(_ydst.ExpressionError):
            eng.render(
                tmpl,
                context={"d": {"a": 1}},
                registry=_ydst.default_registry(),
                options=_ydst.RenderOptions(allow_subscripts_in_expr=False),
            )

        out = eng.render(tmpl, context={"d": {"a": 1}}, registry=_ydst.default_registry())
        self.assertEqual(out, {"x": 1})

    def test_safe_mode_disables_expr_calls(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("n: !expr \"len(xs)\"\n")
        with self.assertRaises(_ydst.ExpressionError):
            eng.render(
                tmpl,
                context={"xs": [1, 2, 3]},
                registry=_ydst.default_registry(),
                options=_ydst.RenderOptions(mode="expr_safe"),
            )

    def test_max_depth_applies_to_containers(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("""
a:
  b:
    c:
      d: 1
""")
        with self.assertRaises(_ydst.RenderError):
            eng.render(tmpl, options=_ydst.RenderOptions(max_depth=3))

    def test_default_omit_for_var_expr_include_rt(self) -> None:
        eng = _ydst.TemplateEngine()

        tmpl_var = eng.load_template_text("""
a: !var
  name: missing
  required: false
  default: !omit
b: 1
""")
        out_var = eng.render(tmpl_var, registry=_ydst.default_registry())
        self.assertEqual(out_var, {"b": 1})

        tmpl_expr = eng.load_template_text("""
a: !expr
  expr: missing_name
  strict: false
  default: !omit
b: 1
""")
        out_expr = eng.render(tmpl_expr, registry=_ydst.default_registry())
        self.assertEqual(out_expr, {"b": 1})

        with _tempfile.TemporaryDirectory() as td:
            td_path = _pathlib.Path(td)
            eng2 = _ydst.TemplateEngine(include_resolver=_ydst.FileIncludeResolver(search_paths=[td_path]))
            tmpl_inc = eng2.load_template_text("""
a: !include_rt
  target: missing.yaml
  required: false
  default: !omit
b: 1
""")
            out_inc = eng2.render(tmpl_inc, registry=_ydst.default_registry())
            self.assertEqual(out_inc, {"b": 1})

    def test_empty_include_file_is_not_missing(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            td_path = _pathlib.Path(td)
            (td_path / "empty.yaml").write_text("", encoding="utf-8")
            (td_path / "main.yaml").write_text("x: !include empty.yaml\n", encoding="utf-8")

            (td_path / "rt.yaml").write_text("x: !include_rt empty.yaml\n", encoding="utf-8")

            eng = _ydst.TemplateEngine(include_resolver=_ydst.FileIncludeResolver(search_paths=[td_path]))
            tmpl = eng.load_template_file(td_path / "main.yaml")
            out = eng.render(tmpl)
            self.assertEqual(out, {"x": None})

            tmpl_rt = eng.load_template_file(td_path / "rt.yaml")
            out_rt = eng.render(tmpl_rt)
            self.assertEqual(out_rt, {"x": None})

            tmpl_rt = eng.load_template_text("x: !include_rt empty.yaml\n")
            out_rt = eng.render(tmpl_rt)
            self.assertEqual(out_rt, {"x": None})


    def test_pipe_unknown_string_stage_default_errors_but_can_be_literal(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """x: !pipe
  - 1
  - not_a_function
"""
        )

        # Default: strict pipe stages => unknown string stage is an error.
        with self.assertRaises(_ydst.RenderError):
            eng.render(tmpl, registry=_ydst.default_registry())

        # Opt-out: allow unknown string stages to be treated as literal values.
        out = eng.render(tmpl, registry=_ydst.default_registry(), options=_ydst.RenderOptions(strict_pipe_stages=False))
        self.assertEqual(out, {"x": "not_a_function"})

    def test_pipe_callable_stage_requires_opt_in(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """x: !pipe
  - 1
  - !var f
"""
        )

        # Default: callable stages are disabled.
        with self.assertRaises(_ydst.RenderError):
            eng.render(tmpl, context={"f": lambda x: x + 1})

        # Opt-in: allow callable stages.
        out = eng.render(tmpl, context={"f": lambda x: x + 1}, options=_ydst.RenderOptions(allow_callable_pipe_stages=True))
        self.assertEqual(out, {"x": 2})

    def test_load_time_include_required_false_defaults_to_none(self) -> None:
        eng = _ydst.TemplateEngine()  # no include_resolver
        tmpl = eng.load_template_text(
            """x: !include
  target: missing.yaml
  required: false
""",
            source_name="inline.yaml",
        )
        out = eng.render(tmpl)
        self.assertEqual(out, {"x": None})

    def test_yaml_parse_error_preserves_mark(self) -> None:
        eng = _ydst.TemplateEngine()
        with self.assertRaises(_ydst.TemplateLoadError) as cm:
            eng.load_template_text("a: [1, 2\n")  # missing closing bracket

        e = cm.exception
        self.assertIsNotNone(e.ctx)
        self.assertIsNotNone(e.ctx.mark)
        assert e.ctx.mark is not None  # type narrowing for mypy
        # Depending on the YAML parser error type, line/column should be present.
        self.assertIsInstance(e.ctx.mark.line, int)
        self.assertIsInstance(e.ctx.mark.column, int)
        self.assertGreaterEqual(e.ctx.mark.line or 0, 1)
        self.assertGreaterEqual(e.ctx.mark.column or 0, 1)



    def test_omit_is_falsy_in_if(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("""
!if
  test: !omit
  then: "YES"
  else: "NO"
""")
        out = eng.render(tmpl)
        self.assertEqual(out, "NO")

    def test_omit_is_falsy_in_foreach_when(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("""
!foreach
  in: [1, 2, 3]
  template: {v: !var item}
  when: !omit
""")
        out = eng.render(tmpl)
        self.assertEqual(out, [])

    def test_loader_validates_boolean_fields(self) -> None:
        eng = _ydst.TemplateEngine()
        with self.assertRaises(_ydst.TemplateLoadError):
            eng.load_template_text('!var {name: x, required: "false"}')

        with self.assertRaises(_ydst.TemplateLoadError):
            eng.load_template_text('!include {timing: load, target: 123}')

    def test_foreach_var_must_be_non_empty_string(self) -> None:
        eng = _ydst.TemplateEngine()
        with self.assertRaises(_ydst.TemplateLoadError):
            eng.load_template_text('!foreach {in: [1], var: "", template: {x: 1}}')

    def test_load_time_include_cycle_is_template_load_error(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            p = _pathlib.Path(td)
            (p / 'a.yaml').write_text('!include b.yaml', encoding='utf-8')
            (p / 'b.yaml').write_text('!include a.yaml', encoding='utf-8')

            resolver = _ydst.FileIncludeResolver(search_paths=[p])
            eng = _ydst.TemplateEngine(include_resolver=resolver)

            with self.assertRaises(_ydst.TemplateLoadError):
                eng.load_template_file(str(p / 'a.yaml'))

    def test_pipe_unknown_stage_strict_errors(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('!pipe [1, unknown]')

        with self.assertRaises(_ydst.RenderError):
            eng.render(tmpl, registry=_ydst.default_registry(), options=_ydst.RenderOptions(strict_pipe_stages=True))

if __name__ == "__main__":
    _unittest.main()
