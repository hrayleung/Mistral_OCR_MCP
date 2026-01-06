# Mistral OCR MCP Server

A Model Context Protocol (MCP) server that provides PDF and document OCR capabilities using Mistral's OCR API. This server exposes tools for extracting text and structure from documents, returning structured JSON results with page-by-page metadata.

## Features

- **Single File OCR**: Process PDFs, Word docs, PowerPoint, text files, and images (JPG, PNG, AVIF, TIFF)
- **Batch Processing**: Process multiple files concurrently with per-file error recovery
- **Structured Output**: Returns JSON with page numbers, text, dimensions, and image coordinates
- **Automatic Markdown Export**: Saves OCR results as formatted markdown files with rich metadata
- **Optional Image Export**: Saves extracted images to disk and links/embeds them in markdown
- **On-Disk Caching**: Reuses OCR results for repeated documents to reduce latency/cost
- **Secure File Handling**: Path traversal prevention, file type validation, and size limits
- **Progress Reporting**: Real-time feedback during document processing

## Installation

### Prerequisites

- Python 3.9+
- Conda environment `deep-learning` (or any Python environment)
- Mistral API key ([Get one here](https://console.mistral.ai/))

### Setup

1. **Navigate to project directory:**
   ```bash
   cd /Users/hinrayleung/Dev/mcp/mistralocr
   ```

2. **Activate conda environment:**
   ```bash
   conda activate deep-learning
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Claude Desktop (recommended):**

   The API key should be provided by Claude Desktop, not stored in a `.env` file.

   **For macOS:**
   - Edit: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Add the following configuration:

   ```json
   {
     "mcpServers": {
       "mistral-ocr": {
         "command": "/opt/miniconda3/envs/deep-learning/bin/python",
         "args": [
           "/Users/hinrayleung/Dev/mcp/mistralocr/mcp_server.py"
         ],
         "env": {
           "MISTRAL_API_KEY": "your_mistral_api_key_here",
           "OCR_OUTPUT_DIR": "/Users/hinrayleung/Documents/OCR_Results",
           "MAX_FILE_SIZE_MB": "50",
           "OCR_CACHE_ENABLED": "true",
           "OCR_CACHE_TTL_HOURS": "168",
           "OCR_IMAGE_MIN_SIZE": "100",
           "OCR_MAX_CONCURRENT": "5"
         }
       }
     }
   }
   ```

   **Environment Variables:**

   | Variable | Required | Default | Description |
   |----------|----------|---------|-------------|
   | `MISTRAL_API_KEY` | Yes | - | Your Mistral API key |
   | `OCR_OUTPUT_DIR` | No | `./ocr_output` | Directory for markdown output |
   | `MAX_FILE_SIZE_MB` | No | `50` | Maximum file size in MB |
   | `OCR_CACHE_ENABLED` | No | `true` | Enable result caching |
   | `OCR_CACHE_TTL_HOURS` | No | `168` | Cache TTL (168 = 7 days) |
   | `OCR_CACHE_DIR` | No | `<OCR_OUTPUT_DIR>/.cache` | Override cache directory |
   | `OCR_IMAGE_MIN_SIZE` | No | `100` | Min image dimension to extract |
   | `OCR_MAX_CONCURRENT` | No | `5` | Max concurrent batch requests |
   | `OCR_URL_TIMEOUT_SECONDS` | No | `30` | URL download timeout |
   | `OCR_URL_MAX_REDIRECTS` | No | `3` | Max URL redirects to follow |
   | `OCR_URL_ALLOW_NONSTANDARD_PORTS` | No | `false` | Allow URL ports other than 80/443 |

   **For local testing only (optional):**
   ```bash
   cp .env.example .env
   # Edit .env and set MISTRAL_API_KEY
   ```

## Usage

### With Claude Desktop (Recommended)

1. **Configure Claude Desktop:**

   Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
   and add the server configuration (see Installation section above).

2. **Restart Claude Desktop:**

   The server will start automatically and tools will be available.

3. **Use the tools:**

   In Claude Desktop, you can now use the OCR tools:
   - "Use OCR to process this PDF: /path/to/document.pdf"
   - "Extract text from these images: /path/to/image1.png, /path/to/image2.jpg"
   - "What file formats are supported for OCR?"

### Development Mode (Testing)

Run the server directly for testing (requires `.env` file with API key):
```bash
# Create .env file first
echo "MISTRAL_API_KEY=your_key_here" > .env

# Run server
python mcp_server.py
```

### MCP Inspector (Debugging)

Test the server with MCP Inspector (requires `.env` file):
```bash
/opt/miniconda3/envs/deep-learning/bin/python -m mcp dev mcp_server.py
```

## MCP Tools

### `ocr_process_file`

Process a single file or URL with OCR.

**Parameters:**
- `file_path` (string, optional): Absolute path to a local file (mutually exclusive with `url`)
- `url` (string, optional): Public HTTP(S) URL (mutually exclusive with `file_path`)
- `include_images` (boolean, optional): Include base64-encoded images in the JSON response (default: false)
- `save_images` (boolean, optional): Save extracted images to disk and link them in markdown (default: false)
- `save_markdown` (boolean, optional): Save a markdown file to `OCR_OUTPUT_DIR` (default: true)
- `image_min_size` (int, optional): Filter out small images (default: `OCR_IMAGE_MIN_SIZE`)
- `image_limit` (int, optional): Max images to include/save (default: unlimited)
- `bypass_cache` (boolean, optional): Skip reading/writing the on-disk cache (default: false)
- `output_dir` (string, optional): Override output directory for this call (default: `OCR_OUTPUT_DIR`)

**Returns:**
```json
{
  "success": true,
  "file_path": "/path/to/document.pdf",
  "file_type": "pdf",
  "from_cache": false,
  "total_pages": 5,
  "pages": [
    {
      "index": 0,
      "markdown": "Extracted text content...",
      "dimensions": {
        "width": 1700,
        "height": 2200,
        "dpi": 200
      }
    }
  ],
  "images": [],
  "model": "mistral-ocr-latest",
  "usage": {},
  "markdown_path": "/path/to/OCR_Results/document_20250103_143022_ab12cd34.md",
  "error_message": null,
  "error_type": null
}
```

### `ocr_batch_process`

Process multiple files with OCR in batch.

**Parameters:**
- `sources` (array of strings, required): List of file paths or HTTP(S) URLs (auto-detected)
- `include_images` (boolean, optional): Include base64-encoded images in the JSON response (default: false)
- `save_images` (boolean, optional): Save extracted images to disk and link them in markdown (default: false)
- `save_markdown` (boolean, optional): Save markdown files for successful results (default: true)
- `image_min_size` (int, optional): Filter out small images (default: `OCR_IMAGE_MIN_SIZE`)
- `image_limit` (int, optional): Max images to include/save per document (default: unlimited)
- `bypass_cache` (boolean, optional): Skip reading/writing the on-disk cache (default: false)
- `max_concurrent` (int, optional): Max concurrent OCR requests (default: `OCR_MAX_CONCURRENT`)
- `output_dir` (string, optional): Override output directory for this call (default: `OCR_OUTPUT_DIR`)

**Returns:**
```json
{
  "total_files": 3,
  "successful": 2,
  "failed": 1,
  "results": [
    /* OCRResult objects */
  ],
  "errors": [
    "/path/to/file3.pdf: File too large"
  ]
}
```

### `ocr_get_supported_formats`

Get supported file formats and configuration limits.

**Returns:**
```json
{
  "formats": [".pdf", ".docx", ".pptx", ".txt", ".jpg", ".jpeg", ".png", ".avif", ".tiff", ".tif"],
  "max_file_size_mb": 50
}
```

### Cache Tools

- `ocr_clear_cache`: Deletes all cache entries
- `ocr_cache_stats`: Returns cache size + entry count
- `ocr_cache_prune`: Deletes expired entries based on TTL

## Markdown Output

By default, the server saves OCR results as markdown files for easy reuse and reference (set `save_markdown=false` to disable per call). If `save_images=true`, extracted images are saved to an `_assets` folder next to the markdown file and embedded/linked in the markdown.

### Configuration

Set the output directory in your Claude Desktop configuration:

```json
"env": {
  "MISTRAL_API_KEY": "your_api_key",
  "OCR_OUTPUT_DIR": "/Users/username/Documents/OCR_Results"
}
```

The directory will be created automatically if it doesn't exist.

### File Naming

Files are named automatically to prevent conflicts:

- **Single files**: `{basename}_{timestamp}_{uid}.md`
  - Example: `document_20250103_143022_ab12cd34.md`
- **Batch processing**: `{batch_name}_{idx}_{basename}.md`
  - Example: `batch_20250103_143022_00_document_20250103_143022_ab12cd34.md`

Timestamp format: `YYYYMMDD_HHMMSS`

### Markdown Format

Each markdown file includes:

- **YAML Frontmatter**: Source file, type, model, processing timestamp
- **Document Title**: Original filename
- **Table of Contents**: For multi-page documents
- **Page Content**: Each page as a separate section with headers
  - Page dimensions (width, height, DPI)
  - Extracted text in markdown format
- **Image Metadata**: Coordinates and sizes for embedded images
- **Footer**: Generation attribution

**Example Output:**

```markdown
---
source: /path/to/document.pdf
type: pdf
model: mistral-ocr-latest
processed: 2025-01-03T14:30:22.123456
---

# Document: document.pdf

## Table of Contents

- [Page 1](#page-1)
- [Page 2](#page-2)

## Page 1

*Metadata:*
- Width: 1700
- Height: 2200
- DPI: 200

This is the extracted text content from page 1...

## Page 2

*Metadata:*
- Width: 1700
- Height: 2200
- DPI: 200

This is the extracted text content from page 2...

---

*Generated by Mistral OCR MCP Server*
```

### Graceful Degradation

If markdown file saving fails (e.g., permission issues, disk full), the OCR operation still succeeds. An error is logged, but the tool continues to return the OCR results in the JSON response.

## Error Handling

All tools return structured JSON with error information:

```json
{
  "success": false,
  "error_message": "File not found: /path/to/file.pdf",
  "error_type": "ValidationError"
}
```

**Error Types:**
- `ValidationError`: Invalid file path, type, or size
- `FileProcessingError`: Failed to read or encode file
- `AuthenticationError`: Invalid API key
- `QuotaExceededError`: API quota exceeded
- `TimeoutError`: Request timeout
- `APIError`: Other API errors
- `ConfigurationError`: Missing/invalid server configuration
- `UnhandledError`: Unexpected internal error

## Security

The server implements several security measures:

1. **Path Traversal Prevention**: All file paths are validated and resolved
2. **File Type Validation**: Only allowed extensions (`.pdf`, `.docx`, `.pptx`, `.txt`, `.jpg`, `.jpeg`, `.png`, `.avif`, `.tiff`, `.tif`)
3. **File Size Limits**: Maximum 50MB per file (configurable)
4. **API Key Security**: Loaded from environment, never hardcoded

## Project Structure

```
mistralocr/
├── mcp_server.py              # Server entry point
├── requirements.txt           # Dependencies
├── .env.example              # Environment template
├── claude_desktop_config.json # Claude Desktop config
├── README.md
└── src/mistralocr/
    ├── __init__.py           # Package exports
    ├── constants.py          # Extensions, MIME types, limits
    ├── models.py             # Pydantic response models
    ├── config.py             # Settings from environment
    ├── utils.py              # Shared utilities
    ├── document_source.py    # Abstract source interface
    ├── file_source.py        # Local file handler
    ├── url_source.py         # URL handler (SSRF protected)
    ├── source_factory.py     # Factory for sources
    ├── ocr_client.py         # Mistral API wrapper
    ├── markdown_writer.py    # Markdown output
    └── tools.py              # MCP tool definitions
```

## Example Usage

### Python Client

```python
from mcp import ClientSession, StdioServerParameters
from pathlib import Path

async def process_document():
    # Connect to MCP server
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"],
        env={"MISTRAL_API_KEY": "your_key"}
    )

    async with ClientSession(server_params) as session:
        # Initialize session
        await session.initialize()

        # Process a PDF
        result = await session.call_tool(
            "ocr_process_file",
            arguments={
                "file_path": "/path/to/document.pdf",
                "include_images": False
            }
        )

        print(f"Pages processed: {result['total_pages']}")
        for page in result['pages']:
            print(f"Page {page['index']}: {page['markdown'][:100]}...")
```

## Limitations

- Maximum file size: 50MB (configurable via `MAX_FILE_SIZE_MB`)
- Maximum pages: 1,000 pages (Mistral API limit)
- Supported formats: PDF, JPG, JPEG, PNG, AVIF

## Troubleshooting

### "MISTRAL_API_KEY environment variable is required"

**For Claude Desktop users:**
Make sure you've added the `env` section with `MISTRAL_API_KEY` in your
`claude_desktop_config.json` file. Check the configuration in the Installation section.

**For local testing:**
Create a `.env` file with your API key:
```bash
echo "MISTRAL_API_KEY=your_key_here" > .env
```

### "File not found" error

Ensure you're using absolute paths:
```bash
# Use absolute path
/Users/username/Documents/file.pdf

# NOT relative path
~/Documents/file.pdf
```

### Tools not appearing in Claude Desktop

1. Check that Claude Desktop configuration JSON is valid
2. Verify the Python path is correct: `/opt/miniconda3/envs/deep-learning/bin/python`
3. Check Claude Desktop logs: Help → Developer → View Logs
4. Restart Claude Desktop after updating configuration

### "File too large" error

Reduce file size or increase the limit in Claude Desktop's `env` section:
```json
"env": {
  "MISTRAL_API_KEY": "your_key",
  "MAX_FILE_SIZE_MB": "100"
}
```

## License

MIT

## Credits

Built with:
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Mistral AI](https://mistral.ai/) OCR API
- [FastMCP](https://github.com/jlowin/fastmcp)
