from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParagraphBlock:
    book_id: str
    book_title: str
    source_path: str

    spine_index: int
    chapter_title: str
    section_title: str

    paragraph_index: int
    paragraph_text: str

    ebook_locator: str  # stable, reproducible locator
