from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class IncludeResult:
    """Resolved include content and identity.

    `content` semantics:

    - `None`   -> target was not found (missing)
    - `""`     -> target was found and is an empty file (valid)
    - nonempty -> target was found and contains YAML text
    """

    content: str | None
    source_name: str
    key: str


class IncludeResolver(Protocol):
    def resolve(self, target: str, *, from_source: Optional[str] = None) -> IncludeResult:
        """Resolve an include target into YAML content.

        `from_source` is a best-effort source identifier for relative resolution.
        """

        ...


class FileIncludeResolver:
    """A simple filesystem include resolver.

    - If `target` is an absolute path, it is used as-is.
    - If `target` is relative and `from_source` is a filesystem path, resolve relative to its directory.
    - Otherwise, search `search_paths` in order.

    Security note: this is not a sandbox; treat templates as trusted.
    """

    def __init__(
        self,
        *,
        search_paths: Optional[Sequence[str | Path]] = None,
        encoding: str = "utf-8",
        cache: bool = False,
        cache_max: Optional[int] = None,
    ):
        self.search_paths = [Path(p) for p in (search_paths or [])]
        self.encoding = encoding

        # Optional in-resolver caching. This caches both hits and misses.
        #
        # Note: this is an LRU-ish cache using insertion order.
        self.cache = cache
        self.cache_max = cache_max
        self._cache: "OrderedDict[tuple[str, str | None], IncludeResult]" = OrderedDict()

    def resolve(self, target: str, *, from_source: Optional[str] = None) -> IncludeResult:
        cache_key = (target, from_source)
        if self.cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                # LRU: bump to end
                self._cache.pop(cache_key, None)
                self._cache[cache_key] = cached
                return cached

        t = Path(target)

        candidates: list[Path] = []
        if t.is_absolute():
            candidates.append(t)
        else:
            if from_source:
                try:
                    fs = Path(from_source)
                    # Heuristic: treat it as path-like if it exists or looks like a filename.
                    if fs.exists() or fs.suffix:
                        candidates.append(fs.parent / t)
                except Exception:
                    pass
            for sp in self.search_paths:
                candidates.append(sp / t)

        for cand in candidates:
            try:
                p = cand.resolve()
            except Exception:
                p = cand

            if p.exists() and p.is_file():
                content = p.read_text(encoding=self.encoding)
                res = IncludeResult(content=content, source_name=str(p), key=str(p))
                if self.cache:
                    self._cache[cache_key] = res
                    if self.cache_max is not None and self.cache_max > 0:
                        while len(self._cache) > self.cache_max:
                            self._cache.popitem(last=False)
                return res

        # Nothing resolved.
        # Use the original target as key/name for diagnostics.
        res = IncludeResult(content=None, source_name=str(target), key=str(target))
        if self.cache:
            self._cache[cache_key] = res
            if self.cache_max is not None and self.cache_max > 0:
                while len(self._cache) > self.cache_max:
                    self._cache.popitem(last=False)
        return res
