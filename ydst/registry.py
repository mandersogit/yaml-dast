from __future__ import annotations

import dataclasses as _dataclasses
import json as _json
import os as _os
import re as _re
import typing as _typing
import collections.abc as _abc

import ydst.nodes as nodes


class FunctionRegistry(_typing.Protocol):
    """Protocol for resolving function names.

    The core contract is intentionally small: only `.get(name)` is required.

    Some registry implementations also provide an optional `.keys()` for
    introspection. ydst does not rely on `.keys()` for correctness.

    Note
    ----
    The return type is `object | None` (not strictly Callable) because:
      - user registries may store non-callables, and ydst checks `callable(...)`
      - python-module overlays may store constants alongside helper functions
    """

    def get(self, name: str) -> object | None: ...


@_dataclasses.dataclass(slots=True)
class DictFunctionRegistry(FunctionRegistry):
    functions: dict[str, object]

    def get(self, name: str) -> object | None:
        return self.functions.get(name)

    def keys(self) -> _abc.Iterable[str]:
        return self.functions.keys()


def chain_registries(*registries: FunctionRegistry) -> FunctionRegistry:
    """Return a registry that resolves names from the first registry that contains them.

    The chained registry only requires that each input registry implements `.get(name)`.

    If one or more underlying registries provide a `.keys()` method, the chained registry
    exposes a `.keys()` generator that yields the union of those keys.
    """

    class _Chained(FunctionRegistry):
        def get(self, name: str) -> object | None:
            for r in registries:
                fn = r.get(name)
                if fn is not None:
                    return fn
            return None

        def keys(self) -> _abc.Iterable[str]:  # pragma: no cover (optional API)
            seen: set[str] = set()
            for r in registries:
                keys = getattr(r, "keys", None)
                if callable(keys):
                    try:
                        for k in keys():
                            if k not in seen:
                                seen.add(k)
                                yield k
                    except Exception:
                        # Do not allow a misbehaving registry to break callers.
                        continue

    return _Chained()


def _parse_path(path: _typing.Any) -> list[_typing.Any]:
    if isinstance(path, (list, tuple)):
        return list(path)
    if isinstance(path, str):
        # dot-separated path; allow escaping dots with backslash
        # e.g. "a.b" -> ["a","b"], "a\.b.c" -> ["a.b","c"]
        parts: list[str] = []
        cur: list[str] = []
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


def get_in(obj: _typing.Any, path: _typing.Any, default: _typing.Any = None) -> _typing.Any:
    """Get a nested value from dict/list-like objects.

    `path` may be:
      - list/tuple of keys/indices
      - dot-separated string path (\\-escaped dots supported)

    Resolution order for each step:
      1) mapping key lookup
      2) sequence integer index
      3) attribute lookup

    This helper is convenience-oriented; it returns `default` on failures.
    """

    cur = obj
    for key in _parse_path(path):
        if cur is None:
            return default
        try:
            if isinstance(cur, _abc.Mapping) and key in cur:
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


def coalesce(*values: _typing.Any, default: _typing.Any = None) -> _typing.Any:
    """Return the first value that is neither OMIT nor None; else `default`."""

    for v in values:
        if v is nodes.OMIT or isinstance(v, nodes.Omit):
            continue
        if v is None:
            continue
        return v
    return default


_slug_re = _re.compile(r"[^a-z0-9]+")


def slugify(value: _typing.Any, *, max_len: int | None = None) -> str:
    s = str(value).strip().lower()
    s = _slug_re.sub("-", s).strip("-")
    if max_len is not None and max_len >= 0:
        s = s[:max_len]
    return s


def env(name: str, default: _typing.Any = None) -> _typing.Any:
    return _os.environ.get(name, default)


def to_int(value: _typing.Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except Exception:
        return default


def to_float(value: _typing.Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except Exception:
        return default


def json_dumps(value: _typing.Any, *, sort_keys: bool = True) -> str:
    return _json.dumps(value, sort_keys=sort_keys)


def default_registry() -> DictFunctionRegistry:
    """Default built-in registry (safe-by-default tier).

    This is *not* enabled automatically; callers must opt in.

    In ydst 0.2.0+, `default_registry()` is intentionally conservative and is
    equivalent to :func:`safe_registry`.

    If you need environment access (`env`) or other extended helpers, use
    :func:`extended_registry`.
    """

    return safe_registry()


# ---------------------------------------------------------------------------
# Registry "tiers" (optional)
# ---------------------------------------------------------------------------


def minimal_registry() -> DictFunctionRegistry:
    """A minimal built-in registry containing pure data helpers.

    This registry intentionally excludes environment access and general-purpose builtins.
    """

    funcs: dict[str, object] = {
        "get_in": get_in,
        "coalesce": coalesce,
        "slugify": slugify,
        "to_int": to_int,
        "to_float": to_float,
    }
    return DictFunctionRegistry(funcs)


def safe_registry() -> DictFunctionRegistry:
    """A safer-by-default registry.

    Includes the minimal helpers plus a small set of explicit, non-I/O builtins.

    Notes
    -----
    - This still isn't a sandbox; it is simply a curated set of helpers.
    - If you need env() / I/O-like access, use extended_registry() explicitly.
    """

    funcs: dict[str, object] = {
        **minimal_registry().functions,
        # Aggregation / ordering
        "len": len,
        "min": min,
        "max": max,
        "sum": sum,
        "sorted": sorted,
        # Type / basic numeric helpers
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "round": round,
        "abs": abs,
        # Encoding
        "json_dumps": json_dumps,
    }
    return DictFunctionRegistry(funcs)



def extended_registry() -> DictFunctionRegistry:
    """An extended registry including environment access.

    This is appropriate for trusted templates only.
    """

    funcs: dict[str, object] = {
        **safe_registry().functions,
        "env": env,
    }
    return DictFunctionRegistry(funcs)
