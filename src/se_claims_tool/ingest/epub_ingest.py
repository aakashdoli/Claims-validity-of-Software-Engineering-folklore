from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from bs4 import BeautifulSoup
from ebooklib import epub

from .common import compute_book_id, normalize_whitespace
from .structures import ParagraphBlock


PARA_SELECTORS = ["p", "li", "blockquote"]
HEADING_SELECTORS = ["h1", "h2", "h3", "h4", "h5", "h6"]
BLOCK_SELECTORS = PARA_SELECTORS + HEADING_SELECTORS


def _read_book_title(book: epub.EpubBook, fallback: str) -> str:
    try:
        titles = book.get_metadata("DC", "title")
        if titles and titles[0] and titles[0][0]:
            return normalize_whitespace(str(titles[0][0]))
    except Exception:
        pass
    return fallback


def _extract_blocks_in_order(html: str) -> List[Tuple[str, str]]:
    """
    Returns list of (tag_name, text) in document order, limited to headings and paragraphs.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: List[Tuple[str, str]] = []

    for tag in soup.find_all(BLOCK_SELECTORS):
        text = tag.get_text(separator=" ", strip=True)
        text = normalize_whitespace(text)
        if not text:
            continue
        out.append((tag.name.lower(), text))
    return out


def ingest_epub_paragraphs(path: str, logger) -> Iterator[ParagraphBlock]:
    """
    Deterministic EPUB ingestion in spine order.
    Produces ParagraphBlock records with stable paragraph_index and ebook_locator.

    ebook_locator here is a safe equivalent (not a true CFI):
      epub:spine={spine_index};para={paragraph_index}
    """
    p = Path(path)
    book_id = compute_book_id(path)
    book = epub.read_epub(path)

    book_title = _read_book_title(book, fallback=p.stem)

    spine_ids = [item[0] for item in book.spine if isinstance(item, tuple) and item[0] != "nav"]
    items = []
    for sid in spine_ids:
        it = book.get_item_with_id(sid)
        if it:
            items.append(it)

    for spine_index, item in enumerate(items):
        try:
            content = item.get_content().decode("utf-8", errors="ignore")
        except Exception:
            logger.warning(f"EPUB spine item decode failed at spine_index={spine_index}")
            continue

        blocks = _extract_blocks_in_order(content)

        chapter_title = ""
        section_title = ""
        chapter_title_set = False
        paragraph_index = 0

        first_heading = None
        for tag_name, text in blocks:
            if tag_name in HEADING_SELECTORS:
                if first_heading is None:
                    first_heading = text
                if tag_name == "h1":
                    chapter_title = text
                    chapter_title_set = True
                    section_title = ""
                else:
                    section_title = text

        if not chapter_title_set:
            if first_heading:
                chapter_title = first_heading
                chapter_title_set = True
            else:
                chapter_title = item.get_name() or f"spine_{spine_index}"
                logger.warning(f"Chapter title fallback used for {p.name} spine_index={spine_index}")

        section_title = ""
        for tag_name, text in blocks:
            if tag_name in HEADING_SELECTORS:
                if tag_name == "h1":
                    chapter_title = text
                    section_title = ""
                else:
                    section_title = text
                continue

            if tag_name in PARA_SELECTORS:
                ebook_locator = f"epub:spine={spine_index};para={paragraph_index}"
                yield ParagraphBlock(
                    book_id=book_id,
                    book_title=book_title,
                    source_path=str(p.name),
                    spine_index=spine_index,
                    chapter_title=chapter_title,
                    section_title=section_title,
                    paragraph_index=paragraph_index,
                    paragraph_text=text,
                    ebook_locator=ebook_locator,
                )
                paragraph_index += 1
    return
