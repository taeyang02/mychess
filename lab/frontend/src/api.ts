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
  error?: string
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

/** Progressive Stockfish search 0→max_time_s with live dual suggestions. */
export async function suggestBoardStream(
  payload: {
    fen: string
    turn: Turn
    elo: number
    multipv?: number
    max_time_s?: number
  },
  onUpdate: (result: SuggestResult) => void,
  signal?: AbortSignal,
): Promise<SuggestResult | null> {
  const res = await fetch('/api/v1/suggest/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      fen: payload.fen,
      turn: payload.turn,
      elo: payload.elo,
      multipv: payload.multipv ?? 5,
      max_time_s: payload.max_time_s ?? 10,
    }),
    signal,
  })
  if (!res.ok) throw new Error(await readError(res))
  if (!res.body) throw new Error('No stream body')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let last: SuggestResult | null = null

  function processLine(line: string): SuggestResult | undefined {
    if (!line.trim()) return
    const data = JSON.parse(line) as SuggestResult
    if (data.error) throw new Error(data.error)
    onUpdate(data)
    last = data
    return data.done ? data : undefined
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        const final = processLine(line)
        if (final) return final
      }
    }
    const final = processLine(buffer + decoder.decode())
    if (final) return final
    if (last) {
      last = { ...last, done: true }
      onUpdate(last)
      return last
    }
    throw new Error('Kết nối phân tích bị ngắt trước khi có kết quả cuối.')
  } finally {
    void reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
