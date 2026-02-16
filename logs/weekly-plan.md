# Weekly plan

Owners: Aakash, Ekshith  
Supervisors: Greg Wilson, Davide Fucci

## How to read this
- This file is the planned week-by-week timeline and expected outputs.
- Actual progress is recorded separately in `logs/YYYY-W##.md`.

---

## Week 1 (Feb 17–Feb 23, 2026)
Goals
- Prepare pipeline and documentation for a verifiable 2-book pilot.

Planned work
- Confirm claim definition and update codebook (include and exclude rules with examples).
- Ensure traceability fields exist for every claim (book, chapter, section, paragraph index, stable locator).
- Validate end-to-end extraction on a small subset.
- Create manual verification sampling template.

Outputs
- Codebook draft in repo.
- One successful end-to-end extraction run with traceability.
- Manual verification template.

---

## Week 2 (Feb 24–Mar 1, 2026)
Goals
- Complete Pilot Book 1 and measure extraction quality.

Planned work
- Run full extraction for Pilot Book 1 and export claims CSV.
- Manual verification sample (30–50 claims): claim correctness, locator correctness, citation label correctness.
- Record error types and counts.

Outputs
- Pilot Book 1 claims CSV.
- Pilot Book 1 verification sample file.
- Error log summary.

---

## Week 3 (Mar 2–Mar 8, 2026)
Goals
- Improve extraction using Pilot 1 findings and complete Pilot Book 2.

Planned work
- Fix extraction rules to reduce false positives such as anecdotes and personal statements.
- Run Pilot Book 2 and export claims CSV.
- Manual verification sample (30–50 claims).
- Compare Pilot 1 vs Pilot 2 error rates.

Outputs
- Pilot Book 2 claims CSV.
- Pilot Book 2 verification sample file.
- Updated extraction rules and error summary.

---

## Week 4 (Mar 9–Mar 15, 2026)
Goals
- Freeze extraction settings and prepare to scale.

Planned work
- Write short pilot report covering what works, what fails, and mitigation actions.
- Freeze extraction settings for the full corpus.
- Tag a stable version of the pipeline.

Outputs
- Pilot report.
- Frozen extraction configuration.
- Release tag for reproducibility.

---

## Week 5 (Mar 16–Mar 22, 2026)
Goals
- Start full corpus extraction.

Planned work
- Run extraction on books 3–6.
- QA checks: missing locators, missing metadata, duplicates.

Outputs
- 4 claim CSV files.
- QA checklist updates.

---

## Week 6 (Mar 23–Mar 29, 2026)
Goals
- Continue full corpus extraction.

Planned work
- Run extraction on books 7–10.
- Continue QA checks and fix failures.

Outputs
- 4 claim CSV files.
- QA checklist updates.

---

## Week 7 (Mar 30–Apr 5, 2026)
Goals
- Finish extraction and merge dataset.

Planned work
- Run extraction on books 11–12.
- Merge all claims into one master dataset.
- Verify traceability fields across all books.

Outputs
- Master claims dataset.
- Merge documentation.

---

## Week 8 (Apr 6–Apr 12, 2026)
Goals
- RQ1 analysis.

Planned work
- Descriptive stats: claim counts, types, topics, citation status distribution.
- Detect repeated claims across books.

Outputs
- RQ1 tables and figures.
- Summary notes for thesis.

---

## Week 9 (Apr 13–Apr 19, 2026)
Goals
- Select justified subset for evidence mapping.

Planned work
- Define selection criteria (frequency, strength, impact).
- Select subset and document justification.

Outputs
- Subset list with traceability.
- Justification notes.

---

## Week 10 (Apr 20–Apr 26, 2026)
Goals
- Evidence mapping protocol and initial searches.

Planned work
- Define search strategy and screening rules.
- Start mapping evidence for first half of subset.

Outputs
- Evidence mapping protocol.
- Evidence table draft.

---

## Week 11 (Apr 27–May 3, 2026)
Goals
- Complete evidence mapping and alignment labels.

Planned work
- Map evidence for second half of subset.
- Assign labels: supported, mixed, not supported, insufficient evidence.

Outputs
- Completed evidence table.
- Alignment labels per claim.

---

## Week 12 (May 4–May 10, 2026)
Goals
- Prepare practitioner survey.

Planned work
- Convert claims to neutral survey statements.
- Draft consent text and minimal demographics.
- Pilot survey wording if possible.

Outputs
- Survey draft.
- Pilot feedback notes.

---

## Week 13 (May 11–May 17, 2026)
Goals
- Launch survey and recruit.

Planned work
- Launch survey and monitor response quality.

Outputs
- Weekly response snapshot.

---

## Week 14 (May 18–May 24, 2026)
Goals
- Analyze survey results.

Planned work
- Compute belief distributions per claim.

Outputs
- RQ3 tables and figures.

---

## Week 15 (May 25–May 31, 2026)
Goals
- Synthesis.

Planned work
- Compare evidence alignment with practitioner beliefs.
- Draft interpretation and threats to validity.

Outputs
- Synthesis notes.

---

## Week 16 (Jun 1–Jun 7, 2026)
Goals
- Write Methods and Results.

Outputs
- Thesis draft sections and artifact checklist.

---

## Week 17 (Jun 8–Jun 14, 2026)
Goals
- Complete writing and polish.

Outputs
- Near-final thesis draft.

---

## Week 18 (Jun 15–Jun 21, 2026)
Goals
- Final revisions and submission package.

Outputs
- Final thesis and final repo release tag.
