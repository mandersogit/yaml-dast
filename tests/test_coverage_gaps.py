"""Sanity tests for low-coverage modules.

These tests verify basic functionality works for modules that have low coverage.
They're not exhaustive, but ensure the code is at least importable and functional.
"""
import tempfile as _tempfile
import pathlib as _pathlib

import ydst as _ydst
import ydst.analysis as _analysis
import ydst.normalize as _normalize
import ydst.registry as _registry
import ydst.validate as _validate


class TestNormalize:
    """ydst.to_jsonable() function."""

    def test_to_jsonable_basic(self) -> None:
        result = _normalize.to_jsonable({"x": 1, "y": [2, 3]})
        assert result == {"x": 1, "y": [2, 3]}

    def test_to_jsonable_with_tuple(self) -> None:
        result = _normalize.to_jsonable({"x": (1, 2, 3)})
        # Tuples should become lists for JSON
        assert result == {"x": [1, 2, 3]}

    def test_to_jsonable_with_set(self) -> None:
        result = _normalize.to_jsonable({"x": {1, 2}})
        # Sets should become sorted lists for JSON
        assert result == {"x": [1, 2]}


class TestAnalysis:
    """ydst analysis functions (require Template objects)."""

    def test_collect_variables(self) -> None:
        tmpl = _ydst.Template.from_text("x: !var foo\ny: !var bar")
        vars_found = _analysis.collect_variables(tmpl)
        assert "foo" in vars_found
        assert "bar" in vars_found

    def test_analyze_dependencies(self) -> None:
        tmpl = _ydst.Template.from_text("""
x: !var foo
y: !expr "bar + 1"
z: !call func
""")
        deps = _analysis.analyze_dependencies(tmpl)
        assert isinstance(deps, _analysis.Dependencies)
        assert "foo" in deps.variables

    def test_collect_expressions(self) -> None:
        tmpl = _ydst.Template.from_text('x: !expr "a + b"')
        exprs = _analysis.collect_expressions(tmpl)
        assert len(exprs) >= 1

    def test_collect_calls(self) -> None:
        tmpl = _ydst.Template.from_text("x: !call my_func")
        calls = _analysis.collect_calls(tmpl)
        assert "my_func" in calls


class TestValidate:
    """ydst.validate_template() function (requires Template object)."""

    def test_validate_valid_template(self) -> None:
        tmpl = _ydst.Template.from_text("x: !var foo")
        # Should not raise
        _validate.validate_template(tmpl)

    def test_validate_complex_template(self) -> None:
        # Validation walks the entire tree - test it handles complex structures
        tmpl = _ydst.Template.from_text("""
top:
  x: !var foo
  nested:
    - !if
        test: !expr "x > 0"
        then: positive
        else: !omit
    - !foreach
        var: i
        in: !var items
        template: !expr "i * 2"
""")
        # Should not raise - template is structurally valid
        _validate.validate_template(tmpl)


class TestRegistryTiers:
    """Function registry tiers."""

    def test_minimal_registry(self) -> None:
        reg = _registry.minimal_registry()
        # Minimal has only: get_in, coalesce, slugify, to_int, to_float
        assert reg.get("get_in") is not None
        assert reg.get("coalesce") is not None
        assert reg.get("len") is None  # len is NOT in minimal

    def test_safe_registry(self) -> None:
        reg = _registry.safe_registry()
        # Safe should have more than minimal
        assert reg.get("len") is not None
        assert reg.get("str") is not None

    def test_default_registry(self) -> None:
        reg = _registry.default_registry()
        # Default is alias for safe
        assert reg.get("len") is not None

    def test_extended_registry(self) -> None:
        reg = _ydst.extended_registry()
        # Extended has everything
        assert reg.get("len") is not None

    def test_chain_registries(self) -> None:
        reg1 = _ydst.DictFunctionRegistry({"foo": lambda: 1})
        reg2 = _ydst.DictFunctionRegistry({"bar": lambda: 2})
        chained = _registry.chain_registries(reg1, reg2)
        assert chained.get("foo") is not None
        assert chained.get("bar") is not None


class TestApiModule:
    """api.py functions still exposed at module level."""

    def test_safe_engine(self) -> None:
        eng = _ydst.safe_engine()
        assert isinstance(eng, _ydst.TemplateEngine)

    def test_safe_engine_configures_include_resolver(self) -> None:
        # safe_engine sets up restricted include resolver
        eng = _ydst.safe_engine(include_paths=["/tmp"])
        # Should have an include resolver configured
        assert eng.include_resolver is not None


class TestIncludeResolver:
    """FileIncludeResolver functionality."""

    def test_file_include_resolver_basic(self) -> None:
        with _tempfile.TemporaryDirectory() as td:
            td_path = _pathlib.Path(td)
            (td_path / "inc.yaml").write_text("value: 42\n", encoding="utf-8")

            resolver = _ydst.FileIncludeResolver(search_paths=[td_path])
            result = resolver.resolve("inc.yaml", from_source=None)
            assert result.content is not None
            assert "42" in result.content

    def test_file_include_resolver_not_found(self) -> None:
        resolver = _ydst.FileIncludeResolver(search_paths=[])
        result = resolver.resolve("nonexistent.yaml", from_source=None)
        assert result.content is None


class TestCLIImport:
    """Verify CLI module at least imports."""

    def test_cli_module_imports(self) -> None:
        import ydst.cli as cli
        assert hasattr(cli, "main")

    def test_main_module_imports(self) -> None:
        import ydst.__main__ as main_mod  # noqa: F401
        # Just verify it imports without error

