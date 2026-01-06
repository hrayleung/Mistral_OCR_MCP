"""
Mistral OCR API client wrapper with connection pooling.
"""

from typing import Any, Optional
from mistralai import Mistral
from mistralai.models import OCRResponse

from .cache import OCRCache


class MistralOCRClient:
    """Client for Mistral's OCR API with caching and connection pooling."""

    def __init__(
        self,
        api_key: str,
        model: str = "mistral-ocr-latest",
        cache: Optional[OCRCache] = None
    ):
        self.client = Mistral(api_key=api_key)
        self.model = model
        self.cache = cache

    def process_document(
        self,
        base64_data: str,
        mime_type: str,
        include_images: bool = False,
        image_limit: Optional[int] = None,
        image_min_size: int = 100
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
        # Check cache (only for non-image requests)
        if self.cache and not include_images:
            cached = self.cache.get(base64_data)
            if cached:
                cached['_from_cache'] = True
                return cached

        try:
            data_uri = f"data:{mime_type};base64,{base64_data}"
            doc_type = "image_url" if mime_type.startswith('image/') else "document_url"
            document = (
                {"type": doc_type, "image_url": {"url": data_uri}}
                if doc_type == "image_url"
                else {"type": doc_type, "document_url": data_uri}
            )

            # Always request image base64 to get full image data
            # The include_images flag controls whether we return it to the user
            response: OCRResponse = self.client.ocr.process(
                model=self.model,
                document=document,
                include_image_base64=True  # Always get images from API
            )

            pages, images = [], []
            image_count = 0

            for page in response.pages:
                page_data = {
                    'index': page.index,
                    'markdown': page.markdown,
                    'dimensions': None,
                    'images': []  # Per-page images
                }

                if hasattr(page, 'dimensions') and page.dimensions:
                    page_data['dimensions'] = {
                        'width': page.dimensions.width,
                        'height': page.dimensions.height,
                        'dpi': getattr(page.dimensions, 'dpi', None)
                    }

                # Process images for this page
                if hasattr(page, 'images') and page.images:
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
                            'id': img.id,
                            'page_index': page.index,
                            'top_left_x': img.top_left_x,
                            'top_left_y': img.top_left_y,
                            'bottom_right_x': img.bottom_right_x,
                            'bottom_right_y': img.bottom_right_y,
                            'width': width,
                            'height': height,
                            'image_base64': None
                        }

                        # Include base64 data if requested
                        if include_images and hasattr(img, 'image_base64') and img.image_base64:
                            img_data['image_base64'] = img.image_base64

                        images.append(img_data)
                        page_data['images'].append(img_data['id'])
                        image_count += 1

                pages.append(page_data)

            result = {
                'success': True,
                'pages': pages,
                'images': images,
                'total_images': image_count,
                'model': response.model,
                'usage': {
                    'pages_processed': response.usage_info.pages_processed,
                    'doc_size_bytes': response.usage_info.doc_size_bytes
                },
                'error': None,
                '_from_cache': False
            }

            # Cache successful results (without image base64)
            if self.cache and not include_images:
                cache_result = {**result}
                for img in cache_result['images']:
                    img['image_base64'] = None
                self.cache.set(base64_data, cache_result)

            return result

        except Exception as e:
            error_msg = str(e).lower()
            if any(x in error_msg for x in ('authentication', 'unauthorized', '401')):
                error_type = 'AuthenticationError'
            elif any(x in error_msg for x in ('quota', 'limit', '429')):
                error_type = 'QuotaExceededError'
            elif 'timeout' in error_msg:
                error_type = 'TimeoutError'
            else:
                error_type = 'APIError'

            return {
                'success': False,
                'pages': [],
                'images': [],
                'total_images': 0,
                'model': self.model,
                'usage': {},
                'error': f'{error_type}: {e}',
                '_from_cache': False
            }
