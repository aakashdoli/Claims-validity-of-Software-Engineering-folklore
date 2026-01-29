from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .candidate_filter import CandidateFilter
from .citations import decide_citation_status
from .config import RunConfig
from .ingest.epub_ingest import ingest_epub_paragraphs
from .ingest.azw3_ingest import ingest_azw3_paragraphs
from .ingest.structures import ParagraphBlock
from .models_rq1 import RQ1ClaimRow
from .tokenize import SentenceTokenizer


@dataclass
class _SentenceLike:
    text: str


def _ingest_paragraphs(input_path: str, cache_dir: str, logger) -> List[ParagraphBlock]:
    p = Path(input_path)
    suffix = p.suffix.lower()

    if suffix == ".epub":
        return list(ingest_epub_paragraphs(str(p), logger))
    if suffix == ".azw3":
        return list(ingest_azw3_paragraphs(str(p), cache_dir=cache_dir, logger=logger))

    raise ValueError(f"Unsupported file type: {suffix}. Only .epub and .azw3")


def extract_claim_rows_for_book(
    input_path: str,
    cfg: RunConfig,
    detector,
    logger,
    cache_dir: str,
) -> Tuple[List[RQ1ClaimRow], Dict[str, Any]]:
    """
    Book-level pipeline for RQ1 tool output (one row per claim).
    claim_id is assigned later at corpus level to ensure global uniqueness.
    """
    tok = SentenceTokenizer(language=cfg.language)
    cand_filter = CandidateFilter(cfg)

    paragraphs = _ingest_paragraphs(input_path, cache_dir=cache_dir, logger=logger)

    rows: List[RQ1ClaimRow] = []
    tested = 0

    for pb in paragraphs:
        sentences = tok.split(pb.paragraph_text)

        if not pb.section_title:
            logger.warning(f"Missing section title: {pb.source_path} spine={pb.spine_index} para={pb.paragraph_index}")

        for s_i, sent_text in enumerate(sentences):
            if not cand_filter.is_candidate_text(sent_text):
                continue

            if cfg.max_llm_calls is not None and tested >= cfg.max_llm_calls:
                logger.warning("Max sentence tests reached; stopping detection.")
                break

            tested += 1
            res = detector.detect(_SentenceLike(sent_text))
            if not res.is_claim:
                continue

            decision = decide_citation_status(
                paragraph_text=pb.paragraph_text,
                sentences=sentences,
                claim_sentence_index=s_i,
            )

            section = pb.section_title or ""
            location_text = f"{pb.chapter_title} > {section} > para {pb.paragraph_index}"

            rows.append(
                RQ1ClaimRow(
                    claim_id="",  # assigned globally later
                    book_id=pb.book_id,
                    book_title=pb.book_title,
                    chapter_title=pb.chapter_title,
                    section_title=section,
                    paragraph_index=pb.paragraph_index,
                    location_text=location_text,
                    ebook_locator=pb.ebook_locator,
                    claim_text=sent_text,
                    sentence_index=s_i,
                    citation_status=decision.citation_status,
                    citation_marker_text=decision.citation_marker_text,
                    citation_marker_location_text=decision.citation_marker_location_text,
                    citation_context=decision.citation_context,
                    confidence=float(getattr(res, "confidence", 0.0) or 0.0),
                    notes="",
                    verified="",
                    verifier="",
                    verification_notes="",
                )
            )

    meta = {
        "input": str(Path(input_path).name),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "language": cfg.language,
        "max_llm_calls": cfg.max_llm_calls,
        "paragraphs_total": len(paragraphs),
        "candidates_tested": tested,
        "claims_found": len(rows),
    }
    return rows, meta
