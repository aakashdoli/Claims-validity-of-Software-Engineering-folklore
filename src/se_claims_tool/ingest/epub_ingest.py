from __future__ import annotations

from pathlib import Path
from typing import Iterator, List

from bs4 import BeautifulSoup
from ebooklib import epub

from ..models import SentenceRecord
from ..tokenize import SentenceTokenizer
from .common import compute_book_id, stable_hash, normalize_whitespace


BLOCK_SELECTORS = ["p", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"]


def _extract_paragraphs_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    paras: List[str] = []

    for tag in soup.find_all(BLOCK_SELECTORS):
        text = tag.get_text(separator=" ", strip=True)
        text = normalize_whitespace(text)
        if text:
            paras.append(text)

    return paras


def ingest_epub(path: str, tokenizer: SentenceTokenizer) -> Iterator[SentenceRecord]:
    """
    EPUB ingestion in spine order (deterministic).
    Adds spine_index (0-based), no real page number.
    """
    book_id = compute_book_id(path)
    book = epub.read_epub(path)

    # Deterministic ordering: use spine
    spine_ids = [item[0] for item in book.spine if isinstance(item, tuple) and item[0] != "nav"]
    items = []
    for sid in spine_ids:
        it = book.get_item_with_id(sid)
        if it:
            items.append(it)

    global_idx = 0

    for spine_index, item in enumerate(items):
        try:
            content = item.get_content().decode("utf-8", errors="ignore")
            chapter_title = item.get_name() or f"chapter_{spine_index}"
            chapter_id = f"epub_{spine_index:04d}_{stable_hash(chapter_title)[:8]}"

            paragraphs = _extract_paragraphs_from_html(content)

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
                        page_number=None,
                        spine_index=spine_index,
                        text=sent,
                    )
                    global_idx += 1

        except Exception:
            # Keep robust: skip broken chapter item
            continue
