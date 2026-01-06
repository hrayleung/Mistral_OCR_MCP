"""
Markdown file writer for OCR results.
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from urllib.parse import urlparse

from .utils import extract_filename_from_url, sanitize_filename

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarkdownWriteResult:
    """Result of markdown write operation."""
    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None


class MarkdownWriter:
    """Writes OCR results to markdown files."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir).resolve()
        self._ensure_dir()

    def write_ocr_result(
        self, ocr_result: Dict, base_filename: Optional[str] = None
    ) -> MarkdownWriteResult:
        """Write single OCR result to markdown."""
        try:
            required = ['file_path', 'file_type', 'model', 'pages', 'images']
            if missing := [f for f in required if f not in ocr_result]:
                return MarkdownWriteResult(False, error=f"Missing: {missing}")

            base = base_filename or self._derive_filename(ocr_result['file_path'])
            path = self._generate_path(base)
            content = self._format(ocr_result, datetime.now())
            path.write_text(content, encoding='utf-8')

            return MarkdownWriteResult(True, str(path))
        except Exception as e:
            logger.exception("Failed to write markdown")
            return MarkdownWriteResult(False, error=str(e))

    def write_batch_results(
        self, batch_results: List[Dict], batch_name: Optional[str] = None
    ) -> Dict[str, MarkdownWriteResult]:
        """Write multiple OCR results."""
        results = {}
        for idx, result in enumerate(batch_results):
            source = result.get('file_path', f'file_{idx}')
            base = f"{batch_name}_{idx:02d}_{self._derive_filename(source)}" if batch_name else None
            results[source] = self.write_ocr_result(result, base)
        return results

    def _ensure_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _derive_filename(self, file_path: str) -> str:
        if file_path.startswith(('http://', 'https://')):
            return sanitize_filename(extract_filename_from_url(file_path), file_path)
        return sanitize_filename(Path(file_path).stem, file_path)

    def _generate_path(self, base: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:8]
        return self.output_dir / f"{base}_{ts}_{uid}.md"

    def _format(self, result: Dict, timestamp: datetime) -> str:
        source = result['file_path']
        pages = result['pages']
        images = result['images']

        # Header
        if source.startswith(('http://', 'https://')):
            doc_name = Path(urlparse(source).path).name or "document"
        else:
            doc_name = Path(source).name

        lines = [
            "---",
            f"source: {source}",
            f"type: {result['file_type']}",
            f"model: {result['model']}",
            f"processed: {timestamp.isoformat()}",
            f"total_images: {len(images)}",
            "---", "",
            f"# Document: {doc_name}", ""
        ]

        # Summary
        if images:
            lines.extend([
                f"**Summary:** {len(pages)} pages, {len(images)} figures/charts/images extracted",
                ""
            ])

        # TOC
        if len(pages) > 1:
            lines.extend(["## Table of Contents", ""])
            lines.extend(f"- [Page {p.get('index', 0) + 1}](#page-{p.get('index', 0) + 1})" for p in pages)
            if images:
                lines.append("- [Extracted Figures & Images](#extracted-figures--images)")
            lines.append("")

        # Pages
        for page in pages:
            idx = page.get('index', 0)
            lines.extend([f"## Page {idx + 1}", ""])
            if dims := page.get('dimensions'):
                lines.extend([
                    "*Metadata:*",
                    f"- Width: {dims.get('width', 'N/A')}",
                    f"- Height: {dims.get('height', 'N/A')}",
                    f"- DPI: {dims.get('dpi', 'N/A')}", ""
                ])

            # Note images on this page
            page_images = page.get('images', [])
            if page_images:
                lines.append(f"*Images on this page: {len(page_images)}*")
                lines.append("")

            lines.extend([page.get('markdown', ''), ""])

        # Images/Figures section
        if images:
            lines.extend([
                "---", "",
                "## Extracted Figures & Images", "",
                f"Total: {len(images)} figures, charts, and images extracted from document.",
                ""
            ])

            # Group by page
            images_by_page: Dict[int, List] = {}
            for img in images:
                page_idx = img.get('page_index', 0)
                if page_idx not in images_by_page:
                    images_by_page[page_idx] = []
                images_by_page[page_idx].append(img)

            for page_idx in sorted(images_by_page.keys()):
                page_imgs = images_by_page[page_idx]
                lines.extend([f"### Page {page_idx + 1} Images", ""])

                for img in page_imgs:
                    img_id = img.get('id', 'unknown')
                    width = img.get('width', 0)
                    height = img.get('height', 0)
                    x1, y1 = img.get('top_left_x', 0), img.get('top_left_y', 0)
                    x2, y2 = img.get('bottom_right_x', 0), img.get('bottom_right_y', 0)

                    lines.extend([
                        f"#### {img_id}", "",
                        f"- **Size**: {width} × {height} pixels",
                        f"- **Position**: ({x1}, {y1}) to ({x2}, {y2})",
                    ])

                    # If base64 data available, note it
                    if img.get('image_base64'):
                        lines.append(f"- **Data**: Base64 encoded ({len(img['image_base64'])} chars)")

                    lines.append("")

        lines.extend(["---", "", "*Generated by Mistral OCR MCP Server*", ""])
        return '\n'.join(lines)
