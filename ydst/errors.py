from __future__ import annotations

import collections.abc as _abc
import dataclasses as _dataclasses
import typing as _typing

import ydst.nodes as nodes


def format_path(path: _abc.Sequence[_typing.Any]) -> str:
    """Format a render/load path into a JSONPath-like string.

    Rules:
      - root is `$`
      - integer segments use `[idx]`
      - string identifier segments use dotted form (`.name`)
      - everything else uses bracketed repr (`[{repr(key)}]`)

    We intentionally only use dotted notation for *actual strings* to avoid
    surprising output for keys like None ("None" isidentifier -> `$.None`).
    """
    if not path:
        return "$"  # root

    parts: list[str] = ["$"]
    for p in path:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        elif isinstance(p, str) and p.isidentifier():
            parts.append(f".{p}")
        else:
            parts.append(f"[{p!r}]")
    return "".join(parts)


def format_mark(mark: nodes.SourceMark | None) -> str:
    if not mark:
        return "<unknown>"
    if mark.source is None and mark.line is None and mark.column is None:
        return "<unknown>"
    src = mark.source or "<unknown>"
    if mark.line is None or mark.column is None:
        return src
    return f"{src}:{mark.line}:{mark.column}"


class YdstError(Exception):
    """Base error for the library."""


@_dataclasses.dataclass
class ErrorContext:
    path: tuple[_typing.Any, ...] = ()
    mark: nodes.SourceMark | None = None
    node_type: str | None = None


class ContextualError(YdstError):
    """Base class for errors that carry an :class:`ErrorContext`.

    This centralizes formatting logic so `TemplateLoadError`, `TemplateValidationError`,
    and `RenderError` remain consistent.
    """

    def __init__(self, message: str, *, ctx: ErrorContext | None = None, cause: Exception | None = None):
        super().__init__(message)
        self.ctx = ctx or ErrorContext()
        if cause is not None:
            self.__cause__ = cause

    def pretty(self) -> str:
        p = format_path(self.ctx.path)
        m = format_mark(self.ctx.mark)
        n = self.ctx.node_type or "<node>"
        return f"{self.__class__.__name__}: {self.args[0]} (path={p}, node={n}, at={m})"

    def __str__(self) -> str:
        return self.pretty()


class TemplateLoadError(ContextualError):
    """Errors raised while parsing/loading templates."""


class TemplateValidationError(ContextualError):
    """Errors raised by static template validation."""


class RenderError(ContextualError):
    """Runtime rendering error."""


class MissingVariableError(RenderError):
    """A required variable (e.g. !var required=true) was missing at render time."""


class RootOmitError(RenderError):
    """The template rendered to OMIT at the document root, which is not allowed."""


class ExpressionError(RenderError):
    """An error occurred evaluating a !expr."""


class FunctionNotFoundError(RenderError):
    """A function name could not be resolved in a registry."""


class FunctionCallError(RenderError):
    """A registry function raised an exception during execution."""


class IncludeError(RenderError):
    """An include operation failed."""


class IncludeCycleError(IncludeError):
    """A cycle was detected in includes."""


class PythonError(RenderError):
    """An error occurred executing a !python / !python_module block."""


class PythonEmitError(PythonError):
    """A !python block completed without emitting a value (strict emit mode)."""
