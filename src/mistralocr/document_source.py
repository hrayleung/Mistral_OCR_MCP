"""
Abstract document source protocol for OCR processing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DocumentSourceType(Enum):
    """Supported document source types."""
    LOCAL_FILE = "local_file"
    URL = "url"


@dataclass(frozen=True)
class ValidationResult:
    """Immutable result of document validation and encoding."""
    success: bool
    data: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    error: Optional[str] = None

    @classmethod
    def failure(cls, error: str) -> "ValidationResult":
        return cls(success=False, error=error)

    @classmethod
    def ok(cls, data: str, mime_type: str, size_bytes: int) -> "ValidationResult":
        return cls(success=True, data=data, mime_type=mime_type, size_bytes=size_bytes)


@dataclass(frozen=True)
class DocumentDescriptor:
    """Immutable descriptor for a document to be processed."""
    source_type: DocumentSourceType
    identifier: str
    display_name: str

    @property
    def is_local(self) -> bool:
        return self.source_type == DocumentSourceType.LOCAL_FILE

    @property
    def is_url(self) -> bool:
        return self.source_type == DocumentSourceType.URL


class DocumentSource(ABC):
    """Abstract base class for document sources."""

    @abstractmethod
    def validate_and_encode(self, identifier: str) -> ValidationResult:
        """Validate and encode document for OCR processing."""
        pass

    @abstractmethod
    def get_display_name(self, identifier: str) -> str:
        """Generate user-friendly display name."""
        pass

    @abstractmethod
    def get_file_type(self, identifier: str) -> Optional[str]:
        """Determine file type from identifier."""
        pass
