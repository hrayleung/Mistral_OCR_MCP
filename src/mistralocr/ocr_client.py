"""
Mistral OCR API client wrapper with connection pooling and async support.
"""

import asyncio
import logging
import random
import time
from typing import Any, Optional

from mistralai import Mistral
from mistralai.models import OCRResponse

from .cache import OCRCache

logger = logging.getLogger(__name__)


class MistralOCRClient:
    """Client for Mistral's OCR API with caching and connection pooling."""

    def __init__(
        self,
        api_key: str,
        model: str = "mistral-ocr-latest",
        cache: Optional[OCRCache] = None,
        api_base: Optional[str] = None,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ):
        self._api_key = api_key
        self._api_base = api_base
        self.client = self._create_client(api_key=api_key, api_base=api_base)
        self.model = model
        self.cache = cache
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    @staticmethod
    def _create_client(api_key: str, api_base: Optional[str]) -> Mistral:
        if not api_base:
            return Mistral(api_key=api_key)
        try:
            return Mistral(api_key=api_key, server_url=api_base)
        except TypeError:
            return Mistral(api_key=api_key)

    def _cache_namespace(self, mime_type: str, image_min_size: int, image_limit: Optional[int]) -> str:
        limit_part = "all" if image_limit is None else str(image_limit)
        return f"v3|model={self.model}|mime={mime_type}|image_min_size={image_min_size}|image_limit={limit_part}"

    def _is_retryable(self, error: Exception) -> bool:
        msg = str(error).lower()
        return any(
            token in msg
            for token in (
                "timeout",
                "timed out",
                "429",
                "rate limit",
                "quota",
                "temporarily",
                "503",
                "502",
                "bad gateway",
                "service unavailable",
                "gateway timeout",
            )
        )

    def process_document(
        self,
        base64_data: str,
        mime_type: str,
        include_images: bool = False,
        save_images: bool = False,
        bypass_cache: bool = False,
        image_limit: Optional[int] = None,
        image_min_size: int = 100,
    ) -> dict[str, Any]:
        """
        Process document with OCR.

        Args:
            base64_data: Base64 encoded document
            mime_type: MIME type of document
            include_images: Include base64 image data in response
            image_limit: Max images to include (None = all)
            image_min_size: Min width/height to include image (filters tiny icons)

        Returns:
            Dict with success, pages, images, model, usage, error
        """
        cache_allowed = self.cache is not None and not include_images and not save_images and not bypass_cache
        if cache_allowed:
            cached = self.cache.get(
                base64_data,
                namespace=self._cache_namespace(mime_type, image_min_size, image_limit),
            )
            if isinstance(cached, dict) and cached.get("success") is True:
                cached["_from_cache"] = True
                return cached

        try:
            data_uri = f"data:{mime_type};base64,{base64_data}"
            if mime_type.startswith("image/"):
                document = {"type": "image_url", "image_url": {"url": data_uri}}
            else:
                document = {"type": "document_url", "document_url": data_uri}

            response: Optional[OCRResponse] = None
            last_error: Optional[Exception] = None
            for attempt in range(self.max_retries + 1):
                try:
                    response = self.client.ocr.process(
                        model=self.model,
                        document=document,
                        include_image_base64=bool(include_images or save_images),
                    )
                    break
                except Exception as e:
                    last_error = e
                    if attempt >= self.max_retries or not self._is_retryable(e):
                        raise
                    # Exponential backoff with jitter to prevent thundering herd
                    base_delay = self.retry_backoff_seconds * (2**attempt)
                    jitter = random.uniform(0, base_delay * 0.1)
                    time.sleep(base_delay + jitter)

            if response is None:
                raise RuntimeError(f"OCR request failed: {last_error}")

            # Process response using shared helper
            return self._process_response(
                response, include_images, save_images, image_limit, image_min_size,
                cache_allowed, base64_data, mime_type
            )

        except Exception as e:
            error_type = self._classify_error(e)
            logger.warning("OCR request failed (%s): %s", error_type, e)

            return {
                "success": False,
                "pages": [],
                "images": [],
                "total_images": 0,
                "model": self.model,
                "usage": {},
                "error": f"{error_type}: {e}",
                "error_type": error_type,
                "_from_cache": False,
            }

    @staticmethod
    def _classify_error(error: Exception) -> str:
        msg = str(error).lower()
        if any(token in msg for token in ("authentication", "unauthorized", "401")):
            return "AuthenticationError"
        if any(token in msg for token in ("quota", "rate limit", "429", "limit")):
            return "QuotaExceededError"
        if "timeout" in msg or "timed out" in msg:
            return "TimeoutError"
        return "APIError"

    async def process_document_async(
        self,
        base64_data: str,
        mime_type: str,
        include_images: bool = False,
        save_images: bool = False,
        bypass_cache: bool = False,
        image_limit: Optional[int] = None,
        image_min_size: int = 100,
    ) -> dict[str, Any]:
        """
        Process document with OCR asynchronously.

        This is a true async implementation that doesn't block the event loop.
        Use this when processing multiple documents concurrently for better performance.

        Args:
            base64_data: Base64 encoded document
            mime_type: MIME type of document
            include_images: Include base64 image data in response
            save_images: Whether images will be saved (affects caching)
            bypass_cache: Skip cache lookup/storage
            image_limit: Max images to include (None = all)
            image_min_size: Min width/height to include image (filters tiny icons)

        Returns:
            Dict with success, pages, images, model, usage, error
        """
        cache_allowed = self.cache is not None and not include_images and not save_images and not bypass_cache
        if cache_allowed:
            cached = self.cache.get(
                base64_data,
                namespace=self._cache_namespace(mime_type, image_min_size, image_limit),
            )
            if isinstance(cached, dict) and cached.get("success") is True:
                cached["_from_cache"] = True
                return cached

        try:
            data_uri = f"data:{mime_type};base64,{base64_data}"
            if mime_type.startswith("image/"):
                document = {"type": "image_url", "image_url": {"url": data_uri}}
            else:
                document = {"type": "document_url", "document_url": data_uri}

            response: Optional[OCRResponse] = None
            last_error: Optional[Exception] = None

            # Use async API - create client once outside retry loop
            async with Mistral(api_key=self._api_key, server_url=self._api_base) as async_client:
                for attempt in range(self.max_retries + 1):
                    try:
                        response = await async_client.ocr.process_async(
                            model=self.model,
                            document=document,
                            include_image_base64=bool(include_images or save_images),
                        )
                        break
                    except Exception as e:
                        last_error = e
                        if attempt >= self.max_retries or not self._is_retryable(e):
                            raise
                        # Async sleep with exponential backoff and jitter
                        base_delay = self.retry_backoff_seconds * (2**attempt)
                        jitter = random.uniform(0, base_delay * 0.1)
                        await asyncio.sleep(base_delay + jitter)

            if response is None:
                raise RuntimeError(f"OCR request failed: {last_error}")

            # Process response (same logic as sync version)
            return self._process_response(
                response, include_images, save_images, image_limit, image_min_size,
                cache_allowed, base64_data, mime_type
            )

        except Exception as e:
            error_type = self._classify_error(e)
            logger.warning("Async OCR request failed (%s): %s", error_type, e)

            return {
                "success": False,
                "pages": [],
                "images": [],
                "total_images": 0,
                "model": self.model,
                "usage": {},
                "error": f"{error_type}: {e}",
                "error_type": error_type,
                "_from_cache": False,
            }

    def _process_response(
        self,
        response: OCRResponse,
        include_images: bool,
        save_images: bool,
        image_limit: Optional[int],
        image_min_size: int,
        cache_allowed: bool,
        base64_data: str,
        mime_type: str,
    ) -> dict[str, Any]:
        """Process OCR response into result dict. Shared by sync and async methods."""
        pages, images = [], []
        image_count = 0

        for page in response.pages:
            page_data = {
                "index": page.index,
                "markdown": page.markdown,
                "dimensions": None,
                "images": [],
            }

            if hasattr(page, "dimensions") and page.dimensions:
                page_data["dimensions"] = {
                    "width": page.dimensions.width,
                    "height": page.dimensions.height,
                    "dpi": getattr(page.dimensions, "dpi", None),
                }

            if hasattr(page, "images") and page.images:
                for img in page.images:
                    width = abs(img.bottom_right_x - img.top_left_x)
                    height = abs(img.bottom_right_y - img.top_left_y)

                    if width < image_min_size or height < image_min_size:
                        continue

                    if image_limit and image_count >= image_limit:
                        continue

                    img_data = {
                        "id": img.id,
                        "page_index": page.index,
                        "top_left_x": img.top_left_x,
                        "top_left_y": img.top_left_y,
                        "bottom_right_x": img.bottom_right_x,
                        "bottom_right_y": img.bottom_right_y,
                        "width": width,
                        "height": height,
                        "image_base64": None,
                    }

                    if (include_images or save_images) and hasattr(img, "image_base64") and img.image_base64:
                        img_data["image_base64"] = img.image_base64

                    images.append(img_data)
                    page_data["images"].append(img_data["id"])
                    image_count += 1

            pages.append(page_data)

        result = {
            "success": True,
            "pages": pages,
            "images": images,
            "total_images": image_count,
            "model": response.model,
            "usage": {
                "pages_processed": getattr(getattr(response, "usage_info", None), "pages_processed", None),
                "doc_size_bytes": getattr(getattr(response, "usage_info", None), "doc_size_bytes", None),
            },
            "error": None,
            "error_type": None,
            "_from_cache": False,
        }

        if cache_allowed:
            cache_result = {**result}
            for img in cache_result["images"]:
                img["image_base64"] = None
            self.cache.set(
                base64_data,
                cache_result,
                namespace=self._cache_namespace(mime_type, image_min_size, image_limit),
            )

        return result
