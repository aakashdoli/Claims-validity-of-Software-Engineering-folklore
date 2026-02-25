from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from dotenv import load_dotenv

from se_claims_tool.llm.claim_labeler import label_claims_with_azure


def _require_env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise SystemExit(f"Missing env var {name}. Put it in .env")
    return v


def _make_azure_client() -> Any:
    """
    Reuse your existing Azure client wrapper.

    Your repo has: src/se_claims_tool/llm/azure_client.py
    It should expose something like AzureChatClient with chat_json method.
    """
    from se_claims_tool.llm.azure_client import AzureChatClient

    endpoint = _require_env("AZURE_OPENAI_ENDPOINT")
    api_key = _require_env("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview").strip()
    deployment = _require_env("AZURE_OPENAI_DEPLOYMENT")

    return AzureChatClient(
        endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        deployment=deployment,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to all_claims.csv")
    ap.add_argument("--out", default="", help="Path to labeled CSV. Default is all_claims_labeled.csv beside input.")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--min-confidence", type=float, default=0.7)
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env")

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    out_path = Path(args.out) if args.out else input_path.with_name("all_claims_labeled.csv")
    meta_path = out_path.with_name("openai_label_metadata.json")

    df = pd.read_csv(input_path)

    required_cols = {"claim_id", "claim_text"}
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")

    model_name = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini").strip()
    run_id = time.strftime("%Y-%m-%dT%H-%M-%S")

    # Prepare rows for labeling
    rows: List[Dict[str, Any]] = df.to_dict(orient="records")

    client = _make_azure_client()
    labels, run_meta = label_claims_with_azure(
        azure_client=client,
        rows=rows,
        model_name=model_name,
        batch_size=args.batch_size,
    )

    by_id = {x.claim_id: x for x in labels}

    # Add new columns
    df["api_is_claim"] = False
    df["api_is_author_perspective"] = False
    df["api_claim_type"] = ""
    df["api_confidence"] = 0.0
    df["api_reason"] = ""
    df["api_model"] = model_name
    df["api_run_id"] = run_id

    for i, r in df.iterrows():
        cid = str(r["claim_id"])
        lab = by_id.get(cid)
        if not lab:
            continue
        df.at[i, "api_is_claim"] = bool(lab.is_claim)
        df.at[i, "api_is_author_perspective"] = bool(lab.is_author_perspective)
        df.at[i, "api_claim_type"] = lab.claim_type
        df.at[i, "api_confidence"] = float(lab.confidence)
        df.at[i, "api_reason"] = lab.reason

    # Convenience column for filtering
    df["api_keep_strict"] = (
        (df["api_is_claim"] == True)
        & (df["api_is_author_perspective"] == False)
        & (df["api_confidence"] >= float(args.min_confidence))
    )

    df.to_csv(out_path, index=False)

    run_meta.update(
        {
            "input_csv": str(input_path),
            "output_csv": str(out_path),
            "min_confidence": float(args.min_confidence),
            "strict_kept_rows": int(df["api_keep_strict"].sum()),
        }
    )
    meta_path.write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote labeled CSV: {out_path}")
    print(f"Wrote metadata: {meta_path}")
    print(f"Strict kept rows: {int(df['api_keep_strict'].sum())} / {len(df)}")


if __name__ == "__main__":
    main()