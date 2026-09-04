import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../api'
import {
  Caveat, Chip, DistBar, ErrorBox, LIKERT_COLORS, LikertLegend, Loading,
  fmtNum, pText,
} from '../components/common'
import type {
  ClaimDetail as Detail, Comparison, Descriptives, GroupSummary,
} from '../types'

const SCALE = ['1', '2', '3', '4', '5'] as const

/**
 * Section anchors. The page is deliberately long: the brief is that an examiner
 * reading only this page for one claim can verify the result by hand, so every
 * number is shown with the data and the arithmetic that produced it.
 */
const SECTIONS = [
  ['identity', 'A · Claim'],
  ['breakdown', 'B · Raw responses'],
  ['working', 'C · Calculation walkthrough'],
  ['bimodality', 'D · Bimodality check'],
  ['result', 'E · Result'],
  ['evidence', 'F · Evidence comparison'],
  ['comments', 'G · Comments'],
] as const

// ---------------------------------------------------------------------------
// Charts
// ---------------------------------------------------------------------------

function DistTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="tooltip">
      <div className="t-title">{d.label}</div>
      <div className="t-row">{d.count} respondents</div>
      <div className="t-row">
        {d.offScale ? `${d.pctAll.toFixed(1)}% of all respondents (off-scale)`
                    : `${d.pct.toFixed(1)}% of valid answers`}
      </div>
    </div>
  )
}

function chartData(freqs: Record<string, number>, nIdk: number, nTotal: number,
                   nValid: number, labels: Record<string, string>, idkLabel: string) {
  const data = SCALE.map(k => ({
    key: k as string,
    label: `${k} · ${labels[k]}`,
    tick: k as string,
    count: freqs[k] ?? 0,
    pct: nValid ? ((freqs[k] ?? 0) / nValid) * 100 : 0,
    pctAll: nTotal ? ((freqs[k] ?? 0) / nTotal) * 100 : 0,
    offScale: false,
  }))
  data.push({
    key: 'IDK', label: idkLabel, tick: 'IDK', count: nIdk, pct: 0,
    pctAll: nTotal ? (nIdk / nTotal) * 100 : 0, offScale: true,
  })
  return data
}

function DistributionChart({ data, height = 300 }: {
  data: ReturnType<typeof chartData>; height?: number
}) {
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 22, right: 8, left: 0, bottom: 4 }}
                  barCategoryGap="22%">
          <CartesianGrid vertical={false} stroke="var(--gridline)" />
          <XAxis dataKey="tick" tickLine={false} axisLine={{ stroke: 'var(--baseline)' }}
                 tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
          <YAxis tickLine={false} axisLine={false} width={44}
                 tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
          <Tooltip content={<DistTooltip />} cursor={{ fill: 'var(--surface-3)' }} />
          <Bar dataKey="count" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {/* Direct value labels: mandatory relief for the sub-3:1 "Agree" step. */}
            <LabelList dataKey="count" position="top"
                       style={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
            {data.map(e => (
              <Cell key={e.key}
                    fill={e.offScale ? 'transparent' : LIKERT_COLORS[e.key]}
                    stroke={e.offScale ? 'var(--likert-idk-ring)' : undefined}
                    strokeWidth={e.offScale ? 2 : 0} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ---------------------------------------------------------------------------
// B — raw response breakdown
// ---------------------------------------------------------------------------

function OverallBreakdown({ d, s }: { d: Detail; s: Descriptives }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Answer</th>
            <th className="num">Count</th>
            <th className="num">% of all {s.n_total}</th>
            <th className="num">% of {s.n_valid} valid</th>
          </tr>
        </thead>
        <tbody>
          {SCALE.map(k => (
            <tr key={k}>
              <td>
                <span className="swatch" style={{
                  background: LIKERT_COLORS[k], display: 'inline-block',
                  marginRight: 6, verticalAlign: 'middle' }} />
                {k} · {d.likert_labels[k]}
              </td>
              <td className="num">{s.frequencies[k] ?? 0}</td>
              <td className="num">
                {s.n_total ? (((s.frequencies[k] ?? 0) / s.n_total) * 100).toFixed(1) : '0.0'}%
              </td>
              <td className="num">{fmtNum(s.percentages[k], 1)}%</td>
            </tr>
          ))}
          <tr>
            <td>
              <span className="swatch hollow" style={{
                display: 'inline-block', marginRight: 6, verticalAlign: 'middle' }} />
              {d.idk_label} <span className="excluded">(off-scale)</span>
            </td>
            <td className="num">{s.n_idk}</td>
            <td className="num">
              {s.n_total ? ((s.n_idk / s.n_total) * 100).toFixed(1) : '0.0'}%
            </td>
            <td className="num excluded">excluded</td>
          </tr>
          <tr>
            <td><strong>Total</strong></td>
            <td className="num"><strong>{s.n_total}</strong></td>
            <td className="num"><strong>100.0%</strong></td>
            <td className="num"><strong>100.0%</strong></td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

function SubgroupBreakdown({ d, c }: { d: Detail; c: Comparison }) {
  const [showCharts, setShowCharts] = useState(false)
  const included = c.groups.filter(g => g.included)
  const tooSmall = c.groups.filter(g => g.excluded_kind === 'below_min_size')
  const unassigned = c.groups.filter(g => g.excluded_kind === 'unassigned')
  const ordered = [...included, ...tooSmall, ...unassigned]

  const row = (g: GroupSummary) => (
    <tr key={g.group} className={g.included ? undefined : 'excluded'}>
      <td style={{ whiteSpace: 'nowrap' }}>
        {g.group}
        {!g.included && (
          <div style={{ marginTop: 3 }}>
            <Chip kind="muted" title={g.exclusion_reason ?? ''}>
              {g.excluded_kind === 'unassigned'
                ? 'excluded — this question was left blank, so no subgroup'
                : `excluded — below minimum group size (${d.min_subgroup_size})`}
            </Chip>
          </div>
        )}
      </td>
      <td className="num">{g.n_total}</td>
      {SCALE.map(k => (
        <td className="num" key={k}>
          {g.frequencies[k] ?? 0}
          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
            {fmtNum(g.percentages[k], 0)}%
          </div>
        </td>
      ))}
      <td className="num">
        {g.n_idk}
        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
          {(g.idk_rate * 100).toFixed(0)}%
        </div>
      </td>
      <td className="num">{g.n_valid}</td>
      <td className="num"><strong>{fmtNum(g.median, 1)}</strong></td>
      <td><DistBar row={{
        freq_1: g.frequencies['1'] ?? 0, freq_2: g.frequencies['2'] ?? 0,
        freq_3: g.frequencies['3'] ?? 0, freq_4: g.frequencies['4'] ?? 0,
        freq_5: g.frequencies['5'] ?? 0 }} /></td>
    </tr>
  )

  return (
    <div className="card">
      <header>
        <h3 style={{ textTransform: 'capitalize' }}>{c.variable.replace(/_/g, ' ')}</h3>
        <span className="sub">
          {included.length} subgroup{included.length === 1 ? '' : 's'} at or above the
          minimum size of {d.min_subgroup_size}
          {tooSmall.length > 0 && `, ${tooSmall.length} below it (listed, not hidden)`}
          {unassigned.length > 0 &&
            `, plus ${unassigned[0].n_total} respondent(s) who left this question blank`}
        </span>
        <div className="spacer" />
        {included.length > 0 && (
          <button className="btn" onClick={() => setShowCharts(v => !v)}>
            {showCharts ? 'Hide' : 'Show'} bar chart per subgroup
          </button>
        )}
      </header>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Subgroup</th>
              <th className="num">n shown</th>
              {SCALE.map(k => <th className="num" key={k} title={d.likert_labels[k]}>{k}</th>)}
              <th className="num">IDK</th>
              <th className="num">n valid</th>
              <th className="num">Median</th>
              <th>Distribution</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map(row)}
            <tr>
              <td><strong>All subgroups</strong></td>
              <td className="num"><strong>
                {c.groups.reduce((a, g) => a + g.n_total, 0)}</strong></td>
              {SCALE.map(k => (
                <td className="num" key={k}><strong>
                  {c.groups.reduce((a, g) => a + (g.frequencies[k] ?? 0), 0)}</strong></td>
              ))}
              <td className="num"><strong>
                {c.groups.reduce((a, g) => a + g.n_idk, 0)}</strong></td>
              <td className="num"><strong>
                {c.groups.reduce((a, g) => a + g.n_valid, 0)}</strong></td>
              <td className="num">—</td>
              <td className="excluded" style={{ fontSize: 11 }}>
                totals must equal the overall breakdown above
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {showCharts && (
        <div style={{ display: 'grid', gap: 12, marginTop: 14,
                      gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
          {included.map(g => (
            <div key={g.group} style={{
              border: '1px solid var(--border)', borderRadius: 6, padding: '10px 8px 4px' }}>
              <div style={{ fontSize: 12, fontWeight: 600, padding: '0 6px' }}>{g.group}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: '0 6px 4px' }}>
                n = {g.n_valid} valid of {g.n_total} · median {fmtNum(g.median, 1)}
              </div>
              <DistributionChart height={190} data={chartData(
                g.frequencies, g.n_idk, g.n_total, g.n_valid,
                d.likert_labels, d.idk_label)} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// C — calculation walkthrough
// ---------------------------------------------------------------------------

function EffectSizeWorking({ c, thresholds }: {
  c: Comparison; thresholds: { small: number; medium: number; large: number }
}) {
  if (c.effect) {
    const e = c.effect
    const f = (e.favourable_pairs + e.tied_pairs / 2) / e.total_pairs
    const u = (e.unfavourable_pairs + e.tied_pairs / 2) / e.total_pairs
    return (
      <table>
        <tbody>
          <tr><td>Cross-group pairs</td>
            <td>n₁ × n₂ = {c.working?.values.n1} × {c.working?.values.n2}</td>
            <td className="num">{e.total_pairs.toLocaleString()}</td></tr>
          <tr><td>Favourable pairs</td>
            <td>first group scored higher</td>
            <td className="num">{e.favourable_pairs.toLocaleString()}</td></tr>
          <tr><td>Unfavourable pairs</td>
            <td>second group scored higher</td>
            <td className="num">{e.unfavourable_pairs.toLocaleString()}</td></tr>
          <tr><td>Tied pairs</td>
            <td>split evenly between the two (Kerby 2014)</td>
            <td className="num">{e.tied_pairs.toLocaleString()}</td></tr>
          <tr><td>Check</td>
            <td>favourable + unfavourable + tied = total</td>
            <td className="num">
              {(e.favourable_pairs + e.unfavourable_pairs + e.tied_pairs).toLocaleString()}
            </td></tr>
          <tr><td>Proportion favourable</td>
            <td>f = ({e.favourable_pairs.toLocaleString()} + {(e.tied_pairs / 2).toLocaleString()}) / {e.total_pairs.toLocaleString()}</td>
            <td className="num">{f.toFixed(4)}</td></tr>
          <tr><td>Proportion unfavourable</td>
            <td>u = ({e.unfavourable_pairs.toLocaleString()} + {(e.tied_pairs / 2).toLocaleString()}) / {e.total_pairs.toLocaleString()}</td>
            <td className="num">{u.toFixed(4)}</td></tr>
          <tr><td><strong>Rank-biserial r</strong></td>
            <td>r = f − u = {f.toFixed(4)} − {u.toFixed(4)}</td>
            <td className="num"><strong>{e.r.toFixed(4)}</strong></td></tr>
          <tr><td>Interpretation</td>
            <td>
              Romano et al. (2006): |r| &gt; {thresholds.large} large ·{' '}
              {thresholds.medium}–{thresholds.large} medium ·{' '}
              {thresholds.small}–{thresholds.medium} small
            </td>
            <td className="num"><strong>{e.magnitude}</strong></td></tr>
          <tr><td>Direction</td><td colSpan={2}>{e.direction}</td></tr>
        </tbody>
      </table>
    )
  }
  if (c.omnibus_effect) {
    const e = c.omnibus_effect
    return (
      <table>
        <tbody>
          <tr><td>Formula</td><td colSpan={2}>{e.formula}</td></tr>
          <tr><td>Substitution</td>
            <td>ε² = ({e.h_statistic.toFixed(4)} − {e.k_groups} + 1) / ({e.n} − {e.k_groups})</td>
            <td className="num"><strong>{e.epsilon_squared.toFixed(4)}</strong></td></tr>
          <tr><td>Interpretation</td>
            <td>Cohen-style η² bands: .01 small · .06 medium · .14 large</td>
            <td className="num"><strong>{e.magnitude}</strong></td></tr>
          <tr><td colSpan={3} style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            {e.field_notes[0]}</td></tr>
        </tbody>
      </table>
    )
  }
  return <p className="excluded" style={{ margin: 0 }}>No effect size — no test was run.</p>
}

function Walkthrough({ c, d }: { c: Comparison; d: Detail }) {
  const [openPairs, setOpenPairs] = useState(false)
  const included = c.groups.filter(g => g.included)

  return (
    <div className="card">
      <header>
        <h3 style={{ textTransform: 'capitalize' }}>{c.variable.replace(/_/g, ' ')}</h3>
        <span className="sub">
          {c.test === 'mann_whitney_u' ? 'Mann–Whitney U (2 subgroups)'
            : c.test === 'kruskal_wallis' ? `Kruskal–Wallis H (${included.length} subgroups)`
            : 'no test run'}
        </span>
        <div className="spacer" />
        {c.significant_adjusted === true &&
          <Chip kind="good">✓ significant after BH</Chip>}
        {c.significant_adjusted === false &&
          <Chip kind="muted">not significant after BH</Chip>}
        {c.excluded && <Chip kind="muted">not tested</Chip>}
      </header>

      {c.excluded && (
        <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
          <strong>Not tested:</strong> {c.exclusion_reason}
        </p>
      )}

      {!c.excluded && (
        <>
          <h4 style={{ margin: '4px 0 6px' }}>1 · Ranks</h4>
          <p style={{ margin: '0 0 8px', fontSize: 12, color: 'var(--text-muted)' }}>
            All valid (non-IDK) answers from the included subgroups are ranked together;
            tied answers share the mean of the ranks they span.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Subgroup</th><th className="num">n valid</th>
                  <th className="num">Rank sum Rᵢ</th><th className="num">Mean rank</th>
                  <th className="num">Median</th>
                </tr>
              </thead>
              <tbody>
                {included.map(g => (
                  <tr key={g.group}>
                    <td>{g.group}</td>
                    <td className="num">{g.n_valid}</td>
                    <td className="num">{fmtNum(g.rank_sum, 1)}</td>
                    <td className="num">{fmtNum(g.mean_rank, 2)}</td>
                    <td className="num">{fmtNum(g.median, 1)}</td>
                  </tr>
                ))}
                <tr>
                  <td><strong>Total</strong></td>
                  <td className="num"><strong>
                    {included.reduce((a, g) => a + g.n_valid, 0)}</strong></td>
                  <td className="num"><strong>
                    {fmtNum(included.reduce((a, g) => a + (g.rank_sum ?? 0), 0), 1)}
                  </strong></td>
                  <td className="num excluded" colSpan={2} style={{ fontSize: 11 }}>
                    = N(N+1)/2 for N ={' '}
                    {included.reduce((a, g) => a + g.n_valid, 0)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <h4 style={{ margin: '16px 0 6px' }}>2 · Test statistic</h4>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Step</th><th>Calculation</th><th>Result</th></tr>
              </thead>
              <tbody>
                {c.working?.steps.map((s, i) => (
                  <tr key={i}>
                    <td style={{ whiteSpace: 'nowrap' }}>{s.label}</td>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{s.formula}</td>
                    <td style={{
                      fontFamily: 'var(--mono)', fontSize: 12,
                      // Short results stay on one line; the long per-group rank
                      // listing wraps rather than being clipped by the column.
                      whiteSpace: s.result.length > 44 ? 'normal' : 'nowrap',
                      minWidth: s.result.length > 44 ? 320 : undefined,
                    }}>
                      <strong>{s.result}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h4 style={{ margin: '16px 0 6px' }}>3 · Multiple-testing correction</h4>
          {c.bh ? (
            <div className="table-wrap">
              <table>
                <tbody>
                  <tr><td>Family</td>
                    <td colSpan={2}>
                      corrected within the <strong>'{c.bh.family}'</strong> family of{' '}
                      {c.bh.family_size} tests (one per claim), separately from every
                      other demographic variable
                    </td></tr>
                  <tr><td>Raw p-value</td><td>from the test above</td>
                    <td className="num">{pText(c.bh.raw_p)}</td></tr>
                  <tr><td>Rank in family</td>
                    <td>j = position when the {c.bh.family_size} raw p-values are sorted ascending</td>
                    <td className="num">{c.bh.rank_in_family}</td></tr>
                  <tr><td>BH critical value</td>
                    <td>(j/m)·α = ({c.bh.rank_in_family}/{c.bh.family_size}) × {c.bh.alpha}</td>
                    <td className="num">{c.bh.critical_value.toFixed(6)}</td></tr>
                  <tr><td><strong>Adjusted p</strong></td>
                    <td>Benjamini–Hochberg ({c.bh.method}), monotone from the largest rank down</td>
                    <td className="num"><strong>{pText(c.bh.p_adjusted)}</strong></td></tr>
                  <tr><td>Verdict</td>
                    <td>adjusted p {c.bh.significant ? '≤' : '>'} α = {c.bh.alpha}</td>
                    <td>{c.bh.significant
                      ? <Chip kind="good">✓ significant</Chip>
                      : <Chip kind="muted">not significant</Chip>}</td></tr>
                </tbody>
              </table>
            </div>
          ) : <p className="excluded" style={{ margin: 0 }}>No correction — no p-value.</p>}

          <h4 style={{ margin: '16px 0 6px' }}>4 · Effect size</h4>
          <div className="table-wrap">
            <EffectSizeWorking c={c} thresholds={d.effect_size_thresholds} />
          </div>

          {c.pairwise.length > 0 && (
            <>
              <h4 style={{ margin: '16px 0 6px' }}>5 · Pairwise follow-ups</h4>
              <button className="btn" onClick={() => setOpenPairs(v => !v)}>
                {openPairs ? 'Hide' : 'Show'} {c.pairwise.length} pairwise comparison
                {c.pairwise.length > 1 ? 's' : ''}
              </button>
              {openPairs && (
                <div className="table-wrap" style={{ marginTop: 10 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Pair</th><th className="num">n₁ / n₂</th><th className="num">U</th>
                        <th className="num">raw p</th><th className="num">BH p</th>
                        <th className="num">r</th><th>Magnitude</th><th>After BH</th>
                      </tr>
                    </thead>
                    <tbody>
                      {c.pairwise.map(p => (
                        <tr key={`${p.group_a}|${p.group_b}`}>
                          <td>{p.group_a} vs {p.group_b}</td>
                          <td className="num">{p.n_a} / {p.n_b}</td>
                          <td className="num">{fmtNum(p.u_statistic, 1)}</td>
                          <td className="num">{pText(p.p_value)}</td>
                          <td className="num">{pText(p.p_adjusted)}</td>
                          <td className="num">{fmtNum(p.effect?.r, 3)}</td>
                          <td>{p.effect?.magnitude}</td>
                          <td>{p.significant_adjusted
                            ? <Chip kind="good">✓ significant</Chip>
                            : <Chip kind="muted">not significant</Chip>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '8px 0 0' }}>
                    Corrected within this claim's own set of {c.pairwise.length} pairwise
                    tests, not against the {c.bh?.family_size ?? 50}-test omnibus family.
                  </p>
                </div>
              )}
            </>
          )}

          {c.notes.map((n, i) => (
            <p key={i} style={{ margin: '10px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
              {n}
            </p>
          ))}
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function ClaimDetail() {
  const { claimId = '' } = useParams()
  const navigate = useNavigate()
  const [d, setD] = useState<Detail | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    setD(null); setErr(null)
    window.scrollTo(0, 0)
    api.claim(claimId).then(setD).catch(e => setErr(String(e.message ?? e)))
  }, [claimId])

  if (err) return <ErrorBox error={err} />
  if (!d) return <Loading what={claimId} />

  const s = d.descriptives
  const k = d.classification
  const b = s.bimodality

  return (
    <>
      <div className="filters" style={{ marginBottom: 12 }}>
        <button className="btn" onClick={() => navigate('/')}>← All claims</button>
        <div className="spacer" />
        <nav className="nav">
          {SECTIONS.map(([id, label]) => (
            <button key={id} onClick={() =>
              document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })}>
              {label}
            </button>
          ))}
        </nav>
      </div>

      <Caveat caveats={d.caveats} />

      {/* ---- A ---- */}
      <div className="card" id="identity">
        <header>
          <h1>{d.claim.claim_id}</h1>
          <span className="sub">Q{d.claim.q_number} · {d.claim.claim_type}</span>
          <div className="spacer" />
          {s.bimodal && <Chip kind="warning" title={b.reason}>bimodal</Chip>}{' '}
          {k.bucket === 'clear_direction' && <Chip kind="good">{k.belief_label}</Chip>}{' '}
          {k.bucket === 'mixed' && <Chip kind="muted" title={k.reason ?? ''}>no clear majority</Chip>}{' '}
          {k.bucket === 'idk_dominant' && <Chip kind="warning" title={k.reason ?? ''}>IDK-dominant</Chip>}{' '}
          {k.mismatch && <Chip kind="critical" title={k.mismatch_kind ?? ''}>⚑ mismatch</Chip>}
        </header>
        <p style={{ fontSize: 16, lineHeight: 1.55, margin: '0 0 16px' }}>
          {d.claim.survey_text}
        </p>
        <dl className="kv">
          <dt>Claim ID</dt><dd>{d.claim.claim_id}</dd>
          <dt>Source book</dt>
          <dd>{d.claim.book === 'MISSING'
            ? <Chip kind="warning" title="Not recorded in Final_50_Claims_Public.xlsx">MISSING</Chip>
            : d.claim.book}</dd>
          <dt>Author</dt>
          <dd>{d.claim.author === 'MISSING'
            ? <Chip kind="warning"
                    title="Final_50_Claims_Public.xlsx has no author column; not inferred from the book title">
                MISSING</Chip>
            : d.claim.author}</dd>
          <dt>RQ2 evidence label</dt>
          <dd>{!k.in_matrix
            ? <span className="excluded">not compared — this claim is outside the matrix</span>
            : k.evidence_label === d.pending_label
            ? <Chip kind="muted" title="Not entered yet in data/claims_evidence.csv">
                {d.pending_label}</Chip>
            : <>
                <strong>{k.evidence_label}</strong>
                {k.evidence_strength && (
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                    strength of evidence: <em>{k.evidence_strength}</em>
                    {' '}— recorded alongside the label, not a separate category
                  </div>
                )}
              </>}</dd>
          {d.claim.source_text && d.claim.source_text !== d.claim.survey_text && (
            <>
              <dt>Wording in the book</dt>
              <dd style={{ color: 'var(--text-secondary)' }}>{d.claim.source_text}</dd>
            </>
          )}
        </dl>
      </div>

      {/* ---- B ---- */}
      <h2 id="breakdown" style={{ margin: '22px 0 10px' }}>B · Raw response breakdown</h2>
      <div className="card">
        <header>
          <h3>All {s.n_total} respondents</h3>
          <span className="sub">
            every number further down this page is derived from these counts
          </span>
        </header>
        <DistributionChart data={chartData(s.frequencies, s.n_idk, s.n_total,
                                           s.n_valid, d.likert_labels, d.idk_label)} />
        <div style={{ margin: '10px 0 12px' }}>
          <LikertLegend idkLabel={d.idk_label} />
        </div>
        <OverallBreakdown d={d} s={s} />
      </div>

      {d.comparisons.map(c => <SubgroupBreakdown key={c.variable} d={d} c={c} />)}

      {/* ---- C ---- */}
      <h2 id="working" style={{ margin: '22px 0 4px' }}>C · Calculation walkthrough</h2>
      <p style={{ margin: '0 0 12px', fontSize: 13, color: 'var(--text-secondary)' }}>
        Each statistic below is rebuilt from the rank sums shown in section B, step by
        step. The test suite asserts these steps land on exactly the value{' '}
        <code>scipy.stats</code> returns, so following the arithmetic by hand reproduces
        the published number.
      </p>
      {d.comparisons.map(c => <Walkthrough key={c.variable} c={c} d={d} />)}

      {/* ---- D ---- */}
      <h2 id="bimodality" style={{ margin: '22px 0 10px' }}>D · Bimodality check</h2>
      <div className="card">
        <header>
          <h3>{b.flag ? 'Flagged as bimodal' : 'Not flagged as bimodal'}</h3>
          <span className="sub">
            rule "{b.rule}" · assessed on {b.n_valid} valid answers
            (minimum {b.min_valid_n})
          </span>
          <div className="spacer" />
          {b.flag ? <Chip kind="warning">bimodal</Chip> : <Chip kind="muted">not bimodal</Chip>}
        </header>
        {!b.assessed ? (
          <p style={{ margin: 0, color: 'var(--text-secondary)' }}>{b.reason}</p>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Condition</th><th className="num">Observed</th>
                    <th className="num">Threshold</th><th>Crossed?</th>
                  </tr>
                </thead>
                <tbody>
                  {b.checks.map(c => (
                    <tr key={c.name}>
                      <td>{c.name}</td>
                      <td className="num"><strong>{c.observed.toFixed(2)}
                        {c.name.startsWith('Sarle') ? '' : '%'}</strong></td>
                      <td className="num">{c.comparator} {c.threshold}
                        {c.name.startsWith('Sarle') ? '' : '%'}</td>
                      <td>{c.passed
                        ? <Chip kind="good">✓ met</Chip>
                        : <Chip kind="muted">not met</Chip>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p style={{ margin: '12px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>
              The flag is driven by the tail/middle heuristic
              ({b.heuristic_pass ? 'all three conditions met' : 'not all conditions met'}).
              Sarle's coefficient ({b.coefficient == null ? 'n/a' : b.coefficient.toFixed(3)} vs
              reference {b.coefficient_threshold}) is reported as a cross-check only — it is
              unreliable on a 5-point scale and does not decide the flag.
            </p>
          </>
        )}
      </div>

      {/* ---- E ---- */}
      <h2 id="result" style={{ margin: '22px 0 10px' }}>E · Result for this claim</h2>
      <div className="card">
        <dl className="kv">
          <dt>Bucket</dt>
          <dd>
            <strong>{k.bucket.replace(/_/g, ' ')}</strong>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 3 }}>
              {k.reason}
            </div>
          </dd>
          <dt>Directional split</dt>
          <dd>{k.pct_agree == null
            ? <span className="excluded">not computed — IDK-dominant</span>
            : <>
                {(k.pct_agree * 100).toFixed(1)}% agreed ·{' '}
                {(k.pct_neutral! * 100).toFixed(1)}% neutral ·{' '}
                {(k.pct_disagree! * 100).toFixed(1)}% disagreed
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 3 }}>
                  of {k.directional_n} directional answers (the five substantive points;
                  IDK excluded). Majority threshold {(d.majority_threshold * 100).toFixed(0)}%,
                  strictly greater than.
                </div>
              </>}</dd>
          <dt>IDK rate</dt>
          <dd>
            <strong>{(k.idk_rate * 100).toFixed(1)}%</strong> of the full sample
            ({s.n_idk} of {k.full_sample_n})
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 3 }}>
              Dominance threshold {(d.idk_dominance_threshold * 100).toFixed(0)}%, checked
              against the full sample before any majority is computed.
            </div>
          </dd>
          <dt>Experience comparison</dt>
          <dd>{d.significant_comparisons.length === 0
            ? <span className="excluded">
                no experience difference survived Benjamini–Hochberg correction
              </span>
            : d.significant_comparisons.map(x => (
                <div key={x.variable}>
                  <strong>Under 10 years vs 10+ years</strong> — adjusted p ={' '}
                  {pText(x.p_adjusted)}
                  {x.effect?.r != null && `, r = ${x.effect.r.toFixed(3)} (${x.effect.magnitude})`}
                </div>
              ))}</dd>
          <dt>Bimodality</dt>
          <dd>{b.flag
            ? 'Flagged — the answers split at both ends.'
            : b.assessed ? 'Not flagged.' : b.reason}</dd>
        </dl>
      </div>

      {/* ---- F ---- */}
      <h2 id="evidence" style={{ margin: '22px 0 10px' }}>F · Evidence comparison</h2>
      <div className="card" style={{
        borderLeft: `3px solid ${
          k.verdict_status === 'mismatch' ? 'var(--status-critical)'
          : k.verdict_status === 'match' ? 'var(--status-good)'
          : k.verdict_status === 'not_scored' ? 'var(--baseline)'
          : 'var(--status-warning)'}` }}>
        <header>
          <h3>
            {k.verdict_status === 'pending' ? 'Awaiting the RQ2 evidence label'
              : k.verdict_status === 'mismatch' ? 'Belief–evidence mismatch'
              : k.verdict_status === 'match' ? 'Belief matches the evidence'
              : k.verdict_status === 'not_scored' ? 'Not scored — no evidence located'
              : 'Not classifiable'}
          </h3>
          <div className="spacer" />
          {k.verdict_status === 'mismatch' && <Chip kind="critical">⚑ mismatch</Chip>}
          {k.verdict_status === 'match' && <Chip kind="good">✓ match</Chip>}
          {k.verdict_status === 'not_scored' && <Chip kind="muted">not scored</Chip>}
          {k.verdict_status === 'pending' && <Chip kind="warning">pending</Chip>}
        </header>
        <p style={{ margin: '0 0 12px', fontSize: 15, lineHeight: 1.55 }}>{k.verdict}</p>
        <dl className="kv">
          <dt>Majority direction</dt>
          <dd>{k.belief_label
            ? <>{k.belief_label} — {(k.pct_agree != null && k.majority_direction === 'agreed'
                  ? k.pct_agree * 100 : (k.pct_disagree ?? 0) * 100).toFixed(1)}%
                of {k.directional_n} directional answers</>
            : <span className="excluded">no majority — this claim is outside the matrix</span>}</dd>
          <dt>Strength of evidence</dt>
          <dd>{k.evidence_strength
            ? <>{k.evidence_strength}{' '}
                <span style={{ color: 'var(--text-muted)' }}>
                  — reported with the claim; strength never changes which of the
                  three categories the claim sits in
                </span></>
            : <span className="excluded">not qualified</span>}</dd>
          <dt>Evidence (RQ2 mapping)</dt>
          <dd>{k.evidence_label === d.pending_label
            ? <>
                <Chip kind="muted">{d.pending_label}</Chip>{' '}
                <span style={{ color: 'var(--text-secondary)' }}>
                  — fill <code>data/claims_evidence.csv</code> and re-run
                </span>
              </>
            : k.evidence_label}</dd>
          {d.claim.evidence_notes && (<><dt>RQ2 notes</dt><dd>{d.claim.evidence_notes}</dd></>)}
        </dl>
      </div>

      {/* ---- G ---- */}
      <h2 id="comments" style={{ margin: '22px 0 10px' }}>G · Comments</h2>
      <div className="card">
        <header>
          <h3>{d.comments.n_comments} comment{d.comments.n_comments === 1 ? '' : 's'}</h3>
          <span className="sub">
            sorted by the review-priority signals below · full text, nothing truncated
          </span>
          <div className="spacer" />
          {d.comments.priority_score > 0
            ? <Chip kind="warning">review priority {d.comments.priority_score}</Chip>
            : <Chip kind="muted">no priority signal</Chip>}
        </header>
        {d.comments.priority_reasons.length > 0 && (
          <ul style={{ margin: '0 0 12px', paddingLeft: 18, fontSize: 12,
                       color: 'var(--text-secondary)' }}>
            {d.comments.priority_reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        )}
        {d.comments.comments.length === 0
          ? <p className="excluded" style={{ margin: 0 }}>No comments on this claim.</p>
          : d.comments.comments.map((c, i) => (
              <div className="comment" key={i}>
                <div className="meta">
                  {c.respondent_id} · answered {c.answer === 'IDK'
                    ? d.idk_label
                    : c.answer ? `${c.answer} · ${d.likert_labels[c.answer] ?? ''}` : '—'}
                </div>
                {c.comment}
              </div>
            ))}
      </div>

      <p style={{ margin: '20px 0 40px', fontSize: 12, color: 'var(--text-muted)' }}>
        <Link to="/">← All claims</Link> · every figure on this page comes from the
        section B counts for this one claim; nothing is computed for display only.
      </p>
    </>
  )
}
