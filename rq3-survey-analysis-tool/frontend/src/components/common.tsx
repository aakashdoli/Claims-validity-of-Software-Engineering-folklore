import type { ReactNode } from 'react'
import type { Caveats } from '../types'

/** Likert scale colours, read from the CSS tokens so light/dark swap in one place. */
export const LIKERT_COLORS: Record<string, string> = {
  '1': 'var(--likert-1)',
  '2': 'var(--likert-2)',
  '3': 'var(--likert-3)',
  '4': 'var(--likert-4)',
  '5': 'var(--likert-5)',
}

export const LIKERT_SHORT: Record<string, string> = {
  '1': 'Strongly Disagree',
  '2': 'Disagree',
  '3': 'Neither agree or disagree',
  '4': 'Agree',
  '5': 'Strongly Agree',
}

export function Caveat({ caveats, extra }: { caveats: Caveats; extra?: ReactNode }) {
  return (
    <div className="caveat" role="note">
      <span className="icon" aria-hidden>⚠</span>
      <div>
        <p><strong>Sampling.</strong> {caveats.sampling}</p>
        <p><strong>Fixed question order.</strong> {caveats.question_order}</p>
        {extra}
      </div>
    </div>
  )
}

export function Tile({ label, value, note, flagged }: {
  label: string; value: ReactNode; note?: string; flagged?: boolean
}) {
  return (
    <div className={flagged ? 'tile flagged' : 'tile'}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {note && <div className="note">{note}</div>}
    </div>
  )
}

export function Chip({ kind = 'muted', children, title }: {
  kind?: 'muted' | 'good' | 'warning' | 'critical'; children: ReactNode; title?: string
}) {
  return <span className={`chip ${kind}`} title={title}>{children}</span>
}

export function Loading({ what }: { what: string }) {
  return <div className="loading">Loading {what}…</div>
}

export function ErrorBox({ error }: { error: string }) {
  return (
    <div className="error">
      <p><strong>Backend error:</strong> {error}</p>
      <p style={{ fontSize: 13 }}>
        Start the API with <code>./run.sh</code> (or
        <code> uvicorn rq3.api:app --port 8000</code> from <code>backend/</code>).
      </p>
    </div>
  )
}

export const fmtP = (p: number | null | undefined) =>
  p == null ? '—' : p < 0.001 ? '&lt;0.001' : p.toFixed(4)

export const pText = (p: number | null | undefined) =>
  p == null ? '—' : p < 0.001 ? '<0.001' : p.toFixed(4)

export const fmtNum = (n: number | null | undefined, dp = 2) =>
  n == null ? '—' : Number(n).toFixed(dp)

/**
 * Inline diverging distribution bar: disagree pole | neutral | agree pole.
 * Percentages are of VALID (non-IDK) answers — IDK is off-scale and gets its
 * own column in the table rather than a segment here.
 */
export function DistBar({ row }: {
  row: { freq_1: number; freq_2: number; freq_3: number; freq_4: number; freq_5: number }
}) {
  const freqs = [row.freq_1, row.freq_2, row.freq_3, row.freq_4, row.freq_5]
  const total = freqs.reduce((a, b) => a + b, 0)
  if (!total) return <span className="excluded">no valid answers</span>
  return (
    <div className="dist" role="img"
         aria-label={freqs.map((f, i) =>
           `${LIKERT_SHORT[String(i + 1)]}: ${((f / total) * 100).toFixed(0)}%`).join(', ')}>
      {freqs.map((f, i) => {
        const pct = (f / total) * 100
        if (pct === 0) return null
        return (
          <div key={i} className="seg"
               style={{ width: `${pct}%`, background: LIKERT_COLORS[String(i + 1)] }}
               title={`${LIKERT_SHORT[String(i + 1)]}: ${f} (${pct.toFixed(1)}%)`} />
        )
      })}
    </div>
  )
}

export function LikertLegend({ idkLabel }: { idkLabel: string }) {
  return (
    <div className="legend">
      {['1', '2', '3', '4', '5'].map(k => (
        <span className="item" key={k}>
          <span className="swatch" style={{ background: LIKERT_COLORS[k] }} />
          {k} · {LIKERT_SHORT[k]}
        </span>
      ))}
      <span className="item">
        <span className="swatch hollow" />
        {idkLabel} — off-scale, excluded from medians and tests
      </span>
    </div>
  )
}
