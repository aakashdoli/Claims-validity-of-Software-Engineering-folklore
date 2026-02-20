import argparse
import pandas as pd

def _binary_map(x):
    x = str(x).strip().lower()
    if x in {"yes", "y", "true", "1"}:
        return 1
    if x in {"no", "n", "false", "0"}:
        return 0
    return None

def percent_agreement(a, b):
    paired = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if not paired:
        return None
    agree = sum(1 for x, y in paired if x == y)
    return agree / len(paired)

def mean_of(series):
    vals = [v for v in series if v is not None]
    return (sum(vals) / len(vals)) if vals else None

def fmt(x):
    return "N/A" if x is None else f"{x*100:.1f}%"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Filled validation sample CSV")
    ap.add_argument("--out_md", required=True, help="Markdown report output path")
    args = ap.parse_args()

    df = pd.read_csv(args.input)

    def col(name):
        if name not in df.columns:
            raise SystemExit(f"Missing column: {name}")
        return df[name].apply(_binary_map)

    # Two-coder agreement
    a_claim = col("is_claim_manual_aakash")
    e_claim = col("is_claim_manual_ekshith")
    a_loc = col("locator_correct_manual_aakash")
    e_loc = col("locator_correct_manual_ekshith")
    a_cit = col("citation_status_correct_manual_aakash")
    e_cit = col("citation_status_correct_manual_ekshith")

    agree_claim = percent_agreement(a_claim, e_claim)
    agree_loc = percent_agreement(a_loc, e_loc)
    agree_cit = percent_agreement(a_cit, e_cit)

    # Use consensus if present and filled, otherwise fallback to Aakash labels
    if "is_claim_consensus" in df.columns and df["is_claim_consensus"].astype(str).str.strip().ne("").any():
        claim_final = df["is_claim_consensus"].apply(_binary_map)
        loc_final = df["locator_correct_consensus"].apply(_binary_map)
        cit_final = df["citation_status_correct_consensus"].apply(_binary_map)
        final_source = "consensus"
    else:
        claim_final, loc_final, cit_final = a_claim, a_loc, a_cit
        final_source = "aakash (fallback)"

    precision = mean_of(claim_final)
    locator_acc = mean_of(loc_final)
    citation_acc = mean_of(cit_final)

    lines = []
    lines.append("# Validation report (manual verification sample)\n")
    lines.append(f"- Sample size: {len(df)}")
    lines.append(f"- Final labels used: {final_source}\n")

    lines.append("## Inter-rater agreement (percent agreement)\n")
    lines.append(f"- Claim correctness agreement: {fmt(agree_claim)}")
    lines.append(f"- Locator correctness agreement: {fmt(agree_loc)}")
    lines.append(f"- Citation status correctness agreement: {fmt(agree_cit)}\n")

    lines.append("## Instrument quality on sample\n")
    lines.append(f"- Precision (extracted item is a true claim): {fmt(precision)}")
    lines.append(f"- Locator accuracy (traceability correct): {fmt(locator_acc)}")
    lines.append(f"- Citation label accuracy: {fmt(citation_acc)}\n")

    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Wrote report: {args.out_md}")

if __name__ == "__main__":
    main()
