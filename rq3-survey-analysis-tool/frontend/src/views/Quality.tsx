import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Caveat, Chip, ErrorBox, Loading } from '../components/common'
import type { Caveats, DatasetList, QualityPayload } from '../types'

export function Quality({ caveats, onRerun }: {
  caveats: Caveats; onRerun: () => void
}) {
  const [q, setQ] = useState<QualityPayload | null>(null)
  const [ds, setDs] = useState<DatasetList | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [scope, setScope] = useState('')
  const [written, setWritten] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.quality(), api.datasets()])
      .then(([a, b]) => { setQ(a); setDs(b) })
      .catch(e => setErr(String(e.message ?? e)))
  }, [])

  const exclusions = useMemo(
    () => (q?.exclusions ?? []).filter(e => !scope || e.scope === scope), [q, scope])

  if (err) return <ErrorBox error={err} />
  if (!q || !ds) return <Loading what="data-quality report" />

  const run = async (path?: string) => {
    setBusy(true); setErr(null)
    try {
      await api.rerun(path)
      const [a, b] = await Promise.all([api.quality(), api.datasets()])
      setQ(a); setDs(b); onRerun()
    } catch (e: any) { setErr(String(e.message ?? e)) } finally { setBusy(false) }
  }

  return (
    <>
      <Caveat caveats={caveats} />

      <div className="card">
        <header>
          <h2>Dataset in use</h2>
          <span className="sub">
            results are always produced by a full re-run against one export —
            exports are never merged or appended
          </span>
        </header>
        <dl className="kv">
          <dt>Input file</dt><dd>{q.dataset.input_file}</dd>
          <dt>SHA-256</dt><dd style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{q.dataset.input_sha256}</dd>
          <dt>Run ID</dt><dd>{q.dataset.run_id}</dd>
          <dt>Run at (UTC)</dt><dd>{q.dataset.timestamp_utc}</dd>
          <dt>Respondents</dt><dd>{q.dataset.n_respondents}</dd>
        </dl>
        <div className="filters" style={{ marginTop: 14, marginBottom: 0 }}>
          {ds.available.map(f => (
            <button key={f.path} className={`btn ${f.current ? 'primary' : ''}`}
                    disabled={busy} onClick={() => run(f.path)}>
              {f.current ? '● ' : ''}{f.name} ({(f.size_bytes / 1024).toFixed(0)} KB)
            </button>
          ))}
          <div className="spacer" />
          <button className="btn" disabled={busy}
                  onClick={async () => {
                    setBusy(true)
                    try { const r = await api.writeExports(); setWritten(r.run_id) }
                    finally { setBusy(false) }
                  }}>
            Write full export set to disk
          </button>
          <a className="btn" href={api.exportUrl('full')} download>Download full run (JSON)</a>
        </div>
        {written && (
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 0 }}>
            Written to <code>data/results/{written}/</code>
          </p>
        )}
      </div>

      <div className="tiles">
        <div className="tile"><div className="label">Respondents</div>
          <div className="value">{q.quality.n_respondents}</div>
          <div className="note">{q.quality.consent_check}</div></div>
        <div className="tile flagged"><div className="label">Flagged for review</div>
          <div className="value">{q.quality.n_flagged}</div>
          <div className="note">flagged only — nothing auto-excluded</div></div>
        <div className="tile"><div className="label">Duplicate answer patterns</div>
          <div className="value">{q.quality.duplicate_pattern_groups.length}</div>
          <div className="note">identical 50-answer strings</div></div>
        <div className="tile"><div className="label">Excluded comparisons</div>
          <div className="value">{q.exclusions.filter(e => e.scope === 'comparison').length}</div>
          <div className="note">too few subgroups to test</div></div>
        <div className="tile"><div className="label">Excluded subgroups</div>
          <div className="value">{q.exclusions.filter(e => e.scope === 'subgroup').length}</div>
          <div className="note">below the minimum subgroup size</div></div>
      </div>

      <div className="card">
        <header>
          <h2>Checks applied</h2>
          <span className="sub">thresholds from config.yaml — every flag is reviewable, none is automatic</span>
        </header>
        <dl className="kv">
          <dt>Straightlining</dt>
          <dd>flag at ≤ {q.quality.thresholds.max_distinct_values} distinct answer value(s) across all claims</dd>
          <dt>Modal dominance</dt>
          <dd>flag at ≥ {(q.quality.thresholds.modal_answer_share * 100).toFixed(0)}% of answers on one value</dd>
          <dt>IDK rate</dt>
          <dd>flag at ≥ {(q.quality.thresholds.idk_rate * 100).toFixed(0)}% IDK</dd>
          <dt>Completion speed</dt>
          <dd>{q.quality.speeding_check.startsWith('unavailable')
            ? <Chip kind="warning" title={q.quality.speeding_check}>
                unavailable — no duration column in this export
              </Chip>
            : `flag under ${q.quality.thresholds.min_completion_seconds}s`}</dd>
        </dl>
        {q.quality.notes.length > 0 && (
          <ul style={{ marginTop: 12, marginBottom: 0, paddingLeft: 18,
                       color: 'var(--text-secondary)', fontSize: 13 }}>
            {q.quality.notes.map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        )}
      </div>

      <div className="card">
        <header>
          <h2>Flagged respondents ({q.quality.flagged.length})</h2>
          <span className="sub">review manually — exclusion is a research decision, not a threshold</span>
          <div className="spacer" />
          <a className="btn" href={api.exportUrl('flagged')} download>Export (CSV)</a>
        </header>
        {q.quality.flagged.length === 0
          ? <p className="excluded" style={{ margin: 0 }}>Nothing flagged.</p>
          : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Respondent</th><th>Flags</th>
                    <th className="num">Distinct values</th><th className="num">Modal share</th>
                    <th className="num">IDK rate</th><th className="num">Answered</th>
                    <th>Demographics</th>
                  </tr>
                </thead>
                <tbody>
                  {q.quality.flagged.map(r => (
                    <tr key={r.respondent_id}>
                      <td>{r.respondent_id}</td>
                      <td>{r.flags.map((f, i) => (
                        <div key={i} style={{ marginBottom: 2 }}>
                          <Chip kind="warning">{f}</Chip>
                        </div>))}</td>
                      <td className="num">{r.distinct_values}</td>
                      <td className="num">{(r.modal_share * 100).toFixed(0)}%</td>
                      <td className="num">{(r.idk_rate * 100).toFixed(0)}%</td>
                      <td className="num">{r.n_answered}</td>
                      <td className="text-cell">
                        {Object.entries(r.demographics)
                          .filter(([, v]) => v != null)
                          .map(([k, v]) => `${k}: ${v}`).join(' · ') || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </div>

      <div className="card">
        <header>
          <h2>Explicit exclusions ({q.exclusions.length})</h2>
          <span className="sub">
            every analysis that did not run, with its reason — nothing is silently missing
          </span>
          <div className="spacer" />
          <div className="field">
            <label htmlFor="scope">Scope</label>
            <select id="scope" value={scope} onChange={e => setScope(e.target.value)}>
              <option value="">All</option>
              <option value="comparison">Comparison not run</option>
              <option value="subgroup">Subgroup dropped</option>
            </select>
          </div>
          <a className="btn" href={api.exportUrl('exclusions')} download>Export (CSV)</a>
        </header>
        <div className="table-wrap" style={{ maxHeight: 460, overflowY: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Scope</th><th>Claim</th><th>Variable</th><th>Subgroup</th>
                <th className="num">n valid</th><th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {exclusions.slice(0, 500).map((e, i) => (
                <tr key={i}>
                  <td>{e.scope}</td><td>{e.claim_id}</td><td>{e.variable}</td>
                  <td>{e.group ?? '—'}</td>
                  <td className="num">{e.n_valid ?? '—'}</td>
                  <td className="text-cell">{e.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {exclusions.length > 500 && (
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 0 }}>
            Showing the first 500 of {exclusions.length}. The CSV export carries all of them.
          </p>
        )}
      </div>
    </>
  )
}
