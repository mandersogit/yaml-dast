"""Tests for !python and !python_module tags."""

import pytest as _pytest

import ydst as _ydst


class TestPythonBasic:
    """Basic !python functionality."""

    def test_python_disabled_by_default(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('x: !python "emit(42)"')
        with _pytest.raises(_ydst.RenderError) as cm:
            eng.render(tmpl)
        assert "disabled" in str(cm.value).lower()

    def test_python_disabled_in_locked_down_mode(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('x: !python "emit(42)"')
        with _pytest.raises(_ydst.RenderError):
            eng.render(tmpl, options=_ydst.RenderOptions(mode="locked_down", allow_python=True))

    def test_python_explicit_emit(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('x: !python "emit(42)"')
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_python=True))
        assert out == {"x": 42}

    def test_python_implicit_emit_trailing_expression(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('x: !python "40 + 2"')
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_python=True))
        assert out == {"x": 42}

    def test_python_implicit_emit_multiline(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
x: !python |
  a = 10
  b = 32
  a + b
"""
        )
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_python=True))
        assert out == {"x": 42}

    def test_python_no_trailing_expression_returns_none(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
x: !python |
  a = 42
"""
        )
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_python=True))
        assert out == {"x": None}

    def test_python_strict_emit_requires_explicit_emit(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('x: !python "42"')
        with _pytest.raises(_ydst.PythonEmitError):
            eng.render(tmpl, options=_ydst.RenderOptions(allow_python=True, python_strict_emit=True))

    def test_python_strict_emit_per_node(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
x: !python
  code: "42"
  strict_emit: true
"""
        )
        with _pytest.raises(_ydst.PythonEmitError):
            eng.render(tmpl, options=_ydst.RenderOptions(allow_python=True))

    def test_python_access_scope_variables(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('x: !python "emit(foo * 2)"')
        out = eng.render(tmpl, context={"foo": 21}, options=_ydst.RenderOptions(allow_python=True))
        assert out == {"x": 42}

    def test_python_emit_omit(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
a: !python "emit(OMIT)"
b: 1
"""
        )
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_python=True))
        assert out == {"b": 1}

    def test_python_syntax_error_raises(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('x: !python "if True"')  # incomplete
        with _pytest.raises(_ydst.PythonError):
            eng.render(tmpl, options=_ydst.RenderOptions(allow_python=True))


class TestPythonModule:
    """!python_module functionality."""

    def test_python_module_disabled_by_default(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('- !python_module "x = 1"')
        with _pytest.raises(_ydst.RenderError) as cm:
            eng.render(tmpl)
        assert "disabled" in str(cm.value).lower()

    def test_python_module_disabled_in_locked_down_mode(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('- !python_module "x = 1"')
        with _pytest.raises(_ydst.RenderError):
            eng.render(tmpl, options=_ydst.RenderOptions(mode="locked_down", allow_python_module=True))

    def test_python_module_returns_omit(self) -> None:
        eng = _ydst.TemplateEngine()
        # Use a dict structure instead of list to verify OMIT filtering works
        tmpl = eng.load_template_text(
            """
setup: !python_module "helper = 1"
x: 42
"""
        )
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_python_module=True))
        # setup key is omitted
        assert out == {"x": 42}

    def test_python_module_defines_function_for_expr(self) -> None:
        eng = _ydst.TemplateEngine()
        # Use dict structure to avoid OMIT-in-list issue
        tmpl = eng.load_template_text(
            """
setup: !python_module |
    def double(x):
        return x * 2
x: !expr "double(21)"
"""
        )
        out = eng.render(
            tmpl,
            options=_ydst.RenderOptions(allow_python_module=True),
            registry=_ydst.default_registry(),
        )
        assert out == {"x": 42}

    def test_python_module_defines_function_for_call(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
setup: !python_module |
    def triple(x):
        return x * 3
x: !call {fn: triple, args: [14]}
"""
        )
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_python_module=True))
        assert out == {"x": 42}

    def test_python_module_defines_function_for_pipe(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
setup: !python_module |
    def add_ten(x):
        return x + 10
x: !pipe
  - 32
  - add_ten
"""
        )
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_python_module=True))
        assert out == {"x": 42}


class TestPythonStatefulPatterns:
    """Stateful patterns using !python and !python_module together."""

    def test_accumulator_pattern(self) -> None:
        """Test that !python can accumulate state across foreach iterations."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
setup: !python_module |
    total = 0

items: !foreach
  var: price
  in: !var prices
  template: !python |
      global total
      total += price
      emit({"price": price, "running_total": total})
"""
        )
        out = eng.render(
            tmpl,
            context={"prices": [10, 20, 30]},
            options=_ydst.RenderOptions(allow_python=True, allow_python_module=True),
        )
        assert out["items"] == \
            [
                {"price": 10, "running_total": 10},
                {"price": 20, "running_total": 30},
                {"price": 30, "running_total": 60},
            ]

    def test_counter_id_generation_pattern(self) -> None:
        """Test ID generation using a counter in !python_module."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
setup: !python_module |
    _counter = 0
    def next_id():
        global _counter
        _counter += 1
        return f"item-{_counter}"

items: !foreach
  var: x
  in: !var data
  template:
    id: !expr "next_id()"
    value: !expr "x"
"""
        )
        out = eng.render(
            tmpl,
            context={"data": ["a", "b", "c"]},
            options=_ydst.RenderOptions(allow_python_module=True),
            registry=_ydst.default_registry(),
        )
        assert out["items"] == \
            [
                {"id": "item-1", "value": "a"},
                {"id": "item-2", "value": "b"},
                {"id": "item-3", "value": "c"},
            ]

    def test_scope_mutation_from_python(self) -> None:
        """Test that !python can mutate scope and later !var sees the change."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
setup: !python |
    scope["computed"] = 42
    emit(OMIT)
x: !var computed
"""
        )
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_python=True))
        assert out == {"x": 42}


class TestSetDefault:
    """Tests for !setdefault tag."""

    def test_setdefault_can_be_manually_disabled(self) -> None:
        """Users can opt-out of !setdefault if desired."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('setup: !setdefault {env: prod}')
        with _pytest.raises(_ydst.RenderError) as cm:
            eng.render(tmpl, options=_ydst.RenderOptions(allow_setdefault=False))
        assert "disabled" in str(cm.value).lower()

    def test_setdefault_basic(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
setup: !setdefault {env: prod}
env: !var env
"""
        )
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_setdefault=True))
        assert out == {"env": "prod"}

    def test_setdefault_does_not_override_caller_value(self) -> None:
        """Caller-provided values take precedence over !setdefault."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
setup: !setdefault {env: prod}
env: !var env
"""
        )
        out = eng.render(
            tmpl,
            context={"env": "dev"},
            options=_ydst.RenderOptions(allow_setdefault=True),
        )
        assert out == {"env": "dev"}

    def test_setdefault_multiple_vars(self) -> None:
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
setup: !setdefault
  env: prod
  region: us-east-1
env: !var env
region: !var region
"""
        )
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_setdefault=True))
        assert out == {"env": "prod", "region": "us-east-1"}

    def test_setdefault_partial_override(self) -> None:
        """Caller provides one value, setdefault provides the other."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
setup: !setdefault
  env: prod
  region: us-east-1
env: !var env
region: !var region
"""
        )
        out = eng.render(
            tmpl,
            context={"env": "dev"},
            options=_ydst.RenderOptions(allow_setdefault=True),
        )
        assert out == {"env": "dev", "region": "us-east-1"}

    def test_setdefault_works_in_locked_down_mode(self) -> None:
        """!setdefault is safe and should work even in locked_down mode."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
setup: !setdefault {x: 42}
x: !var x
"""
        )
        out = eng.render(tmpl, options=_ydst.RenderOptions(mode="locked_down"))
        assert out == {"x": 42}


class TestOmitFiltering:
    """Test that OMIT values are filtered from lists and sets."""

    def test_omit_filtered_from_list(self) -> None:
        """OMIT values should be filtered from list output."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
- !omit
- 1
- !omit
- 2
"""
        )
        out = eng.render(tmpl)
        assert out == [1, 2]

    def test_omit_from_python_filtered_from_list(self) -> None:
        """!python emit(OMIT) should be filtered from list."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
- !python "emit(OMIT)"
- 1
- 2
"""
        )
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_python=True))
        assert out == [1, 2]

    def test_setdefault_filtered_from_list(self) -> None:
        """!setdefault returns OMIT and should be filtered from list."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
- !setdefault {x: 42}
- value: !var x
"""
        )
        out = eng.render(tmpl)
        assert out == [{"value": 42}]

    def test_python_module_filtered_from_list(self) -> None:
        """!python_module returns OMIT and should be filtered from list."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text(
            """
- !python_module "helper = 1"
- x: 42
"""
        )
        out = eng.render(tmpl, options=_ydst.RenderOptions(allow_python_module=True))
        assert out == [{"x": 42}]


class TestExprDictAttributeRemoval:
    """Test that dict attribute convenience has been removed."""

    def test_dict_attribute_access_no_longer_falls_back_to_key(self) -> None:
        """x.key on a dict no longer returns x["key"]."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('x: !expr "d.foo"')
        # Should raise AttributeError because dicts don't have a "foo" attribute
        with _pytest.raises(_ydst.ExpressionError):
            eng.render(tmpl, context={"d": {"foo": 42}}, registry=_ydst.default_registry())

    def test_dict_subscript_still_works(self) -> None:
        """x["key"] still works for dict access."""
        eng = _ydst.TemplateEngine()
        tmpl = eng.load_template_text('x: !expr "d[\'foo\']"')
        out = eng.render(tmpl, context={"d": {"foo": 42}}, registry=_ydst.default_registry())
        assert out == {"x": 42}
