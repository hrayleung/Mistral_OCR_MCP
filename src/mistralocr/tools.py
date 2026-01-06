"""
MCP tool definitions for Mistral OCR server with async concurrent processing.
"""

import asyncio
from datetime import datetime
from typing import List, Optional

from mcp.server.fastmcp import Context, FastMCP

from .config import settings
from .constants import ALLOWED_EXTENSIONS, DEFAULT_MAX_FILE_SIZE_MB
from .models import OCRResult, OCRPage, OCRImage, BatchOCRResult, SupportedFormats
from .ocr_client import MistralOCRClient
from .cache import OCRCache
from .markdown_writer import MarkdownWriter
from .source_factory import get_source_factory

_cache: Optional[OCRCache] = None


def get_cache() -> Optional[OCRCache]:
    global _cache
    if settings and not settings.cache_enabled:
        return None
    if _cache is None:
        cache_dir = f"{settings.output_dir}/.cache" if settings and settings.output_dir else None
        ttl = settings.cache_ttl_hours if settings else 168
        _cache = OCRCache(cache_dir, ttl_hours=ttl)
    return _cache


async def _process_single(
    source: str,
    is_url: bool,
    include_images: bool,
    image_min_size: int,
    client: MistralOCRClient,
    factory
) -> OCRResult:
    """Process a single document."""
    try:
        descriptor = factory.create_descriptor(
            file_path=None if is_url else source,
            url=source if is_url else None
        )
    except ValueError as e:
        return OCRResult(
            success=False, file_path=source, file_type="unknown",
            source_type="unknown", total_pages=0, pages=[], error_message=str(e)
        )

    source_handler = factory.get_source(descriptor)
    loop = asyncio.get_event_loop()

    # Validate and encode
    result = await loop.run_in_executor(
        None, source_handler.validate_and_encode, descriptor.identifier
    )
    if not result.success:
        return OCRResult(
            success=False, file_path=descriptor.identifier,
            file_type="unknown", source_type=descriptor.source_type.value,
            total_pages=0, pages=[], error_message=result.error
        )

    # OCR processing
    ocr_result = await loop.run_in_executor(
        None, lambda: client.process_document(
            result.data, result.mime_type, include_images, image_min_size=image_min_size
        )
    )

    if not ocr_result['success']:
        return OCRResult(
            success=False, file_path=descriptor.identifier,
            file_type=source_handler.get_file_type(descriptor.identifier) or "unknown",
            source_type=descriptor.source_type.value, total_pages=0, pages=[],
            model=ocr_result['model'], error_message=ocr_result['error']
        )

    # Build response
    pages = [OCRPage(
        index=p['index'],
        markdown=p['markdown'],
        dimensions=p.get('dimensions'),
        images=p.get('images', [])
    ) for p in ocr_result['pages']]

    images = [OCRImage(**img) for img in ocr_result['images']]

    return OCRResult(
        success=True, file_path=descriptor.identifier,
        file_type=source_handler.get_file_type(descriptor.identifier) or "unknown",
        source_type=descriptor.source_type.value, total_pages=len(pages),
        pages=pages, images=images, total_images=ocr_result.get('total_images', len(images)),
        model=ocr_result['model']
    )


def register_ocr_tools(mcp: FastMCP) -> None:
    """Register all OCR tools with FastMCP server."""

    @mcp.tool()
    async def ocr_process_file(
        ctx: Context,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        include_images: bool = False,
        image_min_size: int = 100
    ) -> OCRResult:
        """
        Process a document with OCR, extracting text, figures, charts, and images.

        Args:
            file_path: Absolute path to local file (mutually exclusive with url)
            url: Public URL to document (mutually exclusive with file_path)
            include_images: Include base64-encoded image data in response
            image_min_size: Minimum image dimension to include (filters small icons)

        Returns:
            OCRResult with extracted text, images/figures/charts metadata
        """
        if (file_path is None) == (url is None):
            return OCRResult(
                success=False, file_path="unknown", file_type="unknown",
                source_type="unknown", total_pages=0, pages=[],
                error_message="Provide exactly one of 'file_path' or 'url'"
            )

        if not settings or not settings.api_key:
            return OCRResult(
                success=False, file_path=file_path or url or "unknown",
                file_type="unknown", source_type="unknown", total_pages=0,
                pages=[], error_message="MISTRAL_API_KEY not configured"
            )

        factory = get_source_factory()
        client = MistralOCRClient(settings.api_key, settings.ocr_model, get_cache())

        source = url or file_path
        is_url = url is not None
        min_size = image_min_size if image_min_size else settings.image_min_size
        await ctx.info(f"Processing: {source}")

        result = await _process_single(source, is_url, include_images, min_size, client, factory)

        if result.total_images > 0:
            await ctx.info(f"Found {result.total_images} images/figures/charts")

        # Save markdown
        if result.success and settings and settings.output_dir:
            try:
                writer = MarkdownWriter(settings.output_dir)
                write_result = writer.write_ocr_result({
                    'file_path': result.file_path,
                    'file_type': result.file_type,
                    'model': result.model,
                    'pages': [p.model_dump() for p in result.pages],
                    'images': [i.model_dump() for i in result.images]
                })
                if write_result.success:
                    result = OCRResult(**{**result.model_dump(), 'markdown_path': write_result.file_path})
                    await ctx.info(f"Saved: {write_result.file_path}")
            except Exception as e:
                await ctx.error(f"Markdown save failed: {e}")

        return result

    @mcp.tool()
    async def ocr_batch_process(
        ctx: Context,
        sources: List[str],
        include_images: bool = False,
        image_min_size: Optional[int] = None,
        max_concurrent: Optional[int] = None
    ) -> BatchOCRResult:
        """
        Process multiple documents with OCR concurrently.

        Args:
            sources: List of file paths or URLs (auto-detected)
            include_images: Include base64-encoded image data
            image_min_size: Minimum image dimension to include (default from config)
            max_concurrent: Maximum concurrent OCR requests (default from config)

        Returns:
            BatchOCRResult with individual results
        """
        if not settings or not settings.api_key:
            return BatchOCRResult(
                total_files=len(sources), successful=0, failed=len(sources),
                results=[], errors=["MISTRAL_API_KEY not configured"]
            )

        concurrent = max_concurrent if max_concurrent else settings.max_concurrent
        min_size = image_min_size if image_min_size else settings.image_min_size
        await ctx.info(f"Batch processing {len(sources)} sources (max {concurrent} concurrent)")

        factory = get_source_factory()
        client = MistralOCRClient(settings.api_key, settings.ocr_model, get_cache())
        semaphore = asyncio.Semaphore(concurrent)

        async def process_with_semaphore(src: str, idx: int) -> OCRResult:
            async with semaphore:
                descriptor = factory.create_descriptor_auto(src)
                await ctx.info(f"[{idx + 1}/{len(sources)}] {src}")
                return await _process_single(src, descriptor.is_url, include_images, min_size, client, factory)

        try:
            tasks = [process_with_semaphore(src, idx) for idx, src in enumerate(sources)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            final_results, errors = [], []
            successful, failed = 0, 0

            for src, result in zip(sources, results):
                if isinstance(result, Exception):
                    failed += 1
                    errors.append(f"{src}: {result}")
                    final_results.append(OCRResult(
                        success=False, file_path=src, file_type="unknown",
                        source_type="unknown", total_pages=0, pages=[],
                        error_message=str(result)
                    ))
                elif result.success:
                    successful += 1
                    final_results.append(result)
                else:
                    failed += 1
                    errors.append(f"{src}: {result.error_message}")
                    final_results.append(result)

            await ctx.info(f"Completed: {successful} succeeded, {failed} failed")

            # Save batch markdown
            if settings and settings.output_dir and successful > 0:
                try:
                    writer = MarkdownWriter(settings.output_dir)
                    batch_name = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    successful_results = [
                        {'file_path': r.file_path, 'file_type': r.file_type, 'model': r.model,
                         'pages': [p.model_dump() for p in r.pages],
                         'images': [i.model_dump() for i in r.images]}
                        for r in final_results if r.success
                    ]
                    writer.write_batch_results(successful_results, batch_name)
                except Exception as e:
                    await ctx.error(f"Batch markdown save failed: {e}")

            return BatchOCRResult(
                total_files=len(sources), successful=successful, failed=failed,
                results=final_results, errors=errors
            )
        finally:
            factory.close()

    @mcp.tool()
    async def ocr_get_supported_formats(ctx: Context) -> SupportedFormats:
        """Get supported file formats and size limits."""
        if settings:
            return SupportedFormats(
                formats=list(settings.allowed_extensions),
                max_file_size_mb=settings.max_file_size // (1024 * 1024)
            )
        return SupportedFormats(
            formats=list(ALLOWED_EXTENSIONS),
            max_file_size_mb=DEFAULT_MAX_FILE_SIZE_MB
        )

    @mcp.tool()
    async def ocr_clear_cache(ctx: Context) -> dict:
        """Clear the OCR results cache."""
        cache = get_cache()
        if cache is None:
            return {"cleared": 0, "message": "Cache is disabled"}
        count = cache.clear()
        await ctx.info(f"Cleared {count} cached entries")
        return {"cleared": count}
