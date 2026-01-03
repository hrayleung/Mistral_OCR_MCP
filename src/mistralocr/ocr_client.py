"""
Mistral OCR API client wrapper.

Provides a clean interface to Mistral's OCR API for processing
PDF and image files.
"""

from typing import Dict, List, Optional, Any
from mistralai import Mistral
from mistralai.models import OCRResponse


class MistralOCRClient:
    """
    Client for interacting with Mistral's OCR API.

    Handles document processing via base64-encoded data URIs
    and parses responses into structured formats.
    """

    def __init__(self, api_key: str, model: str = "mistral-ocr-latest"):
        """
        Initialize the Mistral OCR client.

        Args:
            api_key: Mistral API key
            model: OCR model to use (default: mistral-ocr-latest)
        """
        self.client = Mistral(api_key=api_key)
        self.model = model

    def process_document(
        self,
        base64_data: str,
        mime_type: str,
        include_images: bool = False
    ) -> Dict[str, Any]:
        """
        Process a document (PDF or image) with Mistral OCR.

        Args:
            base64_data: Base64-encoded file data
            mime_type: MIME type of the file (e.g., 'application/pdf')
            include_images: Whether to include base64-encoded images in response

        Returns:
            Dictionary containing:
                - success (bool): Whether OCR succeeded
                - pages (list): Array of page results with text and metadata
                - images (list): Extracted images with coordinates
                - model (str): Model used
                - usage (dict): Usage information
                - error (str | None): Error message if failed

        Example:
            >>> client = MistralOCRClient(api_key="...")
            >>> result = client.process_document(
            ...     base64_data="JVBERi0xLjQK...",
            ...     mime_type="application/pdf"
            ... )
            >>> if result['success']:
            ...     for page in result['pages']:
            ...         print(page['markdown'])
        """
        try:
            # Construct data URI format required by Mistral API
            data_uri = f"data:{mime_type};base64,{base64_data}"

            # Call Mistral OCR API
            response: OCRResponse = self.client.ocr.process(
                model=self.model,
                document={
                    "type": "document_url",
                    "document_url": data_uri
                },
                include_image_base64=include_images
            )

            # Parse response into structured format
            pages = []
            images = []

            for page in response.pages:
                page_data = {
                    'index': page.index,
                    'markdown': page.markdown,
                    'dimensions': None
                }

                # Add page dimensions if available
                if hasattr(page, 'dimensions') and page.dimensions:
                    page_data['dimensions'] = {
                        'width': page.dimensions.width,
                        'height': page.dimensions.height,
                        'dpi': page.dimensions.dpi
                    }

                # Extract images if present
                if hasattr(page, 'images') and page.images:
                    for img in page.images:
                        image_data = {
                            'id': img.id,
                            'top_left_x': img.top_left_x,
                            'top_left_y': img.top_left_y,
                            'bottom_right_x': img.bottom_right_x,
                            'bottom_right_y': img.bottom_right_y,
                            'image_base64': None
                        }

                        # Include base64 image data if requested
                        if include_images and hasattr(img, 'image_base64'):
                            image_data['image_base64'] = img.image_base64

                        images.append(image_data)

                pages.append(page_data)

            # Extract usage information
            usage_info = {
                'pages_processed': response.usage_info.pages_processed,
                'doc_size_bytes': response.usage_info.doc_size_bytes
            }

            return {
                'success': True,
                'pages': pages,
                'images': images,
                'model': response.model,
                'usage': usage_info,
                'error': None
            }

        except Exception as e:
            # Categorize error types
            error_msg = str(e).lower()

            if 'authentication' in error_msg or 'unauthorized' in error_msg or '401' in error_msg:
                error_type = 'AuthenticationError'
            elif 'quota' in error_msg or 'limit' in error_msg or '429' in error_msg:
                error_type = 'QuotaExceededError'
            elif 'timeout' in error_msg or 'timed out' in error_msg:
                error_type = 'TimeoutError'
            elif 'file too large' in error_msg or 'size' in error_msg:
                error_type = 'FileSizeError'
            elif 'invalid' in error_msg or 'malformed' in error_msg:
                error_type = 'InvalidRequestError'
            else:
                error_type = 'APIError'

            return {
                'success': False,
                'pages': [],
                'images': [],
                'model': self.model,
                'usage': {},
                'error': f'{error_type}: {str(e)}'
            }
