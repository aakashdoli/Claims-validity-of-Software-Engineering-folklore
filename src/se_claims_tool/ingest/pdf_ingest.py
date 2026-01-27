from __future__ import annotations

from pathlib import Path
from typing import Iterator, List

import pdfplumber

from ..models import SentenceRecord
from ..tokenize import SentenceTokenizer
from .common import compute_book_id, stable_hash, normalize_whitespace


def _split_into_paragraphs(page_text: str) -> List[str]:
    """
    Heuristic paragraph splitter for PDFs:
    - paragraphs separated by blank lines
    - join hard-wrapped lines inside paragraphs
    """
    page_text = page_text or ""
    page_text = page_text.replace("\r\n", "\n").replace("\r", "\n")
    chunks = [c.strip() for c in page_text.split("\n\n") if c.strip()]

    paras: List[str] = []
    for c in chunks:
        # Join hard-wrapped lines
        c = " ".join([ln.strip() for ln in c.split("\n") if ln.strip()])
        c = normalize_whitespace(c)
        if c:
            paras.append(c)
    return paras


def ingest_pdf(path: str, tokenizer: SentenceTokenizer) -> Iterator[SentenceRecord]:
    """
    PDF ingestion with deterministic ordering and stable IDs.
    Adds page_number (1-based).
    """
    book_id = compute_book_id(path)
    global_idx = 0

    with pdfplumber.open(path) as pdf:
        for page_i, page in enumerate(pdf.pages):
            page_number = page_i + 1  # 1-based for humans
            chapter_title = f"page_{page_number}"
            chapter_id = f"pdf_{page_number:04d}_{stable_hash(chapter_title)[:8]}"

            try:
                text = page.extract_text() or ""
                text = text.replace("\u00ad", "")  # remove soft hyphen
                text = normalize_whitespace(text)

                if not text:
                    continue

                paragraphs = _split_into_paragraphs(text)

                for p_i, para in enumerate(paragraphs):
                    paragraph_id = f"{chapter_id}_p{p_i:06d}"
                    sents = tokenizer.split(para)

                    for s_i, sent in enumerate(sents):
                        yield SentenceRecord(
                            book_id=book_id,
                            source_path=str(Path(path).name),
                            chapter_id=chapter_id,
                            chapter_title=chapter_title,
                            paragraph_id=paragraph_id,
                            sentence_index=s_i,
                            global_sentence_index=global_idx,
                            page_number=page_number,
                            spine_index=None,
                            text=sent,
                        )
                        global_idx += 1

            except Exception:
                # Let caller log; keep ingestion robust.
                continue
