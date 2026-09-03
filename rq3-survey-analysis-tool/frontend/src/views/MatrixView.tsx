import { useEffect, useState } from 'react'
import { api } from '../api'
import { Caveat, Chip, ErrorBox, Loading } from '../components/common'
import type { Caveats, Matrix } from '../types'

export function MatrixView({ caveats, onOpenClaim }: {
  caveats: Caveats; onOpenClaim: (id: string) => void
}) {
  const [m, setM] = useState<Matrix | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { api.matrix().then(setM).catch(e => setErr(String(e.message ?? e))) }, [])

  if (err) return <ErrorBox error={err} />
  if (!m) return <Loading what="belief–evidence matrix" />

  const cell = (belief: string, label: string) =>
    m.cells.find(c => c.belief_class === belief && c.evidence_label === label)

  // Mismatch cells are the RQ3 finding: a majority agreed with a contradicted
  // claim, or disagreed with a supported one. Marked with a status accent AND a
  // label — never colour alone. NO EVIDENCE FOUND is deliberately absent: with
  // no evidence located there is nothing to agree or disagree with, so that
  // column is reported in its own bucket and never scored either way.
  const isMismatch = (belief: string, label: string) =>
    (belief === 'Majority agreed' && label === 'CONTRADICTED') ||
    (belief === 'Majority disagreed' && label === 'SUPPORTED')

  const cols = m.evidence_labels
  const gridStyle = {
    gridTemplateColumns: `minmax(150px, max-content) repeat(${cols.length}, minmax(170px, 1fr))`,
  }

  return (
    <>
      <Caveat caveats={caveats} extra={
        <p><strong>What enters the matrix.</strong> Only claims where one side passed{' '}
          {(m.majority_threshold * 100).toFixed(0)}% of the directional answers (the five
          substantive Likert points; IDK excluded). {m.bucket_counts.mixed} claim(s) reached
          no majority and {m.bucket_counts.idk_dominant} were IDK-dominant at ≥{' '}
          {(m.idk_dominance_threshold * 100).toFixed(0)}% of the full sample — both are
          listed below rather than placed in a cell.</p>} />

      <div className="tiles">
        <div className="tile"><div className="label">In the matrix</div>
          <div className="value">{m.bucket_counts.clear_direction}</div>
          <div className="note">claims with a clear majority direction</div></div>
        <div className="tile"><div className="label">Mismatches</div>
          <div className="value">{m.n_mismatch}<span style={{ fontSize: 15,
            color: 'var(--text-muted)', fontWeight: 400 }}> / {m.n_scored}</span></div>
          <div className="note">of the {m.n_scored} scored claims</div></div>
        <div className="tile"><div className="label">Matches</div>
          <div className="value">{m.n_match}</div>
          <div className="note">belief agrees with the RQ2 evidence</div></div>
        <div className="tile"><div className="label">Not scored</div>
          <div className="value">{m.n_not_scored}</div>
          <div className="note">NO EVIDENCE FOUND — nothing to agree with</div></div>
        <div className="tile"><div className="label">No majority</div>
          <div className="value">{m.bucket_counts.mixed}</div>
          <div className="note">neither side passed the threshold</div></div>
        <div className="tile flagged"><div className="label">IDK-dominant</div>
          <div className="value">{m.bucket_counts.idk_dominant}</div>
          <div className="note">excluded — most could not answer</div></div>
        <div className="tile"><div className="label">Unlabelled (RQ2 pending)</div>
          <div className="value">{m.n_pending_evidence}</div>
          <div className="note">fill data/claims_evidence.csv</div></div>
      </div>

      <div className="card">
        <header>
          <h2>Belief–evidence matrix</h2>
          <span className="sub">
            majority direction × RQ2 evidence label · clear-direction claims only
          </span>
          <div className="spacer" />
          <a className="btn" href={api.exportUrl('matrix')} download>Export matrix (CSV)</a>
        </header>

        <div className="matrix" style={gridStyle}>
          <div className="matrix-head" />
          {cols.map(c => <div className="matrix-head" key={c}>{c}</div>)}

          {m.belief_classes.map(belief => (
            <Row key={belief} belief={belief} cols={cols} cell={cell}
                 isMismatch={isMismatch} onOpenClaim={onOpenClaim} />
          ))}
        </div>

        <div className="legend" style={{ marginTop: 14 }}>
          <span className="item">
            <span className="swatch" style={{
              background: 'transparent', borderLeft: '3px solid var(--status-critical)',
              width: 3, height: 14 }} />
            ⚑ belief–evidence mismatch
          </span>

        </div>
      </div>

      <div className="card">
        <header><h2>Notes carried with this matrix</h2></header>
        <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--text-secondary)', fontSize: 13 }}>
          {m.notes.map((n, i) => <li key={i} style={{ marginBottom: 4 }}>{n}</li>)}
        </ul>
      </div>

      <div className="card">
        <header>
          <h2>Per-claim classification</h2>
          <span className="sub">every claim, its directional split, and why it is in or out</span>
        </header>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Claim</th><th className="num">% agree</th>
                <th className="num">% disagree</th>
                <th>Bucket</th><th>Majority</th><th>RQ2 evidence</th><th>Status</th>
                <th className="num">directional n</th><th className="num">IDK rate</th>
              </tr>
            </thead>
            <tbody>
              {m.classifications.map(c => (
                <tr key={c.claim_id}>
                  <td className="claim-link">
                    <button onClick={() => onOpenClaim(c.claim_id)}>{c.claim_id}</button>
                  </td>
                  <td className="num">{c.pct_agree == null ? '—' : `${(c.pct_agree * 100).toFixed(1)}%`}</td>
                  <td className="num">{c.pct_disagree == null ? '—' : `${(c.pct_disagree * 100).toFixed(1)}%`}</td>
                  <td>{c.bucket.replace(/_/g, ' ')}</td>
                  <td>{c.belief_label ?? <span className="excluded">—</span>}</td>
                  <td>{c.in_matrix ? c.evidence_label : <span className="excluded">n/a</span>}</td>
                  <td>
                    {c.mismatch && <Chip kind="critical" title={c.mismatch_kind ?? ''}>⚑ mismatch</Chip>}
                    {!c.mismatch && c.in_matrix && <Chip kind="muted">{c.verdict_status}</Chip>}
                    {!c.in_matrix && <Chip kind="warning" title={c.reason ?? ''}>excluded</Chip>}
                  </td>
                  <td className="num">{c.directional_n}</td>
                  <td className="num">{(c.idk_rate * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

function Row({ belief, cols, cell, isMismatch, onOpenClaim }: {
  belief: string
  cols: string[]
  cell: (b: string, l: string) => any
  isMismatch: (b: string, l: string) => boolean
  onOpenClaim: (id: string) => void
}) {
  return (
    <>
      <div className="matrix-head" style={{ alignSelf: 'center', paddingBottom: 0 }}>{belief}</div>
      {cols.map(label => {
        const c = cell(belief, label)
        const count = c?.count ?? 0
        // The mismatch accent marks an actual finding, so an empty cell never
        // wears it — a red rule on a zero would read as a result that isn't there.
        const mismatch = isMismatch(belief, label) && count > 0
        const border = new Set(c?.borderline_claim_ids ?? [])
        return (
          <div key={label}
               className={`cell ${mismatch ? 'mismatch' : ''} ${!count ? 'empty' : ''}`}>
            <div className="count">{count}</div>
            {mismatch && <Chip kind="critical">⚑ mismatch</Chip>}
            <div className="ids">
              {(c?.claim_ids ?? []).map((id: string) => (
                <button key={id} className={border.has(id) ? 'borderline' : undefined}
                        title={border.has(id)
                          ? `${id} — borderline, placement provisional`
                          : id}
                        onClick={() => onOpenClaim(id)}>
                  {id.replace('CLM-', '')}
                </button>
              ))}
            </div>
          </div>
        )
      })}
    </>
  )
}
