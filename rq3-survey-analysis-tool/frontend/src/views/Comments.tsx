import { useEffect, useState } from 'react'
import { api } from '../api'
import { Caveat, Chip, ErrorBox, Loading } from '../components/common'
import type { Caveats, ClaimComments } from '../types'

/**
 * Retrieval, grouping and prioritisation only. The tool deliberately generates
 * no qualitative codes — inductive content analysis stays a human task.
 */
export function Comments({ caveats, onOpenClaim }: {
  caveats: Caveats; onOpenClaim: (id: string) => void
}) {
  const [claims, setClaims] = useState<ClaimComments[] | null>(null)
  const [note, setNote] = useState('')
  const [total, setTotal] = useState(0)
  const [minPriority, setMinPriority] = useState(0)
  const [q, setQ] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [open, setOpen] = useState<Set<string>>(new Set())

  useEffect(() => {
    setClaims(null)
    api.comments(minPriority)
      .then(r => { setClaims(r.claims); setNote(r.note); setTotal(r.total_comments) })
      .catch(e => setErr(String(e.message ?? e)))
  }, [minPriority])

  if (err) return <ErrorBox error={err} />
  if (!claims) return <Loading what="comments" />

  const needle = q.trim().toLowerCase()
  const filtered = needle
    ? claims.map(c => ({
        ...c,
        comments: c.comments.filter(x => x.comment.toLowerCase().includes(needle)),
      })).filter(c => c.comments.length > 0)
    : claims

  const toggle = (id: string) =>
    setOpen(s => {
      const next = new Set(s)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  return (
    <>
      <Caveat caveats={caveats} extra={<p><strong>Scope.</strong> {note}</p>} />

      <div className="filters">
        <div className="field">
          <label htmlFor="mp">Minimum review priority</label>
          <select id="mp" value={minPriority} onChange={e => setMinPriority(Number(e.target.value))}>
            <option value={0}>All claims</option>
            <option value={1}>1+ (any priority signal)</option>
            <option value={3}>3+ (bimodal or mismatch)</option>
            <option value={5}>5+ (multiple signals)</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="cq">Search comment text</label>
          <input id="cq" value={q} onChange={e => setQ(e.target.value)}
                 placeholder="e.g. depends, context, legacy" style={{ minWidth: 300 }} />
        </div>
        <div className="spacer" />
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {total} comments across the survey
        </span>
      </div>

      {filtered.map(c => (
        <div className="card" key={c.claim_id}>
          <header>
            <h2>
              <button className="btn" style={{ marginRight: 8 }}
                      onClick={() => onOpenClaim(c.claim_id)}>{c.claim_id}</button>
            </h2>
            <span className="sub">{c.comments.length} comment{c.comments.length === 1 ? '' : 's'}</span>
            <div className="spacer" />
            {c.priority_score > 0
              ? <Chip kind="warning">review priority {c.priority_score}</Chip>
              : <Chip kind="muted">no priority signal</Chip>}
          </header>
          {c.priority_reasons.length > 0 && (
            <ul style={{ margin: '0 0 10px', paddingLeft: 18, fontSize: 12,
                         color: 'var(--text-secondary)' }}>
              {c.priority_reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          )}
          {c.comments.length > 0 && (
            <>
              <button className="btn" onClick={() => toggle(c.claim_id)}>
                {open.has(c.claim_id) ? 'Hide' : 'Show'} comments
              </button>
              {open.has(c.claim_id) && (
                <div style={{ marginTop: 12 }}>
                  {c.comments.map((x, i) => (
                    <div className="comment" key={i}>
                      <div className="meta">{x.respondent_id} · answered {x.answer || '—'}</div>
                      {x.comment}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      ))}
      {filtered.length === 0 && (
        <div className="card"><p className="excluded" style={{ margin: 0 }}>
          No claims match those filters.</p></div>
      )}
    </>
  )
}
