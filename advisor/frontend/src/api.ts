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

export type Evaluation = {
  type: 'cp' | 'mate'
  value: number | null
  text: string
}

export type AnalyzeResult = {
  board_fen: string
  turn: Turn
  mode?: 'time' | 'depth' | 'progressive'
  depth: number
  movetime_ms?: number | null
  elapsed_ms?: number
  max_ms?: number
  done?: boolean
  best_move_uci: string
  best_move_san: string
  from_square: string
  to_square: string
  evaluation: Evaluation
  pv_uci: string[]
  pv_san: string[]
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
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function analyzeBoardStream(
  payload: {
    fen: string
    turn: Turn
    max_time_s?: number
    history?: { initial_fen: string; moves: string[] }
  },
  onUpdate: (result: AnalyzeResult) => void,
  signal?: AbortSignal,
): Promise<AnalyzeResult | null> {
  const res = await fetch('/api/analyze/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      fen: payload.fen,
      turn: payload.turn,
      max_time_s: payload.max_time_s ?? 10,
      history: payload.history,
    }),
    signal,
  })
  if (!res.ok) throw new Error(await readError(res))
  if (!res.body) throw new Error('No stream body')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  function processLine(line: string): AnalyzeResult | undefined {
    if (!line.trim()) return
    const data = JSON.parse(line) as AnalyzeResult
    if (data.error) throw new Error(data.error)
    onUpdate(data)
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
    throw new Error('Kết nối phân tích bị ngắt trước khi có kết quả cuối.')
  } finally {
    void reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
