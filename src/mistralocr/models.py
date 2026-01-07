"""
Pydantic models for OCR API responses.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class OCRImage(BaseModel):
    """Extracted image/figure/chart from document."""
    id: str = Field(description="Image identifier (e.g., img-0.jpeg)")
    page_index: int = Field(default=0, description="Page where image appears")
    top_left_x: int = Field(description="Top-left X coordinate")
    top_left_y: int = Field(description="Top-left Y coordinate")
    bottom_right_x: int = Field(description="Bottom-right X coordinate")
    bottom_right_y: int = Field(description="Bottom-right Y coordinate")
    width: int = Field(default=0, description="Image width in pixels")
    height: int = Field(default=0, description="Image height in pixels")
    image_base64: Optional[str] = Field(default=None, description="Base64 image data")
    image_path: Optional[str] = Field(default=None, description="Saved image path (for markdown linking)")


class OCRPage(BaseModel):
    """Single OCR page result."""
    index: int = Field(description="Page number (0-indexed)")
    markdown: str = Field(description="Extracted text in markdown format")
    dimensions: Optional[dict] = Field(default=None, description="Page dimensions")
    images: List[str] = Field(default_factory=list, description="Image IDs on this page")


class OCRResult(BaseModel):
    """Complete OCR result for a single document."""
    success: bool = Field(description="Whether OCR succeeded")
    file_path: str = Field(description="Source identifier")
    file_type: str = Field(description="File type: pdf, document, or image")
    source_type: str = Field(default="local_file", description="Source type")
    from_cache: bool = Field(default=False, description="Whether the result came from cache")
    total_pages: int = Field(description="Total pages processed")
    pages: List[OCRPage] = Field(description="Page results")
    images: List[OCRImage] = Field(default_factory=list, description="Extracted images/figures/charts")
    total_images: int = Field(default=0, description="Total images found")
    model: Optional[str] = Field(default=None, description="OCR model used")
    usage: dict = Field(default_factory=dict, description="API usage metadata")
    markdown_path: Optional[str] = Field(default=None, description="Saved markdown path")
    error_message: Optional[str] = Field(default=None, description="Error message")
    error_type: Optional[str] = Field(default=None, description="Error type")


class BatchOCRResult(BaseModel):
    """Batch OCR processing result."""
    total_files: int = Field(description="Total files submitted")
    successful: int = Field(description="Successfully processed")
    failed: int = Field(description="Failed processing")
    results: List[OCRResult] = Field(description="Individual results")
    errors: List[str] = Field(default_factory=list, description="Error messages")


class SupportedFormats(BaseModel):
    """Supported file formats response."""
    formats: List[str] = Field(description="Supported file extensions")
    max_file_size_mb: int = Field(description="Maximum file size in MB")
