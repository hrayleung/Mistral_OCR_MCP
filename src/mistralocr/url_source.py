"""
URL document source for OCR processing.

Handles validation, downloading, and encoding of documents from HTTP(S) URLs.
"""

import base64
import ipaddress
import logging
import mimetypes
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, ParseResult

import httpx

from .document_source import DocumentSource, ValidationResult
from .config import settings
from .utils import (
    extract_filename_from_url,
    get_file_type_from_extension,
    get_mime_type_from_extension,
    sanitize_filename
)


logger = logging.getLogger(__name__)


# IP address ranges that should be blocked (private/local networks)
BLOCKED_IP_RANGES = [
    ipaddress.ip_network('127.0.0.0/8'),      # Loopback
    ipaddress.ip_network('::1/128'),          # IPv6 loopback
    ipaddress.ip_network('169.254.0.0/16'),   # Link-local
    ipaddress.ip_network('fe80::/10'),        # IPv6 link-local
    ipaddress.ip_network('10.0.0.0/8'),       # Private Class A
    ipaddress.ip_network('172.16.0.0/12'),    # Private Class B
    ipaddress.ip_network('192.168.0.0/16'),   # Private Class C
    ipaddress.ip_network('fc00::/7'),         # IPv6 unique local
]


class URLSource(DocumentSource):
    """
    Handles documents accessible via HTTP(S) URLs.

    Features:
    - Public accessibility validation (HEAD request)
    - Content-Type detection
    - Size limit enforcement
    - Secure URL validation
    - User-agent header for server identification
    """

    # Default timeout for URL operations (seconds)
    DEFAULT_TIMEOUT = 30

    # Allowed URL schemes
    ALLOWED_SCHEMES = {'http', 'https'}

    def __init__(
        self,
        max_file_size: Optional[int] = None,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: str = "MistralOCR-MCP/1.0"
    ):
        """
        Initialize URL source handler.

        Args:
            max_file_size: Maximum file size in bytes (uses settings if None)
            timeout: Request timeout in seconds
            user_agent: User-Agent header for HTTP requests
        """
        self.max_file_size = max_file_size or (
            settings.max_file_size if settings else 50 * 1024 * 1024
        )
        self.timeout = timeout
        self.user_agent = user_agent

        # Configure allowed MIME types
        if settings and settings.allowed_extensions:
            self._allowed_extensions = settings.allowed_extensions
        else:
            self._allowed_extensions = {
                '.pdf', '.docx', '.pptx', '.txt',
                '.jpg', '.jpeg', '.png', '.avif', '.tiff', '.tif'
            }

        # Configure HTTP client with sensible defaults
        self._client = None

    @property
    def client(self) -> httpx.Client:
        """
        Lazy-initialize HTTP client.

        Security: follow_redirects is disabled to prevent SSRF attacks
        via open redirect vulnerabilities on target servers.
        """
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=False,  # SSRF prevention: disable automatic redirects
                headers={'User-Agent': self.user_agent}
            )
        return self._client

    def validate_and_encode(self, url: str) -> ValidationResult:
        """
        Validate URL and encode document content to base64.

        Validation steps:
        1. URL format validation
        2. Scheme validation (only http/https)
        3. Accessibility check (HEAD request)
        4. Content-Type validation (from HTTP response)
        5. Size limit check
        6. Download and base64 encoding

        Args:
            url: Document URL

        Returns:
            ValidationResult with base64 data or error details
        """
        try:
            # Step 1: Validate URL format
            parsed_url = self._validate_url_format(url)

            # Step 2: Check accessibility and get metadata (HEAD request)
            content_length, head_content_type = self._check_accessibility(parsed_url.geturl())

            # Enforce size limit from Content-Length if available
            if content_length and content_length > self.max_file_size:
                max_mb = self.max_file_size / (1024 * 1024)
                size_mb = content_length / (1024 * 1024)
                return ValidationResult.failure(
                    f'URL content too large: {size_mb:.1f}MB exceeds limit of {max_mb}MB'
                )

            # Step 3: Download content
            file_data, content_type = self._download_content(parsed_url.geturl())

            # Double-check file size after download
            if len(file_data) > self.max_file_size:
                max_mb = self.max_file_size / (1024 * 1024)
                size_mb = len(file_data) / (1024 * 1024)
                return ValidationResult.failure(
                    f'URL content too large: {size_mb:.1f}MB exceeds limit of {max_mb}MB'
                )

            # Check for empty content
            if len(file_data) == 0:
                return ValidationResult.failure(f'URL returned empty content: {url}')

            # Step 4: Validate Content-Type against allowed types
            mime_type = self._determine_mime_type(content_type, parsed_url)
            if not self._is_allowed_content_type(mime_type):
                allowed_list = ', '.join(sorted(self._allowed_extensions))
                return ValidationResult.failure(
                    f'Unsupported content type: {mime_type}. Supported types: {allowed_list}'
                )

            # Step 5: Encode to base64
            base64_data = base64.b64encode(file_data).decode('utf-8')

            logger.info(f"Successfully encoded URL content: {url} ({len(file_data)} bytes)")

            return ValidationResult.success_with_data(
                data=base64_data,
                mime_type=mime_type,
                size_bytes=len(file_data)
            )

        except httpx.TimeoutException:
            logger.error(f"Timeout accessing URL: {url}")
            return ValidationResult.failure(
                f'Connection timeout after {self.timeout}s: {url}'
            )
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            reason = e.response.reason_phrase or "Unknown"
            logger.error(f"HTTP error accessing URL: {url} - {status_code}")
            error_msg = f'HTTP {status_code}: {reason}'
            if status_code == 404:
                error_msg = f'URL not found (404): {url}'
            elif status_code in (401, 403):
                error_msg = f'Access denied (HTTP {status_code}): {url}'
            return ValidationResult.failure(error_msg)
        except httpx.ConnectError as e:
            logger.error(f"Connection error for URL: {url} - {str(e)}")
            return ValidationResult.failure(f'Could not connect to URL: {url}')
        except Exception as e:
            logger.exception(f"Unexpected error processing URL: {url}")
            return ValidationResult.failure(f'Failed to process URL: {str(e)}')

    def get_display_name(self, url: str) -> str:
        """
        Generate display name from URL.

        Args:
            url: Document URL

        Returns:
            Display name string
        """
        stem = extract_filename_from_url(url)
        return sanitize_filename(stem, fallback_hash_source=url)

    def get_file_type(self, url: str) -> Optional[str]:
        """
        Determine file type from URL.

        Args:
            url: Document URL

        Returns:
            File type ('pdf', 'image', or None)
        """
        try:
            parsed = urlparse(url)
            return get_file_type_from_extension(parsed.path)
        except Exception:
            return None

    def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __del__(self):
        """Clean up HTTP client on deletion."""
        self.close()

    # ========================================================================
    # Private Methods - URL Validation
    # ========================================================================

    def _validate_url_format(self, url: str) -> ParseResult:
        """
        Validate URL format and scheme.

        Args:
            url: URL to validate

        Returns:
            Parsed URL result

        Raises:
            ValueError: If URL is invalid

        Security:
            - Validates URL scheme
            - Blocks access to private/internal network IP ranges (SSRF prevention)
            - Protects against DNS rebinding attacks
        """
        parsed = urlparse(url)

        # Check scheme
        if parsed.scheme not in self.ALLOWED_SCHEMES:
            raise ValueError(
                f'Invalid URL scheme: {parsed.scheme}. '
                f'Only {", ".join(self.ALLOWED_SCHEMES)} are supported.'
            )

        # Check network location
        if not parsed.netloc:
            raise ValueError('URL must include a domain name')

        # Security: Block private/internal IP addresses (SSRF & DNS rebinding protection)
        self._validate_hostname(parsed.netloc)

        return parsed

    def _validate_hostname(self, netloc: str) -> None:
        """
        Validate that hostname is not a private/internal IP address.

        This protects against SSRF attacks targeting internal services
        and DNS rebinding attacks.

        Args:
            netloc: Network location from URL (may include port)

        Raises:
            ValueError: If hostname resolves to a blocked IP range
        """
        # Extract hostname (remove port and auth info if present)
        hostname = netloc.split('@')[-1].split(':')[0]
        hostname = hostname.strip('[]')  # Remove IPv6 brackets

        # Check if it's an IP address
        try:
            ip = ipaddress.ip_address(hostname)
            self._check_ip_blocked(ip)
            return
        except ValueError:
            # Not a plain IP address, resolve hostname
            pass

        # Resolve hostname to IP and check each result
        # This protects against DNS rebinding where initial DNS response
        # points to a valid host but later resolves to an internal IP
        try:
            # Get all addresses (IPv4 and IPv6)
            addr_info = socket.getaddrinfo(hostname, None)
            for family, _, _, _, sockaddr in addr_info:
                ip = ipaddress.ip_address(sockaddr[0])
                self._check_ip_blocked(ip)
        except socket.gaierror:
            # DNS resolution failed - will be caught later when connecting
            pass

    def _check_ip_blocked(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        """
        Check if an IP address is in a blocked range.

        Args:
            ip: IP address to check

        Raises:
            ValueError: If IP is in a blocked range
        """
        for blocked_range in BLOCKED_IP_RANGES:
            if ip.version == blocked_range.version and ip in blocked_range:
                raise ValueError(
                    f'Access to internal network addresses is not allowed: {ip}'
                )

    def _validate_file_extension(self, parsed_url: ParseResult) -> Optional[str]:
        """
        Validate file extension from URL.

        Args:
            parsed_url: Parsed URL result

        Returns:
            File type ('pdf', 'document', 'image') or None if unsupported
        """
        path = parsed_url.path.lower()
        extension = Path(path).suffix

        if extension not in self._allowed_extensions:
            return None

        if extension == '.pdf':
            return 'pdf'
        elif extension in {'.docx', '.pptx', '.txt'}:
            return 'document'
        elif extension in {'.jpg', '.jpeg', '.png', '.avif', '.tiff', '.tif'}:
            return 'image'

        return None

    def _is_allowed_content_type(self, mime_type: str) -> bool:
        """
        Check if a MIME type is allowed for OCR processing.

        Args:
            mime_type: MIME type string (e.g., 'application/pdf')

        Returns:
            True if the MIME type is allowed, False otherwise

        Security: Only explicitly whitelisted MIME types are allowed.
        The wildcard `image/*` was removed to prevent processing of
        potentially malicious image formats.
        """
        if not mime_type:
            return False

        # Only allow explicitly whitelisted MIME types
        allowed_mime_types = {
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'text/plain',
            'image/jpeg',
            'image/png',
            'image/avif',
            'image/tiff'
        }

        # Normalize MIME type (remove parameters like charset)
        mime_type = mime_type.split(';')[0].strip().lower()

        return mime_type in allowed_mime_types

    def _check_accessibility(self, url: str) -> tuple[Optional[int], Optional[str]]:
        """
        Check if URL is publicly accessible via HEAD request.

        Args:
            url: URL to check

        Returns:
            Tuple of (Content-Length header value if available, Content-Type header)

        Raises:
            httpx.HTTPStatusError: If URL is not accessible

        Security: Does not follow redirects (SSRF prevention).
        """
        response = self.client.head(url, follow_redirects=False)
        response.raise_for_status()

        # Extract content length if available
        content_length = response.headers.get('content-length')
        if content_length:
            try:
                content_length = int(content_length)
            except ValueError:
                content_length = None

        # Extract content type
        content_type = response.headers.get('content-type', '').split(';')[0].strip()

        return content_length, content_type

    def _download_content(self, url: str) -> tuple[bytes, str]:
        """
        Download document content from URL.

        Args:
            url: URL to download

        Returns:
            Tuple of (file_data, content_type)

        Raises:
            httpx.HTTPStatusError: If download fails

        Security: Does not follow redirects (SSRF prevention).
        """
        response = self.client.get(url, follow_redirects=False)
        response.raise_for_status()

        file_data = response.content
        content_type = response.headers.get('content-type', '').split(';')[0].strip()

        return file_data, content_type

    def _determine_mime_type(self, content_type: str, parsed_url: ParseResult) -> str:
        """
        Determine MIME type from Content-Type header or URL extension.

        Args:
            content_type: Content-Type header value
            parsed_url: Parsed URL result

        Returns:
            MIME type string
        """
        # Trust Content-Type header if present and valid
        if content_type and content_type.startswith(('application/', 'image/')):
            return content_type

        # Fallback to shared utility
        return get_mime_type_from_extension(parsed_url.path)
