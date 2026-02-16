from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Tuple

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
    soup = BeautifulSoup(html, "html.parser")
    out: List[Tuple[str, str]] = []
    for tag in soup.find_all(BLOCK_SELECTORS):
        text = normalize_whitespace(tag.get_text(separator=" ", strip=True))
        if not text:
            continue
        out.append((tag.name.lower(), text))
    return out


def ingest_epub_paragraphs(path: str, logger) -> Iterator[ParagraphBlock]:
    p = Path(path)
    book_id = compute_book_id(path)
    book = epub.read_epub(path)
    book_title = _read_book_title(book, fallback=p.stem)

    spine_ids = [item[0] for item in book.spine if isinstance(item, tuple) and item[0] != "nav"]
    items = [book.get_item_with_id(sid) for sid in spine_ids if book.get_item_with_id(sid) is not None]

    for spine_index, item in enumerate(items):
        try:
            content = item.get_content().decode("utf-8", errors="ignore")
        except Exception:
            logger.warning(f"EPUB decode failed at spine_index={spine_index}")
            continue

        blocks = _extract_blocks_in_order(content)

        # Maintain running headings within this spine item
        current_chapter = ""
        current_section = ""

        # Prefer first h1 as chapter if present, else first heading
        first_heading = ""
        for tag_name, text in blocks:
            if tag_name in HEADING_SELECTORS:
                first_heading = text
                break

        if first_heading:
            current_chapter = first_heading
        else:
            # fallback to file name for traceability, but warn
            current_chapter = item.get_name() or f"spine_{spine_index}"
            logger.warning(f"Chapter title fallback used: {p.name} spine_index={spine_index}")

        paragraph_index = 0

        for tag_name, text in blocks:
            if tag_name in HEADING_SELECTORS:
                # chapter heading
                if tag_name == "h1":
                    current_chapter = text
                    current_section = ""
                else:
                    current_section = text
                continue

            if tag_name in PARA_SELECTORS:
                ebook_locator = f"epub:spine={spine_index};para={paragraph_index}"
                yield ParagraphBlock(
                    book_id=book_id,
                    book_title=book_title,
                    source_path=str(p.name),
                    spine_index=spine_index,
                    chapter_title=current_chapter,
                    section_title=current_section,
                    paragraph_index=paragraph_index,
                    paragraph_text=text,
                    ebook_locator=ebook_locator,
                )
                paragraph_index += 1
