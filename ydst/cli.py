from __future__ import annotations

import argparse
import importlib
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .engine import TemplateEngine
from .errors import YdstError
from .include import FileIncludeResolver
from .registry import (
    DictFunctionRegistry,
    chain_registries,
    default_registry,
    minimal_registry,
    safe_registry,
)
from .render import RenderOptions


def _load_context(
    *,
    context_json_file: Optional[str],
    context_json: Optional[str],
    context_yaml_file: Optional[str],
    context_yaml: Optional[str],
) -> Dict[str, Any]:
    """Load a context dict from JSON or YAML."""

    if context_json_file:
        text = Path(context_json_file).read_text(encoding="utf-8")
        obj = json.loads(text)
    elif context_json:
        obj = json.loads(context_json)
    elif context_yaml_file:
        text = Path(context_yaml_file).read_text(encoding="utf-8")
        obj = yaml.safe_load(text) or {}
    elif context_yaml:
        obj = yaml.safe_load(context_yaml) or {}
    else:
        obj = {}

    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError(f"Context must be a mapping/object at the top level (got {type(obj).__name__})")
    return obj


def _load_registry(module_name: Optional[str], tier: str) -> Optional[DictFunctionRegistry]:
    reg: Optional[DictFunctionRegistry] = None

    if tier == "default":
        reg = default_registry()
    elif tier == "safe":
        reg = safe_registry()
    elif tier == "minimal":
        reg = minimal_registry()
    elif tier == "none":
        reg = None
    else:
        raise ValueError(f"Unknown registry tier: {tier}")

    if module_name:
        mod = importlib.import_module(module_name)
        obj = getattr(mod, "REGISTRY", None) or getattr(mod, "registry", None)
        if obj is None:
            raise ValueError(f"Registry module '{module_name}' must define REGISTRY or registry")

        if isinstance(obj, dict):
            mod_reg = DictFunctionRegistry(obj)
        else:
            mod_reg = obj  # assume FunctionRegistry-like

        if reg is None:
            return mod_reg  # type: ignore[return-value]

        # Chain: module registry overlays tiered registry.
        return chain_registries(mod_reg, reg)  # type: ignore[return-value]

    return reg


_JSON_KEY_TYPES = (str, int, float, bool, type(None))


def _to_jsonable(obj: Any) -> Any:
    """Best-effort conversion to JSON-serializable structures.

    We primarily handle Python `set` (unsupported by `json`) by converting it to a stable list.
    We also normalize dict keys that are not valid JSON key types.
    """

    if isinstance(obj, dict):
        out: dict[Any, Any] = {}
        for k, v in obj.items():
            kk = k if isinstance(k, _JSON_KEY_TYPES) else str(k)
            out[kk] = _to_jsonable(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, set):
        items = [_to_jsonable(v) for v in obj]
        # Stable output even for mixed/non-orderable elements.
        return sorted(items, key=lambda x: repr(x))
    return obj


def cmd_render(args: argparse.Namespace) -> None:
    include_resolver = None
    if args.include_path:
        include_resolver = FileIncludeResolver(
            search_paths=[Path(p) for p in args.include_path],
            allow_absolute=not args.include_disallow_absolute,
            enforce_roots=args.include_enforce_roots,
        )

    base_loader = yaml.FullLoader if args.full_loader else yaml.SafeLoader
    engine = TemplateEngine(include_resolver=include_resolver, base_loader=base_loader)

    if args.template == "-":
        template_src = sys.stdin.read()
        tmpl = engine.load_template(template_src, source_name="<stdin>")
    else:
        tmpl = engine.load_template_file(args.template)

    ctx = _load_context(
        context_json_file=args.context_file,
        context_json=args.context_json,
        context_yaml_file=args.context_yaml_file,
        context_yaml=args.context_yaml,
    )

    registry = _load_registry(args.registry_module, args.registry_tier)

    options = RenderOptions(
        mode=args.mode,
        strict=not args.non_strict,
        dict_key_conflict=args.dict_key_conflict,
        wrap_exceptions=not args.raw_exceptions,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
        strict_pipe_stages=args.strict_pipe_stages,
    )

    out = engine.render(tmpl, context=ctx, registry=registry, options=options)

    if args.output == "json":
        json.dump(_to_jsonable(out), sys.stdout, indent=2, sort_keys=False)
        sys.stdout.write("\n")
    else:
        yaml.safe_dump(out, sys.stdout, sort_keys=False)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ydst", description="Render YAML data-structure templates.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="Render a template")
    r.add_argument("template", help="Template file path, or '-' for stdin")

    ctx_group = r.add_mutually_exclusive_group()
    ctx_group.add_argument("--context-file", help="Path to JSON context file")
    ctx_group.add_argument("--context-json", help="Inline JSON context string")
    ctx_group.add_argument("--context-yaml-file", help="Path to YAML context file")
    ctx_group.add_argument("--context-yaml", help="Inline YAML context string")

    reg_group = r.add_mutually_exclusive_group()
    reg_group.add_argument(
        "--registry-tier",
        choices=["none", "minimal", "safe", "default"],
        default="none",
        help="Enable a built-in registry tier",
    )
    # Back-compat flag (maps to default tier).
    reg_group.add_argument(
        "--default-registry",
        action="store_true",
        help="Enable ydst.default_registry() (same as --registry-tier=default)",
    )
    r.add_argument("--registry-module", help="Python module providing REGISTRY or registry")

    r.add_argument("--include-path", action="append", default=[], help="Add an include search path (repeatable)")
    r.add_argument("--include-disallow-absolute", action="store_true", help="Disallow absolute include targets")
    r.add_argument(
        "--include-enforce-roots",
        action="store_true",
        help="Require includes to resolve under include-path roots",
    )

    r.add_argument("--full-loader", action="store_true", help="Use yaml.FullLoader instead of SafeLoader")

    r.add_argument("--mode", choices=["trusted", "safe", "expr_safe", "locked_down"], default="trusted")
    r.add_argument("--non-strict", action="store_true", help="Non-strict mode (missing vars -> None/defaults)")
    r.add_argument(
        "--dict-key-conflict",
        choices=["auto", "error", "last", "first"],
        default="auto",
        help="Duplicate key policy during rendering",
    )
    r.add_argument("--strict-pipe-stages", action="store_true", help="Error on unknown string pipe stages")

    r.add_argument("--raw-exceptions", action="store_true", help="Do not wrap exceptions (debugging)")
    r.add_argument("--max-depth", type=int, default=200)
    r.add_argument("--max-nodes", type=int, default=None)

    r.add_argument("--output", choices=["json", "yaml"], default="json")

    r.add_argument("--debug", action="store_true", help="Show full tracebacks on error")

    r.set_defaults(func=cmd_render)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Back-compat flag mapping.
    if getattr(args, "default_registry", False):
        args.registry_tier = "default"

    try:
        args.func(args)  # type: ignore[misc]
        return 0
    except YdstError as e:
        sys.stderr.write(str(e))
        sys.stderr.write("\n")
        if getattr(args, "debug", False):
            traceback.print_exc()
        return 2
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        if getattr(args, "debug", False):
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
