# se-claims-tool

Extract **verbatim** causal claims (sentence-level) from software engineering books (EPUB first-class, PDF fallback),
and export results to **JSONL + CSV** using a deterministic, rule-based claim detector.

## Install

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -U pip
pip install -e .
```

## Extract from a single book

```bash
python scripts/run_pipeline.py extract-batch --inputs path/to/book.epub --outdir out/book1
```

## Extract from a folder / ZIP (12-book corpus)

```bash
python scripts/run_pipeline.py extract-batch --inputs path/to/big12_folder --outdir out/big12
```

Outputs include:
- per-book: `<outdir>/<filename>/claims.jsonl`, `claims.csv`, `run_metadata.json`
- corpus: `<outdir>/all_claims.jsonl`, `<outdir>/all_claims.csv`, `<outdir>/manifest.csv`, `<outdir>/run_summary.json`, `<outdir>/results.zip`

## Validation (manual verification sampling)

1) Create a deterministic sample

```bash
python scripts/validate_sample.py --input out/<book>_claims.csv --out out/<book>_validation_sample.csv --n 50 --seed 42
```

2) Two coders fill Yes/No in these columns:
- is_claim_manual_aakash, is_claim_manual_ekshith
- locator_correct_manual_aakash, locator_correct_manual_ekshith
- citation_status_correct_manual_aakash, citation_status_correct_manual_ekshith

3) Score and generate a report

```bash
python scripts/score_validation.py --input out/<book>_validation_sample_filled.csv --out_md out/<book>_validation_report.md
```
