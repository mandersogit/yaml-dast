from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

from .nodes import SourceMark


def format_path(path: Sequence[Any]) -> str:
    if not path:
        return "$"  # root
    parts: list[str] = ["$"]

    for p in path:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        else:
            # dotted if safe identifier, bracketed otherwise
            s = str(p)
            if s and s.isidentifier():
                parts.append(f".{s}")
            else:
                parts.append(f"[{s!r}]")
    return "".join(parts)


def format_mark(mark: Optional[SourceMark]) -> str:
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

    pass


@dataclass
class ErrorContext:
    path: Tuple[Any, ...] = ()
    mark: Optional[SourceMark] = None
    node_type: Optional[str] = None


class TemplateLoadError(YdstError):
    def __init__(self, message: str, *, ctx: Optional[ErrorContext] = None, cause: Exception | None = None):
        super().__init__(message)
        self.ctx = ctx or ErrorContext()
        if cause is not None:
            self.__cause__ = cause


class TemplateValidationError(YdstError):
    def __init__(self, message: str, *, ctx: Optional[ErrorContext] = None, cause: Exception | None = None):
        super().__init__(message)
        self.ctx = ctx or ErrorContext()
        if cause is not None:
            self.__cause__ = cause


class RenderError(YdstError):
    def __init__(self, message: str, *, ctx: Optional[ErrorContext] = None, cause: Exception | None = None):
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
        # Prefer the contextualized form; keep the raw message in `.args[0]`.
        return self.pretty()


class MissingVariableError(RenderError):
    pass


class RootOmitError(RenderError):
    pass


class ExpressionError(RenderError):
    pass


class FunctionNotFoundError(RenderError):
    pass


class FunctionCallError(RenderError):
    pass


class IncludeError(RenderError):
    pass


class IncludeCycleError(IncludeError):
    pass
