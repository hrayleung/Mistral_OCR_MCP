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

    def _hash_content(self, data: str) -> str:
        """Generate hash from base64 content."""
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _cache_path(self, content_hash: str) -> Path:
        return self.cache_dir / f"{content_hash}.json"

    def get(self, base64_data: str) -> Optional[dict]:
        """Get cached result if exists and not expired."""
        try:
            content_hash = self._hash_content(base64_data)
            cache_file = self._cache_path(content_hash)

            if not cache_file.exists():
                return None

            data = json.loads(cache_file.read_text())
            cached_at = datetime.fromisoformat(data.get("_cached_at", ""))

            if datetime.now() - cached_at > self.ttl:
                cache_file.unlink(missing_ok=True)
                return None

            logger.info(f"Cache hit: {content_hash}")
            return data.get("result")
        except Exception:
            return None

    def set(self, base64_data: str, result: dict) -> None:
        """Cache OCR result."""
        try:
            content_hash = self._hash_content(base64_data)
            cache_file = self._cache_path(content_hash)
            cache_file.write_text(json.dumps({
                "_cached_at": datetime.now().isoformat(),
                "result": result
            }))
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
