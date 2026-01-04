"""
Abstract document source protocol for OCR processing.

Defines the interface for all document sources (local files, URLs, etc.)
ensuring consistent behavior and enabling extensibility.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DocumentSourceType(Enum):
    """Enumeration of supported document source types."""
    LOCAL_FILE = "local_file"
    URL = "url"
    # Future: S3 = "s3", GCS = "gcs", etc.


@dataclass(frozen=True)
class ValidationResult:
    """
    Immutable result of document validation and encoding.

    This abstraction allows consistent error handling across all
    document source types.
    """
    success: bool
    data: Optional[str] = None  # Base64 encoded content
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    error: Optional[str] = None

    @classmethod
    def failure(cls, error: str) -> "ValidationResult":
        """Create a failed validation result."""
        return cls(success=False, error=error)

    @classmethod
    def success_with_data(
        cls,
        data: str,
        mime_type: str,
        size_bytes: int
    ) -> "ValidationResult":
        """Create a successful validation result."""
        return cls(
            success=True,
            data=data,
            mime_type=mime_type,
            size_bytes=size_bytes,
            error=None
        )


@dataclass(frozen=True)
class DocumentDescriptor:
    """
    Immutable descriptor for a document to be processed.

    This abstraction allows treating files and URLs uniformly
    throughout the processing pipeline.
    """
    source_type: DocumentSourceType
    identifier: str  # file path or URL
    display_name: str  # User-friendly name for markdown files

    @property
    def is_local(self) -> bool:
        """Check if this is a local file."""
        return self.source_type == DocumentSourceType.LOCAL_FILE

    @property
    def is_url(self) -> bool:
        """Check if this is a remote URL."""
        return self.source_type == DocumentSourceType.URL


class DocumentSource(ABC):
    """
    Abstract base class for document sources.

    All document sources must implement this interface to ensure
    consistent validation and encoding behavior.
    """

    @abstractmethod
    def validate_and_encode(self, identifier: str) -> ValidationResult:
        """
        Validate and encode a document for OCR processing.

        Args:
            identifier: Document identifier (path, URL, etc.)

        Returns:
            ValidationResult with base64 data and metadata
        """
        pass

    @abstractmethod
    def get_display_name(self, identifier: str) -> str:
        """
        Generate a user-friendly display name for the document.

        Used for markdown file naming and logging.

        Args:
            identifier: Document identifier

        Returns:
            Display name string
        """
        pass

    @abstractmethod
    def get_file_type(self, identifier: str) -> Optional[str]:
        """
        Determine the file type from the identifier.

        Args:
            identifier: Document identifier

        Returns:
            File type string ('pdf', 'image', or None)
        """
        pass
