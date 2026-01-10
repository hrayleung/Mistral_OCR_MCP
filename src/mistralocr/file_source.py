"""
Local file document source for OCR processing.
"""

import base64
import mimetypes
from pathlib import Path
from typing import Optional

from .document_source import DocumentSource, ValidationResult
from .config import settings
from .constants import ALLOWED_EXTENSIONS, DEFAULT_MAX_FILE_SIZE_BYTES, get_file_type, get_mime_type
from .utils import sanitize_filename


class LocalFileSource(DocumentSource):
    """Handles local file documents with security validation."""

    def __init__(self, max_file_size: Optional[int] = None, allow_symlinks: bool = False):
        self.max_file_size = max_file_size or (
            settings.max_file_size if settings else DEFAULT_MAX_FILE_SIZE_BYTES
        )
        self.allow_symlinks = allow_symlinks
        self._allowed = settings.allowed_extensions if settings else ALLOWED_EXTENSIONS

    def validate_and_encode(self, file_path: str) -> ValidationResult:
        """Validate file and encode to base64."""
        try:
            path = Path(file_path).resolve()

            # Security: reject symlinks
            if not self.allow_symlinks and self._has_symlink(file_path):
                return ValidationResult.failure(f'Symbolic links not allowed: {file_path}')

            if not path.exists():
                return ValidationResult.failure(f'File not found: {file_path}')

            if not path.is_file():
                return ValidationResult.failure(f'Not a file: {file_path}')

            ext = path.suffix.lower()
            if ext not in self._allowed:
                return ValidationResult.failure(
                    f'Unsupported type: {ext}. Supported: {", ".join(sorted(self._allowed))}'
                )

            size = path.stat().st_size
            if size > self.max_file_size:
                return ValidationResult.failure(
                    f'File too large: {size / 1024 / 1024:.1f}MB > {self.max_file_size / 1024 / 1024}MB'
                )

            if size == 0:
                return ValidationResult.failure(f'File is empty: {file_path}')

            with open(path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')

            mime = mimetypes.guess_type(str(path))[0] or get_mime_type(ext)
            return ValidationResult.ok(data, mime, size)

        except PermissionError:
            return ValidationResult.failure(f'Permission denied: {file_path}')
        except Exception as e:
            return ValidationResult.failure(f'Failed to read file: {e}')

    def get_display_name(self, file_path: str) -> str:
        return sanitize_filename(Path(file_path).stem, file_path)

    def get_file_type(self, file_path: str) -> Optional[str]:
        try:
            return get_file_type(Path(file_path).suffix)
        except Exception:
            return None

    def _has_symlink(self, file_path: str) -> bool:
        """Check if path contains symlinks."""
        current = Path(file_path).expanduser().absolute()
        return any(p.is_symlink() for p in [current] + list(current.parents))
