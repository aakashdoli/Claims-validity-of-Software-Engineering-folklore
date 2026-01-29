from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterator

from .epub_ingest import ingest_epub_paragraphs
from .structures import ParagraphBlock


def ingest_azw3_paragraphs(path: str, cache_dir: str, logger) -> Iterator[ParagraphBlock]:
    """
    AZW3 ingestion via local conversion to EPUB using calibre (ebook-convert).
    This is deterministic given the same calibre version and input file.

    cache_dir is a folder where converted EPUBs will be stored.
    """
    p = Path(path)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)

    converter = shutil.which("ebook-convert")
    if not converter:
        raise RuntimeError(
            "AZW3 ingest requires calibre 'ebook-convert' on PATH. "
            "Install calibre locally and ensure ebook-convert is available."
        )

    out_epub = cache / f"{p.stem}.converted.epub"
    if not out_epub.exists():
        logger.info(f"Converting AZW3 to EPUB with calibre: {p.name}")
        cmd = [converter, str(p), str(out_epub)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                "Calibre conversion failed.\n"
                f"stdout: {proc.stdout}\n"
                f"stderr: {proc.stderr}"
            )

    yield from ingest_epub_paragraphs(str(out_epub), logger)
