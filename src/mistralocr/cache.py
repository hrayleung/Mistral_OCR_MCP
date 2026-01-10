"""
Simple file-based cache for OCR results with in-memory LRU layer.
"""

import copy
import hashlib
import json
import logging
import os
import threading
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Chunk size for hashing large documents (64KB)
HASH_CHUNK_SIZE = 65536


class LRUCache:
    """Thread-safe in-memory LRU cache."""

    def __init__(self, maxsize: int = 50):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._maxsize = maxsize
        self._lock = threading.Lock()

    def __len__(self) -> int:
        """Return number of entries in cache."""
        with self._lock:
            return len(self._cache)

    @property
    def maxsize(self) -> int:
        """Return maximum cache size."""
        return self._maxsize

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                # Return a copy to prevent mutation of cached data
                return copy.deepcopy(self._cache[key])
            return None

    def set(self, key: str, value: dict) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            # Store a copy to prevent mutation of cached data
            self._cache[key] = copy.deepcopy(value)
            # Evict oldest if over capacity
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def clear(self) -> int:
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count


class OCRCache:
    """File-based cache for OCR results with in-memory LRU layer."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        ttl_hours: int = 24 * 7,
        memory_cache_size: int = 50,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "mistralocr"
        self.ttl = timedelta(hours=ttl_hours)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache = LRUCache(maxsize=memory_cache_size)

    def _hash_content(self, data: str, namespace: str = "") -> str:
        """Generate hash from base64 content plus an optional namespace (cache version/options).

        Uses chunked hashing for better performance with large documents.
        """
        h = hashlib.sha256()
        if namespace:
            h.update(namespace.encode("utf-8"))
            h.update(b"\0")
        # Hash in chunks for large documents (more memory efficient)
        data_bytes = data.encode("utf-8")
        for i in range(0, len(data_bytes), HASH_CHUNK_SIZE):
            h.update(data_bytes[i:i + HASH_CHUNK_SIZE])
        return h.hexdigest()[:16]

    def _cache_path(self, content_hash: str) -> Path:
        return self.cache_dir / f"{content_hash}.json"

    def get(self, base64_data: str, namespace: str = "") -> Optional[dict]:
        """Get cached result if exists and not expired.

        Checks in-memory LRU cache first, then falls back to disk.
        """
        content_hash = self._hash_content(base64_data, namespace=namespace)

        # Check memory cache first (fast path)
        memory_result = self._memory_cache.get(content_hash)
        if memory_result is not None:
            logger.debug(f"Memory cache hit: {content_hash}")
            return memory_result

        # Fall back to disk cache
        cache_file: Optional[Path] = None
        try:
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

            result = data.get("result")
            logger.info(f"Disk cache hit: {content_hash}")

            # Populate memory cache for next access
            if result is not None:
                self._memory_cache.set(content_hash, result)

            return result
        except Exception:
            if cache_file is not None:
                try:
                    cache_file.unlink(missing_ok=True)
                except Exception:
                    pass
            return None

    def set(self, base64_data: str, result: dict, namespace: str = "") -> None:
        """Cache OCR result to both memory and disk."""
        try:
            content_hash = self._hash_content(base64_data, namespace=namespace)

            # Store in memory cache first (fast access for repeated requests)
            self._memory_cache.set(content_hash, result)

            # Then persist to disk
            cache_file = self._cache_path(content_hash)
            payload = json.dumps(
                {
                    "_cached_at": datetime.now().isoformat(),
                    "_namespace": namespace,
                    "result": result,
                }
            )
            tmp_file = cache_file.with_name(f"{cache_file.name}.{uuid.uuid4().hex}.tmp")
            tmp_file.write_text(payload, encoding="utf-8")
            os.replace(tmp_file, cache_file)
            logger.info(f"Cached: {content_hash}")
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")

    def clear(self) -> int:
        """Clear all cache files and memory cache. Returns count of deleted files."""
        # Clear memory cache
        memory_cleared = self._memory_cache.clear()
        logger.debug(f"Cleared {memory_cleared} memory cache entries")

        # Clear disk cache
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
                f.unlink(missing_ok=True)
                deleted += 1
        return {"deleted": deleted, "remaining": remaining, "cache_dir": str(self.cache_dir)}

    def stats(self) -> dict:
        """Return basic cache stats without reading contents."""
        count = 0
        total_bytes = 0
        mtimes: list[float] = []
        for f in self.cache_dir.glob("*.json"):
            try:
                st = f.stat()
                count += 1
                total_bytes += st.st_size
                mtimes.append(st.st_mtime)
            except Exception:
                continue

        return {
            "cache_dir": str(self.cache_dir),
            "disk_entries": count,
            "memory_entries": len(self._memory_cache),
            "memory_max_size": self._memory_cache.maxsize,
            "total_bytes": total_bytes,
            "ttl_seconds": int(self.ttl.total_seconds()),
            "oldest_mtime": datetime.fromtimestamp(min(mtimes)).isoformat() if mtimes else None,
            "newest_mtime": datetime.fromtimestamp(max(mtimes)).isoformat() if mtimes else None,
        }
