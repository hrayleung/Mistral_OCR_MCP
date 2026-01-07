"""
Mistral OCR API client wrapper with connection pooling.
"""

import logging
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
            doc_type = "image_url" if mime_type.startswith("image/") else "document_url"
            document = (
                {"type": doc_type, "image_url": {"url": data_uri}}
                if doc_type == "image_url"
                else {"type": doc_type, "document_url": data_uri}
            )

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
                    time.sleep(self.retry_backoff_seconds * (2**attempt))

            if response is None:
                raise RuntimeError(f"OCR request failed: {last_error}")

            pages, images = [], []
            image_count = 0

            for page in response.pages:
                page_data = {
                    "index": page.index,
                    "markdown": page.markdown,
                    "dimensions": None,
                    "images": [],  # Per-page images
                }

                if hasattr(page, "dimensions") and page.dimensions:
                    page_data["dimensions"] = {
                        "width": page.dimensions.width,
                        "height": page.dimensions.height,
                        "dpi": getattr(page.dimensions, "dpi", None),
                    }

                # Process images for this page
                if hasattr(page, "images") and page.images:
                    for img in page.images:
                        width = abs(img.bottom_right_x - img.top_left_x)
                        height = abs(img.bottom_right_y - img.top_left_y)

                        # Filter small images (icons, bullets, etc.)
                        if width < image_min_size or height < image_min_size:
                            continue

                        # Check image limit
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

                        # Include base64 data if requested (for response or for saving to disk)
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

            # Cache successful results (without image base64)
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
