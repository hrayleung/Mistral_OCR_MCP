# Mistral OCR MCP Server

A Model Context Protocol (MCP) server that provides PDF and image OCR capabilities using Mistral's OCR API. This server exposes tools for extracting text and structure from documents, returning structured JSON results with page-by-page metadata.

## Features

- **Single File OCR**: Process individual PDFs and images (JPG, PNG, AVIF)
- **Batch Processing**: Process multiple files sequentially with error recovery
- **Structured Output**: Returns JSON with page numbers, text, dimensions, and image coordinates
- **Secure File Handling**: Path traversal prevention, file type validation, and size limits
- **Progress Reporting**: Real-time feedback during document processing

## Installation

### Prerequisites

- Python 3.8+
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
           "MISTRAL_API_KEY": "your_mistral_api_key_here"
         }
       }
     }
   }
   ```

   Replace `your_mistral_api_key_here` with your actual Mistral API key.

   **For local testing only (optional):**
   ```bash
   cp .env.example .env
   # Edit .env and uncomment MISTRAL_API_KEY for local testing
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

Process a single file (PDF or image) with OCR.

**Parameters:**
- `file_path` (string, required): Absolute path to the file
- `include_images` (boolean, optional): Include base64-encoded images (default: false)

**Returns:**
```json
{
  "success": true,
  "file_path": "/path/to/document.pdf",
  "file_type": "pdf",
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
  "error_message": null
}
```

### `ocr_batch_process`

Process multiple files with OCR in batch.

**Parameters:**
- `file_paths` (array of strings, required): List of absolute file paths
- `include_images` (boolean, optional): Include base64-encoded images (default: false)

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
  "formats": [".pdf", ".jpg", ".jpeg", ".png", ".avif"],
  "max_file_size_mb": 50
}
```

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

## Security

The server implements several security measures:

1. **Path Traversal Prevention**: All file paths are validated and resolved
2. **File Type Validation**: Only allowed extensions (`.pdf`, `.jpg`, `.jpeg`, `.png`, `.avif`)
3. **File Size Limits**: Maximum 50MB per file (configurable)
4. **API Key Security**: Loaded from environment, never hardcoded

## Project Structure

```
mistralocr/
├── mcp_server.py                # Main server entry point
├── requirements.txt             # Python dependencies
├── .env.example                # Environment variables template (for local testing)
├── claude_desktop_config.json  # Claude Desktop configuration template
├── README.md                   # This file
└── src/
    └── mistralocr/
        ├── __init__.py       # Package initialization
        ├── config.py         # Configuration management
        ├── file_handler.py   # Secure file validation
        ├── ocr_client.py     # Mistral API wrapper
        └── tools.py          # MCP tool definitions
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
