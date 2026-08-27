import { useMemo, useState } from 'react'
import { Caveat, Chip, DistBar, LikertLegend, Tile, fmtNum } from '../components/common'
import { api } from '../api'
import type { ClaimRow, Overview as OverviewData } from '../types'

type SortKey = keyof ClaimRow
type Filters = {
  q: string
  evidence: string
  belief: string
  flag: string
}

const FLAG_OPTIONS = [
  ['', 'All claims'],
  ['bimodal', 'Bimodal distribution'],
  ['mismatch', 'Belief–evidence mismatch'],
  ['borderline', 'Borderline against threshold'],
  ['significant', 'Has a significant subgroup difference'],
  ['high_idk', 'IDK rate ≥ 25%'],
] as const

export function Overview({ data, onOpenClaim }: {
  data: OverviewData; onOpenClaim: (id: string) => void
}) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'q_number', dir: 1 })
  const [f, setF] = useState<Filters>({ q: '', evidence: '', belief: '', flag: '' })

  const evidenceOptions = useMemo(
    () => Array.from(new Set(data.claims.map(c => c.evidence_label))).sort(), [data.claims])
  const beliefOptions = useMemo(
    () => Array.from(new Set(data.claims.map(c => c.belief_class))).sort(), [data.claims])

  const rows = useMemo(() => {
    const needle = f.q.trim().toLowerCase()
    const out = data.claims.filter(c => {
      if (needle && !(`${c.claim_id} ${c.survey_text} ${c.book}`.toLowerCase().includes(needle)))
        return false
      if (f.evidence && c.evidence_label !== f.evidence) return false
      if (f.belief && c.belief_class !== f.belief) return false
      switch (f.flag) {
        case 'bimodal': return c.bimodal
        case 'mismatch': return c.belief_evidence_mismatch
        case 'borderline': return c.borderline
        case 'significant': return !!c.significant_variables
        case 'high_idk': return c.idk_rate_pct >= 25
        default: return true
      }
    })
    return out.sort((a, b) => {
      const av = a[sort.key], bv = b[sort.key]
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * sort.dir
      return String(av).localeCompare(String(bv)) * sort.dir
    })
  }, [data.claims, f, sort])

  const th = (key: SortKey, label: string, cls = '') => (
    <th className={`sortable ${cls}`} onClick={() =>
      setSort(s => ({ key, dir: s.key === key && s.dir === 1 ? -1 : 1 }))}
        title={`Sort by ${label}`}>
      {label}{sort.key === key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
    </th>
  )

  const s = data.summary
  return (
    <>
      <Caveat caveats={data.caveats} extra={
        s.n_pending_evidence > 0 ? (
          <p><strong>RQ2 labels incomplete.</strong> {s.n_pending_evidence} of {s.n_claims} claims
            still carry <code>PENDING</code>. Fill <code>data/claims_evidence.csv</code> before
            reporting the belief–evidence matrix.</p>
        ) : undefined} />

      <div className="tiles">
        <Tile label="Respondents" value={s.n_respondents}
              note={`${s.n_flagged_respondents} flagged for review`} />
        <Tile label="Claims" value={s.n_claims} note={`${s.n_comments} free-text comments`} />
        <Tile label="Belief–evidence mismatches" value={s.n_mismatch}
              note="believed but contradicted, or vice versa" />
        <Tile label="Bimodal claims" value={s.n_bimodal} note="answers split, median hides it" />
        <Tile label="Borderline claims" value={s.n_borderline}
              note="within 0.2 of the belief threshold" flagged={s.n_borderline > 0} />
        <Tile label="Median IDK rate" value={`${fmtNum(s.median_idk_rate_pct, 1)}%`}
              note="excluded from medians and tests" />
      </div>

      <div className="card">
        <header>
          <h2>Multiple-testing correction by demographic family</h2>
          <span className="sub">
            Benjamini–Hochberg FDR applied within each variable's own family of 50 tests,
            never pooled across variables
          </span>
        </header>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Variable</th>
                <th className="num">Tests run</th>
                <th className="num">Not testable</th>
                <th className="num">Significant (raw p &lt; α)</th>
                <th className="num">Significant after BH</th>
              </tr>
            </thead>
            <tbody>
              {data.correction_families.map(fam => (
                <tr key={fam.variable}>
                  <td>{fam.variable}</td>
                  <td className="num">{fam.n_tests}</td>
                  <td className="num">{fam.n_excluded}</td>
                  <td className="num">{fam.n_significant_raw}</td>
                  <td className="num"><strong>{fam.n_significant_adjusted}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="filters">
        <div className="field">
          <label htmlFor="q">Search claim text / ID / book</label>
          <input id="q" value={f.q} placeholder="e.g. inspection, CLM-000015"
                 onChange={e => setF({ ...f, q: e.target.value })} style={{ minWidth: 280 }} />
        </div>
        <div className="field">
          <label htmlFor="ev">RQ2 evidence label</label>
          <select id="ev" value={f.evidence} onChange={e => setF({ ...f, evidence: e.target.value })}>
            <option value="">All labels</option>
            {evidenceOptions.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="bc">Belief class</label>
          <select id="bc" value={f.belief} onChange={e => setF({ ...f, belief: e.target.value })}>
            <option value="">All</option>
            {beliefOptions.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="fl">Flag</label>
          <select id="fl" value={f.flag} onChange={e => setF({ ...f, flag: e.target.value })}>
            {FLAG_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="spacer" />
        <a className="btn" href={api.exportUrl('claims')} download>Export table (CSV)</a>
      </div>

      <div className="card">
        <header>
          <h2>All claims</h2>
          <span className="sub">{rows.length} of {data.claims.length} shown · click a claim ID for detail</span>
          <div className="spacer" />
          <LikertLegend idkLabel="I don't know how to answer this" />
        </header>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {th('q_number', 'Q', 'num')}
                {th('claim_id', 'Claim')}
                <th>Distribution (valid answers)</th>
                {th('median', 'Median', 'num')}
                {th('iqr', 'IQR', 'num')}
                {th('idk_rate_pct', 'IDK %', 'num')}
                {th('n_valid', 'n valid', 'num')}
                <th>Flags</th>
                {th('evidence_label', 'RQ2 evidence')}
                {th('belief_class', 'Belief')}
                {th('significant_variables', 'Significant subgroups')}
                {th('n_comments', 'Comments', 'num')}
                {th('book', 'Source book')}
                {th('author', 'Author')}
                {th('survey_text', 'Claim as shown to respondents')}
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.claim_id} className={r.excluded ? 'excluded' : undefined}>
                  <td className="num">{r.q_number}</td>
                  <td className="claim-link">
                    <button onClick={() => onOpenClaim(r.claim_id)}>{r.claim_id}</button>
                  </td>
                  <td><DistBar row={r} /></td>
                  <td className="num"><strong>{fmtNum(r.median, 1)}</strong></td>
                  <td className="num">{fmtNum(r.iqr, 1)}</td>
                  <td className="num">
                    {fmtNum(r.idk_rate_pct, 1)}
                    {r.high_idk && <span title="High IDK rate — needs manual review"
                                         style={{ color: 'var(--status-serious)' }}> ⚑</span>}
                  </td>
                  <td className="num">{r.n_valid}</td>
                  <td>
                    {r.bimodal && <Chip kind="warning" title="Answers split at both ends; the median alone is misleading">bimodal</Chip>}{' '}
                    {r.high_idk && <Chip kind="warning" title="IDK rate at or above the review threshold; the median rests on a shrinking subset">high IDK</Chip>}{' '}
                    {r.borderline && <Chip kind="warning" title="Median within 0.2 of the belief threshold — classification provisional">borderline</Chip>}{' '}
                    {r.belief_evidence_mismatch &&
                      <Chip kind="critical" title={r.mismatch_kind ?? ''}>⚑ mismatch</Chip>}
                    {r.excluded && <Chip kind="muted" title={r.exclusion_reason ?? ''}>excluded</Chip>}
                  </td>
                  <td>{r.evidence_label === 'PENDING'
                    ? <Chip kind="muted" title="RQ2 label not entered yet">PENDING</Chip>
                    : <>
                        {r.evidence_label}
                        {r.evidence_strength && (
                          <div style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>
                            {r.evidence_strength}
                          </div>
                        )}
                        {!r.scored && r.evidence_label !== 'PENDING' && (
                          <div style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>
                            not scored
                          </div>
                        )}
                      </>}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{r.belief_class}</td>
                  <td>{r.significant_variables || <span className="excluded">none</span>}</td>
                  <td className="num">{r.n_comments}</td>
                  <td style={{ minWidth: 190, maxWidth: 260 }}>
                    {r.book === 'MISSING'
                      ? <Chip kind="warning" title="Not recorded in Final_50_Claims.xlsx">MISSING</Chip>
                      : r.book}
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {r.author === 'MISSING'
                      ? <Chip kind="warning"
                              title="Final_50_Claims.xlsx has no author column — not inferred from the book title">
                          MISSING</Chip>
                      : r.author}
                  </td>
                  <td className="text-cell">{r.survey_text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
