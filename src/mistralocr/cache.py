"""
Simple file-based cache for OCR results.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class OCRCache:
    """File-based cache for OCR results using content hash."""

    def __init__(self, cache_dir: Optional[str] = None, ttl_hours: int = 24 * 7):
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "mistralocr"
        self.ttl = timedelta(hours=ttl_hours)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _hash_content(self, data: str, namespace: str = "") -> str:
        """Generate hash from base64 content plus an optional namespace (cache version/options)."""
        h = hashlib.sha256()
        if namespace:
            h.update(namespace.encode("utf-8"))
            h.update(b"\0")
        h.update(data.encode("utf-8"))
        return h.hexdigest()[:16]

    def _cache_path(self, content_hash: str) -> Path:
        return self.cache_dir / f"{content_hash}.json"

    def get(self, base64_data: str, namespace: str = "") -> Optional[dict]:
        """Get cached result if exists and not expired."""
        try:
            content_hash = self._hash_content(base64_data, namespace=namespace)
            cache_file = self._cache_path(content_hash)

            if not cache_file.exists():
                return None

            data = json.loads(cache_file.read_text(encoding="utf-8"))
            cached_at_raw = data.get("_cached_at")
            cached_at = datetime.fromisoformat(cached_at_raw) if cached_at_raw else None
            if not cached_at:
                cache_file.unlink(missing_ok=True)
                return None

            if datetime.now() - cached_at > self.ttl:
                cache_file.unlink(missing_ok=True)
                return None

            logger.info(f"Cache hit: {content_hash}")
            return data.get("result")
        except Exception:
            try:
                cache_file.unlink(missing_ok=True)  # type: ignore[name-defined]
            except Exception:
                pass
            return None

    def set(self, base64_data: str, result: dict, namespace: str = "") -> None:
        """Cache OCR result."""
        try:
            content_hash = self._hash_content(base64_data, namespace=namespace)
            cache_file = self._cache_path(content_hash)
            cache_file.write_text(
                json.dumps(
                    {
                        "_cached_at": datetime.now().isoformat(),
                        "_namespace": namespace,
                        "result": result,
                    }
                ),
                encoding="utf-8",
            )
            logger.info(f"Cached: {content_hash}")
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")

    def clear(self) -> int:
        """Clear all cache files. Returns count of deleted files."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink(missing_ok=True)
            count += 1
        return count

    def prune(self) -> dict:
        """Delete expired cache files based on file mtime and TTL."""
        now = datetime.now()
        deleted = 0
        remaining = 0
        for f in self.cache_dir.glob("*.json"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if now - mtime > self.ttl:
                    f.unlink(missing_ok=True)
                    deleted += 1
                else:
                    remaining += 1
            except Exception:
                try:
                    f.unlink(missing_ok=True)
                    deleted += 1
                except Exception:
                    pass
        return {"deleted": deleted, "remaining": remaining, "cache_dir": str(self.cache_dir)}

    def stats(self) -> dict:
        """Return basic cache stats without reading contents."""
        count = 0
        total_bytes = 0
        oldest_mtime: Optional[float] = None
        newest_mtime: Optional[float] = None
        for f in self.cache_dir.glob("*.json"):
            try:
                st = f.stat()
            except Exception:
                continue
            count += 1
            total_bytes += st.st_size
            oldest_mtime = st.st_mtime if oldest_mtime is None else min(oldest_mtime, st.st_mtime)
            newest_mtime = st.st_mtime if newest_mtime is None else max(newest_mtime, st.st_mtime)

        return {
            "cache_dir": str(self.cache_dir),
            "entries": count,
            "total_bytes": total_bytes,
            "ttl_seconds": int(self.ttl.total_seconds()),
            "oldest_mtime": datetime.fromtimestamp(oldest_mtime).isoformat() if oldest_mtime else None,
            "newest_mtime": datetime.fromtimestamp(newest_mtime).isoformat() if newest_mtime else None,
        }
