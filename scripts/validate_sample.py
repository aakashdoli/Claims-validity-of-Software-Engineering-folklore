import argparse
import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Final extracted claims CSV")
    ap.add_argument("--out", required=True, help="Sample CSV for manual validation")
    ap.add_argument("--n", type=int, default=40, help="Sample size")
    ap.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = ap.parse_args()

    df = pd.read_csv(args.input)
    if len(df) == 0:
        raise SystemExit("No rows in input CSV")

    # Stabilize order so sampling is reproducible even if extraction output order changes
    stable_cols = [c for c in ["claim_id", "book_id", "spine_id", "para_index", "sentence_index", "locator"] if c in df.columns]
    if stable_cols:
        df = df.sort_values(stable_cols).reset_index(drop=True)

    n = min(args.n, len(df))
    sample = df.sample(n=n, random_state=args.seed).copy()

    sample["validation_row_id"] = range(1, len(sample) + 1)
    sample["sample_seed"] = args.seed
    sample["sample_n_requested"] = args.n
    sample["coding_instructions"] = "Use Yes/No for manual fields."

    for coder in ["aakash", "ekshith"]:
        sample[f"is_claim_manual_{coder}"] = ""
        sample[f"locator_correct_manual_{coder}"] = ""
        sample[f"citation_status_correct_manual_{coder}"] = ""
        sample[f"notes_{coder}"] = ""

    sample["is_claim_consensus"] = ""
    sample["locator_correct_consensus"] = ""
    sample["citation_status_correct_consensus"] = ""
    sample["disagreement_resolved_notes"] = ""

    sample.to_csv(args.out, index=False)
    print(f"Wrote sample: {args.out} (n={n}, seed={args.seed})")

if __name__ == "__main__":
    main()