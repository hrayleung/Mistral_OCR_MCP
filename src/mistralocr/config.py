"""
Configuration management for Mistral OCR MCP Server.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Optional
from dotenv import load_dotenv

from .constants import ALLOWED_EXTENSIONS, DEFAULT_MAX_FILE_SIZE_BYTES

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""
    # Required
    api_key: str

    # API settings
    api_base: str = "https://api.mistral.ai/v1"
    ocr_model: str = "mistral-ocr-latest"

    # Server settings
    server_name: str = "MistralOCR"
    log_level: str = "INFO"

    # File processing
    max_file_size: int = DEFAULT_MAX_FILE_SIZE_BYTES
    allowed_extensions: FrozenSet[str] = ALLOWED_EXTENSIONS

    # Output settings
    output_dir: str = "./ocr_output"

    # Cache settings
    cache_enabled: bool = True
    cache_ttl_hours: int = 168  # 7 days

    # Image extraction settings
    image_min_size: int = 100  # Min dimension to include images
    max_concurrent: int = 5    # Max concurrent batch requests

    @classmethod
    def from_env(cls) -> Optional["Settings"]:
        """Load settings from environment. Returns None if API key missing."""
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            return None

        max_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
        output_dir = os.getenv("OCR_OUTPUT_DIR", "./ocr_output")

        return cls(
            api_key=api_key,
            api_base=os.getenv("MISTRAL_API_BASE", "https://api.mistral.ai/v1"),
            ocr_model=os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-latest"),
            server_name=os.getenv("MCP_SERVER_NAME", "MistralOCR"),
            log_level=os.getenv("MCP_LOG_LEVEL", "INFO"),
            max_file_size=max_size_mb * 1024 * 1024,
            output_dir=str(Path(output_dir).resolve()),
            cache_enabled=os.getenv("OCR_CACHE_ENABLED", "true").lower() == "true",
            cache_ttl_hours=int(os.getenv("OCR_CACHE_TTL_HOURS", "168")),
            image_min_size=int(os.getenv("OCR_IMAGE_MIN_SIZE", "100")),
            max_concurrent=int(os.getenv("OCR_MAX_CONCURRENT", "5")),
        )


settings: Optional[Settings] = Settings.from_env()
