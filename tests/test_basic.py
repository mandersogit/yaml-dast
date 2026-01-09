import pytest as _pytest
import pathlib as _pathlib
import tempfile as _tempfile

import ydst as _ydst
import ydst.errors as _errors
import ydst.registry as _registry


class TestYdstBasic:
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
        out = tmpl.render( context={"x": 2}, registry=_registry.default_registry())
        assert out == {"a": 1, "b": 2, "c": "yes"}

        out2 = tmpl.render( context={"x": 1}, registry=_registry.default_registry())
        assert out2 == {"a": 1, "b": 1}

    def test_root_omit_is_error(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("!omit")
        with _pytest.raises(_errors.RootOmitError):
            tmpl.render( context={}, registry=_registry.default_registry())

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
        out = tmpl.render( context={"xs": [1, 2, 3]}, registry=_registry.default_registry())
        assert out["items"] == [2, 4, 6]

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
        out = tmpl.render( context={"xs": [1, 2, 3]}, registry=_registry.default_registry())
        assert out["m"] == {1: 1, 2: 4, 3: 9}

    def test_foreach_allows_explicit_null_template_key_value(self) -> None:
        eng = _ydst.TemplateEngine()

        tmpl_list = eng.load_template_text(
            """
x: !foreach
  in: [1, 2, 3]
  template: null
"""
        )
        assert tmpl_list.render() == {"x": [None, None, None]}

        tmpl_set = eng.load_template_text(
            """
x: !foreach
  in: [1, 2]
  into: set
  template: null
"""
        )
        assert tmpl_set.render() == {"x": {None}}

        tmpl_dict = eng.load_template_text(
            """
x: !foreach
  in: [1]
  into: dict
  key: null
  value: null
"""
        )
        assert tmpl_dict.render() == {"x": {None: None}}

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
        reg = _registry.default_registry()
        reg.functions["truncate"] = lambda s, max_len=5: str(s)[:max_len]

        out = tmpl.render( context={"title": "Hello, World"}, registry=reg)
        assert out["slug"] == "hello"

    def test_load_time_include(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            td_path = _pathlib.Path(td)
            (td_path / "a.yaml").write_text("x: 1\n", encoding="utf-8")
            (td_path / "b.yaml").write_text("y: !include a.yaml\n", encoding="utf-8")

            eng = _ydst.TemplateEngine(include_resolver=_ydst.FileIncludeResolver(search_paths=[td_path]))
            tmpl = eng.load_template_path(td_path / "b.yaml")
            out = tmpl.render()
            assert out == {"y": {"x": 1}}

    def test_runtime_include(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            td_path = _pathlib.Path(td)
            (td_path / "a.yaml").write_text("x: !var v\n", encoding="utf-8")
            (td_path / "b.yaml").write_text("y: !include_rt a.yaml\n", encoding="utf-8")

            eng = _ydst.TemplateEngine(include_resolver=_ydst.FileIncludeResolver(search_paths=[td_path]))
            tmpl = eng.load_template_path(td_path / "b.yaml")
            out = tmpl.render( context={"v": 42})
            assert out == {"y": {"x": 42}}

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
        out = tmpl.render( registry=_registry.default_registry(), options=_ydst.RenderOptions(dict_key_conflict="last"))
        assert out["m"] == {1: 1}

        # strict with error
        with _pytest.raises(_ydst.RenderError) as cm:
            tmpl.render( registry=_registry.default_registry(), options=_ydst.RenderOptions(dict_key_conflict="error"))

        # Ensure the error path includes the iteration index that caused the conflict.
        assert "path=$.m[1].key" in str(cm.value)

    def test_expr_calls_with_chained_registry(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("n: !expr \"len(xs)\"\n")

        extra = _registry.default_registry()
        extra.functions = {"noop": lambda x: x}

        reg = _registry.chain_registries(extra, _registry.default_registry())
        out = tmpl.render( context={"xs": [1, 2, 3]}, registry=reg)
        assert out["n"] == 3

    def test_expr_calls_with_get_only_registry(self) -> None:
        class _GetOnly:
            def __init__(self, funcs: dict) -> None:
                self._funcs = dict(funcs)

            def get(self, name: str):
                return self._funcs.get(name)

        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("n: !expr \"len(xs)\"\n")
        reg = _GetOnly({"len": len})
        out = tmpl.render( context={"xs": [1, 2, 3]}, registry=reg)
        assert out["n"] == 3

    def test_expr_dict_unpacking_rejected(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("x: !expr \"{**d}\"\n")
        with _pytest.raises(_errors.ExpressionError):
            tmpl.render( context={"d": {"a": 1}}, registry=_registry.default_registry())

    def test_expr_private_attributes_rejected(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("x: !expr \"obj.__class__.__name__\"\n")
        with _pytest.raises(_errors.ExpressionError):
            tmpl.render(context={"obj": object()}, registry=_registry.default_registry())

        # Opt-in: allow private/dunder attribute access.
        out = tmpl.render(
            context={"obj": object()},
            registry=_registry.default_registry(),
            options=_ydst.RenderOptions(allow_private_attributes_in_expr=True),
        )
        assert out["x"] == "object"

    def test_expr_subscripts_policy_toggle(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("x: !expr \"d['a']\"\n")

        with _pytest.raises(_errors.ExpressionError):
            tmpl.render(
                context={"d": {"a": 1}},
                registry=_registry.default_registry(),
                options=_ydst.RenderOptions(allow_subscripts_in_expr=False),
            )

        out = tmpl.render(context={"d": {"a": 1}}, registry=_registry.default_registry())
        assert out == {"x": 1}

    def test_safe_mode_disables_expr_calls(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("n: !expr \"len(xs)\"\n")
        with _pytest.raises(_errors.ExpressionError):
            tmpl.render(
                context={"xs": [1, 2, 3]},
                registry=_registry.default_registry(),
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
        with _pytest.raises(_ydst.RenderError):
            tmpl.render( options=_ydst.RenderOptions(max_depth=3))

    def test_default_omit_for_var_expr_include_rt(self) -> None:
        eng = _ydst.TemplateEngine()

        tmpl_var = eng.load_template_text("""
a: !var
  name: missing
  required: false
  default: !omit
b: 1
""")
        out_var = tmpl_var.render(registry=_registry.default_registry())
        assert out_var == {"b": 1}

        tmpl_expr = eng.load_template_text("""
a: !expr
  expr: missing_name
  strict: false
  default: !omit
b: 1
""")
        out_expr = tmpl_expr.render(registry=_registry.default_registry())
        assert out_expr == {"b": 1}

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
            out_inc = tmpl_inc.render(registry=_registry.default_registry())
            assert out_inc == {"b": 1}

    def test_empty_include_file_is_not_missing(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            td_path = _pathlib.Path(td)
            (td_path / "empty.yaml").write_text("", encoding="utf-8")
            (td_path / "main.yaml").write_text("x: !include empty.yaml\n", encoding="utf-8")

            (td_path / "rt.yaml").write_text("x: !include_rt empty.yaml\n", encoding="utf-8")

            eng = _ydst.TemplateEngine(include_resolver=_ydst.FileIncludeResolver(search_paths=[td_path]))
            tmpl = eng.load_template_path(td_path / "main.yaml")
            out = tmpl.render()
            assert out == {"x": None}

            tmpl_rt = eng.load_template_path(td_path / "rt.yaml")
            out_rt = tmpl_rt.render()
            assert out_rt == {"x": None}

            tmpl_rt = eng.load_template_text("x: !include_rt empty.yaml\n")
            out_rt = tmpl_rt.render()
            assert out_rt == {"x": None}


    def test_pipe_unknown_string_stage_default_errors_but_can_be_literal(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """x: !pipe
  - 1
  - not_a_function
"""
        )

        # Default: strict pipe stages => unknown string stage is an error.
        with _pytest.raises(_ydst.RenderError):
            tmpl.render( registry=_registry.default_registry())

        # Opt-out: allow unknown string stages to be treated as literal values.
        out = tmpl.render( registry=_registry.default_registry(), options=_ydst.RenderOptions(strict_pipe_stages=False))
        assert out == {"x": "not_a_function"}

    def test_pipe_callable_stage_requires_opt_in(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """x: !pipe
  - 1
  - !var f
"""
        )

        # Default: callable stages are disabled.
        with _pytest.raises(_ydst.RenderError):
            tmpl.render( context={"f": lambda x: x + 1})

        # Opt-in: allow callable stages.
        out = tmpl.render( context={"f": lambda x: x + 1}, options=_ydst.RenderOptions(allow_callable_pipe_stages=True))
        assert out == {"x": 2}

    def test_load_time_include_required_false_defaults_to_none(self) -> None:
        eng = _ydst.TemplateEngine()  # no include_resolver
        tmpl = eng.load_template_text(
            """x: !include
  target: missing.yaml
  required: false
""",
            source_name="inline.yaml",
        )
        out = tmpl.render()
        assert out == {"x": None}

    def test_yaml_parse_error_preserves_mark(self) -> None:
        eng = _ydst.TemplateEngine()
        with _pytest.raises(_ydst.TemplateLoadError) as cm:
            eng.load_template_text("a: [1, 2\n")  # missing closing bracket

        e = cm.value
        assert e.ctx is not None
        assert e.ctx.mark is not None
        assert e.ctx.mark is not None  # type narrowing for mypy
        # Depending on the YAML parser error type, line/column should be present.
        assert isinstance(e.ctx.mark.line, int)
        assert isinstance(e.ctx.mark.column, int)
        assert e.ctx.mark.line or 0 >= 1
        assert e.ctx.mark.column or 0 >= 1



    def test_omit_is_falsy_in_if(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("""
!if
  test: !omit
  then: "YES"
  else: "NO"
""")
        out = tmpl.render()
        assert out == "NO"

    def test_omit_is_falsy_in_foreach_when(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text("""
!foreach
  in: [1, 2, 3]
  template: {v: !var item}
  when: !omit
""")
        out = tmpl.render()
        assert out == []

    def test_loader_validates_boolean_fields(self) -> None:
        eng = _ydst.TemplateEngine()
        with _pytest.raises(_ydst.TemplateLoadError):
            eng.load_template_text('!var {name: x, required: "false"}')

        with _pytest.raises(_ydst.TemplateLoadError):
            eng.load_template_text('!include {timing: load, target: 123}')

    def test_foreach_var_must_be_non_empty_string(self) -> None:
        eng = _ydst.TemplateEngine()
        with _pytest.raises(_ydst.TemplateLoadError):
            eng.load_template_text('!foreach {in: [1], var: "", template: {x: 1}}')

    def test_load_time_include_cycle_is_template_load_error(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            p = _pathlib.Path(td)
            (p / 'a.yaml').write_text('!include b.yaml', encoding='utf-8')
            (p / 'b.yaml').write_text('!include a.yaml', encoding='utf-8')

            resolver = _ydst.FileIncludeResolver(search_paths=[p])
            eng = _ydst.TemplateEngine(include_resolver=resolver)

            with _pytest.raises(_ydst.TemplateLoadError):
                eng.load_template_path(str(p / 'a.yaml'))

    def test_pipe_unknown_stage_strict_errors(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('!pipe [1, unknown]')

        with _pytest.raises(_ydst.RenderError):
            tmpl.render( registry=_registry.default_registry(), options=_ydst.RenderOptions(strict_pipe_stages=True))