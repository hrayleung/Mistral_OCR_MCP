"""
URL document source for OCR processing.
"""

import base64
import ipaddress
import logging
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, ParseResult

import httpx

from .document_source import DocumentSource, ValidationResult
from .config import settings
from .constants import (
    ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES, DEFAULT_MAX_FILE_SIZE_BYTES,
    get_file_type, get_mime_type
)
from .utils import extract_filename_from_url, sanitize_filename

logger = logging.getLogger(__name__)

# Blocked IP ranges (SSRF protection)
BLOCKED_IP_RANGES = [
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('169.254.0.0/16'),
    ipaddress.ip_network('fe80::/10'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('fc00::/7'),
]


class URLSource(DocumentSource):
    """Handles documents accessible via HTTP(S) URLs."""

    TIMEOUT = 30
    ALLOWED_SCHEMES = {'http', 'https'}

    def __init__(self, max_file_size: Optional[int] = None, timeout: int = TIMEOUT):
        self.max_file_size = max_file_size or (
            settings.max_file_size if settings else DEFAULT_MAX_FILE_SIZE_BYTES
        )
        self.timeout = timeout
        self._allowed = settings.allowed_extensions if settings else ALLOWED_EXTENSIONS
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=False,
                headers={'User-Agent': 'MistralOCR-MCP/1.0'}
            )
        return self._client

    def validate_and_encode(self, url: str) -> ValidationResult:
        """Validate URL and encode content to base64."""
        try:
            parsed = self._validate_url(url)
            content_len, _ = self._head_request(parsed.geturl())

            if content_len and content_len > self.max_file_size:
                return ValidationResult.failure(
                    f'Content too large: {content_len / 1024 / 1024:.1f}MB'
                )

            data, content_type = self._download(parsed.geturl())

            if len(data) > self.max_file_size:
                return ValidationResult.failure(
                    f'Content too large: {len(data) / 1024 / 1024:.1f}MB'
                )

            if not data:
                return ValidationResult.failure(f'Empty content: {url}')

            mime = self._resolve_mime(content_type, parsed)
            if mime not in ALLOWED_MIME_TYPES:
                return ValidationResult.failure(f'Unsupported type: {mime}')

            return ValidationResult.ok(
                base64.b64encode(data).decode('utf-8'), mime, len(data)
            )

        except httpx.TimeoutException:
            return ValidationResult.failure(f'Timeout: {url}')
        except httpx.HTTPStatusError as e:
            return ValidationResult.failure(f'HTTP {e.response.status_code}: {url}')
        except httpx.ConnectError:
            return ValidationResult.failure(f'Connection failed: {url}')
        except ValueError as e:
            return ValidationResult.failure(str(e))
        except Exception as e:
            return ValidationResult.failure(f'Error: {e}')

    def get_display_name(self, url: str) -> str:
        return sanitize_filename(extract_filename_from_url(url), url)

    def get_file_type(self, url: str) -> Optional[str]:
        try:
            return get_file_type(Path(urlparse(url).path).suffix)
        except Exception:
            return None

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def __del__(self):
        self.close()

    def _validate_url(self, url: str) -> ParseResult:
        parsed = urlparse(url)
        if parsed.scheme not in self.ALLOWED_SCHEMES:
            raise ValueError(f'Invalid scheme: {parsed.scheme}')
        if not parsed.netloc:
            raise ValueError('Missing domain')
        self._check_hostname(parsed.netloc)
        return parsed

    def _check_hostname(self, netloc: str) -> None:
        hostname = netloc.split('@')[-1].split(':')[0].strip('[]')
        try:
            ip = ipaddress.ip_address(hostname)
            self._check_ip(ip)
            return
        except ValueError:
            pass

        try:
            for _, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
                self._check_ip(ipaddress.ip_address(sockaddr[0]))
        except socket.gaierror:
            pass

    def _check_ip(self, ip) -> None:
        for blocked in BLOCKED_IP_RANGES:
            if ip.version == blocked.version and ip in blocked:
                raise ValueError(f'Internal address blocked: {ip}')

    def _head_request(self, url: str) -> tuple[Optional[int], Optional[str]]:
        resp = self.client.head(url)
        resp.raise_for_status()
        length = resp.headers.get('content-length')
        return int(length) if length else None, resp.headers.get('content-type', '')

    def _download(self, url: str) -> tuple[bytes, str]:
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.content, resp.headers.get('content-type', '').split(';')[0]

    def _resolve_mime(self, content_type: str, parsed: ParseResult) -> str:
        if content_type and content_type.startswith(('application/', 'image/', 'text/')):
            return content_type.split(';')[0].strip()
        return get_mime_type(Path(parsed.path).suffix)
