import { useEffect, useState } from 'react'
import { api } from '../api'
import { Caveat, ErrorBox, Loading } from '../components/common'
import type { Methodology as Meth } from '../types'

/**
 * Every config value that shaped the current numbers, shown in full, so a
 * result can be audited against the exact settings that produced it.
 */
export function Methodology() {
  const [m, setM] = useState<Meth | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { api.methodology().then(setM).catch(e => setErr(String(e.message ?? e))) }, [])

  if (err) return <ErrorBox error={err} />
  if (!m) return <Loading what="methodology" />

  const c = m.config
  return (
    <>
      <Caveat caveats={m.caveats} extra={
        <p><strong>Belief classification.</strong> Claims are bucketed by the direction a
          majority took, not by a median. A claim is IDK-dominant when{' '}
          {(c.belief.idk_dominance.threshold * 100).toFixed(0)}% or more of the full sample
          answered "I don't know" — checked first, and it removes the claim from the matrix.
          Otherwise a side must exceed {(c.belief.majority.threshold * 100).toFixed(0)}% of the
          directional answers (IDK excluded) for the claim to count as a clear direction. Both
          values are read from <code>{m.config_path}</code> and defined nowhere else in the
          codebase.</p>} />

      <div className="card">
        <header><h2>Configuration in force for this run</h2>
          <span className="sub">{m.config_path}</span></header>
        <dl className="kv">
          <dt>IDK-dominance threshold</dt>
          <dd>{(c.belief.idk_dominance.threshold * 100).toFixed(0)}% of the full sample (IDK
              included) — at or above this the claim is reported on its own terms and never
              classified. Evaluated before the majority rule and short-circuits it</dd>
          <dt>Majority threshold</dt>
          <dd>more than {(c.belief.majority.threshold * 100).toFixed(0)}% of the directional
              denominator (the five substantive Likert points, IDK excluded). Strictly greater
              than: an exact 50/50 split is mixed, not a majority. Neutral answers count toward
              the denominator but toward neither side</dd>
          <dt>Minimum subgroup size</dt>
          <dd>{c.comparisons.min_subgroup_size} valid (non-IDK) answers; smaller subgroups are
              excluded from that comparison and logged</dd>
          <dt>Alpha</dt><dd>{c.comparisons.alpha}</dd>
          <dt>Correction</dt>
          <dd>{c.correction.method} applied {c.correction.family_scope.replace('_', ' ')} —
              one family per demographic variable, never pooled</dd>
          <dt>Pairwise follow-ups</dt>
          <dd>{c.comparisons.pairwise_requires_significant_omnibus
            ? 'only after a BH-significant Kruskal–Wallis omnibus'
            : 'always run'}; corrected within each claim's own set</dd>
          <dt>Bimodality rule</dt>
          <dd>{c.descriptives.bimodality.rule} — flag when the lower tail (1–2) ≥{' '}
              {c.descriptives.bimodality.min_lower_tail_pct}% and the upper tail (4–5) ≥{' '}
              {c.descriptives.bimodality.min_upper_tail_pct}% and the middle (3) ≤{' '}
              {c.descriptives.bimodality.max_middle_pct}%, assessed only at ≥{' '}
              {c.descriptives.bimodality.min_valid_n} valid answers. Sarle's coefficient
              (reference {c.descriptives.bimodality.coefficient_threshold}) is reported as a
              cross-check and does not drive the flag.</dd>
          <dt>Effect-size bands</dt>
          <dd>|r| &gt; {c.effect_size.thresholds.large} large ·{' '}
              {c.effect_size.thresholds.medium}–{c.effect_size.thresholds.large} medium ·{' '}
              {c.effect_size.thresholds.small}–{c.effect_size.thresholds.medium} small ·
              below that negligible</dd>
          <dt>IDK rule</dt>
          <dd>excluded from medians{c.idk_rule.exclude_from_tests && ' and from all test data'};
              the IDK rate is reported separately per claim and per subgroup</dd>
          <dt>Low-effort flags</dt>
          <dd>≤ {c.quality.low_effort.max_distinct_values} distinct values ·
              ≥ {(c.quality.low_effort.modal_answer_share * 100).toFixed(0)}% on one value ·
              ≥ {(c.quality.low_effort.idk_rate * 100).toFixed(0)}% IDK ·
              faster than {c.quality.low_effort.min_completion_seconds}s (when a duration
              column exists). Flag only — never auto-exclusion.</dd>
          <dt>Comment priority weights</dt>
          <dd>{Object.entries(c.comments.priority_weights)
                .map(([k, v]) => `${k.replace(/_/g, ' ')} +${v}`).join(' · ')}</dd>
        </dl>
      </div>

      <div className="card">
        <header>
          <h2>Tests actually run</h2>
          <span className="sub">
            what this dataset produced — not what the pipeline is capable of
          </span>
        </header>
        <dl className="kv">
          <dt>Comparisons</dt>
          <dd>{m.tests_run.n_run} run of {m.tests_run.n_attempted} attempted
              (50 claims × {Object.keys(m.tests_run.subgroups_per_variable).length} demographic variables)</dd>
          <dt>Kruskal–Wallis H</dt>
          <dd><strong>{m.tests_run.by_test.kruskal_wallis}</strong> omnibus tests</dd>
          <dt>Mann–Whitney U</dt>
          <dd>
            <strong>{m.tests_run.by_test.mann_whitney_u}</strong> omnibus tests
            {m.tests_run.by_test.mann_whitney_u === 0 && (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 3 }}>
                No two-group comparison arose: {Object.entries(m.tests_run.subgroups_per_variable)
                  .map(([v, n]) => `${v.replace(/_/g, ' ')} ${n}`).join(' · ')} subgroups
                cleared the minimum size, so every omnibus test was Kruskal–Wallis.
              </div>
            )}
          </dd>
          <dt>Effect size, omnibus</dt>
          <dd>
            ε² on {m.tests_run.n_epsilon_squared_omnibus} tests ·
            rank-biserial on {m.tests_run.n_rank_biserial_omnibus}
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 3 }}>
              Rank-biserial is undefined for three or more groups, so the omnibus
              results carry ε² (Tomczak &amp; Tomczak 2014). Computed for every test,
              not only the {m.tests_run.n_significant_omnibus} that survived correction.
            </div>
          </dd>
          <dt>Pairwise follow-ups</dt>
          <dd>
            {m.tests_run.n_pairwise} Mann–Whitney tests, all carrying Kerby&rsquo;s
            rank-biserial; {m.tests_run.n_pairwise_significant} significant after
            correction within their claim
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 3 }}>
              Run only where a Kruskal–Wallis omnibus survived Benjamini–Hochberg.
            </div>
          </dd>
          <dt>Significant after BH</dt>
          <dd><strong>{m.tests_run.n_significant_omnibus}</strong> of {m.tests_run.n_run} omnibus tests</dd>
        </dl>
        <p style={{ margin: '14px 0 0', fontSize: 12.5, lineHeight: 1.6,
                    color: 'var(--text-secondary)' }}>
          {m.tests_run.note}
        </p>
        <p style={{ margin: '10px 0 0', fontSize: 12.5, lineHeight: 1.6,
                    color: 'var(--text-secondary)' }}>
          <strong>These tests answer a secondary question</strong> — whether belief
          varies by who the respondent is. The belief–evidence classification itself
          is descriptive: a median per claim, cross-tabulated against the RQ2 label.
          No hypothesis test contributes to it.
        </p>
      </div>

      <div className="card">
        <header><h2>Why each statistical choice</h2>
          <span className="sub">the same citations sit in code comments beside the functions</span></header>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Stage</th><th>Rationale</th><th>Source</th></tr></thead>
            <tbody>
              {m.citations.map((x, i) => (
                <tr key={i}>
                  <td style={{ whiteSpace: 'nowrap' }}>{x.stage}</td>
                  <td className="text-cell">{x.why}</td>
                  <td className="text-cell">{x.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <header><h2>Known limitations this tool cannot correct</h2></header>
        <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--text-secondary)' }}>
          <li style={{ marginBottom: 6 }}><strong>Fixed question order.</strong>{' '}
            {m.caveats.question_order}</li>
          <li style={{ marginBottom: 6 }}><strong>Purposive sampling.</strong>{' '}
            {m.caveats.sampling}</li>
          <li style={{ marginBottom: 6 }}><strong>A majority is a cutoff, not a margin.</strong>{' '}
            A claim clearing 50% of the directional answers by a handful of respondents is
            placed in the same cell as one clearing it by hundreds. The winning percentage and
            the directional denominator are shown on every claim so a marginal placement can be
            read off directly.</li>
          {m.manifest.notes.map((n, i) => <li key={i} style={{ marginBottom: 6 }}>{n}</li>)}
        </ul>
      </div>

      <div className="card">
        <header><h2>Run provenance</h2>
          <span className="sub">the same values are written into every export</span></header>
        <dl className="kv">
          <dt>Tool version</dt><dd>{m.manifest.tool_version}</dd>
          <dt>Run ID</dt><dd>{m.manifest.run_id}</dd>
          <dt>Run at (UTC)</dt><dd>{m.manifest.timestamp_utc}</dd>
          <dt>Input file</dt><dd>{m.manifest.input_file}</dd>
          <dt>Input SHA-256</dt>
          <dd style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{m.manifest.input_sha256}</dd>
          <dt>Respondents / claims</dt>
          <dd>{m.manifest.n_respondents} / {m.manifest.n_claims}</dd>
          <dt>Python</dt><dd>{m.manifest.python_version} · {m.manifest.platform}</dd>
          <dt>Libraries</dt>
          <dd>{Object.entries(m.manifest.library_versions)
                .map(([k, v]) => `${k} ${v}`).join(' · ')}</dd>
        </dl>
      </div>

      <div className="card">
        <header><h2>Full configuration (verbatim)</h2></header>
        <pre className="config">{JSON.stringify(m.config, null, 2)}</pre>
      </div>
    </>
  )
}
