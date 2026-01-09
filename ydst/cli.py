from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .engine import TemplateEngine
from .include import FileIncludeResolver
from .registry import DictFunctionRegistry, default_registry
from .render import RenderOptions


def _load_context(context_file: Optional[str], context_json: Optional[str]) -> Dict[str, Any]:
    if context_file:
        text = Path(context_file).read_text(encoding="utf-8")
        return json.loads(text)
    if context_json:
        return json.loads(context_json)
    return {}


def _load_registry(module_name: Optional[str], use_default: bool) -> Optional[DictFunctionRegistry]:
    reg = None
    if use_default:
        reg = default_registry()
    if module_name:
        mod = importlib.import_module(module_name)
        obj = getattr(mod, "REGISTRY", None) or getattr(mod, "registry", None)
        if obj is None:
            raise SystemExit(f"Registry module '{module_name}' must define REGISTRY or registry")
        if isinstance(obj, dict):
            mod_reg = DictFunctionRegistry(obj)
        else:
            mod_reg = obj  # assume FunctionRegistry-like
        if reg is None:
            return mod_reg
        # chain: module registry overlays default? keep module first
        from .registry import chain_registries

        return chain_registries(mod_reg, reg)  # type: ignore[return-value]
    return reg


def cmd_render(args: argparse.Namespace) -> None:
    include_resolver = None
    if args.include_path:
        include_resolver = FileIncludeResolver(search_paths=[Path(p) for p in args.include_path])

    base_loader = yaml.FullLoader if args.full_loader else yaml.SafeLoader
    engine = TemplateEngine(include_resolver=include_resolver, base_loader=base_loader)

    if args.template == "-":
        template_src = sys.stdin.read()
        tmpl = engine.load_template(template_src, source_name="<stdin>")
    else:
        tmpl = engine.load_template_file(args.template)

    ctx = _load_context(args.context_file, args.context_json)
    registry = _load_registry(args.registry_module, args.default_registry)

    options = RenderOptions(
        mode=args.mode,
        strict=not args.non_strict,
        dict_key_conflict=args.dict_key_conflict,
        wrap_exceptions=not args.raw_exceptions,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
    )

    out = engine.render(tmpl, context=ctx, registry=registry, options=options)

    if args.output == "json":
        json.dump(out, sys.stdout, indent=2, sort_keys=False)
        sys.stdout.write("\n")
    else:
        yaml.safe_dump(out, sys.stdout, sort_keys=False)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ydst", description="Render YAML data-structure templates.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="Render a template")
    r.add_argument("template", help="Template file path, or '-' for stdin")
    r.add_argument("--context-file", help="Path to JSON context file")
    r.add_argument("--context-json", help="Inline JSON context string")

    r.add_argument("--default-registry", action="store_true", help="Enable ydst.default_registry()")
    r.add_argument("--registry-module", help="Python module providing REGISTRY or registry")

    r.add_argument("--include-path", action="append", default=[], help="Add an include search path (repeatable)")
    r.add_argument("--full-loader", action="store_true", help="Use yaml.FullLoader instead of SafeLoader")

    r.add_argument("--mode", choices=["trusted", "safe"], default="trusted")
    r.add_argument("--non-strict", action="store_true", help="Non-strict mode (missing vars -> None/defaults)")
    r.add_argument(
        "--dict-key-conflict",
        choices=["auto", "error", "last", "first"],
        default="auto",
        help="Duplicate key policy during rendering",
    )
    r.add_argument("--raw-exceptions", action="store_true", help="Do not wrap exceptions (debugging)")
    r.add_argument("--max-depth", type=int, default=200)
    r.add_argument("--max-nodes", type=int, default=None)

    r.add_argument("--output", choices=["json", "yaml"], default="json")
    r.set_defaults(func=cmd_render)

    return p


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)  # type: ignore[misc]


if __name__ == "__main__":
    main()
