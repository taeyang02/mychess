export type MoveLine = {
  rank: number
  san: string
  uci: string
  score_cp: number | null
  mate: number | null
  eval_text: string | null
  probability: number | null
  pv_san: string[]
}

export type SuggestResponse = {
  fen: string
  turn: 'white' | 'black'
  elo_band: number
  engine: Record<string, unknown>
  human: Record<string, unknown>
  stockfish_best: MoveLine
  stockfish_lines: MoveLine[]
  human_typical: MoveLine
  human_lines: MoveLine[]
  disclaimer: string
}

export function suggest(payload: {
  fen: string
  turn?: 'white' | 'black'
  elo: number
  depth?: number
  multipv?: number
}) {
  return fetch('/api/v1/suggest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(async (res) => {
    if (!res.ok) throw new Error(await res.text())
    return res.json() as Promise<SuggestResponse>
  })
}
