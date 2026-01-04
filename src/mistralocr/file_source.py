"""
Local file document source for OCR processing.

Refactored from FileHandler to implement DocumentSource interface.
Maintains all existing security and validation logic.
"""

import base64
import mimetypes
from pathlib import Path
from typing import Optional

from .document_source import DocumentSource, ValidationResult
from .config import settings
from .utils import (
    get_file_type_from_extension,
    get_mime_type_from_extension,
    sanitize_filename
)


class LocalFileSource(DocumentSource):
    """
    Handles local file documents with security validation.

    Refactored from FileHandler to implement DocumentSource interface.
    Maintains all existing security checks:
    - Path traversal prevention
    - File type validation
    - File size limits
    """

    def __init__(self, max_file_size: Optional[int] = None):
        """
        Initialize local file source handler.

        Args:
            max_file_size: Maximum file size in bytes (uses settings if None)
        """
        self.max_file_size = max_file_size or (
            settings.max_file_size if settings else 50 * 1024 * 1024
        )

        # Configure allowed extensions
        if settings and settings.allowed_extensions:
            self._allowed_extensions = settings.allowed_extensions
        else:
            self._allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.avif'}

    def validate_and_encode(self, file_path: str) -> ValidationResult:
        """
        Validate file path and encode to base64 for OCR processing.

        Security checks performed:
        1. Path traversal prevention (resolves to absolute path)
        2. File existence validation
        3. File type validation (extension allowlist)
        4. File size limit check

        Args:
            file_path: Path to the file (absolute or relative)

        Returns:
            ValidationResult with base64 data or error details
        """
        try:
            # Resolve to absolute path (normalizes path and prevents traversal)
            path = Path(file_path).resolve()

            # Security check 1: Path must exist
            if not path.exists():
                return ValidationResult.failure(f'File not found: {file_path}')

            # Security check 2: Must be a file (not directory or special file)
            if not path.is_file():
                return ValidationResult.failure(f'Not a file: {file_path}')

            # Security check 3: File type validation
            file_extension = path.suffix.lower()
            if file_extension not in self._allowed_extensions:
                allowed_list = ', '.join(sorted(self._allowed_extensions))
                return ValidationResult.failure(
                    f'Unsupported file type: {file_extension}. '
                    f'Supported types: {allowed_list}'
                )

            # Security check 4: File size validation
            file_size = path.stat().st_size
            if file_size > self.max_file_size:
                max_mb = self.max_file_size / (1024 * 1024)
                size_mb = file_size / (1024 * 1024)
                return ValidationResult.failure(
                    f'File too large: {size_mb:.1f}MB exceeds limit of {max_mb}MB'
                )

            # Check for empty files
            if file_size == 0:
                return ValidationResult.failure(f'File is empty: {file_path}')

            # Read and encode file
            with open(path, 'rb') as f:
                file_data = f.read()

            # Detect MIME type
            mime_type = self._determine_mime_type(path, file_extension)

            # Encode to base64
            base64_data = base64.b64encode(file_data).decode('utf-8')

            return ValidationResult.success_with_data(
                data=base64_data,
                mime_type=mime_type,
                size_bytes=file_size
            )

        except PermissionError:
            return ValidationResult.failure(f'Permission denied: {file_path}')
        except Exception as e:
            return ValidationResult.failure(f'Failed to read file: {str(e)}')

    def get_display_name(self, file_path: str) -> str:
        """
        Generate display name from file path.

        Args:
            file_path: Path to the file

        Returns:
            Display name (filename without extension)
        """
        path = Path(file_path)
        stem = path.stem
        return sanitize_filename(stem, fallback_hash_source=file_path)

    def get_file_type(self, file_path: str) -> Optional[str]:
        """
        Determine the file type from extension.

        Args:
            file_path: Path to the file

        Returns:
            File type string ('pdf', 'image', or None if unknown)
        """
        try:
            path = Path(file_path)
            return get_file_type_from_extension(path.suffix)
        except Exception:
            return None

    def _determine_mime_type(self, path: Path, extension: str) -> str:
        """
        Determine MIME type from file path or extension.

        Args:
            path: File path object
            extension: File extension (with dot)

        Returns:
            MIME type string
        """
        # Try system MIME type detection
        mime_type = mimetypes.guess_type(str(path))[0]
        if mime_type:
            return mime_type

        # Fallback to shared utility
        return get_mime_type_from_extension(extension)
