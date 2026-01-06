"""
Centralized constants for Mistral OCR MCP Server.

Single source of truth for file formats, MIME types, and limits.
"""

from typing import FrozenSet

# Supported file extensions
DOCUMENT_EXTENSIONS: FrozenSet[str] = frozenset({'.pdf', '.docx', '.pptx', '.txt'})
IMAGE_EXTENSIONS: FrozenSet[str] = frozenset({'.jpg', '.jpeg', '.png', '.avif', '.tiff', '.tif'})
ALLOWED_EXTENSIONS: FrozenSet[str] = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS

# MIME type mappings
MIME_TYPES = {
    '.pdf': 'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.txt': 'text/plain',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.avif': 'image/avif',
    '.tiff': 'image/tiff',
    '.tif': 'image/tiff',
}

# Allowed MIME types for URL validation
ALLOWED_MIME_TYPES: FrozenSet[str] = frozenset(MIME_TYPES.values())

# Default limits
DEFAULT_MAX_FILE_SIZE_MB = 50
DEFAULT_MAX_FILE_SIZE_BYTES = DEFAULT_MAX_FILE_SIZE_MB * 1024 * 1024

# Invalid filename characters
INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def get_file_type(extension: str) -> str | None:
    """Get file type from extension."""
    ext = extension.lower()
    if ext == '.pdf':
        return 'pdf'
    if ext in DOCUMENT_EXTENSIONS:
        return 'document'
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    return None


def get_mime_type(extension: str) -> str:
    """Get MIME type from extension."""
    return MIME_TYPES.get(extension.lower(), 'application/octet-stream')
