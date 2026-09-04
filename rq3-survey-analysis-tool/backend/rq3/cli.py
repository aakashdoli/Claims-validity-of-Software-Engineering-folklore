"""Command line entry points.

    python -m rq3.cli build-claims [--source data/source/Final_50_Claims_Public.xlsx]
    python -m rq3.cli run [--input <export.xlsx>] [--config config.yaml]
    python -m rq3.cli summary
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .claims import build_claims_csv, build_evidence_scaffold, load_claims
from .config import PROJECT_ROOT, load_config
from .pipeline import export_all, run


def _cmd_build_claims(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    source = Path(args.source) if args.source else PROJECT_ROOT / "data/source/Final_50_Claims_Public.xlsx"
    claims_path = cfg.resolve_path("dataset.claims_file")
    evidence_path = cfg.resolve_path("dataset.evidence_file")

    claims = build_claims_csv(source, claims_path)
    print(f"wrote {claims_path} ({len(claims)} claims)")

    existed = evidence_path.exists()
    build_evidence_scaffold(claims, evidence_path, str(cfg.get("belief.pending_label")))
    if existed:
        print(f"kept existing {evidence_path} (hand-maintained; never overwritten)")
    else:
        print(f"wrote {evidence_path} — fill in the RQ2 evidence_label column")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    result = run(cfg, input_file=args.input)
    paths = export_all(result, cfg)
    m = result.manifest
    print(f"run {m.run_id}")
    print(f"  input        {m.input_file}")
    print(f"  sha256       {m.input_sha256[:16]}...")
    print(f"  respondents  {m.n_respondents}")
    print(f"  claims       {m.n_claims}")
    print(f"  comments     {m.n_comments}")
    print(f"  flagged      {result.quality.n_flagged} respondent(s)")
    print(f"  exclusions   {len(result.exclusions)}")
    b = result.matrix.bucket_counts
    print(f"  buckets      clear_direction {b['clear_direction']} · "
          f"mixed {b['mixed']} · idk_dominant {b['idk_dominant']}")
    print(f"  matrix       match {result.matrix.n_match} · "
          f"mismatch {result.matrix.n_mismatch} · "
          f"not scored {result.matrix.n_not_scored}")
    e = result.experience
    print(f"  experience   {e.group_1_label} n={e.group_1_total} vs "
          f"{e.group_2_label} n={e.group_2_total}")
    print(f"               {e.n_tested} Mann-Whitney tests, "
          f"{e.n_significant_raw} raw sig, "
          f"{e.n_significant_corrected} after {e.method}")
    print(f"  pending RQ2  {result.matrix.n_pending_evidence} claim(s)")
    for f in result.families:
        print(f"  BH {f.variable:<13} {f.n_significant_adjusted}/{f.n_tests} significant "
              f"(raw {f.n_significant_raw}), {f.n_excluded} not tested")
    print("  exports:")
    for name, p in paths.items():
        print(f"    {name:<28} {p}")
    return 0


def _cmd_evidence(args: argparse.Namespace) -> int:
    """Import RQ2 labels from a workbook, gated on claim identity."""
    from .evidence import read_workbook, write_evidence_csv
    cfg = load_config(args.config)
    claims = load_claims(cfg)
    report = read_workbook(args.file, claims, cfg,
                           min_similarity=args.min_text_similarity)

    print(f"source   {report.source_file}")
    print(f"shape    {report.shape}")
    print(f"gate     claim text must match the surveyed claim at "
          f"similarity >= {report.min_similarity}")
    print(f"\nACCEPTED {len(report.accepted)} / {len(report.rows)}")
    for r in report.accepted:
        print(f"  ✓ {r.claim_id}  {r.label:<26} sim={r.text_similarity:.2f}")
    if report.rejected:
        para = [r for r in report.rejected if r.triage == "likely_paraphrase"]
        diff = [r for r in report.rejected if r.triage != "likely_paraphrase"]
        print(f"\nREJECTED {len(report.rejected)}  "
              f"({len(para)} look like a reworded version of the right claim, "
              f"{len(diff)} look like a different claim entirely)")
        for title, group in (("LIKELY PARAPHRASE — same subject, reworded; "
                              "confirm by hand then accept", para),
                             ("LIKELY DIFFERENT CLAIM — do not import", diff)):
            if not group:
                continue
            print(f"\n  {title}")
            for r in group:
                print(f"    ✗ {r.claim_id}  {r.label_raw:<26} sim={r.text_similarity:.2f}"
                      + (f"  shared: {', '.join(r.shared_terms[:6])}" if r.shared_terms else ""))
                print(f"        evidence used : {r.source_text[:105]}")
                print(f"        surveyed claim: {r.surveyed_text[:105]}")
    if report.missing_claims:
        print(f"\nNO ROW IN SOURCE ({len(report.missing_claims)}): "
              f"{', '.join(report.missing_claims)}")
    if report.unknown_ids:
        print(f"\nIDS NOT IN THE SURVEY POOL ({len(report.unknown_ids)}): "
              f"{', '.join(report.unknown_ids)}")

    if not args.write:
        print("\nNothing written. Re-run with --write to update "
              f"{cfg.resolve_path('dataset.evidence_file')} "
              "(rejected and absent claims stay PENDING).")
        return 0 if not report.rejected else 1

    if report.rejected and not args.allow_partial:
        print(f"\nRefusing to write: {len(report.rejected)} row(s) failed the "
              "claim-identity gate. Fix the source, or pass --allow-partial to "
              "write only the accepted rows and leave the rest PENDING.")
        return 1

    out = cfg.resolve_path("dataset.evidence_file")
    frame = write_evidence_csv(report, claims, out, cfg)
    pending = str(cfg.get("belief.pending_label"))
    n_pending = int((frame["evidence_label"] == pending).sum())
    print(f"\nwrote {out}")
    print(f"  {len(frame) - n_pending} labelled, {n_pending} still {pending}")
    print("  next: ./run.sh pipeline")
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    claims = load_claims(cfg)
    pending = str(cfg.get("belief.pending_label"))
    counts = claims["evidence_label"].value_counts().to_dict()
    print(f"{len(claims)} claims")
    for k, v in counts.items():
        print(f"  {k:<28} {v}")
    if counts.get(pending):
        print(f"\n{counts[pending]} claim(s) still need an RQ2 evidence label in "
              f"{cfg.resolve_path('dataset.evidence_file')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rq3", description="RQ3 survey analysis tool")
    p.add_argument("--config", default=None, help="path to config.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build-claims", help="regenerate data/claims.csv from the source workbook")
    b.add_argument("--source", default=None)
    b.set_defaults(func=_cmd_build_claims)

    r = sub.add_parser("run", help="run the full pipeline and write all exports")
    r.add_argument("--input", default=None, help="override dataset.input_file")
    r.set_defaults(func=_cmd_run)

    e = sub.add_parser("evidence",
                       help="import RQ2 evidence labels from a workbook, gated "
                            "on claim identity")
    e.add_argument("file", help="summary table or 50-sheet detailed evidence log")
    e.add_argument("--write", action="store_true",
                   help="update data/claims_evidence.csv (dry run by default)")
    e.add_argument("--allow-partial", action="store_true",
                   help="write accepted rows even if some were rejected")
    e.add_argument("--min-text-similarity", type=float, default=None,
                   help="override evidence.min_text_similarity for this run")
    e.set_defaults(func=_cmd_evidence)

    s = sub.add_parser("summary", help="show claim / evidence-label counts")
    s.set_defaults(func=_cmd_summary)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
