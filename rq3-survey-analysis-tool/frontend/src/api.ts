import type {
  ClaimDetail, DatasetList, Matrix, Methodology, Overview, QualityPayload,
} from './types'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* keep statusText */ }
    throw new Error(`${res.status} ${detail}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  overview: () => get<Overview>('/api/overview'),
  claim: (id: string) => get<ClaimDetail>(`/api/claims/${encodeURIComponent(id)}`),
  conclusions: () => get<Record<string, any>>('/api/conclusions'),
  matrix: () => get<Matrix>('/api/matrix').then(r => (r as any).matrix as Matrix),
  quality: () => get<QualityPayload>('/api/quality'),
  methodology: () => get<Methodology>('/api/methodology'),
  datasets: () => get<DatasetList>('/api/datasets'),
  comments: (minPriority = 0) =>
    get<{ claims: any[]; total_comments: number; note: string }>(
      `/api/comments?min_priority=${minPriority}`),
  rerun: async (inputFile?: string) => {
    const q = inputFile ? `?input_file=${encodeURIComponent(inputFile)}` : ''
    const res = await fetch(`/api/run${q}`, { method: 'POST' })
    if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText)
    return res.json()
  },
  writeExports: async () => {
    const res = await fetch('/api/export/write', { method: 'POST' })
    if (!res.ok) throw new Error(res.statusText)
    return res.json() as Promise<{ paths: Record<string, string>; run_id: string }>
  },
  exportUrl: (kind: string) => `/api/export/${kind}`,
}
