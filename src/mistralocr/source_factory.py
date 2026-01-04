"""
Factory for creating appropriate document source handlers.

Implements Factory Pattern to abstract source creation logic.
"""

from typing import Optional

from .document_source import DocumentSource, DocumentDescriptor, DocumentSourceType
from .file_source import LocalFileSource
from .url_source import URLSource


class DocumentSourceFactory:
    """
    Factory for creating document source handlers.

    Automatically determines the appropriate source type based on
    the input and returns a configured handler instance.
    """

    def __init__(self):
        """Initialize factory with cached source instances."""
        self._local_source: Optional[LocalFileSource] = None
        self._url_source: Optional[URLSource] = None

    def create_descriptor(
        self,
        file_path: Optional[str] = None,
        url: Optional[str] = None
    ) -> DocumentDescriptor:
        """
        Create a DocumentDescriptor from the provided input.

        Only one of file_path or url should be provided.

        Args:
            file_path: Local file path
            url: Remote URL

        Returns:
            DocumentDescriptor for the input

        Raises:
            ValueError: If neither or both parameters are provided
        """
        # Exactly one parameter must be provided
        if file_path is None and url is None:
            raise ValueError("Either file_path or url must be provided")

        if file_path is not None and url is not None:
            raise ValueError("Only one of file_path or url should be provided")

        if file_path is not None:
            source = LocalFileSource()
            return DocumentDescriptor(
                source_type=DocumentSourceType.LOCAL_FILE,
                identifier=file_path,
                display_name=source.get_display_name(file_path)
            )
        else:  # url is not None
            source = URLSource()
            return DocumentDescriptor(
                source_type=DocumentSourceType.URL,
                identifier=url,
                display_name=source.get_display_name(url)
            )

    def create_descriptor_auto(self, source: str) -> DocumentDescriptor:
        """
        Create a DocumentDescriptor by auto-detecting source type.

        Detects URL vs file path based on http:// or https:// prefix
        (case-insensitive).

        Args:
            source: File path or URL

        Returns:
            DocumentDescriptor for the input
        """
        # Case-insensitive URL detection
        source_lower = source.lower()
        if source_lower.startswith(('http://', 'https://')):
            url_source = URLSource()
            return DocumentDescriptor(
                source_type=DocumentSourceType.URL,
                identifier=source,
                display_name=url_source.get_display_name(source)
            )
        else:
            file_source = LocalFileSource()
            return DocumentDescriptor(
                source_type=DocumentSourceType.LOCAL_FILE,
                identifier=source,
                display_name=file_source.get_display_name(source)
            )

    def get_source(self, descriptor: DocumentDescriptor) -> DocumentSource:
        """
        Get the appropriate source handler for a descriptor.

        Args:
            descriptor: Document descriptor

        Returns:
            Configured DocumentSource instance
        """
        if descriptor.source_type == DocumentSourceType.LOCAL_FILE:
            if self._local_source is None:
                self._local_source = LocalFileSource()
            return self._local_source

        elif descriptor.source_type == DocumentSourceType.URL:
            if self._url_source is None:
                self._url_source = URLSource()
            return self._url_source

        else:
            raise ValueError(f"Unsupported source type: {descriptor.source_type}")

    def close(self) -> None:
        """Close all cached source handlers."""
        if self._url_source is not None:
            self._url_source.close()
            self._url_source = None


# Singleton factory instance
_factory_instance: Optional[DocumentSourceFactory] = None


def get_source_factory() -> DocumentSourceFactory:
    """
    Get the singleton document source factory instance.

    Returns:
        DocumentSourceFactory instance
    """
    global _factory_instance
    if _factory_instance is None:
        _factory_instance = DocumentSourceFactory()
    return _factory_instance
