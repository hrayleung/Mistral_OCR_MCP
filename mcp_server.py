#!/usr/bin/env python3
"""
Mistral OCR MCP Server

Usage:
    python mcp_server.py                    # Development mode
    python -m mcp dev mcp_server.py         # MCP Inspector
    python -m mcp install mcp_server.py     # Install in Claude Desktop
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp.server.fastmcp import FastMCP
from src.mistralocr.config import settings
from src.mistralocr.tools import register_ocr_tools

def _configure_logging() -> None:
    level_name = (settings.log_level if settings else "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


_configure_logging()

mcp = FastMCP(
    name=settings.server_name if settings else "MistralOCR",
    instructions="OCR server for PDFs, documents, and images using Mistral AI"
)

register_ocr_tools(mcp)

if __name__ == "__main__":
    mcp.run()
