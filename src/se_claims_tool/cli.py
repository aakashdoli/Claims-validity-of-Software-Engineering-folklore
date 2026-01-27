# src/se_claims_tool/cli.py
from __future__ import annotations

import argparse
from pathlib import Path

from .config import RunConfig
from .logging_utils import setup_logger

from .pipeline import extract_claims
from .batch_pipeline import run_corpus

from .export.exporter import write_jsonl, write_csv, write_metadata

from .llm.claim_detector import MockClaimDetector, AzureClaimDetector
from .llm.azure_client import AzureChatClient

from .eval.evaluator import run_evaluation


def cmd_extract(args) -> int:
    logger = setup_logger(args.log_level)
    cfg = RunConfig(
        max_llm_calls=args.max_calls,
        store_only_snippets=True,
    )

    if args.mock_llm:
        detector = MockClaimDetector()
    else:
        client = AzureChatClient()
        detector = AzureClaimDetector(client)

    claims, meta = extract_claims(args.input, cfg, detector, logger)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    write_jsonl(str(outdir / "claims.jsonl"), claims)
    write_csv(str(outdir / "claims.csv"), claims)
    write_metadata(str(outdir / "run_metadata.json"), meta)

    logger.info(f"Done. Wrote: {outdir/'claims.jsonl'} and {outdir/'claims.csv'}")
    return 0


def cmd_extract_batch(args) -> int:
    logger = setup_logger(args.log_level)
    cfg = RunConfig(
        max_llm_calls=args.max_calls,
        store_only_snippets=True,
    )

    if args.mock_llm:
        detector = MockClaimDetector()
    else:
        client = AzureChatClient()
        detector = AzureClaimDetector(client)

    run_corpus(
        inputs=args.inputs,
        outdir=args.outdir,
        cfg=cfg,
        detector=detector,
        logger=logger,
    )
    return 0


def cmd_eval(args) -> int:
    logger = setup_logger(args.log_level)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    run_evaluation(
        ai_claims_path=args.ai_claims,
        human_path=args.human,
        outdir=str(outdir),
        fuzzy=args.fuzzy,
        fuzzy_threshold=args.fuzzy_threshold,
        logger=logger,
    )
    logger.info("Evaluation complete.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="se-claims-tool")
    sub = p.add_subparsers(dest="cmd", required=True)

    # --- extract (single file) ---
    p_extract = sub.add_parser("extract", help="Extract causal claims from one EPUB/PDF")
    p_extract.add_argument("--input", required=True, help="Path to .epub or .pdf")
    p_extract.add_argument("--outdir", required=True, help="Output directory")
    p_extract.add_argument("--mock-llm", action="store_true", help="Run without Azure; deterministic mock detector")
    p_extract.add_argument("--max-calls", type=int, default=None, help="Cap LLM calls (cost control)")
    p_extract.add_argument("--log-level", default="INFO")
    p_extract.set_defaults(func=cmd_extract)

    # --- extract-batch (folder/zip/multi) ---
    p_batch = sub.add_parser("extract-batch", help="Extract claims from a folder, a ZIP, or a single book file")
    p_batch.add_argument("--inputs", required=True, help="Folder path, .zip, or single .epub/.pdf")
    p_batch.add_argument("--outdir", required=True, help="Output directory")
    p_batch.add_argument("--mock-llm", action="store_true", help="Run without Azure; deterministic mock detector")
    p_batch.add_argument("--max-calls", type=int, default=None, help="Cap LLM calls (cost control)")
    p_batch.add_argument("--log-level", default="INFO")
    p_batch.set_defaults(func=cmd_extract_batch)

    # --- eval (manual vs AI) ---
    p_eval = sub.add_parser("eval", help="Evaluate AI claims vs human ground-truth (Phase 2)")
    p_eval.add_argument("--ai-claims", required=True, help="Path to AI claims.csv or claims.jsonl")
    p_eval.add_argument("--human", required=True, help="Path to human CSV/XLSX ground-truth")
    p_eval.add_argument("--outdir", required=True, help="Output directory for eval results")
    p_eval.add_argument("--fuzzy", action="store_true", help="Enable fuzzy matching (exact is default)")
    p_eval.add_argument("--fuzzy-threshold", type=float, default=0.92, help="Fuzzy threshold (0-1)")
    p_eval.add_argument("--log-level", default="INFO")
    p_eval.set_defaults(func=cmd_eval)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
