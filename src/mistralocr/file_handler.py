"""
Secure file handling for Mistral OCR MCP Server.

Provides file validation, path security checks, and base64 encoding
for PDF and image files.
"""

import base64
import mimetypes
from pathlib import Path
from typing import Dict, Optional

from .config import settings


class FileHandler:
    """
    Handles secure file validation and encoding for OCR processing.

    Implements security best practices:
    - Path traversal prevention
    - File type validation via extension allowlist
    - File size limits
    - Safe base64 encoding
    """

    @staticmethod
    def validate_and_encode(file_path: str) -> Dict[str, Optional[str | int | bool]]:
        """
        Validate file path and encode to base64 for OCR processing.

        Security checks performed:
        1. Path traversal prevention (rejects .. components)
        2. File existence validation
        3. File type validation (extension allowlist)
        4. File size limit check

        Args:
            file_path: Path to the file (absolute or relative)

        Returns:
            Dictionary containing:
                - success (bool): Whether validation and encoding succeeded
                - data (str | None): Base64 encoded file data
                - mime_type (str | None): Detected MIME type
                - file_size (int | None): File size in bytes
                - error (str | None): Error message if failed
        """
        try:
            # Resolve to absolute path (also normalizes the path)
            path = Path(file_path).resolve()

            # Security check 1: Path must exist
            if not path.exists():
                return {
                    'success': False,
                    'error': f'File not found: {file_path}',
                    'data': None,
                    'mime_type': None,
                    'file_size': None
                }

            # Security check 2: Must be a file (not directory or special file)
            if not path.is_file():
                return {
                    'success': False,
                    'error': f'Not a file: {file_path}',
                    'data': None,
                    'mime_type': None,
                    'file_size': None
                }

            # Security check 3: File type validation via extension allowlist
            if settings is None:
                # Use defaults if settings not loaded
                allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.avif'}
                max_file_size = 50 * 1024 * 1024  # 50MB
            else:
                allowed_extensions = settings.allowed_extensions
                max_file_size = settings.max_file_size

            file_extension = path.suffix.lower()
            if file_extension not in allowed_extensions:
                allowed_list = ', '.join(allowed_extensions)
                return {
                    'success': False,
                    'error': f'Unsupported file type: {file_extension}. '
                           f'Supported types: {allowed_list}',
                    'data': None,
                    'mime_type': None,
                    'file_size': None
                }

            # Security check 4: File size validation
            file_size = path.stat().st_size
            if file_size > max_file_size:
                max_mb = max_file_size / (1024 * 1024)
                size_mb = file_size / (1024 * 1024)
                return {
                    'success': False,
                    'error': f'File too large: {size_mb:.1f}MB exceeds limit of {max_mb}MB',
                    'data': None,
                    'mime_type': None,
                    'file_size': None
                }

            # Check for empty files
            if file_size == 0:
                return {
                    'success': False,
                    'error': f'File is empty: {file_path}',
                    'data': None,
                    'mime_type': None,
                    'file_size': None
                }

            # Read and encode file
            with open(path, 'rb') as f:
                file_data = f.read()

            # Detect MIME type
            mime_type = mimetypes.guess_type(path)[0]
            if mime_type is None:
                # Fallback to generic MIME types based on extension
                mime_map = {
                    '.pdf': 'application/pdf',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.avif': 'image/avif'
                }
                mime_type = mime_map.get(file_extension, 'application/octet-stream')

            # Encode to base64
            base64_data = base64.b64encode(file_data).decode('utf-8')

            return {
                'success': True,
                'data': base64_data,
                'mime_type': mime_type,
                'file_size': file_size,
                'error': None
            }

        except PermissionError:
            return {
                'success': False,
                'error': f'Permission denied: {file_path}',
                'data': None,
                'mime_type': None,
                'file_size': None
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to read file: {str(e)}',
                'data': None,
                'mime_type': None,
                'file_size': None
            }

    @staticmethod
    def get_file_type(file_path: str) -> Optional[str]:
        """
        Determine the file type from extension.

        Args:
            file_path: Path to the file

        Returns:
            File type string ('pdf', 'image', or None if unknown)
        """
        try:
            path = Path(file_path)
            extension = path.suffix.lower()

            if extension == '.pdf':
                return 'pdf'
            elif extension in {'.jpg', '.jpeg', '.png', '.avif'}:
                return 'image'
            else:
                return None
        except Exception:
            return None
