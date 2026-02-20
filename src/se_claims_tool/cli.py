from __future__ import annotations

import argparse
from pathlib import Path

from .batch_pipeline import run_corpus
from .config import RunConfig
from .llm.claim_detector import RuleBasedClaimDetector
from .logging_utils import setup_logger


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="se-claims-tool")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_batch = sub.add_parser(
        "extract-batch",
        help="Extract RQ1 folklore claim rows from an EPUB/AZW3 corpus (deterministic rule-based detector).",
    )
    p_batch.add_argument("--inputs", required=True, help="Folder path, .zip, or single .epub/.azw3")
    p_batch.add_argument("--outdir", required=True, help="Output directory")
    p_batch.add_argument("--max-calls", type=int, default=None, help="Cap detector invocations (debugging)")
    p_batch.add_argument("--pilot-books", default="", help="Comma-separated stems or filenames to run as pilot")
    p_batch.add_argument("--log-level", default="INFO")
    return p


def main() -> int:
    args = build_parser().parse_args()
    logger = setup_logger(args.log_level)

    outdir_path = Path(args.outdir)
    outdir_path.mkdir(parents=True, exist_ok=True)

    cfg = RunConfig(max_llm_calls=args.max_calls)  # Name kept for backwards compatibility

    detector = RuleBasedClaimDetector()

    pilot_books = [x.strip() for x in (args.pilot_books or "").split(",") if x.strip()]

    run_corpus(
        inputs=args.inputs,
        outdir=str(outdir_path),
        cfg=cfg,
        detector=detector,
        logger=logger,
        pilot_books=pilot_books if pilot_books else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
