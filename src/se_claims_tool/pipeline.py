from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pysbd

from .citations import decide_citation_status
from .config import RunConfig
from .ingest.azw3_ingest import ingest_azw3_paragraphs
from .ingest.epub_ingest import ingest_epub_paragraphs
from .models_rq1 import RQ1ClaimRow
from .ingest.common import compute_book_id


SUPPORTED = {".epub", ".azw3"}


def _sentence_split(paragraph_text: str) -> List[str]:
    seg = pysbd.Segmenter(language="en", clean=True)
    sents = seg.segment(paragraph_text or "")
    out = []
    for s in sents:
        s = (s or "").strip()
        if s:
            out.append(s)
    return out


def _pick_ingestor(path: str):
    suffix = Path(path).suffix.lower()
    if suffix == ".epub":
        return ingest_epub_paragraphs
    if suffix == ".azw3":
        return ingest_azw3_paragraphs
    raise ValueError(f"Unsupported input format: {suffix}")


def extract_claim_rows_for_book(
    input_path: str,
    cfg: RunConfig,
    detector,
    logger,
    cache_dir: str | None = None,
) -> Tuple[List[RQ1ClaimRow], Dict[str, Any]]:
    p = Path(input_path)
    if p.suffix.lower() not in SUPPORTED:
        raise ValueError("Only .epub and .azw3 are supported for RQ1")

    ingestor = _pick_ingestor(input_path)

    rows: List[RQ1ClaimRow] = []
    paragraphs_total = 0
    candidates_tested = 0
    claims_found = 0

    book_id = compute_book_id(input_path)

    for block in ingestor(input_path, logger=logger):
        paragraphs_total += 1

        paragraph_text = (block.paragraph_text or "").strip()
        if not paragraph_text:
            continue

        sentences = _sentence_split(paragraph_text)
        if not sentences:
            continue

        for si, sent_text in enumerate(sentences):
            candidates_tested += 1

            # HARD GATE: only detector-approved sentences become CSV rows
            res = detector.detect(type("Sent", (), {"text": sent_text})())
            if not getattr(res, "is_claim", False):
                continue

            claims_found += 1

            cite = decide_citation_status(
                paragraph_text=paragraph_text,
                sentences=sentences,
                claim_sentence_index=si,
            )

            chapter_title = getattr(block, "chapter_title", "") or ""
            section_title = getattr(block, "section_title", "") or ""
            para_index = int(getattr(block, "paragraph_index", 0))
            locator = getattr(block, "ebook_locator", "") or ""

            source_path = getattr(block, "source_path", "") or p.name
            loc_text = f"{source_path} > {chapter_title} > {section_title} > para {para_index}".strip()

            raw = getattr(res, "raw", {})
            notes = ""
            if isinstance(raw, dict) and raw.get("reason"):
                notes = f"detector_reason={raw.get('reason')}"

            confidence = float(getattr(res, "confidence", 0.6) or 0.6)

            rows.append(
                RQ1ClaimRow(
                    claim_id="",  # assigned later in batch_pipeline
                    book_id=book_id,
                    book_title=getattr(block, "book_title", p.stem),
                    chapter_title=chapter_title,
                    section_title=section_title,
                    paragraph_index=para_index,
                    location_text=loc_text,
                    ebook_locator=locator,
                    claim_text=sent_text,
                    sentence_index=int(si),
                    citation_status=cite.citation_status,
                    citation_marker_text=cite.citation_marker_text,
                    citation_marker_location_text=cite.citation_marker_location_text,
                    citation_context=cite.citation_context,
                    confidence=confidence,
                    notes=notes,
                    verified="",
                    verifier="",
                    verification_notes="",
                )
            )

    meta: Dict[str, Any] = {
        "input_file": p.name,
        "book_id": book_id,
        "paragraphs_total": paragraphs_total,
        "candidates_tested": candidates_tested,
        "claims_found": claims_found,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        f"Book done: {p.name} paragraphs={paragraphs_total} candidates={candidates_tested} claims={claims_found}"
    )
    return rows, meta
