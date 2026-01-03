"""
Configuration management for Mistral OCR MCP Server.

Loads settings from environment variables (typically passed by the client)
and provides configuration constants for the server.
"""

import os
from dataclasses import dataclass
from typing import FrozenSet, Optional
from dotenv import load_dotenv

# Load environment variables from .env file if present (optional)
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    # Mistral API Configuration
    api_key: str
    api_base: str = "https://api.mistral.ai/v1"
    ocr_model: str = "mistral-ocr-latest"

    # Server Configuration
    server_name: str = "MistralOCR"
    log_level: str = "INFO"

    # File Processing
    max_file_size: int = 50 * 1024 * 1024  # 50MB in bytes
    allowed_extensions: FrozenSet[str] = frozenset({
        '.pdf', '.jpg', '.jpeg', '.png', '.avif'
    })

    @classmethod
    def from_env(cls) -> Optional["Settings"]:
        """
        Load settings from environment variables.

        The API key is expected to be provided by the MCP client (e.g., Claude Desktop)
        rather than stored in a .env file.

        Returns:
            Settings: Configuration instance, or None if API key is not set

        Note:
            If MISTRAL_API_KEY is not set, returns None. The actual initialization
            will happen when the client connects and provides the API key.
        """
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            # API key not provided yet - will be set by client
            return None

        # Parse max file size from MB to bytes
        max_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
        max_file_size = max_size_mb * 1024 * 1024

        return cls(
            api_key=api_key,
            api_base=os.getenv("MISTRAL_API_BASE", "https://api.mistral.ai/v1"),
            ocr_model=os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-latest"),
            server_name=os.getenv("MCP_SERVER_NAME", "MistralOCR"),
            log_level=os.getenv("MCP_LOG_LEVEL", "INFO"),
            max_file_size=max_file_size,
        )


# Global settings instance (lazy loaded when client connects)
settings: Optional[Settings] = Settings.from_env()
