# RQ1 — Claim Extraction Pipeline

Extracts candidate software engineering folklore claims from practitioner
books and classifies them by claim type.

Part of the master's thesis *Claims Validity of Software Engineering Folklore*
(PA2534 VT26, Blekinge Institute of Technology). See the
[repository root](../README.md) for thesis and authorship details.

---

## Overview

A two-stage pipeline. Stage 1 is a cheap, high-recall rule-based filter that
narrows a book's full sentence set to a candidate pool. Stage 2 makes the
precise final decision with a language model. Precision is prioritised over
recall throughout.

**Claim definition**

> A declarative sentence that asserts a generalizable proposition about
> software engineering practice, behavior, process, tools, or outcomes, which
> is falsifiable or evaluable against empirical evidence.

**Claim types**

`NORMATIVE` · `CAUSAL` · `COMPARATIVE` · `QUANTITATIVE` · `GENERALIZATION` · `AUTHOR_PERSPECTIVE`

### Ingestion

EPUB, AZW3, and PDF are each handled by a dedicated ingestor under
`src/se_claims_tool/ingest/`. PDFs are read page by page with block-level
extraction; publisher watermarks, page numbers, and very short blocks are
discarded before any sentence-level processing. Paragraphs are split into
sentences with **pysbd**.

Structural metadata — chapter, section, paragraph index, and locator — travels
with every sentence so each extracted claim remains traceable to its position
in the source. PDFs carry page-level provenance only.

### Stage 1 — NLP pre-filter

`src/se_claims_tool/nlp/claim_detector.py`

Each sentence passes three sequential checks:

1. **Quality filter** — discards sentences under 30 characters, questions,
   colon-terminated headings, numbered structural headings, and bibliography
   entries.
2. **Domain-vocabulary filter** — requires at least one software engineering
   term, so that generic advice does not enter the candidate pool.
3. **Claim-type patterns** — regular expressions for the six claim types,
   evaluated in a fixed priority order with matching stopping at the first hit.

Every rejection is recorded with a reason code, so the filter's behaviour can
be audited. Surviving sentences are paired with the preceding and following
sentence from the same paragraph.

### Stage 2 — LLM classification

`src/se_claims_tool/llm/azure_llm_filter.py`

Candidates are sent to Azure OpenAI (**gpt-4o**) in batches of 15, at
temperature 0.0 with a JSON-constrained response, and retried up to three times
on failure. Each candidate is submitted with its surrounding context and the
Stage 1 pattern label, the latter as a hint rather than a fixed label.

The model returns, in a single judgment, whether the sentence is a genuine
claim, which of the six types it belongs to, a confidence score in [0, 1], and
a brief justification. Only confirmed claims are written to the output.

### Citation status

Confirmed claims are examined for evidentiary support and marked `cited`,
`ambiguous`, or `not_cited`, together with the marker text and its surrounding
context. Only a formal marker in the claim sentence itself counts as `cited`.

---

## Setup

Run from this directory.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Copy the environment template and fill in your Azure OpenAI credentials:

```bash
cp .env.example .env
```

`.env` is gitignored. Never commit a real key.

## Running

```bash
streamlit run ui/app.py
```

Upload one or more books, run the extraction, and download the results. Books
and outputs are written to a temporary directory for the session and are not
retained.

---

## Output

Each confirmed claim is written as a 29-column record
(`src/se_claims_tool/models_rq1.py`), covering provenance, claim text and
context, citation evidence, both stages' judgements, and empty columns for
manual verification. A run also produces per-book and corpus-level CSV and
JSONL files, a manifest, and a summary.

Books and extraction outputs are excluded from version control by
`.gitignore` at the repository root.

## Structure

```
rq1-extraction-pipeline/
  src/se_claims_tool/
    ingest/              EPUB, AZW3, PDF ingestion
    nlp/claim_detector.py    Stage 1 — NLP pre-filter
    llm/azure_llm_filter.py  Stage 2 — LLM classification
    pipeline.py          Two-stage extraction for one book
    batch_pipeline.py    Corpus runner
    citations.py         Citation-status detection
    models_rq1.py        Output schema
    export/              CSV and JSONL writers
  ui/app.py              Streamlit interface
  tests/
```
