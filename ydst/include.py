from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class IncludeResult:
    """Resolved include content and identity."""

    content: str
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

    def __init__(self, *, search_paths: Optional[Sequence[str | Path]] = None, encoding: str = "utf-8"):
        self.search_paths = [Path(p) for p in (search_paths or [])]
        self.encoding = encoding

    def resolve(self, target: str, *, from_source: Optional[str] = None) -> IncludeResult:
        t = Path(target)

        candidates: list[Path] = []
        if t.is_absolute():
            candidates.append(t)
        else:
            if from_source:
                try:
                    fs = Path(from_source)
                    if fs.exists() or fs.suffix:  # heuristic: treat as path-like
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
                return IncludeResult(content=content, source_name=str(p), key=str(p))

        # If we got here, nothing resolved.
        # Use the original target as key/name for diagnostics.
        return IncludeResult(content="", source_name=str(target), key=str(target))
