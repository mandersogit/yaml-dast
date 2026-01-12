from __future__ import annotations

import argparse as _argparse
import dataclasses as _dataclasses
import json as _json
import pathlib as _pathlib
import sys as _sys
import traceback as _traceback
import typing as _typing

import yaml as _yaml

import ydst.analysis as analysis_mod
import ydst.engine as engine_mod
import ydst.errors as errors_mod
import ydst.include as include_mod
import ydst.normalize as normalize_mod
import ydst.registry as registry_mod
import ydst.render as render_mod
import ydst.template as template_mod
import ydst.validate as validate_mod


def _load_template(engine: engine_mod.TemplateEngine, template_arg: str) -> template_mod.Template:
    if template_arg == "-":
        text = _sys.stdin.read()
        return engine.load_template_text(text, source_name="<stdin>")
    return engine.load_template_path(template_arg)


def _load_json_context(args: _argparse.Namespace) -> dict[str, _typing.Any]:
    if args.context_file:
        with open(args.context_file, "r", encoding="utf-8") as f:
            return _json.load(f)

    if args.context_json:
        return _json.loads(args.context_json)

    return {}


def _make_engine(args: _argparse.Namespace) -> engine_mod.TemplateEngine:
    include_paths = [str(_pathlib.Path(p)) for p in (args.include_path or [])]
    include_resolver = None
    if include_paths:
        include_resolver = include_mod.FileIncludeResolver(
            search_paths=include_paths,
            allow_absolute=not args.include_disallow_absolute,
            enforce_roots=args.include_enforce_roots,
            max_bytes=1_000_000,
            cache=True,
            cache_max=256,
        )

    base_loader: type[_yaml.Loader] = _yaml.SafeLoader  # type: ignore[assignment]
    if args.full_loader:
        base_loader = _yaml.FullLoader  # type: ignore[assignment]

    return engine_mod.TemplateEngine(
        include_resolver=include_resolver,
        base_loader=base_loader,
        max_include_depth=args.max_include_depth,
        allow_load_time_includes=not args.disable_load_includes,
    )


def _truncate_repr(obj: _typing.Any, max_len: int = 200) -> str:
    try:
        s = repr(obj)
    except Exception:
        s = f"<{type(obj).__name__}>"
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _trace_sink(fp: _typing.TextIO) -> render_mod.TraceSink:
    def sink(ev: render_mod.TraceEvent) -> None:
        record = {
            "path": errors_mod.format_path(ev.path),
            "node_type": ev.node_type,
            "mark": errors_mod.format_mark(ev.mark),
            "before": _truncate_repr(ev.before),
            "after": _truncate_repr(ev.after),
        }
        fp.write(_json.dumps(record))
        fp.write("\n")
        fp.flush()

    return sink


def cmd_render(args: _argparse.Namespace) -> None:
    engine = _make_engine(args)

    template = _load_template(engine, args.template)
    context = _load_json_context(args)

    registry = None
    if args.registry_tier == "minimal":
        registry = registry_mod.minimal_registry()
    elif args.registry_tier == "safe":
        registry = registry_mod.safe_registry()
    elif args.registry_tier == "extended":
        registry = registry_mod.extended_registry()
    elif args.registry_tier == "none":
        registry = None
    else:
        raise ValueError(f"Unknown registry tier: {args.registry_tier!r}")

    trace_fp: _typing.TextIO | None = None
    trace_sink: render_mod.TraceSink | None = None
    if args.trace:
        trace_fp = _sys.stderr
        if args.trace_file:
            trace_fp = open(args.trace_file, "w", encoding="utf-8")  # noqa: SIM115
        assert trace_fp is not None  # guaranteed by control flow
        trace_sink = _trace_sink(trace_fp)

    try:
        options = render_mod.RenderOptions(
            mode=args.mode,
            strict=not args.non_strict,
            dict_key_conflict=args.dict_key_conflict,
            strict_pipe_stages=(args.pipe_unknown == "error"),
            allow_callable_pipe_stages=args.callable_pipe_stages,
            allow_pipe_registry_calls=not args.no_pipe_registry_calls,
            wrap_exceptions=not args.raw_exceptions,
            max_depth=args.max_depth,
            max_nodes=args.max_nodes,
            allow_python=args.allow_python,
            allow_python_module=args.allow_python_module,
            python_strict_emit=args.python_strict_emit,
            trace=trace_sink,
        )

        out = template.render(context=context, registry=registry, options=options)
    finally:
        if args.trace and trace_fp is not None and trace_fp is not _sys.stderr:
            trace_fp.close()

    if args.output == "yaml":
        payload = out
        dump = _yaml.safe_dump(payload, sort_keys=False)
    else:
        payload = normalize_mod.to_jsonable(out)
        dump = _json.dumps(payload, indent=2, sort_keys=False)

    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            f.write(dump)
            f.write("\n")
    else:
        _sys.stdout.write(dump)
        _sys.stdout.write("\n")


def cmd_validate(args: _argparse.Namespace) -> None:
    engine = _make_engine(args)
    template = _load_template(engine, args.template)

    options = render_mod.RenderOptions(
        mode=args.mode,
        strict=not args.non_strict,
        allow_python=args.allow_python,
        allow_python_module=args.allow_python_module,
    )

    validate_mod.validate_template(template, options=options)

    if not args.quiet:
        _sys.stdout.write("OK\n")


def cmd_deps(args: _argparse.Namespace) -> None:
    engine = _make_engine(args)
    template = _load_template(engine, args.template)

    registry = None
    if args.registry_tier == "minimal":
        registry = registry_mod.minimal_registry()
    elif args.registry_tier == "safe":
        registry = registry_mod.safe_registry()
    elif args.registry_tier == "extended":
        registry = registry_mod.extended_registry()
    elif args.registry_tier == "none":
        registry = None
    else:
        raise ValueError(f"Unknown registry tier: {args.registry_tier!r}")

    deps = analysis_mod.analyze_dependencies(template, registry=registry)
    payload = _dataclasses.asdict(deps)
    dump = _json.dumps(payload, indent=2, sort_keys=True)

    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            f.write(dump)
            f.write("\n")
    else:
        _sys.stdout.write(dump)
        _sys.stdout.write("\n")


def _add_engine_flags(p: _argparse.ArgumentParser) -> None:
    p.add_argument(
        "--include-path",
        action="append",
        default=[],
        help="Add a directory to the runtime include search path (may be specified multiple times)",
    )
    p.add_argument(
        "--include-disallow-absolute",
        action="store_true",
        help="Disallow absolute paths in runtime includes",
    )
    p.add_argument(
        "--include-enforce-roots",
        action="store_true",
        help="Require runtime include targets to resolve within the include search roots",
    )
    p.add_argument(
        "--full-loader",
        action="store_true",
        help="Use PyYAML FullLoader (default is SafeLoader)",
    )
    p.add_argument(
        "--disable-load-includes",
        action="store_true",
        help="Disable load-time !include expansion",
    )
    p.add_argument(
        "--max-include-depth",
        type=int,
        default=20,
        help="Maximum include depth (load-time includes)",
    )


def build_parser() -> _argparse.ArgumentParser:
    p = _argparse.ArgumentParser(prog="ydst", description="YAML data-structure templates.")
    sub = p.add_subparsers(dest="cmd", required=True)

    # -----------------
    # render
    # -----------------
    r = sub.add_parser("render", help="Render a template")
    r.add_argument("template", help="Template file path, or '-' for stdin")

    ctx_group = r.add_mutually_exclusive_group()
    ctx_group.add_argument("--context-file", help="Path to JSON context file")
    ctx_group.add_argument("--context-json", help="Inline JSON context string")

    r.add_argument(
        "--registry-tier",
        choices=["none", "minimal", "safe", "extended"],
        default="safe",
        help="Registry tier for !call / !pipe / !expr function calls",
    )

    _add_engine_flags(r)

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

    # Power tags (disabled by default)
    r.add_argument("--allow-python", action="store_true", help="Enable !python (trusted templates only)")
    r.add_argument("--allow-python-module", action="store_true", help="Enable !python_module (trusted templates only)")
    r.add_argument(
        "--python-strict-emit",
        action="store_true",
        help="Require explicit emit(...) inside every !python block",
    )

    r.add_argument("--raw-exceptions", action="store_true", help="Do not wrap exceptions (debugging)")
    r.add_argument("--max-depth", type=int, default=200)
    r.add_argument("--max-nodes", type=int, default=None)

    r.add_argument("--output", choices=["json", "yaml"], default="json")
    r.add_argument("--output-file", help="Write output to a file instead of stdout")

    r.add_argument("--trace", action="store_true", help="Emit per-node trace events as JSON lines")
    r.add_argument("--trace-file", help="Write trace events (JSONL) to the given file")

    r.add_argument("--debug", action="store_true", help="Show full tracebacks on error")
    r.set_defaults(func=cmd_render)

    # -----------------
    # validate
    # -----------------
    v = sub.add_parser("validate", help="Parse and validate a template")
    v.add_argument("template", help="Template file path, or '-' for stdin")
    _add_engine_flags(v)
    v.add_argument("--mode", choices=["trusted", "expr_safe", "locked_down"], default="trusted")
    v.add_argument("--non-strict", action="store_true", help="Non-strict mode (missing vars -> None/defaults)")
    v.add_argument("--quiet", action="store_true", help="Only set exit code; do not print 'OK'")

    v.add_argument("--allow-python", action="store_true", help="Allow !python")
    v.add_argument("--allow-python-module", action="store_true", help="Allow !python_module")

    v.add_argument("--debug", action="store_true", help="Show full tracebacks on error")
    v.set_defaults(func=cmd_validate)

    # -----------------
    # deps
    # -----------------
    d = sub.add_parser("deps", help="Analyze a template's static dependencies")
    d.add_argument("template", help="Template file path, or '-' for stdin")
    _add_engine_flags(d)
    d.add_argument(
        "--registry-tier",
        choices=["none", "minimal", "safe", "extended"],
        default="safe",
        help="Registry tier for dependency analysis",
    )
    d.add_argument("--output-file", help="Write output to a file instead of stdout")
    d.add_argument("--debug", action="store_true", help="Show full tracebacks on error")
    d.set_defaults(func=cmd_deps)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        args.func(args)  # type: ignore[misc]
        return 0
    except errors_mod.YdstError as e:
        _sys.stderr.write(str(e))
        _sys.stderr.write("\n")
        if getattr(args, "debug", False):
            _traceback.print_exc()
        return 2
    except Exception as e:
        _sys.stderr.write(f"Error: {e}\n")
        if getattr(args, "debug", False):
            _traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
