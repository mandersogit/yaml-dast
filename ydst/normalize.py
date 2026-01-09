from __future__ import annotations

from typing import Any

from .nodes import OMIT, Omit


_JSON_KEY_TYPES = (str, int, float, bool, type(None))


def to_jsonable(obj: Any) -> Any:
    """Best-effort conversion to JSON-serializable structures.

    This helper is intended for downstream tooling (CLIs, API responses, etc.) that
    need to serialize rendered output.

    Conversions performed
    ---------------------
    - `OMIT` / `!omit` -> `None`
    - `set` -> stable `list` (sorted by repr for determinism)
    - dict keys that are not valid JSON key types -> `str(key)`
    """

    if obj is OMIT or isinstance(obj, Omit):
        return None

    if isinstance(obj, dict):
        out: dict[Any, Any] = {}
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
