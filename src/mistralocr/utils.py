"""
Shared utility functions for document processing.
"""

import hashlib
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .constants import INVALID_FILENAME_CHARS


def sanitize_filename(name: str, fallback_hash_source: Optional[str] = None) -> str:
    """Sanitize filename by removing invalid characters."""
    def make_fallback() -> str:
        if fallback_hash_source:
            return f"unnamed_{hashlib.sha256(fallback_hash_source.encode()).hexdigest()[:12]}"
        return "unnamed"

    name = (name or "").strip()
    if not name or name in (".", ".."):
        return make_fallback()

    for char in INVALID_FILENAME_CHARS:
        name = name.replace(char, "_")

    name = name.strip().rstrip(" .")
    if not name or name in (".", ".."):
        return make_fallback()

    max_len = 150
    if len(name) > max_len:
        suffix = hashlib.sha256((fallback_hash_source or name).encode()).hexdigest()[:8]
        name = f"{name[:max_len - 9]}_{suffix}"

    return name


def extract_filename_from_url(url: str) -> str:
    """Extract display filename from URL."""
    parsed = urlparse(url)
    stem = Path(parsed.path).stem
    if not stem or stem in ('.', '/', ''):
        stem = parsed.netloc.replace('.', '_')
    return stem
