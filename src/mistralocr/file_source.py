"""
Local file document source for OCR processing.

Refactored from FileHandler to implement DocumentSource interface.
Maintains all existing security and validation logic.
"""

import base64
import mimetypes
import os
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
    - Symlink attack prevention
    - File type validation
    - File size limits
    """

    def __init__(self, max_file_size: Optional[int] = None, allow_symlinks: bool = False):
        """
        Initialize local file source handler.

        Args:
            max_file_size: Maximum file size in bytes (uses settings if None)
            allow_symlinks: Whether to follow symbolic links (default: False for security)
        """
        self.max_file_size = max_file_size or (
            settings.max_file_size if settings else 50 * 1024 * 1024
        )
        self.allow_symlinks = allow_symlinks

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
        2. Symlink attack prevention (rejects symlinks unless explicitly allowed)
        3. File existence validation
        4. File type validation (extension allowlist)
        5. File size limit check

        Args:
            file_path: Path to the file (absolute or relative)

        Returns:
            ValidationResult with base64 data or error details
        """
        try:
            # Resolve to absolute path (normalizes path and prevents traversal)
            # Note: resolve() follows symlinks by default, so we check separately
            path = Path(file_path).resolve()
            original_path = Path(file_path)

            # Security check 0: Reject symbolic links unless explicitly allowed
            # This prevents symlink attacks where a malicious user creates
            # symlinks pointing to sensitive files
            if not self.allow_symlinks:
                # Check if the original path or any component is a symlink
                current = Path(file_path).expanduser().absolute()
                if current.is_symlink():
                    return ValidationResult.failure(
                        f'Symbolic links are not allowed for security reasons: {file_path}'
                    )
                # Also check parent directories
                for parent in [current] + list(current.parents):
                    if parent.is_symlink():
                        return ValidationResult.failure(
                            f'Symbolic links in path are not allowed: {file_path}'
                        )

            # Security check 1: Path must exist
            if not path.exists():
                return ValidationResult.failure(f'File not found: {file_path}')

            # Security check 2: Must be a file (not directory or special file)
            if not path.is_file():
                return ValidationResult.failure(f'Not a file: {file_path}')

            # Security check 3: Verify file is not accessed through a symlink
            # Even if the file itself isn't a symlink, ensure we didn't follow one
            if not self.allow_symlinks:
                try:
                    # Get the real path without following symlinks
                    real_path = Path(os.path.realpath(file_path))
                    # Compare with resolved path (which follows symlinks)
                    if real_path.resolve() != path:
                        return ValidationResult.failure(
                            f'Path contains symbolic links which are not allowed: {file_path}'
                        )
                except OSError:
                    return ValidationResult.failure(f'Invalid path: {file_path}')

            # Security check 4: File type validation
            file_extension = path.suffix.lower()
            if file_extension not in self._allowed_extensions:
                allowed_list = ', '.join(sorted(self._allowed_extensions))
                return ValidationResult.failure(
                    f'Unsupported file type: {file_extension}. '
                    f'Supported types: {allowed_list}'
                )

            # Security check 5: File size validation
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
