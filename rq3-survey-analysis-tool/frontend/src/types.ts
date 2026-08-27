export interface Manifest {
  tool_version: string
  run_id: string
  timestamp_utc: string
  input_file: string
  input_sha256: string
  input_bytes: number
  n_respondents: number
  n_claims: number
  n_comments: number
  config_path: string
  config: Record<string, any>
  library_versions: Record<string, string>
  python_version: string
  platform: string
  notes: string[]
}

export interface Caveats { sampling: string; question_order: string }

export interface ClaimRow {
  q_number: number
  claim_id: string
  claim_type: string
  book: string
  author: string
  survey_text: string
  n_total: number
  n_valid: number
  n_idk: number
  idk_rate_pct: number
  high_idk: boolean
  median: number | null
  mode: string
  iqr: number | null
  pct_disagree_1_2: number | null
  pct_neutral_3: number | null
  pct_agree_4_5: number | null
  freq_1: number; freq_2: number; freq_3: number; freq_4: number; freq_5: number
  bimodal: boolean
  bimodality_coefficient: number | null
  evidence_label: string
  evidence_strength: string
  scored: boolean
  belief_class: string
  borderline: boolean
  belief_evidence_mismatch: boolean
  mismatch_kind: string | null
  significant_variables: string
  n_comments: number
  excluded: boolean
  exclusion_reason: string | null
}

export interface Overview {
  manifest: Manifest
  caveats: Caveats
  claims: ClaimRow[]
  summary: {
    n_respondents: number; n_claims: number; n_comments: number
    n_bimodal: number; n_borderline: number; n_mismatch: number
    n_match: number; n_not_scored: number; n_scored: number
    n_pending_evidence: number; n_flagged_respondents: number
    n_excluded_comparisons: number; n_excluded_subgroups: number
    median_idk_rate_pct: number
  }
  correction_families: FamilySummary[]
}

export interface FamilySummary {
  variable: string; n_tests: number; n_excluded: number
  n_significant_raw: number; n_significant_adjusted: number
  method: string; alpha: number
}

export interface GroupSummary {
  group: string; n_total: number; n_valid: number; n_idk: number
  idk_rate: number; median: number | null; mean_rank: number | null
  included: boolean
  frequencies: Record<string, number>
  percentages: Record<string, number>
  rank_sum: number | null
  excluded_kind: 'below_min_size' | 'unassigned' | null
  exclusion_reason: string | null
}

export interface WorkingStep { label: string; formula: string; result: string }

export interface TestWorking {
  test: string
  steps: WorkingStep[]
  values: Record<string, any>
}

export interface BHDetail {
  family: string; family_size: number; rank_in_family: number
  raw_p: number; critical_value: number; p_adjusted: number
  significant: boolean; method: string; alpha: number
}

export interface BimodalityCheck {
  name: string; observed: number; comparator: string
  threshold: number; passed: boolean
}

export interface BimodalityAssessment {
  rule: string; assessed: boolean; n_valid: number; min_valid_n: number
  lower_tail_pct: number | null; middle_pct: number | null
  upper_tail_pct: number | null
  coefficient: number | null; coefficient_threshold: number
  heuristic_pass: boolean; coefficient_pass: boolean; flag: boolean
  checks: BimodalityCheck[]; reason: string
}

export interface RankBiserial {
  r: number; favourable_pairs: number; unfavourable_pairs: number
  tied_pairs: number; total_pairs: number; magnitude: string
  direction: string; formula: string
}

export interface EpsilonSquared {
  epsilon_squared: number; h_statistic: number; n: number
  k_groups: number; magnitude: string; formula: string; field_notes: string[]
}

export interface PairwiseResult {
  group_a: string; group_b: string; n_a: number; n_b: number
  u_statistic: number; p_value: number
  p_adjusted: number | null; significant_adjusted: boolean | null
  effect: RankBiserial | null
}

export interface Comparison {
  claim_id: string; variable: string; test: string | null
  statistic: number | null; p_value: number | null
  p_adjusted: number | null; significant_adjusted: boolean | null
  effect: RankBiserial | null
  omnibus_effect: EpsilonSquared | null
  groups: GroupSummary[]
  pairwise: PairwiseResult[]
  working: TestWorking | null
  bh: BHDetail | null
  excluded: boolean; exclusion_reason: string | null; notes: string[]
}

export interface Descriptives {
  claim_id: string; n_total: number; n_valid: number; n_idk: number
  n_missing: number; idk_rate: number
  frequencies: Record<string, number>
  percentages: Record<string, number>
  median: number | null; mode: number[]
  q1: number | null; q3: number | null; iqr: number | null
  agree_pct: number | null; disagree_pct: number | null; neutral_pct: number | null
  bimodal: boolean; bimodality_reason: string
  bimodality_coefficient: number | null
  bimodality: BimodalityAssessment
  high_idk: boolean; high_idk_threshold_pct: number
  excluded: boolean; exclusion_reason: string | null; notes: string[]
}

export interface Classification {
  claim_id: string; median: number | null; belief_class: string
  evidence_label: string; borderline: boolean
  distance_from_threshold: number | null
  mismatch: boolean; mismatch_kind: string | null
  n_valid: number; idk_rate: number
  evidence_strength: string
  verdict_status: 'match' | 'mismatch' | 'not_scored' | 'pending' | 'unclassifiable'
  verdict: string
  reason: string | null
}

export interface CommentEntry { respondent_id: string; answer: string; comment: string }

export interface ClaimComments {
  claim_id: string; n_comments: number; priority_score: number
  priority_reasons: string[]; comments: CommentEntry[]
}

export interface ClaimDetail {
  claim: Record<string, any>
  descriptives: Descriptives
  classification: Classification
  comparisons: Comparison[]
  significant_comparisons: {
    variable: string; test: string | null
    p_adjusted: number | null; effect: any
  }[]
  comments: ClaimComments
  likert_labels: Record<string, string>
  idk_label: string
  min_subgroup_size: number
  belief_threshold: number
  belief_threshold_status: string
  borderline_delta: number
  pending_label: string
  effect_size_thresholds: { small: number; medium: number; large: number }
  caveats: Caveats
}

export interface MatrixCell {
  belief_class: string; evidence_label: string; count: number
  claim_ids: string[]; borderline_claim_ids: string[]
}

export interface Matrix {
  threshold: number; borderline_delta: number; threshold_status: string
  belief_classes: string[]; evidence_labels: string[]
  cells: MatrixCell[]; classifications: Classification[]
  n_borderline: number; n_pending_evidence: number; n_mismatch: number
  n_match: number; n_not_scored: number; n_scored: number
  notes: string[]
}

export interface Exclusion {
  scope: string; claim_id: string; variable: string
  group: string | null; reason: string; n_valid: number | null
}

export interface RespondentFlag {
  respondent_id: string; flags: string[]; distinct_values: number
  modal_answer: string | null; modal_share: number; idk_rate: number
  n_answered: number; duration_seconds: number | null
  demographics: Record<string, any>
}

export interface QualityPayload {
  quality: {
    n_respondents: number; n_flagged: number
    flag_counts: Record<string, number>
    flagged: RespondentFlag[]
    duplicate_pattern_groups: string[][]
    speeding_check: string; consent_check: string
    thresholds: Record<string, any>; notes: string[]
  }
  exclusions: Exclusion[]
  dataset: {
    input_file: string; input_sha256: string; run_id: string
    timestamp_utc: string; n_respondents: number
  }
  caveats: Caveats
}

export interface Methodology {
  config: Record<string, any>
  config_path: string
  manifest: Manifest
  caveats: Caveats
  belief_threshold_status: string
  citations: { stage: string; why: string; source: string }[]
}

export interface DatasetList {
  available: { name: string; path: string; size_bytes: number; current: boolean }[]
  current: string | null
  note: string
}
