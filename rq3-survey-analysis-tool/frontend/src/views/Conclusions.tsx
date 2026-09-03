import { useEffect, useState } from 'react'
import {
  Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis,
} from 'recharts'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/common'

/**
 * The findings view — what a reader should leave with.
 *
 * Deliberately quiet: no filters, no tables of 50 rows, no warning banners
 * competing with the numbers. Caveats sit at the end, where they qualify the
 * findings rather than interrupt them.
 *
 * Colour job here is POLARITY, not status: a claim either agrees or disagrees
 * with the evidence. So it uses the same validated diverging poles the rest of
 * the app already uses — blue for agreement/support, red for disagreement —
 * rather than the green/red that reads as one colour under deuteranopia
 * (measured ΔE 4.1, a hard fail). Every mark is also directly labelled, so
 * identity never rests on hue alone.
 */

type C = Record<string, any>

const MATCH = 'var(--concl-match)'
const MISMATCH = 'var(--concl-mismatch)'
const NEUTRAL = 'var(--concl-neutral)'

const pct = (n: number, d: number) => (d ? (n / d) * 100 : 0)

function Section({ n, title, lede, children }: {
  n: string; title: string; lede?: string; children: React.ReactNode
}) {
  return (
    <section className="cc-section">
      <div className="cc-head">
        <span className="cc-num">{n}</span>
        <div>
          <h2>{title}</h2>
          {lede && <p className="cc-lede">{lede}</p>}
        </div>
      </div>
      {children}
    </section>
  )
}

/** Part-to-whole across the 50 claims. Horizontal stacked bar, 2px surface gaps. */
function SplitBar({ h }: { h: C }) {
  const parts = [
    { key: 'match', label: 'Majority matches the evidence', n: h.n_match, fill: MATCH },
    { key: 'mismatch', label: 'Majority–evidence mismatch', n: h.n_mismatch, fill: MISMATCH },
    { key: 'not_scored', label: 'No evidence found — a research gap', n: h.n_not_scored, fill: NEUTRAL },
  ]
  const total = parts.reduce((a, p) => a + p.n, 0)
  return (
    <>
      <div className="cc-split" role="img"
           aria-label={parts.map(p => `${p.label}: ${p.n} of ${total}`).join('. ')}>
        {parts.map(p => (
          <div key={p.key} className="seg" style={{ width: `${pct(p.n, total)}%`, background: p.fill }}>
            <span className="seg-n">{p.n}</span>
          </div>
        ))}
      </div>
      <div className="cc-legend">
        {parts.map(p => (
          <span className="item" key={p.key}>
            <span className="sw" style={{ background: p.fill }} />
            <strong>{p.n}</strong> {p.label}
          </span>
        ))}
      </div>
    </>
  )
}

/** The 2 × 3 grid. Counts are the marks; mismatch cells carry an icon + label. */
function Matrix({ m }: { m: C }) {
  const cols: string[] = m.evidence_labels
  const cell = (b: string, l: string) =>
    m.cells.find((c: C) => c.belief_class === b && c.evidence_label === l)
  const isMismatch = (b: string, l: string) =>
    (b === 'Majority agreed' && l === 'CONTRADICTED') ||
    (b === 'Majority disagreed' && l === 'SUPPORTED')

  return (
    <div className="cc-matrix" style={{
      gridTemplateColumns: `minmax(120px, max-content) repeat(${cols.length}, 1fr)`,
    }}>
      <div />
      {cols.map(c => <div className="cc-mh" key={c}>{c}</div>)}
      {m.belief_classes.map((b: string) => (
        <Row key={b} b={b} cols={cols} cell={cell} isMismatch={isMismatch} />
      ))}
    </div>
  )
}

function Row({ b, cols, cell, isMismatch }: {
  b: string; cols: string[]
  cell: (b: string, l: string) => C | undefined
  isMismatch: (b: string, l: string) => boolean
}) {
  return (
    <>
      <div className="cc-rh">{b}</div>
      {cols.map(l => {
        const c = cell(b, l)
        const n = c?.count ?? 0
        const bad = isMismatch(b, l) && n > 0
        return (
          <div key={l} className={`cc-cell${bad ? ' bad' : ''}${n ? '' : ' zero'}`}>
            <div className="n">{n}</div>
            {bad && <div className="tag">⚑ mismatch</div>}
          </div>
        )
      })}
    </>
  )
}

/** Emphasis bars: the point is one value against a muted comparison. */
function IdkChart({ idk }: { idk: C }) {
  const data = [
    { name: 'Matched claims', v: idk.match, hi: false },
    { name: 'Mismatched claims', v: idk.mismatch, hi: true },
  ]
  return (
    <div style={{ width: '100%', height: 132 }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" barCategoryGap="26%"
                  margin={{ top: 2, right: 66, left: 0, bottom: 2 }}>
          <XAxis type="number" hide domain={[0, Math.max(idk.mismatch, idk.match) * 1.25]} />
          <YAxis type="category" dataKey="name" width={150} tickLine={false} axisLine={false}
                 tick={{ fill: 'var(--text-secondary)', fontSize: 14 }} />
          <Bar dataKey="v" radius={[0, 4, 4, 0]} barSize={34} isAnimationActive={false}>
            <LabelList dataKey="v" position="right" formatter={(v: any) => `${v}%`}
                       style={{ fill: 'var(--text-primary)', fontSize: 17, fontWeight: 600 }} />
            {data.map(d => (
              <Cell key={d.name} fill={d.hi ? MISMATCH : NEUTRAL} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Magnitude, one hue. Direct-labelled; claim text is the y-axis. */
function AgreeBars({ rows }: { rows: C[] }) {
  return (
    <div className="cc-claims">
      {rows.map(r => (
        <div className="cc-claim" key={r.claim_id}>
          <div className="cc-claim-txt">
            <span className="id">{r.claim_id}</span>
            {r.text}
          </div>
          <div className="cc-claim-bar">
            <div className="track">
              <div className="fill" style={{ width: `${r.agree_pct}%` }} />
            </div>
            <span className="val">{Math.round(r.agree_pct)}%</span>
          </div>
        </div>
      ))}
      <p className="cc-note">Share of respondents who agreed or strongly agreed, of those who answered on the scale.</p>
    </div>
  )
}

export function Conclusions() {
  const [d, setD] = useState<C | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.conclusions().then(setD).catch(e => setErr(String(e.message ?? e)))
  }, [])

  if (err) return <ErrorBox error={err} />
  if (!d) return <Loading what="findings" />

  const h = d.headline
  const idk = d.idk_contrast
  const bk = d.buckets
  const sg = d.subgroups

  return (
    <div className="cc">
      <header className="cc-title">
        <p className="cc-kicker">RQ3 · Conclusions</p>
        <h1>Do practitioners believe what the books claim?</h1>
        <p className="cc-sub">
          {h.n_respondents} practitioners · {h.n_claims} claims · {sg.n_tests} statistical tests
        </p>
      </header>

      {/* ---- 1 ---- */}
      <Section n="1" title="Roughly three in ten claims disagree with the evidence">
        <div className="cc-hero">
          <div className="fig">{h.n_mismatch}<span className="of">of {h.n_scored}</span></div>
          <p>
            scored claims are <strong>majority–evidence mismatches</strong> — {h.pct_mismatch}%.
            Of the {h.n_claims} claims, {bk.counts.clear_direction} reached a clear majority
            in one direction; {bk.counts.mixed} split without one and {bk.counts.idk_dominant}
            drew so many “I don’t know” answers that no direction can be read. Only the first
            group is cross-tabulated against the evidence — sections 2 and 3 cover the rest.
          </p>
        </div>
        <SplitBar h={h} />
      </Section>

      {/* ---- 2 ---- */}
      <Section n="2" title="Where the disagreement sits"
               lede={`Majority direction against the RQ2 evidence review — the ${bk.counts.clear_direction} claims with a clear majority.`}>
        <Matrix m={d.matrix} />
        <p className="cc-body">
          A claim enters this grid only when one side passed{' '}
          {(bk.majority_threshold * 100).toFixed(0)}% of the directional answers — the five
          substantive Likert points, with “I don’t know” excluded. Neutral answers count
          toward that denominator but toward neither side, so a claim can genuinely have
          no majority either way.
        </p>
        <div className="cc-two" style={{ marginTop: 22 }}>
          <div className="cc-stat">
            <div className="v">{bk.counts.mixed}<span className="of">no clear majority</span></div>
            <p>Neither side passed the threshold. Reported rather than forced onto one
              side of a cut point.</p>
          </div>
          <div className="cc-list">
            {bk.mixed.map((id: string) => {
              const c = d.matrix.classifications.find((x: C) => x.claim_id === id)
              return (
                <div className="cc-row" key={id}>
                  <span className="cc-pill quiet">
                    {(c.pct_agree * 100).toFixed(0)}% / {(c.pct_disagree * 100).toFixed(0)}%
                  </span>
                  <span className="cc-row-txt"><span className="id">{id}</span>
                    {d.survey_text?.[id] ?? ''}</span>
                </div>
              )
            })}
          </div>
        </div>
      </Section>


      {/* ---- 3 ---- */}
      <Section n="3" title={`${d.research_gap.n} claims the literature has never tested`}
               lede="Asserted as guidance in practitioner books, and unaddressed by empirical research. This is where future work has the clearest opening.">
        <p className="cc-body" style={{ marginTop: 0 }}>
          These are excluded from the match/mismatch count because a majority has nothing
          to agree or disagree with — not because the result is empty. The sharpest
          pointers are the claims practitioners are <strong>confident</strong> about:
          high agreement <em>and</em> a low “I don’t know” rate, so the gap cannot be
          explained away by respondents simply not knowing.
        </p>
        <div className="cc-gap">
          {d.research_gap.believed.map((r: C) => {
            const confident = r.idk_pct <= d.research_gap.confident_idk_ceiling
            return (
              <div className={`cc-gap-row${confident ? ' confident' : ''}`} key={r.claim_id}>
                <div className="cc-gap-nums">
                  <span className="agree">{Math.round(r.agree_pct)}%</span>
                  <span className="lbl">agree</span>
                  <span className="idk">{Math.round(r.idk_pct)}% IDK</span>
                </div>
                <div className="cc-gap-txt">
                  <span className="id">{r.claim_id}</span>{r.text}
                  {confident && <span className="cc-flag">high confidence, untested</span>}
                </div>
              </div>
            )
          })}
        </div>
        <p className="cc-body">
          <strong>{d.research_gap.believed.filter((r: C) => r.idk_pct <= d.research_gap.confident_idk_ceiling).length} of
          the {d.research_gap.believed.length}</strong> are held confidently and remain
          unexamined — the shortest route from this thesis to a follow-up study.
          {d.research_gap.not_believed.length > 0 && ` The remaining ${d.research_gap.not_believed.length} sit on the not-believed side, where the book's guidance and the profession already disagree and no evidence settles it.`}
        </p>
      </Section>

      {/* ---- 4 ---- */}
      <Section n="4" title="Three claims are believed despite contradicting evidence"
               lede="The clearest folklore in the set — widely held, and the literature says otherwise.">
        <AgreeBars rows={d.believed_contradicted} />
      </Section>

      {/* ---- 4 ---- */}
      <Section n="5" title="Practitioners are not disagreeing — they cannot evaluate"
               lede={`Mismatched claims drew ${(idk.mismatch / idk.match).toFixed(1)}× the "I don't know" rate of matched ones.`}>
        <IdkChart idk={idk} />
        <p className="cc-body">
          The gap is not belief against evidence so much as reach: the quantitative
          measurement claims in these books describe a practice most respondents have
          no contact with. {idk.n_above_threshold} of {h.n_claims} claims drew an
          IDK rate of {idk.threshold_pct}% or more.
        </p>
        <div className="cc-list">
          {idk.highest.slice(0, 4).map((r: C) => (
            <div className="cc-row" key={r.claim_id}>
              <span className="cc-pill">{Math.round(r.idk_pct)}% IDK</span>
              <span className="cc-row-txt"><span className="id">{r.claim_id}</span>{r.text}</span>
            </div>
          ))}
        </div>
      </Section>

      {/* ---- 5 ---- */}
      <Section n="6" title="Belief is uniform across the profession"
               lede="Experience, role, team size, industry, company size and country.">
        <div className="cc-two">
          <div className="cc-stat">
            <div className="v">{sg.n_significant}<span className="of">of {sg.n_tests}</span></div>
            <p>subgroup comparisons survived Benjamini–Hochberg correction. Every
              surviving effect is <strong>small</strong> (ε² 0.024–0.058).</p>
          </div>
          <div className="cc-list">
            {sg.results.map((r: C) => (
              <div className="cc-row" key={`${r.claim_id}-${r.variable}`}>
                <span className="cc-pill quiet">{r.variable.replace(/_/g, ' ')}</span>
                <span className="cc-row-txt"><span className="id">{r.claim_id}</span>{r.text}</span>
              </div>
            ))}
          </div>
        </div>
        <p className="cc-body">
          Who you are barely predicts what you believe about these claims — itself a
          finding, and one that holds across {sg.n_tests} tests.
        </p>
      </Section>

      {/* ---- 6 ---- */}
      <Section n="7" title="Read these numbers with two things in mind">
        <div className="cc-caveats">
          <div>
            <h3>A majority is not a consensus</h3>
            <p>
              The rule asks only whether one side passed{' '}
              {(bk.majority_threshold * 100).toFixed(0)}% of the directional answers. A claim
              at 51% agreement and one at 94% both read as “majority agreed”, so the direction
              is the finding, not its strength — the per-claim percentages carry that. Neutral
              answers count toward the denominator but toward neither side, which is why{' '}
              {bk.counts.mixed} claims land in no-majority rather than being pushed one way.
            </p>
          </div>
          <div>
            <h3>{bk.counts.idk_dominant} claims could not be classified at all</h3>
            <p>
              At or above {(bk.idk_dominance_threshold * 100).toFixed(0)}% of the{' '}
              <em>full sample</em> answering “I don’t know”, no direction is computed: the
              split among those who remain describes a self-selected minority. That check runs
              before the majority rule and cannot be overridden by a lopsided result among
              the answerers.
            </p>
          </div>
        </div>
        {d.evidence_strength.n_qualified < d.evidence_strength.n_claims && (
          <div style={{ marginTop: 26 }}>
            <h3 style={{ fontSize: 15, margin: '0 0 8px' }}>Strength of evidence is recorded, not yet filled in</h3>
            <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
              A claim supported by one small-sample study is a weaker warrant than one
              supported by a systematic review, and the tool carries an{' '}
              <code>evidence_strength</code> field for exactly that — it travels with the
              claim without splitting the matrix into more categories. It is currently
              filled for {d.evidence_strength.n_qualified} of {d.evidence_strength.n_claims} claims,
              so the {d.matrix.cells.filter((c: C) => c.evidence_label === 'SUPPORTED')
                .reduce((a: number, c: C) => a + c.count, 0)} SUPPORTED claims are presently
              read as equally well warranted. Adding the qualifier per claim would let the
              write-up separate strongly-evidenced agreement from thinly-evidenced agreement.
            </p>
          </div>
        )}
        <p className="cc-fine">{d.caveats.sampling}</p>
        <p className="cc-fine">{d.caveats.question_order}</p>
      </Section>
    </div>
  )
}
