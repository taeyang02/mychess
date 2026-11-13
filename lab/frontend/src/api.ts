export type Turn = 'white' | 'black'

export type DetectionResult = {
  fen: string
  piece_placement: string
  turn_guess: Turn
  turn_source?: 'model' | 'last_move_highlight'
  confidence: number
  orientation: Turn
  is_valid: boolean
  validation_errors: string[]
  filename: string
  used_crop?: boolean
  crop_box?: number[] | null
  board_preview?: string
}

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

export type SuggestResult = {
  fen: string
  turn: Turn
  elo_band: number
  depth: number
  elapsed_ms: number
  max_ms: number
  done: boolean
  stockfish_best: MoveLine
  stockfish_lines: MoveLine[]
  human_typical: MoveLine
  human_lines: MoveLine[]
  disclaimer: string
}

async function readError(res: Response): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') return data.detail
    if (Array.isArray(data?.detail)) {
      return data.detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join('; ')
    }
    return JSON.stringify(data)
  } catch {
    return res.statusText || 'Request failed'
  }
}

export async function detectBoard(file: File, signal?: AbortSignal): Promise<DetectionResult> {
  const form = new FormData()
  form.append('image', file)
  const res = await fetch('/api/detect', { method: 'POST', body: form, signal })
  if (!res.ok) {
    throw new Error(
      (await readError(res)) +
        ' (Detect dùng advisor ver1 :8000 — hãy chạy ver1 backend nếu cần nhận diện ảnh.)',
    )
  }
  return res.json()
}

/** Suggest like ver1 analyze: abortable, reports progress while waiting. */
export async function suggestBoard(
  payload: {
    fen: string
    turn: Turn
    elo: number
    depth?: number
    multipv?: number
  },
  onProgress: (elapsedMs: number, maxMs: number) => void,
  signal?: AbortSignal,
): Promise<SuggestResult> {
  const maxMs = 10_000
  const started = performance.now()
  const tick = window.setInterval(() => {
    const elapsed = performance.now() - started
    onProgress(Math.min(elapsed, maxMs * 0.95), maxMs)
  }, 120)

  try {
    const res = await fetch('/api/v1/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fen: payload.fen,
        turn: payload.turn,
        elo: payload.elo,
        depth: payload.depth ?? 14,
        multipv: payload.multipv ?? 5,
      }),
      signal,
    })
    if (!res.ok) throw new Error(await readError(res))
    const data = await res.json()
    const elapsed = Math.round(performance.now() - started)
    onProgress(elapsed, maxMs)
    return {
      fen: data.fen,
      turn: data.turn,
      elo_band: data.elo_band,
      depth: data.engine?.depth ?? payload.depth ?? 14,
      elapsed_ms: elapsed,
      max_ms: maxMs,
      done: true,
      stockfish_best: data.stockfish_best,
      stockfish_lines: data.stockfish_lines,
      human_typical: data.human_typical,
      human_lines: data.human_lines,
      disclaimer: data.disclaimer,
    }
  } finally {
    window.clearInterval(tick)
  }
}
