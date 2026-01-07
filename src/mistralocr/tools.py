"""
MCP tool definitions for Mistral OCR server with async concurrent processing.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from mcp.server.fastmcp import Context, FastMCP

from .config import settings
from .constants import ALLOWED_EXTENSIONS, DEFAULT_MAX_FILE_SIZE_MB
from .models import OCRResult, OCRPage, OCRImage, BatchOCRResult, SupportedFormats
from .ocr_client import MistralOCRClient
from .cache import OCRCache
from .image_writer import ImageWriter
from .markdown_writer import MarkdownWriter
from .source_factory import get_source_factory

_cache: Optional[OCRCache] = None


def get_cache() -> Optional[OCRCache]:
    global _cache
    if settings and not settings.cache_enabled:
        return None
    if _cache is None:
        cache_dir = None
        if settings:
            cache_dir = settings.cache_dir or str(Path(settings.output_dir) / ".cache")
        ttl = settings.cache_ttl_hours if settings else 168
        _cache = OCRCache(cache_dir, ttl_hours=ttl)
    return _cache


async def _process_single(
    source: str,
    is_url: bool,
    include_images: bool,
    save_images: bool,
    bypass_cache: bool,
    image_min_size: int,
    image_limit: Optional[int],
    client: MistralOCRClient,
    factory,
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
            source_type="unknown", total_pages=0, pages=[],
            error_message=str(e), error_type="ValidationError"
        )

    source_handler = factory.get_source(descriptor)

    # Validate and encode
    result = await asyncio.to_thread(source_handler.validate_and_encode, descriptor.identifier)
    if not result.success:
        err = result.error or "Validation failed"
        err_lower = err.lower()
        if "timeout" in err_lower:
            error_type = "TimeoutError"
        elif err_lower.startswith("http ") or "connection failed" in err_lower:
            error_type = "ValidationError"
        elif "permission denied" in err_lower or "failed to read file" in err_lower:
            error_type = "FileProcessingError"
        else:
            error_type = "ValidationError"
        return OCRResult(
            success=False, file_path=descriptor.identifier,
            file_type="unknown", source_type=descriptor.source_type.value,
            total_pages=0, pages=[], error_message=err, error_type=error_type
        )
    if not result.data or not result.mime_type:
        return OCRResult(
            success=False,
            file_path=descriptor.identifier,
            file_type="unknown",
            source_type=descriptor.source_type.value,
            total_pages=0,
            pages=[],
            error_message="Validation succeeded but returned no data/mime_type",
            error_type="ValidationError",
        )

    # OCR processing
    ocr_result = await asyncio.to_thread(
        client.process_document,
        result.data,
        result.mime_type,
        include_images,
        save_images,
        bypass_cache,
        image_limit,
        image_min_size,
    )

    if not ocr_result["success"]:
        return OCRResult(
            success=False, file_path=descriptor.identifier,
            file_type=source_handler.get_file_type(descriptor.identifier) or "unknown",
            source_type=descriptor.source_type.value, total_pages=0, pages=[],
            model=ocr_result.get("model"),
            usage=ocr_result.get("usage") or {},
            from_cache=bool(ocr_result.get("_from_cache", False)),
            error_message=ocr_result.get("error"),
            error_type=ocr_result.get("error_type") or "APIError",
        )

    # Build response
    pages = [OCRPage(
        index=p["index"],
        markdown=p["markdown"],
        dimensions=p.get("dimensions"),
        images=p.get("images", []),
    ) for p in ocr_result["pages"]]

    images = [OCRImage(**img) for img in ocr_result["images"]]

    return OCRResult(
        success=True, file_path=descriptor.identifier,
        file_type=source_handler.get_file_type(descriptor.identifier) or "unknown",
        source_type=descriptor.source_type.value, total_pages=len(pages),
        pages=pages, images=images, total_images=ocr_result.get("total_images", len(images)),
        model=ocr_result.get("model"),
        usage=ocr_result.get("usage") or {},
        from_cache=bool(ocr_result.get("_from_cache", False)),
    )


def register_ocr_tools(mcp: FastMCP) -> None:
    """Register all OCR tools with FastMCP server."""

    @mcp.tool()
    async def ocr_process_file(
        ctx: Context,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        include_images: bool = False,
        save_images: bool = False,
        save_markdown: bool = True,
        image_min_size: Optional[int] = None,
        image_limit: Optional[int] = None,
        bypass_cache: bool = False,
        output_dir: Optional[str] = None,
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
                error_message="Provide exactly one of 'file_path' or 'url'",
                error_type="ValidationError",
            )

        if not settings or not settings.api_key:
            return OCRResult(
                success=False, file_path=file_path or url or "unknown",
                file_type="unknown", source_type="unknown", total_pages=0,
                pages=[], error_message="MISTRAL_API_KEY not configured", error_type="ConfigurationError"
            )

        factory = get_source_factory()
        cache = get_cache()

        source = url or file_path
        is_url = url is not None
        min_size = image_min_size if image_min_size is not None else settings.image_min_size
        resolved_output_dir = str(Path(output_dir).resolve()) if output_dir else settings.output_dir
        await ctx.info(f"Processing: {source}")

        writer: Optional[MarkdownWriter] = None
        markdown_path: Optional[Path] = None
        assets_dir: Optional[Path] = None
        if save_markdown or save_images:
            writer = MarkdownWriter(resolved_output_dir)
            base = writer.derive_filename(source)
            markdown_path = writer.reserve_path(base)
            assets_dir = writer.assets_dir_for_markdown(markdown_path)

        result = await _process_single(
            source,
            is_url,
            include_images,
            save_images,
            bypass_cache,
            min_size,
            image_limit,
            MistralOCRClient(
                settings.api_key,
                settings.ocr_model,
                cache,
                api_base=settings.api_base,
            ),
            factory,
        )

        if result.total_images > 0:
            await ctx.info(f"Found {result.total_images} images/figures/charts")

        # Save extracted images (optionally stripping base64 from the response)
        if result.success and save_images and assets_dir and markdown_path:
            try:
                image_writer = ImageWriter(assets_dir, link_base_dir=markdown_path.parent)
                updated_images, summary = image_writer.write_images(
                    [i.model_dump() for i in result.images]
                )
                if not include_images:
                    for img in updated_images:
                        img["image_base64"] = None
                result = OCRResult(
                    **{
                        **result.model_dump(),
                        "images": [OCRImage(**img) for img in updated_images],
                    }
                )
                await ctx.info(
                    f"Saved {summary.written} images to {summary.assets_dir} (skipped {summary.skipped}, failed {summary.failed})"
                )
            except Exception as e:
                await ctx.error(f"Image save failed: {e}")

        # Save markdown
        if result.success and save_markdown and writer and markdown_path:
            try:
                write_result = writer.write_ocr_result({
                    'file_path': result.file_path,
                    'file_type': result.file_type,
                    'model': result.model,
                    'pages': [p.model_dump() for p in result.pages],
                    'images': [i.model_dump() for i in result.images]
                }, output_path=str(markdown_path))
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
        save_images: bool = False,
        save_markdown: bool = True,
        image_min_size: Optional[int] = None,
        image_limit: Optional[int] = None,
        bypass_cache: bool = False,
        max_concurrent: Optional[int] = None,
        output_dir: Optional[str] = None,
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

        concurrent = max_concurrent if max_concurrent is not None else settings.max_concurrent
        if concurrent < 1:
            return BatchOCRResult(
                total_files=len(sources),
                successful=0,
                failed=len(sources),
                results=[],
                errors=[f"Invalid max_concurrent: {concurrent}"],
            )

        min_size = image_min_size if image_min_size is not None else settings.image_min_size
        resolved_output_dir = str(Path(output_dir).resolve()) if output_dir else settings.output_dir
        await ctx.info(f"Batch processing {len(sources)} sources (max {concurrent} concurrent)")

        factory = get_source_factory()
        cache = get_cache()
        semaphore = asyncio.Semaphore(concurrent)

        async def process_with_semaphore(src: str, idx: int) -> OCRResult:
            async with semaphore:
                descriptor = factory.create_descriptor_auto(src)
                await ctx.info(f"[{idx + 1}/{len(sources)}] {src}")
                return await _process_single(
                    src,
                    descriptor.is_url,
                    include_images,
                    save_images,
                    bypass_cache,
                    min_size,
                    image_limit,
                    MistralOCRClient(
                        settings.api_key,
                        settings.ocr_model,
                        cache,
                        api_base=settings.api_base,
                    ),
                    factory,
                )

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
                        error_message=str(result), error_type="UnhandledError"
                    ))
                elif result.success:
                    successful += 1
                    final_results.append(result)
                else:
                    failed += 1
                    errors.append(f"{src}: {result.error_message}")
                    final_results.append(result)

            await ctx.info(f"Completed: {successful} succeeded, {failed} failed")

            # Save batch markdown + images
            if successful > 0 and (save_markdown or save_images):
                try:
                    writer = MarkdownWriter(resolved_output_dir)
                    batch_name = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    successful_indices = [i for i, r in enumerate(final_results) if r.success]
                    for idx, i in enumerate(successful_indices):
                        r = final_results[i]
                        base = f"{batch_name}_{idx:02d}_{writer.derive_filename(r.file_path)}"
                        md_path = writer.reserve_path(base)
                        assets_dir = writer.assets_dir_for_markdown(md_path)

                        images_dicts = [img.model_dump() for img in r.images]
                        if save_images:
                            image_writer = ImageWriter(assets_dir, link_base_dir=md_path.parent)
                            images_dicts, _ = image_writer.write_images(images_dicts)
                            if not include_images:
                                for img in images_dicts:
                                    img["image_base64"] = None
                            r = OCRResult(**{**r.model_dump(), "images": [OCRImage(**img) for img in images_dicts]})

                        if save_markdown:
                            write_result = writer.write_ocr_result(
                                {
                                    "file_path": r.file_path,
                                    "file_type": r.file_type,
                                    "model": r.model,
                                    "pages": [p.model_dump() for p in r.pages],
                                    "images": [img.model_dump() for img in r.images],
                                },
                                base_filename=base,
                                output_path=str(md_path),
                            )
                            if write_result.success:
                                r = OCRResult(**{**r.model_dump(), "markdown_path": write_result.file_path})

                        final_results[i] = r
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

    @mcp.tool()
    async def ocr_cache_stats(ctx: Context) -> dict:
        """Get basic cache statistics."""
        cache = get_cache()
        if cache is None:
            return {"enabled": False, "message": "Cache is disabled"}
        stats = cache.stats()
        stats["enabled"] = True
        return stats

    @mcp.tool()
    async def ocr_cache_prune(ctx: Context) -> dict:
        """Delete expired cache entries based on TTL."""
        cache = get_cache()
        if cache is None:
            return {"enabled": False, "message": "Cache is disabled"}
        result = cache.prune()
        result["enabled"] = True
        await ctx.info(f"Pruned cache: deleted {result.get('deleted', 0)} entries")
        return result
