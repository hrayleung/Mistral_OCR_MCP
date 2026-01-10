"""
Factory for creating document source handlers.
"""

from typing import Optional

from .document_source import DocumentSource, DocumentDescriptor, DocumentSourceType
from .file_source import LocalFileSource
from .url_source import URLSource


class DocumentSourceFactory:
    """Factory for creating document source handlers."""

    def __init__(self):
        self._local: Optional[LocalFileSource] = None
        self._url: Optional[URLSource] = None

    def _get_local(self) -> LocalFileSource:
        if not self._local:
            self._local = LocalFileSource()
        return self._local

    def _get_url(self) -> URLSource:
        if not self._url:
            self._url = URLSource()
        return self._url

    def create_descriptor(
        self, file_path: Optional[str] = None, url: Optional[str] = None
    ) -> DocumentDescriptor:
        """Create descriptor from file_path or url (mutually exclusive)."""
        if (file_path is None) == (url is None):
            raise ValueError("Provide exactly one of file_path or url")

        if file_path:
            return DocumentDescriptor(
                DocumentSourceType.LOCAL_FILE, file_path, self._get_local().get_display_name(file_path)
            )
        return DocumentDescriptor(
            DocumentSourceType.URL, url, self._get_url().get_display_name(url)
        )

    def create_descriptor_auto(self, source: str) -> DocumentDescriptor:
        """Auto-detect source type from string."""
        if source.lower().startswith(('http://', 'https://')):
            return DocumentDescriptor(
                DocumentSourceType.URL, source, self._get_url().get_display_name(source)
            )
        return DocumentDescriptor(
            DocumentSourceType.LOCAL_FILE, source, self._get_local().get_display_name(source)
        )

    def get_source(self, descriptor: DocumentDescriptor) -> DocumentSource:
        """Get source handler for descriptor."""
        if descriptor.source_type == DocumentSourceType.LOCAL_FILE:
            return self._get_local()
        if descriptor.source_type == DocumentSourceType.URL:
            return self._get_url()
        raise ValueError(f"Unknown source type: {descriptor.source_type}")

    def close(self) -> None:
        """Close cached handlers."""
        if self._url:
            self._url.close()
            self._url = None


_factory: Optional[DocumentSourceFactory] = None


def get_source_factory() -> DocumentSourceFactory:
    """Get singleton factory instance."""
    global _factory
    if _factory is None:
        _factory = DocumentSourceFactory()
    return _factory
