# Weekly Plan – SE Folklore Thesis

Status: Active  
Start date: 17 Feb 2026  
Owners: Aakash, Ekshith  
Supervisors: Greg Wilson, Davide Fucci  

---

## Purpose

This document defines the week-by-week execution plan for:

- Claim extraction from 12 practitioner books
- Pilot validation (2 books)
- Evidence mapping
- Practitioner survey
- Thesis writing and synthesis

Progress updates will be recorded separately if needed.

---

## Phase 1: Tool Calibration and Pilot Study (February)

## Week 06 (Feb 02 - Feb 08, 2026)

Objective  
Finalize pipeline architecture for EPUB ingestion and baseline extraction with traceability-ready output.

Tasks

- Finalize EPUB ingestion pipeline and baseline extraction logic.
- Define the formal schema for claim storage and export format.
- Ensure robust metadata capture for traceability:
  - book
  - chapter
  - section (if available)
  - paragraph index
  - stable ebook locator
- Run a small end-to-end test extraction and confirm output structure.

Expected Output

- Stable pipeline structure and extraction baseline.
- Claim schema documented and implemented.
- Test output confirms traceability fields.

Success Criteria

- Pipeline runs end-to-end on a small sample without structural errors.
- Traceability fields are consistently present in outputs.

---

## Week 07 (Feb 09 - Feb 15, 2026)

Objective  
Run Pilot Book 1 and identify extraction errors and failure patterns.

Tasks

- Run the extraction tool on the first pilot book.
- Review extracted outputs to identify:
  - false positives (non-claims extracted)
  - missed claims
  - metadata and locator errors
- Record error types and likely causes.
- Draft refinement actions for Week 08.

Expected Output

- Pilot Book 1 extraction output.
- Error list with categorized failure patterns.
- Refinement plan for rule updates.

Success Criteria

- Pilot Book 1 successfully processed.
- Clear error categories and causes recorded.

---

## Week 08 (Feb 16 - Feb 22, 2026)

Objective  
Run Pilot Book 2 and refine extraction rules based on Pilot Book 1 findings.

Tasks

- Update extraction prompts and rules using Week 07 error patterns.
- Run the extraction tool on the second pilot book.
- Review outputs to check if major Pilot 1 error patterns reduced.
- Prepare manual verification sampling template for Week 09.

Expected Output

- Pilot Book 2 extraction output.
- Updated extraction rules documented.
- Manual verification template ready.

Success Criteria

- Pilot Book 2 processed successfully.
- Observable improvement in major Pilot 1 failure patterns.

---

## Week 09 (Feb 23 - Mar 01, 2026)

Objective  
Validate pilot results through manual checking and finalize tool settings for full corpus extraction. Prepare the supervisor demo.

Tasks

- Perform manual verification sampling (30–50 extracted items).
- Categorize error types (false positives, missed claims, metadata errors).
- Refine extraction rules based on observed issues.
- Finalize extraction settings for full corpus processing.
- Prepare and deliver pipeline demo to supervisors (Feb 26).

Expected Output

- Completed verification sheet.
- Error summary report with categorized issues.
- Stabilized extraction configuration.
- Demo-ready pipeline presentation.

Success Criteria

- Manual verification completed for planned sample size.
- Clear understanding of extraction limitations and error patterns.
- Extraction settings ready for scaling.

Demo milestone (Feb 26)

- Demo the end-to-end extraction pipeline to supervisors.
- Show initial extraction results from at least one pilot book (CSV output with traceability fields).
- Present 10–20 example extracted items and briefly discuss known limitations.
- Show the manual verification sampling approach and early accuracy observations.

---

## Phase 2: Data Extraction (March)

## Week 10 (Mar 02 - Mar 08, 2026)

Objective  
Begin full corpus extraction with controlled monitoring.

Tasks

- Run extraction on first four books.
- Verify traceability fields and citation labeling.
- Check for structural CSV issues.
- Log technical problems.

Expected Output

- Four claim datasets generated.
- Initial QA checklist completed.

Success Criteria

- No pipeline crashes.
- Traceability fields consistently populated.

---

## Week 11 (Mar 09 - Mar 15, 2026)

Objective  
Continue extraction and ensure process stability.

Tasks

- Run extraction on next four books.
- Monitor runtime performance.
- Identify duplicate or malformed entries.

Expected Output

- Eight total books processed.
- QA report updated.

Success Criteria

- Stable extraction performance.
- No major metadata inconsistencies.

---

## Week 12 (Mar 16 - Mar 22, 2026)

Objective  
Complete extraction for remaining books and consolidate dataset.

Tasks

- Run extraction on remaining books.
- Merge all claim files into master dataset.
- Preserve complete traceability metadata.

Expected Output

- Master claims dataset created.
- Consolidated extraction report.

Success Criteria

- All books processed successfully.
- Master dataset verified for completeness.

---

## Week 13 (Mar 23 - Mar 29, 2026)

Objective  
Clean dataset and produce initial RQ1 descriptive analysis.

Tasks

- Remove duplicates.
- Normalize metadata.
- Categorize claims by topic and type.
- Produce summary statistics for RQ1.

Expected Output

- Cleaned master dataset.
- RQ1 descriptive summary tables.

Success Criteria

- Dataset ready for evidence mapping phase.
- Clear overview of claim distribution.

---

## Phase 3: Literature Review and Evidence Mapping (April)

## Week 14 (Mar 30 - Apr 05, 2026)

Objective  
Select high-impact claims for deeper investigation.

Tasks

- Define selection criteria (frequency, strength, impact).
- Select subset of claims for evidence mapping.
- Document justification for selection.

Expected Output

- Finalized subset list.
- Selection rationale documented.

Success Criteria

- Subset transparently justified.
- Claims traceable to original books.

---

## Week 15 (Apr 06 - Apr 12, 2026)

Objective  
Conduct systematic literature search.

Tasks

- Search ACM, IEEE, and other relevant sources.
- Apply inclusion and exclusion criteria.
- Record search strategy.

Expected Output

- List of relevant peer-reviewed studies.
- Search documentation.

Success Criteria

- Evidence sources clearly linked to selected claims.

---

## Week 16 (Apr 13 - Apr 19, 2026)

Objective  
Extract and organize scientific evidence.

Tasks

- Read selected papers.
- Extract key findings and study context.
- Record methodological details.

Expected Output

- Structured evidence table.
- Extracted summaries per claim.

Success Criteria

- Evidence clearly categorized per claim.

---

## Week 17 (Apr 20 - Apr 26, 2026)

Objective  
Compare claims to scientific evidence (RQ2).

Tasks

- Label each claim as supported, mixed, not supported, or insufficient evidence.
- Analyze patterns across topics.
- Document reasoning behind classifications.

Expected Output

- Evidence alignment table.
- RQ2 summary analysis.

Success Criteria

- Transparent and reproducible alignment process.

---

## Phase 4: Practitioner Survey (May)

## Week 18 (Apr 27 - May 03, 2026)

Objective  
Design practitioner survey instrument.

Tasks

- Convert selected claims into neutral survey statements.
- Create demographic questions.
- Draft consent information.

Expected Output

- Draft survey questionnaire.
- Survey structure document.

Success Criteria

- Survey questions neutral and clear.

---

## Week 19 (May 04 - May 10, 2026)

Objective  
Pilot and launch survey.

Tasks

- Pilot survey with small group.
- Adjust wording if necessary.
- Launch survey to practitioners.

Expected Output

- Final survey version.
- Survey link distributed.

Success Criteria

- Survey operational and collecting responses.

---

## Week 20 (May 11 - May 17, 2026)

Objective  
Monitor and encourage participation.

Tasks

- Track response rates.
- Send reminders if needed.
- Ensure data quality.

Expected Output

- Mid-survey response report.

Success Criteria

- Adequate response volume for analysis.

---

## Week 21 (May 18 - May 24, 2026)

Objective  
Analyze survey responses (RQ3).

Tasks

- Clean survey data.
- Compute descriptive statistics.
- Compare belief strength across claims.

Expected Output

- RQ3 results summary.
- Visualizations and statistical tables.

Success Criteria

- Clear measurement of practitioner belief levels.

---

## Phase 5: Triangulation and Thesis Writing (June)

## Week 22 (May 25 - May 31, 2026)

Objective  
Triangulate findings across RQ1, RQ2, and RQ3.

Tasks

- Compare extraction results, evidence mapping, and survey findings.
- Identify convergence and divergence patterns.

Expected Output

- Triangulation summary document.

Success Criteria

- Clear integration of all research components.

---

## Week 23 (Jun 01 - Jun 07, 2026)

Objective  
Write Results and Discussion chapters.

Tasks

- Draft results section.
- Draft discussion and implications.
- Link findings to existing literature.

Expected Output

- Results and Discussion draft.

Success Criteria

- Coherent narrative supported by evidence.

---

## Week 24 (Jun 08 - Jun 14, 2026)

Objective  
Finalize thesis structure and validity discussion.

Tasks

- Write Threats to Validity.
- Review formatting and references.
- Improve clarity and flow.

Expected Output

- Near-final thesis draft.

Success Criteria

- Structurally complete and academically sound document.

---

## Week 25 (Jun 15 - Jun 21, 2026)

Objective  
Submit final thesis.

Tasks

- Final proofreading.
- Supervisor feedback integration.
- Submit thesis document.

Expected Output

- Final submitted thesis.

Success Criteria

- Submission completed within deadline.