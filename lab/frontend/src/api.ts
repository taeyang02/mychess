export type ImportResponse = {
  game_id: string
  status: string
  warnings: string[]
  metadata: Record<string, unknown>
}

export type AnalysisJob = {
  analysis_id: string
  game_id: string
  status: string
}

const BASE = ''

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json() as Promise<T>
}

export function importPgn(pgn_text: string, platform = 'offline') {
  return json<ImportResponse>('/api/v1/games/import', {
    method: 'POST',
    body: JSON.stringify({ pgn_text, platform }),
  })
}

export function startAnalysis(game_id: string, depth = 10, multipv = 5) {
  return json<AnalysisJob>('/api/v1/analysis', {
    method: 'POST',
    body: JSON.stringify({ game_id, depth, multipv, side: 'both' }),
  })
}

export function getReport(analysis_id: string) {
  return json<Record<string, unknown>>(`/api/v1/analysis/${analysis_id}/report`)
}

export function getMoves(analysis_id: string) {
  return json<Array<Record<string, unknown>>>(`/api/v1/analysis/${analysis_id}/moves`)
}
