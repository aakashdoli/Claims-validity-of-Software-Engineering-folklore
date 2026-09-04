# RQ3 Results Summary

*Claims Validity of Software Engineering Folklore — BTH PA2534 VT26*

## 1. Run identity

| | |
|---|---|
| Run ID | `20260904T170248Z-d602c796` |
| Timestamp (UTC) | 2026-09-04T17:02:48Z |
| Input file | `export (4).xlsx` |
| Input SHA-256 | `d602c796f3cbfb3f5322be5551f12e280f71dbd1880fbd430253c4518e4ddd95` |
| Respondents | 751 |
| Claims | 50 |
| Free-text comments | 5,590 |
| Tool version | 1.0.0 (Python 3.14.2) |
| Logged exclusions | 1,888 |
| Flagged respondents | 3 (flagged for review, not removed) |

Classification thresholds in force: IDK-dominance **0.30** of the full sample,
majority **> 0.50** of the directional denominator.

## 2. Evidence label distribution

RQ2 labels across all 50 claims, imported from `Evidence_Summary_Public.xlsx`
through the claim-identity gate.

| Evidence label | Count |
|---|---:|
| SUPPORTED | 32 |
| CONTRADICTED | 10 |
| NO EVIDENCE FOUND | 8 |
| **Total** | **50** |

## 3. Belief–evidence matrix

Only the 33 clear-direction claims enter the matrix. Cells marked ⚑ are
belief–evidence mismatches.

| | Supported | Contradicted | No Evidence Found | Row total |
|---|---:|---:|---:|---:|
| **Majority agreed** | 21 | 4 ⚑ | 4 | **29** |
| **Majority disagreed** | 1 ⚑ | 2 | 1 | **4** |
| **Column total** | **22** | **6** | **5** | **33** |

Outcome: **23 match**, **5 mismatch**, **5 not scored**.
`NO EVIDENCE FOUND` is unscored — with no evidence located there is nothing for
belief to agree or disagree with — so the mismatch rate is over the 28 scored
claims: **5 / 28 = 17.9%**.

### Claim identifiers per cell

| Majority | Evidence | n | Claim IDs |
|---|---|---:|---|
| Agreed | Supported | 21 | CLM-000028, CLM-000032, CLM-000059, CLM-000060, CLM-000073, CLM-000086, CLM-000097, CLM-000101, CLM-000109, CLM-000129, CLM-000131, CLM-000142, CLM-000147, CLM-000179, CLM-000180, CLM-000190, CLM-000199, CLM-000242, CLM-000269, CLM-000329, CLM-000502 |
| Agreed | Contradicted ⚑ | 4 | CLM-000045, CLM-000085, CLM-000169, CLM-000496 |
| Agreed | No Evidence Found | 4 | CLM-000087, CLM-000201, CLM-000210, CLM-000450 |
| Disagreed | Supported ⚑ | 1 | CLM-000007 |
| Disagreed | Contradicted | 2 | CLM-000204, CLM-000337 |
| Disagreed | No Evidence Found | 1 | CLM-000223 |

### Marginal placements

Two claims clear the 50% line by a handful of respondents and would move to the
mixed bucket on a few different answers:

| Claim | Winning share | Directional n | Verdict |
|---|---:|---:|---|
| CLM-000085 | 50.31% (329 / 654) | 654 | **mismatch** |
| CLM-000337 | 50.62% (326 / 644) | 644 | match |

## 4. Three-way bucket split

Buckets are evaluated in order; IDK-dominance is checked first and
short-circuits the majority calculation.

| Bucket | Count | Rule |
|---|---:|---|
| Clear direction | **33** | one side exceeded 50% of the directional denominator |
| — Majority agreed | 29 | |
| — Majority disagreed | 4 | |
| Mixed | **5** | neither side passed 50% |
| IDK-dominant | **12** | 30%+ of the full sample answered "I don't know" |
| **Total** | **50** | |

**Mixed (5):** CLM-000026, CLM-000115, CLM-000122, CLM-000486, CLM-000581

**IDK-dominant (12):** CLM-000015, CLM-000036, CLM-000062, CLM-000100,
CLM-000178, CLM-000194, CLM-000224, CLM-000238, CLM-000361, CLM-000374,
CLM-000459, CLM-000470

## 5. Demographic subgroup comparisons

Two separate analyses are run. They answer different questions and their
experience results are **not** interchangeable.

### 5a. Subgroup family tests — 300 Kruskal–Wallis tests

Benjamini–Hochberg is applied within each variable's own family of 50 tests,
never pooled across variables.

| Variable | Tests | Not testable | Significant (raw) | Significant after BH |
|---|---:|---:|---:|---:|
| experience | 50 | 0 | 11 | 1 |
| role | 50 | 0 | 4 | 0 |
| team_size | 50 | 0 | 2 | 0 |
| industry | 50 | 0 | 10 | **4** |
| company_size | 50 | 0 | 1 | 0 |
| country | 50 | 0 | 5 | 0 |
| **Total** | **300** | **0** | **33** | **5** |

**5 of 300 tests survive correction**, four of them on *industry*:

| Claim | H | p (raw) | p (BH) | ε² | Magnitude |
|---|---:|---:|---:|---:|---|
| CLM-000100 | 24.569 | 0.000169 | 0.008437 | 0.0579 | small |
| CLM-000199 | 24.204 | 0.000479 | 0.009164 | 0.0250 | small |
| CLM-000223 | 23.379 | 0.000679 | 0.009164 | 0.0241 | small |
| CLM-000028 | 23.197 | 0.000733 | 0.009164 | 0.0236 | small |

The fifth is on *experience* (multi-band): CLM-000059, p = 0.000048,
p(BH) = 0.002383.

> **Country caveat.** The pipeline runs and exports 50 country tests; none
> survives correction. The thesis excludes country from subgroup reporting on
> sample-concentration grounds (only 8 of 42 countries reach n ≥ 10, with 56
> respondents not answering), so these exported results should not be read as a
> reported finding.

### 5b. Two-group experience analysis — 50 Mann–Whitney U tests

Under 10 years (**n = 153**) vs 10+ years (**n = 598**); 0 respondents
unassigned. One BH family of 50. Effect sizes are computed only where the
corrected p survives.

| | |
|---|---|
| Tested | 50 |
| Significant (raw) | 10 |
| **Significant after BH** | **4** |

| Claim | n (u10 / 10+) | U | p (raw) | p (BH) | r | Magnitude | Median u10 / 10+ |
|---|---|---:|---:|---:|---:|---|---|
| CLM-000059 | 149 / 564 | 50844.5 | 0.000009 | 0.000472 | +0.2101 | small | 4.0 / 4.0 |
| CLM-000201 | 148 / 579 | 50050.0 | 0.000789 | 0.019728 | +0.1681 | small | 4.0 / 4.0 |
| CLM-000026 | 149 / 578 | 50151.5 | 0.001319 | 0.021987 | +0.1647 | small | 4.0 / 3.0 |
| CLM-000194 | 91 / 392 | 21210.5 | 0.003137 | 0.039213 | +0.1892 | small | 4.0 / 3.0 |

All four effects are positive and small: the under-10 group agreed more on every
one. CLM-000059 is the only claim significant in both analyses.

---

## Cross-check against locked thesis values

Every figure below was verified against `full_run.json` for this run before this
document was written. **All 18 checks pass; nothing was adjusted to fit.**

| Value | Locked | This run |
|---|---:|---:|
| SUPPORTED | 32 | 32 ✓ |
| CONTRADICTED | 10 | 10 ✓ |
| NO EVIDENCE FOUND | 8 | 8 ✓ |
| Clear direction | 33 | 33 ✓ |
| — agreed | 29 | 29 ✓ |
| — disagreed | 4 | 4 ✓ |
| Mixed | 5 | 5 ✓ |
| IDK-dominant | 12 | 12 ✓ |
| Supported × Agreed | 21 | 21 ✓ |
| Supported × Disagreed | 1 | 1 ✓ |
| Contradicted × Agreed | 4 | 4 ✓ |
| Contradicted × Disagreed | 2 | 2 ✓ |
| No Evidence Found × Agreed | 4 | 4 ✓ |
| No Evidence Found × Disagreed | 1 | 1 ✓ |
| Match | 23 | 23 ✓ |
| Mismatch | 5 | 5 ✓ |
| Not scored | 5 | 5 ✓ |
| Scored | 28 | 28 ✓ |

## Files in this folder

| File | Contents |
|---|---|
| `manifest.json` | run provenance: input SHA-256, full config snapshot, library versions |
| `belief_evidence_matrix.csv` | the 2 × 3 matrix with claim IDs per cell |
| `bucket_summary.csv` | the three-way bucket split |
| `claim_results.csv` | all 50 claims: distribution, percentages, bucket, label, verdict |
| `excluded_claims.csv` | the 17 claims outside the matrix, with reasons |
| `experience_mannwhitney.csv` | the 50 two-group tests (section 5b) |
| `role_breakdown.csv` | role distribution per claim (descriptive only, untested) |
| `subgroup_comparisons.csv` | the 300 family tests (section 5a) |
| `exclusions.csv` | all 1,888 logged exclusions |

Not committed, by data-protection policy: `full_run.json` and
`flagged_respondents.csv` carry per-respondent comments and demographics.

## Caveats carried with these numbers

- **Purposive sampling.** Results describe this sample, not practitioners in
  general (Baltes & Ralph, 2022). No inference to a wider population is
  supported.
- **Fixed question order.** BTHSurvey has no randomisation; order effects cannot
  be estimated.
- **A majority is a cutoff, not a margin.** A claim clearing 50% by two
  respondents sits in the same cell as one clearing it by hundreds. See the
  marginal placements in section 3.
