"""
Shared utility functions for document processing.

Provides common functionality used across multiple document source types.
"""

import hashlib
from pathlib import Path
from typing import Optional


# MIME type mapping for file extensions
MIME_TYPE_MAP = {
    '.pdf': 'application/pdf',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.avif': 'image/avif'
}


# Invalid characters for filenames
INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def get_file_type_from_extension(extension: str) -> Optional[str]:
    """
    Determine the file type from a file extension.

    Args:
        extension: File extension (with or without leading dot)

    Returns:
        File type string ('pdf', 'image', or None if unknown)
    """
    ext = extension.lower()
    if ext == '.pdf':
        return 'pdf'
    elif ext in {'.jpg', '.jpeg', '.png', '.avif'}:
        return 'image'
    return None


def get_mime_type_from_extension(extension: str) -> str:
    """
    Get MIME type from file extension.

    Args:
        extension: File extension (with or without leading dot)

    Returns:
        MIME type string or 'application/octet-stream' if unknown
    """
    ext = extension.lower() if not extension.startswith('.') else extension
    return MIME_TYPE_MAP.get(ext, 'application/octet-stream')


def sanitize_filename(name: str, fallback_hash_source: Optional[str] = None) -> str:
    """
    Sanitize a filename by removing invalid characters.

    Args:
        name: The filename to sanitize
        fallback_hash_source: If name is empty after sanitization, use this
            to generate a unique hash-based name

    Returns:
        Sanitized filename safe for use on all filesystems
    """
    if not name or name in ('.', '..'):
        if fallback_hash_source:
            hash_obj = hashlib.sha256(fallback_hash_source.encode())
            return f"unnamed_{hash_obj.hexdigest()[:12]}"
        return "unnamed"

    # Remove invalid characters
    for char in INVALID_FILENAME_CHARS:
        name = name.replace(char, '_')

    # Handle empty result after sanitization
    if not name or name in ('.', '..'):
        if fallback_hash_source:
            hash_obj = hashlib.sha256(fallback_hash_source.encode())
            return f"unnamed_{hash_obj.hexdigest()[:12]}"
        return "unnamed"

    return name


def extract_filename_from_url(url: str) -> str:
    """
    Extract a display filename from a URL.

    Args:
        url: The URL to extract filename from

    Returns:
        Display filename (hostname if no filename in path)
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    path = Path(parsed.path)
    stem = path.stem

    # If no filename in path, use hostname
    if not stem or stem in ('.', '/', ''):
        stem = parsed.netloc.replace('.', '_')

    return stem
