from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, List

import fitz

from .common import compute_book_id, normalize_whitespace
from .structures import ParagraphBlock


_NOISE_RE = re.compile(
    r"^(?:downloaded\s+by|licensed\s+to|taylor\s*&?\s*francis|"
    r"routledge|crc\s+press|vitalsource|all\s+rights\s+reserved|"
    r"©|\d{4}\s+(?:taylor|routledge|crc)|"
    r"this\s+(?:article|chapter|book)\s+was\s+downloaded)",
    re.IGNORECASE,
)

# Single short line that looks like a header/page artifact
_HEADER_RE = re.compile(r"^.{1,60}$")
_PAGE_NUM_RE = re.compile(r"^\d{1,4}$")


def _is_noise(text: str) -> bool:
    if len(text) < 40:
        return True
    if _PAGE_NUM_RE.match(text.strip()):
        return True
    if _NOISE_RE.search(text):
        return True
    return False


def _extract_paragraphs(page: fitz.Page) -> List[str]:
    """
    Use PyMuPDF block-level extraction instead of raw text.
    Each block is a natural paragraph unit — avoids header/body merging.
    """
    blocks = page.get_text("blocks")  # returns (x0, y0, x1, y1, text, block_no, block_type)
    paras = []
    for block in sorted(blocks, key=lambda b: (b[1], b[0])):  # sort top-to-bottom, left-to-right
        if block[6] != 0:  # skip non-text blocks (images etc)
            continue
        text = block[4].replace("\u00ad", "")  # soft hyphen
        text = normalize_whitespace(" ".join(text.split()))
        if text:
            paras.append(text)
    return paras


def ingest_pdf_paragraphs(path: str, logger) -> Iterator[ParagraphBlock]:
    p = Path(path)
    book_id = compute_book_id(path)
    book_title = p.stem.replace("-", " ").replace("_", " ")
    para_idx = 0

    doc = fitz.open(path)
    try:
        meta = doc.metadata or {}
        if meta.get("title"):
            book_title = normalize_whitespace(str(meta["title"]))

        for page_i in range(len(doc)):
            try:
                for para in _extract_paragraphs(doc[page_i]):
                    if _is_noise(para):
                        continue

                    yield ParagraphBlock(
                        book_id=book_id,
                        book_title=book_title,
                        source_path=p.name,
                        spine_index=page_i,
                        chapter_title=f"Page {page_i + 1}",
                        section_title="",
                        paragraph_index=para_idx,
                        paragraph_text=para,
                        ebook_locator=f"pdf:page={page_i + 1};para={para_idx}",
                    )
                    para_idx += 1

            except Exception as e:
                logger.warning(f"Page {page_i + 1} failed: {e}")
    finally:
        doc.close()