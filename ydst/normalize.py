from __future__ import annotations

import typing as _typing

import ydst.nodes as nodes


_JSON_KEY_TYPES = (str, int, float, bool, type(None))


def to_jsonable(obj: _typing.Any) -> _typing.Any:
    """Best-effort conversion to JSON-serializable structures.

    This helper is intended for downstream tooling (CLIs, API responses, etc.) that
    need to serialize rendered output.

    Conversions performed
    ---------------------
    - `OMIT` / `!omit` -> `None`
    - `set` -> stable `list` (sorted by repr for determinism)
    - dict keys that are not valid JSON key types -> `str(key)`
    """

    if obj is nodes.OMIT or isinstance(obj, nodes.Omit):
        return None

    if isinstance(obj, dict):
        out: dict[_typing.Any, _typing.Any] = {}
        for k, v in obj.items():
            kk = k if isinstance(k, _JSON_KEY_TYPES) else str(k)
            out[kk] = to_jsonable(v)
        return out

    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]

    if isinstance(obj, set):
        items = [to_jsonable(v) for v in obj]
        return sorted(items, key=lambda x: repr(x))

    return obj
