"""
pipeline.py
-----------
Two-stage claim extraction pipeline.

Stage 1 — NLP Pre-filter (fast, free, high recall):
    - Splits book into sentences
    - Keeps sentences matching claim patterns (normative, causal, etc.)
    - Attaches prev/next sentence context to each candidate

Stage 2 — LLM Filter (precise, literature-grounded):
    - Sends candidates + context to Azure OpenAI (gpt-4o-mini)
    - LLM decides: is this a genuine claim? what type?
    - Only confirmed claims are written to output

Design decisions from thesis meetings:
    - "Pass the claim along with a couple of surrounding sentences" — Davide Fucci
    - "Focus on precision over recall" — Davide Fucci, Meeting 4
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pysbd

from .config import RunConfig
from .citations import decide_citation_status
from .ingest.common import compute_book_id
from .ingest.epub_ingest import ingest_epub_paragraphs
from .ingest.azw3_ingest import ingest_azw3_paragraphs
from .models_rq1 import RQ1ClaimRow
from .nlp.claim_detector import NLPClaimDetector
from .llm.azure_llm_filter import AzureLLMFilter, LLMFilterResult

SUPPORTED = {".epub", ".azw3"}


def _sentence_split(paragraph_text: str) -> List[str]:
    seg = pysbd.Segmenter(language="en", clean=True)
    sents = seg.segment(paragraph_text or "")
    return [s.strip() for s in sents if (s or "").strip()]


def _pick_ingestor(path: str):
    suffix = Path(path).suffix.lower()
    if suffix == ".epub":
        return ingest_epub_paragraphs
    if suffix == ".azw3":
        return ingest_azw3_paragraphs
    raise ValueError(f"Unsupported format: {suffix}")


def _format_candidate_id(book_idx: int, sent_idx: int) -> str:
    return f"C-{book_idx:04d}-{sent_idx:06d}"


def extract_claims_for_book(
    input_path: str,
    cfg: RunConfig,
    llm_filter: Optional[AzureLLMFilter],
    logger,
    cache_dir: Optional[str] = None,
    book_idx: int = 0,
) -> Tuple[List[RQ1ClaimRow], Dict[str, Any]]:
    """
    Two-stage extraction for a single book.
    Returns (claim_rows, metadata_dict)
    """
    p = Path(input_path)
    if p.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Only .epub and .azw3 are supported, got: {p.suffix}")

    ingestor = _pick_ingestor(input_path)
    book_id = compute_book_id(input_path)
    nlp_detector = NLPClaimDetector()

    # ── Stage 1: Ingest + NLP pre-filter ──────────────────────────────────────
    logger.info(f"[Stage 1] NLP pre-filter: {p.name}")

    all_sentences = []  # list of (sent_text, block, si_in_para, all_sents_in_para)

    ingest_kwargs = {"logger": logger}
    if p.suffix.lower() == ".azw3":
        if not cache_dir:
            cache_dir = str(p.parent / "_converted_cache")
        ingest_kwargs["cache_dir"] = cache_dir

    paragraphs_total = 0
    for block in ingestor(input_path, **ingest_kwargs):
        paragraphs_total += 1
        paragraph_text = (block.paragraph_text or "").strip()
        if not paragraph_text:
            continue
        sentences = _sentence_split(paragraph_text)
        for si, sent in enumerate(sentences):
            all_sentences.append((sent, block, si, sentences))

    logger.info(f"[Stage 1] Total sentences extracted: {len(all_sentences)}")

    # NLP filter — high recall, loose
    candidates = []
    candidate_meta = {}
    global_sent_idx = 0

    for idx, (sent_text, block, si, sentences) in enumerate(all_sentences):
        global_sent_idx += 1
        nlp_result = nlp_detector.detect(sent_text)
        if not nlp_result.is_candidate:
            continue

        cid = _format_candidate_id(book_idx, global_sent_idx)
        prev_sentence = sentences[si - 1] if si > 0 else ""
        next_sentence = sentences[si + 1] if si < len(sentences) - 1 else ""

        candidates.append({
            "candidate_id":       cid,
            "prev_sentence":      prev_sentence,
            "candidate_sentence": sent_text,
            "next_sentence":      next_sentence,
            "nlp_type":           nlp_result.claim_type,
        })
        candidate_meta[cid] = (sent_text, block, si, sentences, nlp_result)

    logger.info(
        f"[Stage 1] NLP candidates: {len(candidates)} / {global_sent_idx} "
        f"({100*len(candidates)/max(global_sent_idx,1):.1f}%)"
    )

    # ── Stage 2: LLM filter ───────────────────────────────────────────────────
    llm_decisions: Dict[str, LLMFilterResult] = {}

    if llm_filter and candidates:
        logger.info(f"[Stage 2] Sending {len(candidates)} candidates to Azure LLM...")
        llm_decisions = llm_filter.filter_candidates(candidates, logger=logger)
    else:
        if not llm_filter:
            logger.info("[Stage 2] LLM skipped — no API configured. Using NLP results only.")
        for c in candidates:
            nlp_res = candidate_meta[c["candidate_id"]][4]
            llm_decisions[c["candidate_id"]] = LLMFilterResult(
                candidate_id=c["candidate_id"],
                is_claim=True,
                claim_type=nlp_res.claim_type,
                is_author_perspective=(nlp_res.claim_type == "AUTHOR_PERSPECTIVE"),
                confidence=0.6,
                reason="nlp_only_no_llm",
            )

    # ── Build output rows ──────────────────────────────────────────────────────
    rows: List[RQ1ClaimRow] = []
    claims_found = 0

    for c in candidates:
        cid = c["candidate_id"]
        decision = llm_decisions.get(cid)
        if not decision or not decision.is_claim:
            continue

        claims_found += 1
        sent_text, block, si, sentences, nlp_result = candidate_meta[cid]

        cite = decide_citation_status(
            paragraph_text=block.paragraph_text or "",
            sentences=sentences,
            claim_sentence_index=si,
        )

        chapter_title  = getattr(block, "chapter_title", "") or ""
        section_title  = getattr(block, "section_title", "") or ""
        para_index     = int(getattr(block, "paragraph_index", 0))
        locator        = getattr(block, "ebook_locator", "") or ""
        source_path    = getattr(block, "source_path", "") or p.name
        book_title_val = getattr(block, "book_title", p.stem)
        loc_text = f"{source_path} > {chapter_title} > {section_title} > para {para_index}".strip()

        notes = (
            f"nlp_type={nlp_result.claim_type}|"
            f"nlp_term={nlp_result.matched_term}|"
            f"llm_reason={decision.reason}"
        )

        rows.append(
            RQ1ClaimRow(
                claim_id="",
                book_id=book_id,
                book_title=book_title_val,
                chapter_title=chapter_title,
                section_title=section_title,
                paragraph_index=para_index,
                location_text=loc_text,
                ebook_locator=locator,
                claim_text=sent_text,
                prev_sentence=c.get("prev_sentence", ""),
                next_sentence=c.get("next_sentence", ""),
                sentence_index=si,
                citation_status=cite.citation_status,
                citation_marker_text=cite.citation_marker_text,
                citation_marker_location_text=cite.citation_marker_location_text,
                citation_context=cite.citation_context,
                nlp_claim_type=nlp_result.claim_type,
                nlp_matched_term=nlp_result.matched_term,
                llm_is_claim=str(decision.is_claim),
                llm_claim_type=decision.claim_type,
                llm_is_author_perspective=str(decision.is_author_perspective),
                llm_confidence=str(round(decision.confidence, 3)),
                llm_reason=decision.reason,
                llm_error=decision.error,
                confidence=decision.confidence,
                notes=notes,
                verified="",
                verifier="",
                verification_notes="",
            )
        )

    meta: Dict[str, Any] = {
        "input_file":       p.name,
        "book_id":          book_id,
        "paragraphs_total": paragraphs_total,
        "sentences_total":  global_sent_idx,
        "nlp_candidates":   len(candidates),
        "claims_found":     claims_found,
        "llm_used":         llm_filter is not None,
        "timestamp_utc":    datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        f"Book done: {p.name} | sentences={global_sent_idx} | "
        f"nlp_candidates={len(candidates)} | claims_confirmed={claims_found}"
    )
    return rows, meta
