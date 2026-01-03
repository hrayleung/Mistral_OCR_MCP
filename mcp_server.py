#!/usr/bin/env python3
"""
Mistral OCR MCP Server

A Model Context Protocol server that provides PDF and image OCR capabilities
using Mistral's OCR API.

This server exposes tools for:
- Single file OCR (PDF and images)
- Batch processing multiple files
- Getting supported file formats

Usage:
    # Development mode
    python mcp_server.py

    # With MCP Inspector for testing
    python -m mcp dev mcp_server.py

    # Install in Claude Desktop
    python -m mcp install mcp_server.py --name "mistral-ocr"
"""

import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from mcp.server.fastmcp import FastMCP
from src.mistralocr.config import settings
from src.mistralocr.tools import register_ocr_tools


def main():
    """
    Initialize and run the MCP server.

    Note:
        The MISTRAL_API_KEY is expected to be provided by the MCP client
        (e.g., Claude Desktop) via environment variables, not stored locally.
    """
    # Determine server name
    server_name = "MistralOCR" if settings is None else settings.server_name

    # Initialize FastMCP server
    mcp = FastMCP(
        name=server_name,
        json_response=True,  # Production mode
        stateless_http=True  # Better scalability
    )

    # Register OCR tools
    register_ocr_tools(mcp)

    # Run server
    mcp.run()


if __name__ == "__main__":
    main()
