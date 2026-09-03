import { useCallback, useEffect, useState } from 'react'
import {
  BrowserRouter, NavLink, Navigate, Route, Routes, useNavigate,
} from 'react-router-dom'
import './theme.css'
import { api } from './api'
import { ErrorBox, Loading } from './components/common'
import { ClaimDetail } from './views/ClaimDetail'
import { Comments } from './views/Comments'
import { Conclusions } from './views/Conclusions'
import { MatrixView } from './views/MatrixView'
import { Methodology } from './views/Methodology'
import { Overview } from './views/Overview'
import { Quality } from './views/Quality'
import type { Overview as OverviewData } from './types'

const TABS: [string, string][] = [
  ['/', 'Claims'],
  ['/conclusions', 'Conclusions'],
  ['/matrix', 'Belief–evidence matrix'],
  ['/comments', 'Comments'],
  ['/quality', 'Data quality'],
  ['/methodology', 'Methodology'],
]

function Shell() {
  const [data, setData] = useState<OverviewData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [theme, setTheme] = useState<'system' | 'light' | 'dark'>('system')
  const navigate = useNavigate()

  const load = useCallback(() => {
    setErr(null)
    api.overview().then(setData).catch(e => setErr(String(e.message ?? e)))
  }, [])

  useEffect(load, [load])

  useEffect(() => {
    if (theme === 'system') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  // Claim navigation is a real URL, so a claim page can be linked, bookmarked
  // and cited directly in the thesis write-up.
  const openClaim = (id: string) => navigate(`/claims/${encodeURIComponent(id)}`)

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          RQ3 Survey Analysis
          <small>Claims validity of software engineering folklore · BTH PA2534</small>
        </div>
        <nav className="nav">
          {TABS.map(([path, label]) => (
            <NavLink key={path} to={path} end={path === '/'}
                     className={({ isActive }) => (isActive ? 'active' : undefined)}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="spacer" />
        {data && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'right' }}>
            {data.manifest.n_respondents} respondents · run {data.manifest.run_id}
            <br />
            {data.manifest.input_file.split('/').pop()}
          </span>
        )}
        <select value={theme} onChange={e => setTheme(e.target.value as any)}
                aria-label="Colour theme"
                style={{ font: 'inherit', fontSize: 12, padding: '4px 6px',
                         background: 'var(--surface-1)', color: 'var(--text-primary)',
                         border: '1px solid var(--border-strong)', borderRadius: 6 }}>
          <option value="system">System theme</option>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
        </select>
      </header>

      <main>
        {err && <ErrorBox error={err} />}
        {!err && !data && <Loading what="analysis run" />}
        {data && (
          <Routes>
            <Route path="/" element={<Overview data={data} onOpenClaim={openClaim} />} />
            <Route path="/claims/:claimId" element={<ClaimDetail />} />
            <Route path="/conclusions" element={<Conclusions />} />
            <Route path="/matrix"
                   element={<MatrixView caveats={data.caveats} onOpenClaim={openClaim} />} />
            <Route path="/comments"
                   element={<Comments caveats={data.caveats} onOpenClaim={openClaim} />} />
            <Route path="/quality"
                   element={<Quality caveats={data.caveats} onRerun={load} />} />
            <Route path="/methodology" element={<Methodology />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  )
}
