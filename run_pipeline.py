from __future__ import annotations

import argparse

from se_claims_tool.logging_utils import setup_logger
from se_claims_tool.config import RunConfig
from se_claims_tool.batch_pipeline import run_corpus
from se_claims_tool.llm.claim_detector import RuleBasedClaimDetector


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", required=True, help="Folder containing EPUB/AZW3 books")
    parser.add_argument("--output", required=True, help="Output CSV path, like out/all_claims.csv")
    parser.add_argument("--pilot_books", default="", help="Comma-separated stems or filenames to run as pilot")
    parser.add_argument("--log_level", default="INFO")
    args = parser.parse_args()

    logger = setup_logger(args.log_level)

    out_csv = args.output
    outdir = out_csv.rsplit("/", 1)[0] if "/" in out_csv else "out"

    cfg = RunConfig()
    detector = RuleBasedClaimDetector()

    pilot_books = [x.strip() for x in (args.pilot_books or "").split(",") if x.strip()]

    run_corpus(
        inputs=args.input_dir,
        outdir=outdir,
        cfg=cfg,
        detector=detector,
        logger=logger,
        pilot_books=pilot_books if pilot_books else None,
    )

    logger.info(f"Done. Your combined CSV is in: {outdir}/all_claims.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
