"""
Utilities for saving extracted images to disk.
"""

import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .utils import sanitize_filename

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageWriteSummary:
    written: int
    skipped: int
    failed: int
    assets_dir: str


class ImageWriter:
    def __init__(self, assets_dir: Path, link_base_dir: Optional[Path] = None):
        self.assets_dir = assets_dir.resolve()
        self.link_base_dir = link_base_dir.resolve() if link_base_dir else None
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def write_images(self, images: Iterable[dict]) -> tuple[list[dict], ImageWriteSummary]:
        written = 0
        skipped = 0
        failed = 0
        updated: list[dict] = []

        for img in images:
            img_id = str(img.get("id", "image"))
            img_b64: Optional[str] = img.get("image_base64")
            if not img_b64:
                skipped += 1
                updated.append(img)
                continue

            filename = sanitize_filename(Path(img_id).name or img_id, img_id)
            if not Path(filename).suffix:
                filename = f"{filename}.bin"

            out_path = self.assets_dir / filename
            try:
                if out_path.exists():
                    stem, suffix = out_path.stem, out_path.suffix
                    counter = 1
                    while out_path.exists():
                        out_path = self.assets_dir / f"{stem}_{counter:02d}{suffix}"
                        counter += 1
                out_path.write_bytes(base64.b64decode(img_b64))
                written += 1
                image_path = str(out_path)
                if self.link_base_dir:
                    try:
                        image_path = out_path.relative_to(self.link_base_dir).as_posix()
                    except Exception:
                        pass
                updated.append({**img, "image_path": image_path})
            except Exception as e:
                failed += 1
                logger.warning(f"Failed to write image {img_id}: {e}")
                updated.append(img)

        return updated, ImageWriteSummary(written, skipped, failed, str(self.assets_dir))
