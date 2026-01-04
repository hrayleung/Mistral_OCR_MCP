"""
MCP tool definitions and Pydantic models for Mistral OCR server.

Defines structured output models and implements MCP tools for
OCR processing.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from mcp.server.fastmcp import Context
from mcp.server.fastmcp import FastMCP

from .config import settings
from .file_handler import FileHandler
from .ocr_client import MistralOCRClient
from .markdown_writer import MarkdownWriter
from .source_factory import get_source_factory
from .document_source import DocumentSourceType


# ============================================================================
# Pydantic Models for Structured Output
# ============================================================================

class OCRPage(BaseModel):
    """Single OCR page result."""
    index: int = Field(description="Page number (0-indexed)")
    markdown: str = Field(description="Extracted text in markdown format")
    dimensions: Optional[dict] = Field(
        default=None,
        description="Page dimensions (width, height, DPI)"
    )


class OCRImage(BaseModel):
    """Embedded image in document."""
    id: str = Field(description="Image identifier")
    top_left_x: int = Field(description="Top-left X coordinate")
    top_left_y: int = Field(description="Top-left Y coordinate")
    bottom_right_x: int = Field(description="Bottom-right X coordinate")
    bottom_right_y: int = Field(description="Bottom-right Y coordinate")
    image_base64: Optional[str] = Field(
        default=None,
        description="Base64 encoded image data (if include_images=True)"
    )


class OCRResult(BaseModel):
    """Complete OCR result for a single file or URL."""
    success: bool = Field(description="Whether OCR succeeded")
    file_path: str = Field(description="Source identifier (file path or URL)")
    file_type: str = Field(description="File type: pdf or image")
    source_type: str = Field(
        default="local_file",
        description="Source type: local_file or url"
    )
    total_pages: int = Field(description="Total pages processed")
    pages: List[OCRPage] = Field(description="Array of page results")
    images: List[OCRImage] = Field(
        default=[],
        description="Extracted images with coordinates"
    )
    model: Optional[str] = Field(default=None, description="OCR model used")
    markdown_path: Optional[str] = Field(
        default=None,
        description="Path to saved markdown file (if enabled)"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if failed"
    )


class BatchOCRResult(BaseModel):
    """Batch OCR processing result for multiple files."""
    total_files: int = Field(description="Total files submitted")
    successful: int = Field(description="Successfully processed")
    failed: int = Field(description="Failed processing")
    results: List[OCRResult] = Field(description="Individual file results")
    errors: List[str] = Field(
        default=[],
        description="List of error messages for failed files"
    )


class SupportedFormats(BaseModel):
    """Supported file formats response."""
    formats: List[str] = Field(description="List of supported file extensions")
    max_file_size_mb: int = Field(description="Maximum file size in MB")


# ============================================================================
# MCP Tool Implementations
# ============================================================================

def register_ocr_tools(mcp: FastMCP) -> None:
    """
    Register all OCR tools with the FastMCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool()
    async def ocr_process_file(
        ctx: Context,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        include_images: bool = False
    ) -> OCRResult:
        """
        Process a single document (PDF or image) with OCR.

        Supports both local files and publicly accessible URLs.
        Extracts text and structure from PDF documents and images using
        Mistral's OCR API. Returns structured results with page-by-page
        text extraction and metadata.

        Args:
            file_path: Absolute path to local file (mutually exclusive with url)
            url: Public URL to document (mutually exclusive with file_path)
            include_images: Whether to include base64-encoded images in output

        Returns:
            OCRResult: Structured OCR results with pages, text, and metadata
        """
        # Validate mutual exclusivity of parameters
        if file_path is not None and url is not None:
            await ctx.error("Cannot specify both file_path and url parameters")
            return OCRResult(
                success=False,
                file_path="unknown",
                file_type="unknown",
                source_type="unknown",
                total_pages=0,
                pages=[],
                images=[],
                error_message="Cannot specify both 'file_path' and 'url' parameters. "
                             "Please provide only one source."
            )

        if file_path is None and url is None:
            await ctx.error("Must specify either file_path or url parameter")
            return OCRResult(
                success=False,
                file_path="unknown",
                file_type="unknown",
                source_type="unknown",
                total_pages=0,
                pages=[],
                images=[],
                error_message="Must specify either 'file_path' or 'url' parameter."
            )

        # Create descriptor and source using factory
        factory = get_source_factory()
        try:
            descriptor = factory.create_descriptor(file_path=file_path, url=url)
        except ValueError as e:
            await ctx.error(f"Invalid source specification: {str(e)}")
            return OCRResult(
                success=False,
                file_path=file_path or url or "unknown",
                file_type="unknown",
                source_type="unknown",
                total_pages=0,
                pages=[],
                images=[],
                error_message=str(e)
            )

        source = factory.get_source(descriptor)

        await ctx.info(
            f"Starting OCR processing for {descriptor.source_type.value}: "
            f"{descriptor.identifier}"
        )

        # Step 1: Validate and encode document
        await ctx.debug(f"Validating {descriptor.source_type.value} and encoding to base64...")
        validation_result = source.validate_and_encode(descriptor.identifier)

        if not validation_result.success:
            await ctx.error(f"Document validation failed: {validation_result.error}")
            return OCRResult(
                success=False,
                file_path=descriptor.identifier,
                file_type="unknown",
                source_type=descriptor.source_type.value,
                total_pages=0,
                pages=[],
                images=[],
                error_message=validation_result.error
            )

        await ctx.info(
            f"Document validated successfully ({validation_result.size_bytes} bytes)"
        )

        # Step 2: Check configuration
        if settings is None or not settings.api_key:
            await ctx.error("MISTRAL_API_KEY not configured")
            return OCRResult(
                success=False,
                file_path=descriptor.identifier,
                file_type="unknown",
                source_type=descriptor.source_type.value,
                total_pages=0,
                pages=[],
                images=[],
                error_message="MISTRAL_API_KEY environment variable is required. "
                           "Please configure it in your MCP client settings."
            )

        # Step 3: Initialize OCR client
        await ctx.debug("Initializing Mistral OCR client...")
        ocr_client = MistralOCRClient(
            api_key=settings.api_key,
            model=settings.ocr_model
        )

        # Step 4: Process with Mistral OCR
        await ctx.info("Sending document to Mistral OCR API...")
        try:
            ocr_response = ocr_client.process_document(
                base64_data=validation_result.data,
                mime_type=validation_result.mime_type,
                include_images=include_images
            )
        except Exception as e:
            await ctx.error(f"OCR processing failed: {str(e)}")
            return OCRResult(
                success=False,
                file_path=descriptor.identifier,
                file_type=source.get_file_type(descriptor.identifier) or "unknown",
                source_type=descriptor.source_type.value,
                total_pages=0,
                pages=[],
                images=[],
                error_message=f"OCR processing error: {str(e)}"
            )

        # Step 5: Check for API errors
        if not ocr_response['success']:
            await ctx.error(f"Mistral API error: {ocr_response['error']}")
            return OCRResult(
                success=False,
                file_path=descriptor.identifier,
                file_type=source.get_file_type(descriptor.identifier) or "unknown",
                source_type=descriptor.source_type.value,
                total_pages=0,
                pages=[],
                images=[],
                model=ocr_response['model'],
                error_message=ocr_response['error']
            )

        # Step 6: Build success response
        await ctx.info(
            f"OCR completed successfully! "
            f"Processed {len(ocr_response['pages'])} pages"
        )

        pages = [
            OCRPage(
                index=p['index'],
                markdown=p['markdown'],
                dimensions=p.get('dimensions')
            )
            for p in ocr_response['pages']
        ]

        images = [
            OCRImage(**img)
            for img in ocr_response['images']
        ]

        # Step 7: Save to markdown file
        markdown_path = None
        if settings and settings.output_dir:
            await ctx.debug("Saving OCR results to markdown file...")
            try:
                writer = MarkdownWriter(output_dir=settings.output_dir)
                write_result = writer.write_ocr_result({
                    'success': True,
                    'file_path': descriptor.identifier,
                    'file_type': source.get_file_type(descriptor.identifier) or "unknown",
                    'total_pages': len(pages),
                    'pages': ocr_response['pages'],
                    'images': ocr_response['images'],
                    'model': ocr_response['model']
                })

                if write_result.success:
                    markdown_path = write_result.file_path
                    await ctx.info(f"✓ Saved markdown to: {markdown_path}")
                else:
                    await ctx.error(f"Failed to save markdown: {write_result.error}")
            except Exception as e:
                await ctx.error(f"Error saving markdown: {str(e)}")

        return OCRResult(
            success=True,
            file_path=descriptor.identifier,
            file_type=source.get_file_type(descriptor.identifier) or "unknown",
            source_type=descriptor.source_type.value,
            total_pages=len(pages),
            pages=pages,
            images=images,
            model=ocr_response['model'],
            markdown_path=markdown_path
        )

    @mcp.tool()
    async def ocr_batch_process(
        ctx: Context,
        sources: List[str],
        include_images: bool = False
    ) -> BatchOCRResult:
        """
        Process multiple documents (PDFs and images) with OCR in batch.

        Supports mixing local files and URLs in a single batch.
        Processes multiple documents sequentially, continuing even if individual
        documents fail. Returns summary statistics and individual results.

        Args:
            sources: List of source identifiers (file paths or URLs).
                     URLs are auto-detected by http:// or https:// prefix.
            include_images: Whether to include base64-encoded images in output

        Returns:
            BatchOCRResult: Summary with individual results for each document
        """
        await ctx.info(
            f"Starting batch OCR processing for {len(sources)} sources "
            f"(files and URLs)"
        )

        factory = get_source_factory()
        try:
            results = []
            errors = []
            successful = 0
            failed = 0

            for idx, source in enumerate(sources, 1):
                # Auto-detect source type
                descriptor = factory.create_descriptor_auto(source)
                source_type_label = "URL" if descriptor.is_url else "file"

                await ctx.info(
                    f"Processing source {idx}/{len(sources)}: {source} "
                    f"(detected as {source_type_label})"
                )

                # Process each source by routing to appropriate handler
                if descriptor.is_url:
                    result = await ocr_process_file(
                        file_path=None,
                        url=source,
                        include_images=include_images,
                        ctx=ctx
                    )
                else:
                    result = await ocr_process_file(
                        file_path=source,
                        url=None,
                        include_images=include_images,
                        ctx=ctx
                    )

                results.append(result)

                if result.success:
                    successful += 1
                    await ctx.info(f"Success: {source}")
                else:
                    failed += 1
                    error_msg = f"{source}: {result.error_message}"
                    errors.append(error_msg)
                    await ctx.error(f"Failed: {source} - {result.error_message}")

            await ctx.info(
                f"Batch processing complete: "
                f"{successful} succeeded, {failed} failed"
            )

            # Step 7: Save batch results to markdown files
            if settings and settings.output_dir:
                await ctx.debug("Saving batch OCR results to markdown files...")
                try:
                    writer = MarkdownWriter(output_dir=settings.output_dir)
                    batch_name = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                    # Only write successful results
                    successful_results = [
                        {
                            'success': True,
                            'file_path': r.file_path,
                            'file_type': r.file_type,
                            'total_pages': r.total_pages,
                            'pages': [p.model_dump() for p in r.pages],
                            'images': [img.model_dump() for img in r.images],
                            'model': r.model
                        }
                        for r in results
                        if r.success
                    ]

                    write_results = writer.write_batch_results(
                        batch_results=successful_results,
                        batch_name=batch_name
                    )

                    # Log results
                    saved_count = sum(1 for r in write_results.values() if r.success)
                    await ctx.info(f"Saved {saved_count} markdown files to {settings.output_dir}")

                except Exception as e:
                    await ctx.error(f"Error saving batch markdown files: {str(e)}")

            return BatchOCRResult(
                total_files=len(sources),
                successful=successful,
                failed=failed,
                results=results,
                errors=errors
            )
        finally:
            # Ensure HTTP client is closed after batch processing
            factory.close()

    @mcp.tool()
    async def ocr_get_supported_formats(ctx: Context) -> SupportedFormats:
        """
        Get the list of supported file formats and configuration limits.

        Returns information about which file types are supported and
        the maximum file size allowed for OCR processing.

        Returns:
            SupportedFormats: List of supported formats and size limits
        """
        await ctx.debug("Retrieving supported formats information")

        # Use defaults if settings not loaded
        if settings is None:
            return SupportedFormats(
                formats=['.pdf', '.jpg', '.jpeg', '.png', '.avif'],
                max_file_size_mb=50
            )

        return SupportedFormats(
            formats=list(settings.allowed_extensions),
            max_file_size_mb=settings.max_file_size // (1024 * 1024)
        )
