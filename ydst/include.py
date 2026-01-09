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
    """Filesystem include resolver.

    Resolution algorithm
    -------------------
    - If `target` is absolute, it is used as-is.
    - If `target` is relative and `from_source` is a filesystem path, resolve relative to its directory.
    - Otherwise, search `search_paths` in order.

    Optional hardening
    ------------------
    `allow_absolute=False` disallows absolute include targets.

    `enforce_roots=True` requires the resolved path to be under one of the configured roots.
    This can help prevent ".." traversal and symlink escapes.

    Notes
    -----
    - This is still not a security sandbox.
    - Missing targets return `IncludeResult(content=None, ...)`.
    """

    def __init__(
        self,
        *,
        search_paths: Optional[Sequence[str | Path]] = None,
        encoding: str = "utf-8",
        cache: bool = False,
        cache_max: Optional[int] = None,
        allow_absolute: bool = True,
        enforce_roots: bool = False,
        roots: Optional[Sequence[str | Path]] = None,
    ):
        self.search_paths = [Path(p) for p in (search_paths or [])]
        self.encoding = encoding

        self.allow_absolute = allow_absolute
        self.enforce_roots = enforce_roots

        # If roots are not provided, default to search_paths.
        roots_seq = list(roots) if roots is not None else list(self.search_paths)
        self.roots = [Path(p).resolve() for p in roots_seq]

        if self.enforce_roots and not self.roots:
            raise ValueError("enforce_roots=True requires at least one root (pass roots=... or search_paths=...)")

        # Optional in-resolver caching. This caches both hits and misses.
        # Note: this is an LRU-ish cache using insertion order.
        self.cache = cache
        self.cache_max = cache_max
        self._cache: "OrderedDict[tuple[str, str | None], IncludeResult]" = OrderedDict()

    def _check_roots(self, resolved_path: Path) -> None:
        if not self.enforce_roots:
            return

        for root in self.roots:
            try:
                if resolved_path.is_relative_to(root):
                    return
            except Exception:
                # Older/edge Path implementations; fall back to string prefix.
                try:
                    rp = str(resolved_path)
                    rr = str(root)
                    if rp.startswith(rr.rstrip("/") + "/") or rp == rr:
                        return
                except Exception:
                    pass

        roots_str = ", ".join(str(r) for r in self.roots)
        raise ValueError(f"Resolved include path is outside allowed roots: {resolved_path} (roots: {roots_str})")

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
            if not self.allow_absolute:
                raise ValueError(f"Absolute include targets are disallowed: {target!r}")
            candidates.append(t)
        else:
            if from_source:
                try:
                    fs = Path(from_source)
                    # Heuristic: treat it as path-like if it exists or looks like a filename.
                    if fs.is_absolute() or fs.exists() or len(fs.parts) > 1:
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
                # Optional hardening.
                self._check_roots(p)
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