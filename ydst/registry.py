from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Protocol, Sequence

from .nodes import OMIT, Omit


class FunctionRegistry(Protocol):
    def get(self, name: str) -> Optional[Callable[..., Any]]: ...


@dataclass
class DictFunctionRegistry(FunctionRegistry):
    functions: Dict[str, Callable[..., Any]]

    def get(self, name: str) -> Optional[Callable[..., Any]]:
        return self.functions.get(name)

    def keys(self) -> Iterable[str]:
        return self.functions.keys()


def chain_registries(*registries: FunctionRegistry) -> FunctionRegistry:
    """Return a registry that resolves names from the first registry that contains them."""

    class _Chained(FunctionRegistry):
        def get(self, name: str) -> Optional[Callable[..., Any]]:
            for r in registries:
                fn = r.get(name)
                if fn is not None:
                    return fn
            return None

    return _Chained()


def _parse_path(path: Any) -> list[Any]:
    if isinstance(path, (list, tuple)):
        return list(path)
    if isinstance(path, str):
        # dot-separated path; allow escaping dots with backslash
        # e.g. "a.b" -> ["a","b"], "a\.b.c" -> ["a.b","c"]
        parts: list[str] = []
        cur = []
        esc = False
        for ch in path:
            if esc:
                cur.append(ch)
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == ".":
                parts.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
        parts.append("".join(cur))
        return parts
    return [path]


def get_in(obj: Any, path: Any, default: Any = None) -> Any:
    """Get a nested value from dict/list-like objects.

    `path` may be:
      - list/tuple of keys/indices
      - dot-separated string path (\-escaped dots supported)

    For mappings: uses key lookup.
    For sequences: uses integer indices when possible.
    For objects: uses getattr fallback.
    """
    cur = obj
    for key in _parse_path(path):
        if cur is None:
            return default
        try:
            if isinstance(cur, Mapping) and key in cur:
                cur = cur[key]
                continue
            # integer index for sequences
            if isinstance(cur, (list, tuple)) and isinstance(key, str) and key.isdigit():
                cur = cur[int(key)]
                continue
            if isinstance(cur, (list, tuple)) and isinstance(key, int):
                cur = cur[key]
                continue
            # attribute fallback
            if isinstance(key, str) and hasattr(cur, key):
                cur = getattr(cur, key)
                continue
            return default
        except Exception:
            return default
    return cur


def coalesce(*values: Any, default: Any = None) -> Any:
    """Return the first value that is neither OMIT nor None; else `default`."""
    for v in values:
        if v is OMIT or isinstance(v, Omit):
            continue
        if v is None:
            continue
        return v
    return default


_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(value: Any, *, max_len: int | None = None) -> str:
    s = str(value).strip().lower()
    s = _slug_re.sub("-", s).strip("-")
    if max_len is not None and max_len >= 0:
        s = s[:max_len]
    return s


def env(name: str, default: Any = None) -> Any:
    return os.environ.get(name, default)


def to_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except Exception:
        return default


def to_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except Exception:
        return default


def json_dumps(value: Any, *, sort_keys: bool = True) -> str:
    return json.dumps(value, sort_keys=sort_keys)


def default_registry() -> DictFunctionRegistry:
    """An optional built-in registry for convenience.

    This is *not* enabled automatically; callers must opt in.
    """
    funcs: Dict[str, Callable[..., Any]] = {
        # basic helpers
        "get_in": get_in,
        "coalesce": coalesce,
        "slugify": slugify,
        "env": env,
        "to_int": to_int,
        "to_float": to_float,
        "json_dumps": json_dumps,
        # common safe builtins (explicitly listed)
        "len": len,
        "min": min,
        "max": max,
        "sum": sum,
        "sorted": sorted,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "round": round,
        "abs": abs,
    }
    return DictFunctionRegistry(funcs)
