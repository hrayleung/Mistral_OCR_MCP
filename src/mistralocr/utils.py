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
    if not name or name in ('.', '..'):
        if fallback_hash_source:
            return f"unnamed_{hashlib.sha256(fallback_hash_source.encode()).hexdigest()[:12]}"
        return "unnamed"

    for char in INVALID_FILENAME_CHARS:
        name = name.replace(char, '_')

    if not name or name in ('.', '..'):
        if fallback_hash_source:
            return f"unnamed_{hashlib.sha256(fallback_hash_source.encode()).hexdigest()[:12]}"
        return "unnamed"

    return name


def extract_filename_from_url(url: str) -> str:
    """Extract display filename from URL."""
    parsed = urlparse(url)
    stem = Path(parsed.path).stem
    if not stem or stem in ('.', '/', ''):
        stem = parsed.netloc.replace('.', '_')
    return stem
