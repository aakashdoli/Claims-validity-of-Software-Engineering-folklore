from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, List

import fitz  # PyMuPDF — better word-spacing reconstruction than pdfplumber

from .common import compute_book_id, normalize_whitespace
from .structures import ParagraphBlock


_NOISE_RE = re.compile(
    r"downloaded\s+by|licensed\s+to|taylor\s*&?\s*francis|"
    r"routledge|crc\s+press|vitalsource|all\s+rights\s+reserved",
    re.IGNORECASE,
)


def _split_paragraphs(text: str) -> List[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
    result = []
    for chunk in chunks:
        line = normalize_whitespace(" ".join(ln.strip() for ln in chunk.split("\n") if ln.strip()))
        if line:
            result.append(line)
    return result


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
                page = doc[page_i]
                text = (page.get_text("text") or "").replace("\u00ad", "")
                if not text.strip():
                    continue

                for para in _split_paragraphs(text):
                    if len(para) < 30 or _NOISE_RE.search(para):
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
                logger.warning(f"Page {page_i + 1} extraction failed: {e}")
    finally:
        doc.close()