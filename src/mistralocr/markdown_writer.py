"""
Markdown file writer for OCR results.

Handles formatting and persistence of OCR results to markdown files
with rich metadata and conflict resolution via timestamps.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarkdownWriteResult:
    """Result of markdown file write operation."""
    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None


@dataclass
class MarkdownFormatConfig:
    """Configuration for markdown formatting."""
    include_metadata: bool = True
    include_page_headers: bool = True
    include_dimensions: bool = True
    include_image_metadata: bool = True
    include_toc: bool = True
    timestamp_format: str = "%Y%m%d_%H%M%S"


class MarkdownWriter:
    """
    Writes OCR results to markdown files with rich formatting.

    Features:
    - Automatic conflict resolution via timestamps
    - Rich metadata (page headers, dimensions, model info)
    - Batch processing with separate files
    - Configurable output directory
    - Graceful error handling
    """

    def __init__(
        self,
        output_dir: str,
        config: Optional[MarkdownFormatConfig] = None
    ):
        """
        Initialize MarkdownWriter.

        Args:
            output_dir: Directory path for markdown files (created if missing)
            config: Formatting configuration (uses defaults if None)

        Raises:
            ValueError: If output_dir is invalid or cannot be created
        """
        self.output_dir = Path(output_dir).resolve()
        self.config = config or MarkdownFormatConfig()

        # Validate output directory is within safe bounds (user's home directory)
        user_home = Path.home()
        try:
            self.output_dir.relative_to(user_home)
        except ValueError:
            raise ValueError(
                f"Output directory must be within user home directory: {user_home}"
            )

        # Ensure output directory exists
        self._ensure_output_directory()

    def write_ocr_result(
        self,
        ocr_result: Dict,
        base_filename: Optional[str] = None
    ) -> MarkdownWriteResult:
        """
        Write a single OCR result to markdown file.

        Args:
            ocr_result: OCR result dictionary (from MistralOCRClient or OCRResult model)
            base_filename: Base filename without extension (derived from source if None)

        Returns:
            MarkdownWriteResult with success status and file path
        """
        try:
            # Validate required fields
            required_fields = ['file_path', 'file_type', 'model', 'pages', 'images']
            for field in required_fields:
                if field not in ocr_result:
                    return MarkdownWriteResult(
                        success=False,
                        file_path=None,
                        error=f"Missing required field: {field}"
                    )

            # Extract metadata
            file_path = ocr_result.get('file_path', 'unknown')
            file_type = ocr_result.get('file_type', 'unknown')
            model = ocr_result.get('model', 'unknown')
            pages = ocr_result.get('pages', [])
            images = ocr_result.get('images', [])

            # Generate base filename from source if not provided
            if base_filename is None:
                base_filename = self._derive_base_filename(file_path)

            # Generate conflict-free filename
            target_path = self._generate_filepath(base_filename)

            # Format markdown content
            markdown_content = self._format_markdown(
                source_file=file_path,
                file_type=file_type,
                model=model,
                pages=pages,
                images=images,
                timestamp=datetime.now()
            )

            # Write to file
            target_path.write_text(markdown_content, encoding='utf-8')

            return MarkdownWriteResult(
                success=True,
                file_path=str(target_path),
                error=None
            )

        except PermissionError:
            logger.error(f"Permission denied writing to {self.output_dir}", exc_info=True)
            return MarkdownWriteResult(
                success=False,
                file_path=None,
                error="Permission denied writing to output directory"
            )
        except Exception as e:
            logger.error(f"Failed to write markdown: {str(e)}", exc_info=True)
            return MarkdownWriteResult(
                success=False,
                file_path=None,
                error="Failed to write markdown file. Check logs for details."
            )

    def write_batch_results(
        self,
        batch_results: List[Dict],
        batch_name: Optional[str] = None
    ) -> Dict[str, MarkdownWriteResult]:
        """
        Write multiple OCR results to separate markdown files.

        Args:
            batch_results: List of OCR result dictionaries
            batch_name: Optional batch identifier for grouping

        Returns:
            Dictionary mapping source file paths to write results
        """
        write_results = {}

        for idx, ocr_result in enumerate(batch_results):
            source_file = ocr_result.get('file_path', f'file_{idx}')

            # Generate unique filename for batch
            if batch_name:
                base_filename = f"{batch_name}_{idx:02d}_{self._derive_base_filename(source_file)}"
            else:
                base_filename = f"{idx:02d}_{self._derive_base_filename(source_file)}"

            write_results[source_file] = self.write_ocr_result(
                ocr_result=ocr_result,
                base_filename=base_filename
            )

        return write_results

    # ========================================================================
    # Private Methods - File Management
    # ========================================================================

    def _ensure_output_directory(self) -> None:
        """Create output directory if it doesn't exist."""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ValueError(
                f"Cannot create output directory {self.output_dir}: {str(e)}"
            )

    def _derive_base_filename(self, file_path: str) -> str:
        """
        Extract base filename from source file path.

        Args:
            file_path: Source file path

        Returns:
            Base filename without extension (e.g., "document" from "/path/to/document.pdf")
        """
        path = Path(file_path)
        stem = path.stem

        if not stem or stem in ('.', '..'):
            # Generate unique identifier for unnamed files
            import hashlib
            hash_obj = hashlib.md5(file_path.encode())
            return f"unnamed_{hash_obj.hexdigest()[:8]}"

        # Sanitize filename: remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            stem = stem.replace(char, '_')

        return stem

    def _generate_filepath(self, base_filename: str) -> Path:
        """
        Generate conflict-free filepath with timestamp if needed.

        Args:
            base_filename: Base filename without extension

        Returns:
            Resolved Path object with unique filename
        """
        # Try base filename first
        candidate = self.output_dir / f"{base_filename}.md"

        if not candidate.exists():
            return candidate

        # Add timestamp for conflict resolution
        timestamp = datetime.now().strftime(self.config.timestamp_format)
        candidate = self.output_dir / f"{base_filename}_{timestamp}.md"

        # Handle unlikely race condition with counter
        counter = 0
        while candidate.exists():
            counter += 1
            candidate = self.output_dir / f"{base_filename}_{timestamp}_{counter}.md"

        return candidate

    # ========================================================================
    # Private Methods - Markdown Formatting
    # ========================================================================

    def _format_markdown(
        self,
        source_file: str,
        file_type: str,
        model: str,
        pages: List[Dict],
        images: List[Dict],
        timestamp: datetime
    ) -> str:
        """
        Format OCR result as markdown document.

        Args:
            source_file: Original source file path
            file_type: File type (pdf/image)
            model: OCR model used
            pages: List of page results
            images: List of extracted images
            timestamp: Processing timestamp

        Returns:
            Complete markdown document as string
        """
        lines = []

        # Document header with YAML frontmatter
        if self.config.include_metadata:
            lines.extend(self._format_document_header(
                source_file, file_type, model, timestamp
            ))

        # Table of contents (if multiple pages)
        if len(pages) > 1 and self.config.include_toc:
            lines.extend(self._format_table_of_contents(pages))

        # Page content
        for page in pages:
            lines.extend(self._format_page(page))

        # Image metadata section
        if images and self.config.include_image_metadata:
            lines.extend(self._format_image_section(images))

        # Footer
        if self.config.include_metadata:
            lines.extend(self._format_footer())

        return '\n'.join(lines)

    def _format_document_header(
        self,
        source_file: str,
        file_type: str,
        model: str,
        timestamp: datetime
    ) -> List[str]:
        """Format document metadata header with YAML frontmatter."""
        lines = [
            "---",
            f"source: {source_file}",
            f"type: {file_type}",
            f"model: {model}",
            f"processed: {timestamp.isoformat()}",
            "---",
            "",
            f"# Document: {Path(source_file).name}",
            ""
        ]
        return lines

    def _format_table_of_contents(self, pages: List[Dict]) -> List[str]:
        """Format table of contents for multi-page documents."""
        lines = [
            "## Table of Contents",
            ""
        ]

        for page in pages:
            page_num = page.get('index', 0) + 1
            # Create anchor-friendly heading
            lines.append(f"- [Page {page_num}](#page-{page_num})")

        lines.append("")
        return lines

    def _format_page(self, page: Dict) -> List[str]:
        """Format individual page content."""
        index = page.get('index', 0)
        markdown = page.get('markdown', '')
        dimensions = page.get('dimensions')

        lines = []

        # Page header
        if self.config.include_page_headers:
            lines.append(f"## Page {index + 1}")
            lines.append("")

            # Add dimensions if available
            if dimensions and self.config.include_dimensions:
                lines.append("*Metadata:*")
                lines.append(f"- Width: {dimensions.get('width', 'N/A')}")
                lines.append(f"- Height: {dimensions.get('height', 'N/A')}")
                lines.append(f"- DPI: {dimensions.get('dpi', 'N/A')}")
                lines.append("")

        # Page content
        lines.append(markdown)
        lines.append("")

        return lines

    def _format_image_section(self, images: List[Dict]) -> List[str]:
        """Format extracted images metadata section."""
        lines = [
            "---",
            "",
            "## Extracted Images",
            "",
            f"Total images found: {len(images)}",
            ""
        ]

        for idx, image in enumerate(images, 1):
            lines.append(f"### Image {idx}")
            lines.append("")
            lines.append(f"- **ID**: `{image.get('id', 'N/A')}`")

            # Validate and format coordinates
            x1, y1 = image.get('top_left_x', 0), image.get('top_left_y', 0)
            x2, y2 = image.get('bottom_right_x', 0), image.get('bottom_right_y', 0)

            lines.append(f"- **Position**: ({x1}, {y1}) to ({x2}, {y2})")

            # Validate size calculation to prevent negative values
            width = max(0, x2 - x1)
            height = max(0, y2 - y1)
            lines.append(f"- **Size**: {width} × {height} pixels")
            lines.append("")

        return lines

    def _format_footer(self) -> List[str]:
        """Format document footer."""
        lines = [
            "---",
            "",
            "*Generated by Mistral OCR MCP Server*",
            ""
        ]
        return lines
