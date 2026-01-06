"""
Mistral OCR MCP Server

A Model Context Protocol server for PDF and document OCR using Mistral's API.
"""

__version__ = "1.0.0"

from .models import OCRResult, OCRPage, OCRImage, BatchOCRResult, SupportedFormats
from .config import settings, Settings
from .constants import ALLOWED_EXTENSIONS, MIME_TYPES
from .cache import OCRCache

__all__ = [
    "OCRResult", "OCRPage", "OCRImage", "BatchOCRResult", "SupportedFormats",
    "settings", "Settings", "ALLOWED_EXTENSIONS", "MIME_TYPES", "OCRCache"
]
