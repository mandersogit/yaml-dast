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
from .errors import YdstError, format_path, format_mark
from .include import FileIncludeResolver
from .nodes import OMIT, Omit
from .registry import (
    FunctionRegistry,
    DictFunctionRegistry,
    chain_registries,
    minimal_registry,
    safe_registry,
    extended_registry,
)
from .render import RenderOptions
from .normalize import to_jsonable


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


def _load_registry(module_name: Optional[str], tier: str) -> Optional[FunctionRegistry]:
    reg: Optional[FunctionRegistry] = None

    if tier == "extended":
        reg = extended_registry()
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




def _truncate_repr(obj: object, *, max_len: int = 500) -> str:
    r = repr(obj)
    if len(r) > max_len:
        return r[: max_len - 3] + "..."
    return r


def _build_trace_sink(trace_file: Optional[str]) -> tuple[Optional[callable], Optional[Any]]:
    """Build a trace sink and optional file handle.

    The sink writes JSON lines with basic per-node information.
    """

    if trace_file:
        fh: Any = open(trace_file, "w", encoding="utf-8")
        stream = fh
    else:
        fh = None
        stream = sys.stderr

    def sink(ev: Any) -> None:  # TraceEvent
        try:
            rec = {
                "path": format_path(getattr(ev, "path", ())),
                "node_type": getattr(ev, "node_type", None),
                "mark": format_mark(getattr(ev, "mark", None)),
                "before": _truncate_repr(getattr(ev, "before", None)),
                "after": _truncate_repr(getattr(ev, "after", None)),
            }
            stream.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            # Trace should never crash the render.
            pass

    return sink, fh

def cmd_render(args: argparse.Namespace) -> None:
    include_resolver = None
    if args.include_path:
        include_resolver = FileIncludeResolver(
            search_paths=[Path(p) for p in args.include_path],
            allow_absolute=not args.include_disallow_absolute,
            enforce_roots=args.include_enforce_roots,
        )

    base_loader = yaml.FullLoader if args.full_loader else yaml.SafeLoader
    engine = TemplateEngine(
        include_resolver=include_resolver,
        base_loader=base_loader,
        max_include_depth=args.max_include_depth,
        allow_load_time_includes=not args.disable_load_includes,
    )

    if args.template == "-":
        template_src = sys.stdin.read()
        tmpl = engine.load_template_text(template_src, source_name="<stdin>")
    else:
        tmpl = engine.load_template_file(args.template)

    ctx = _load_context(
        context_json_file=args.context_file,
        context_json=args.context_json,
        context_yaml_file=args.context_yaml_file,
        context_yaml=args.context_yaml,
    )

    registry = _load_registry(args.registry_module, args.registry_tier)

    trace_sink = None
    trace_fh = None
    if getattr(args, "trace", False) or getattr(args, "trace_file", None):
        trace_sink, trace_fh = _build_trace_sink(getattr(args, "trace_file", None))

    options = RenderOptions(
        mode=args.mode,
        strict=not args.non_strict,
        dict_key_conflict=args.dict_key_conflict,
        wrap_exceptions=not args.raw_exceptions,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
        strict_pipe_stages=(args.pipe_unknown == "error"),
        allow_callable_pipe_stages=args.callable_pipe_stages,
        allow_pipe_registry_calls=not args.no_pipe_registry_calls,
        trace=trace_sink,
    )

    out = engine.render(tmpl, context=ctx, registry=registry, options=options)

    # CLI-friendly normalization: a root-level !omit in non-strict mode is serialized as null.
    if out is OMIT or isinstance(out, Omit):
        out = None

    output_stream = sys.stdout
    out_fh = None
    if getattr(args, "output_file", None):
        out_fh = open(args.output_file, "w", encoding="utf-8")
        output_stream = out_fh

    try:
        if args.output == "json":
            json.dump(to_jsonable(out), output_stream, indent=2, sort_keys=False)
            output_stream.write("\n")
        else:
            yaml.safe_dump(out, output_stream, sort_keys=False)
    finally:
        if out_fh is not None:
            out_fh.close()
        if trace_fh is not None:
            trace_fh.close()


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
        choices=["none", "minimal", "safe", "extended"],
        default="none",
        help="Enable a built-in registry tier",
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

    r.add_argument("--mode", choices=["trusted", "expr_safe", "locked_down"], default="trusted")
    r.add_argument("--non-strict", action="store_true", help="Non-strict mode (missing vars -> None/defaults)")
    r.add_argument(
        "--dict-key-conflict",
        choices=["auto", "error", "last", "first"],
        default="auto",
        help="Duplicate key policy during rendering",
    )
    r.add_argument(
        "--pipe-unknown",
        choices=["error", "literal"],
        default="error",
        help="How to handle unknown string stages in !pipe (default: error)",
    )
    r.add_argument(
        "--callable-pipe-stages",
        action="store_true",
        help="Allow pipe stages that render to arbitrary callables (advanced)",
    )
    r.add_argument(
        "--no-pipe-registry-calls",
        action="store_true",
        help="Treat string pipe stages as literal values (do not call registry functions)",
    )

    r.add_argument("--raw-exceptions", action="store_true", help="Do not wrap exceptions (debugging)")
    r.add_argument("--max-depth", type=int, default=200)
    r.add_argument("--max-nodes", type=int, default=None)

    r.add_argument(
        "--max-include-depth",
        type=int,
        default=None,
        help="Maximum include depth for load-time !include expansion",
    )
    r.add_argument(
        "--disable-load-includes",
        action="store_true",
        help="Disable load-time includes (!include)",
    )

    r.add_argument("--output", choices=["json", "yaml"], default="json")
    r.add_argument("--output-file", help="Write output to a file instead of stdout")

    r.add_argument("--trace", action="store_true", help="Emit per-node trace events as JSON lines to stderr")
    r.add_argument("--trace-file", help="Write trace events (JSONL) to the given file")

    r.add_argument("--debug", action="store_true", help="Show full tracebacks on error")

    r.set_defaults(func=cmd_render)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

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
