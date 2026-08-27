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
        <p><strong>Belief threshold.</strong> {m.belief_threshold_status} — currently{' '}
          {c.belief.threshold}, read from <code>{m.config_path}</code> and defined nowhere else
          in the codebase.</p>} />

      <div className="card">
        <header><h2>Configuration in force for this run</h2>
          <span className="sub">{m.config_path}</span></header>
        <dl className="kv">
          <dt>Belief threshold</dt>
          <dd>{c.belief.threshold} — median ≥ this counts as "widely believed" ({m.belief_threshold_status})</dd>
          <dt>Borderline band</dt>
          <dd>± {c.belief.borderline_delta} around the threshold flags a claim for manual review</dd>
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
          <li style={{ marginBottom: 6 }}><strong>Belief threshold not finalised.</strong>{' '}
            {m.belief_threshold_status}. Any claim near the cutoff is flagged borderline rather
            than presented as classified.</li>
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
