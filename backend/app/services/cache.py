"""Simple TTL filesystem cache (replaceable with Redis later)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

_LOG = logging.getLogger("echoshield.cache")

_SAFE_KEY_RE = re.compile(r"[^a-zA-Z0-9._-]+")


class FileCache:
    """JSON-file cache with TTL, deterministic keys and size-aware pruning."""

    def __init__(self, directory: Path | str, ttl_seconds: int = 3600) -> None:
        self.directory = Path(directory)
        self.ttl_seconds = ttl_seconds

    # -- key handling --------------------------------------------------------

    @staticmethod
    def make_key(prefix: str, payload: Any) -> str:
        canonical = json.dumps(payload, sort_keys=True, default=str)
        digest = hashlib.sha256(canonical.encode()).hexdigest()[:24]
        safe_prefix = _SAFE_KEY_RE.sub("_", prefix)[:40]
        return f"{safe_prefix}-{digest}"

    def _path_for(self, key: str) -> Path:
        safe = _SAFE_KEY_RE.sub("_", key)
        return self.directory / f"{safe}.json"

    # -- core operations -----------------------------------------------------

    def get(self, key: str) -> Any | None:
        path = self._path_for(key)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        stored_at = float(record.get("stored_at", 0))
        if time.time() - stored_at > self.ttl_seconds:
            path.unlink(missing_ok=True)
            return None
        return record.get("value")

    def set(self, key: str, value: Any) -> None:
        self.prune_if_needed()
        path = self._path_for(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"stored_at": time.time(), "value": value}, default=str),
                encoding="utf-8",
            )
        except (OSError, TypeError, ValueError):
            _LOG.debug("cache_write_failed key=%s", key, exc_info=True)

    def get_or_set(self, key: str, producer: Callable[[], Any]) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = producer()
        self.set(key, value)
        return value

    def invalidate(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)

    def clear(self) -> None:
        if self.directory.is_dir():
            for entry in self.directory.glob("*.json"):
                entry.unlink(missing_ok=True)

    def prune_if_needed(self, max_total_bytes: int = 256 * 1024 * 1024) -> None:
        """Delete oldest entries when the cache exceeds ``max_total_bytes``."""
        if not self.directory.is_dir():
            return
        entries = sorted(self.directory.glob("*.json"), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in entries)
        for entry in entries:
            if total <= max_total_bytes:
                break
            size = entry.stat().st_size
            entry.unlink(missing_ok=True)
            total -= size
