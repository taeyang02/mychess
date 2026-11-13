import { useEffect, useEffectEvent, useMemo, useRef, useState } from 'react'
import { Chessboard } from 'react-chessboard'
import type { SquareHandlerArgs } from 'react-chessboard'
import {
  detectBoard,
  suggestBoardStream,
  type SuggestResult,
  type Turn,
} from './api'
import {
  getLegalTargets,
  normalizeFen,
  playLegalMove,
  startingFen,
  type LegalTarget,
} from './fen'
import { boardPieces } from './boardPieces'
import './App.css'

type Status =
  | { kind: 'idle'; message?: string }
  | { kind: 'loading'; message: string }
  | { kind: 'error'; message: string }
  | { kind: 'ok'; message: string }

type Orientation = 'white' | 'black'

type BoardSnapshot = {
  fen: string
  turn: Turn
  lastPlayed: string | null
}

type SuggestFocus = 'engine' | 'human'

const MAX_THINK_S = 10

function turnLabel(turn: Turn): string {
  return turn === 'white' ? 'Trắng' : 'Đen'
}

function buildOptionStyles(
  selected: string | null,
  targets: LegalTarget[],
): Record<string, React.CSSProperties> {
  const styles: Record<string, React.CSSProperties> = {}
  if (selected) {
    styles[selected] = { background: 'rgba(61, 220, 132, 0.45)' }
  }
  for (const t of targets) {
    styles[t.to] = t.capture
      ? {
          background:
            'radial-gradient(circle, transparent 58%, rgba(61, 220, 132, 0.85) 60%, rgba(61, 220, 132, 0.85) 78%, transparent 80%)',
        }
      : {
          background:
            'radial-gradient(circle, rgba(61, 220, 132, 0.85) 22%, transparent 24%)',
        }
  }
  return styles
}

function uciSquares(uci: string | undefined) {
  if (!uci || uci.length < 4) return null
  return { from: uci.slice(0, 2), to: uci.slice(2, 4) }
}

export default function App() {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [fen, setFen] = useState(startingFen())
  const [turn, setTurn] = useState<Turn>('white')
  const [orientation, setOrientation] = useState<Orientation>('white')
  const [suggestion, setSuggestion] = useState<SuggestResult | null>(null)
  const [focus, setFocus] = useState<SuggestFocus>('engine')
  const [elo, setElo] = useState(1500)
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [dragOver, setDragOver] = useState(false)
  const [lastPlayed, setLastPlayed] = useState<string | null>(null)
  const [selectedSquare, setSelectedSquare] = useState<string | null>(null)
  const [moveTargets, setMoveTargets] = useState<LegalTarget[]>([])
  const [thinkProgress, setThinkProgress] = useState(0)
  const [thinking, setThinking] = useState(false)
  const [history, setHistory] = useState<BoardSnapshot[]>([])

  const boardFen = useMemo(() => normalizeFen(fen, turn), [fen, turn])
  const analyzeSeq = useRef(0)
  const abortRef = useRef<AbortController | null>(null)
  const detectAbortRef = useRef<AbortController | null>(null)
  const canUndo = history.length > 0

  const squareStyles = useMemo(() => {
    const styles = buildOptionStyles(selectedSquare, moveTargets)
    if (!suggestion) return styles
    const sf = uciSquares(suggestion.stockfish_best.uci)
    const hu = uciSquares(suggestion.human_typical.uci)
    const same = suggestion.human_typical.uci === suggestion.stockfish_best.uci
    if (sf) {
      styles[sf.from] = {
        ...(styles[sf.from] || {}),
        boxShadow: 'inset 0 0 0 3px rgba(61, 220, 132, 0.7)',
      }
      styles[sf.to] = {
        ...(styles[sf.to] || {}),
        boxShadow: 'inset 0 0 0 3px rgba(61, 220, 132, 0.7)',
      }
    }
    if (hu && !same) {
      styles[hu.from] = {
        ...(styles[hu.from] || {}),
        boxShadow: 'inset 0 0 0 3px rgba(232, 197, 107, 0.75)',
      }
      styles[hu.to] = {
        ...(styles[hu.to] || {}),
        boxShadow: 'inset 0 0 0 3px rgba(232, 197, 107, 0.75)',
      }
    }
    return styles
  }, [selectedSquare, moveTargets, suggestion])

  // Always draw both proposals when they differ: green = SF, yellow = human.
  const arrows = useMemo(() => {
    if (!suggestion) return []
    const sf = uciSquares(suggestion.stockfish_best.uci)
    const hu = uciSquares(suggestion.human_typical.uci)
    const same = suggestion.human_typical.uci === suggestion.stockfish_best.uci
    const list: { startSquare: string; endSquare: string; color: string }[] = []
    if (sf) {
      list.push({
        startSquare: sf.from,
        endSquare: sf.to,
        color: 'rgba(61, 220, 132, 0.95)',
      })
    }
    if (hu && !same) {
      list.push({
        startSquare: hu.from,
        endSquare: hu.to,
        color: 'rgba(232, 197, 107, 0.95)',
      })
    }
    return list
  }, [suggestion])

  function clearSelection() {
    setSelectedSquare(null)
    setMoveTargets([])
  }

  function selectSquare(square: string) {
    const targets = getLegalTargets(fen, turn, square)
    if (!targets.length) {
      clearSelection()
      return false
    }
    setSelectedSquare(square)
    setMoveTargets(targets)
    return true
  }

  function stopAnalyze() {
    abortRef.current?.abort()
    abortRef.current = null
  }

  function stopDetect() {
    detectAbortRef.current?.abort()
    detectAbortRef.current = null
  }

  async function runSuggest(overrides?: {
    fen?: string
    turn?: Turn
    note?: string
    elo?: number
  }) {
    stopDetect()
    const nextTurn = overrides?.turn ?? turn
    const nextFen = normalizeFen(overrides?.fen ?? fen, nextTurn)
    const nextElo = overrides?.elo ?? elo
    const seq = ++analyzeSeq.current

    stopAnalyze()
    const controller = new AbortController()
    abortRef.current = controller

    setThinking(true)
    setThinkProgress(0)
    setStatus({
      kind: 'loading',
      message: 'Stockfish đang suy nghĩ 0→10s (nông→sâu)…',
    })

    try {
      const final = await suggestBoardStream(
        {
          fen: nextFen,
          turn: nextTurn,
          elo: nextElo,
          multipv: 5,
          max_time_s: MAX_THINK_S,
        },
        (update) => {
          if (seq !== analyzeSeq.current) return
          setSuggestion(update)
          const elapsed = update.elapsed_ms ?? 0
          const maxMs = update.max_ms ?? MAX_THINK_S * 1000
          setThinkProgress(Math.min(100, (elapsed / maxMs) * 100))
          if (update.done) return
          setStatus({
            kind: 'loading',
            message: `Đang suy nghĩ ${(elapsed / 1000).toFixed(1)}s / ${MAX_THINK_S}s — SF ${update.stockfish_best.san} (depth ${update.depth})`,
          })
        },
        controller.signal,
      )

      if (seq !== analyzeSeq.current) return null
      setThinking(false)
      setThinkProgress(100)
      if (!final) {
        setStatus({ kind: 'error', message: 'Không nhận được gợi ý từ Stockfish.' })
        return null
      }
      setSuggestion(final)
      setStatus({
        kind: 'ok',
        message:
          overrides?.note ??
          `Đến lượt ${turnLabel(final.turn)} — SF ${final.stockfish_best.san} · Human ${final.human_typical.san} · ${(final.elapsed_ms / 1000).toFixed(1)}s depth ${final.depth}`,
      })
      return final
    } catch (err) {
      if (seq !== analyzeSeq.current) return null
      if (err instanceof DOMException && err.name === 'AbortError') return null
      setThinking(false)
      setStatus({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Gợi ý thất bại.',
      })
      return null
    }
  }

  function applyPlayedMove(source: string, target: string): boolean {
    const played = playLegalMove(fen, turn, source, target)
    if (!played) return false

    setHistory((prev) => [...prev, { fen, turn, lastPlayed }])
    analyzeSeq.current += 1
    stopAnalyze()
    setFen(played.fen)
    setTurn(played.turn)
    setLastPlayed(played.san)
    setSuggestion(null)
    setThinkProgress(0)
    clearSelection()
    void runSuggest({
      fen: played.fen,
      turn: played.turn,
      note: `Bạn đi ${played.san} → đến lượt ${turnLabel(played.turn)}.`,
    })
    return true
  }

  function undoMove() {
    if (history.length === 0) return
    const prev = history[history.length - 1]
    setHistory((h) => h.slice(0, -1))
    analyzeSeq.current += 1
    stopAnalyze()
    setFen(prev.fen)
    setTurn(prev.turn)
    setLastPlayed(prev.lastPlayed)
    setSuggestion(null)
    setThinkProgress(0)
    clearSelection()
    void runSuggest({
      fen: prev.fen,
      turn: prev.turn,
      note: prev.lastPlayed
        ? `Đã hoàn tác — quay lại sau nước ${prev.lastPlayed}.`
        : 'Đã hoàn tác nước vừa đi.',
    })
  }

  function resetBoard() {
    const start = startingFen()
    stopAnalyze()
    analyzeSeq.current += 1
    setFen(start)
    setTurn('white')
    setOrientation('white')
    setSuggestion(null)
    setLastPlayed(null)
    setHistory([])
    setThinkProgress(0)
    clearSelection()
    void runSuggest({
      fen: start,
      turn: 'white',
      note: 'Reset — đến lượt Trắng, đang gợi ý…',
    })
  }

  async function handleFile(file: File | null | undefined) {
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setStatus({ kind: 'error', message: 'Chỉ nhận file ảnh (PNG, JPG, WEBP, GIF…).' })
      return
    }

    stopDetect()
    const controller = new AbortController()
    detectAbortRef.current = controller
    setPreviewUrl(URL.createObjectURL(file))
    setSuggestion(null)
    setLastPlayed(null)
    setHistory([])
    clearSelection()
    analyzeSeq.current += 1
    stopAnalyze()
    setThinking(false)
    setThinkProgress(0)
    setStatus({ kind: 'loading', message: 'Đang nhận diện bàn cờ & bên đi…' })

    try {
      const result = await detectBoard(file, controller.signal)
      if (controller.signal.aborted) return
      setFen(result.fen)
      setTurn(result.turn_guess)
      setOrientation(result.orientation === 'black' ? 'black' : 'white')
      setHistory([])
      if (result.board_preview) setPreviewUrl(result.board_preview)

      if (!result.is_valid) {
        setStatus({
          kind: 'error',
          message: 'Nhận diện lệch — upload lại ảnh rõ hơn hoặc chọn quân rồi đi nước hợp lệ.',
        })
        return
      }

      await runSuggest({
        fen: result.fen,
        turn: result.turn_guess,
        note: `Đến lượt ${turnLabel(result.turn_guess)} — gợi ý sau khi suy nghĩ xong.`,
      })
    } catch (err) {
      if (controller.signal.aborted) return
      setStatus({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Không nhận diện được bàn cờ.',
      })
    } finally {
      if (detectAbortRef.current === controller) detectAbortRef.current = null
    }
  }

  function onSquareClick({ square }: SquareHandlerArgs) {
    if (selectedSquare) {
      if (square === selectedSquare) {
        clearSelection()
        return
      }
      const isTarget = moveTargets.some((t) => t.to === square)
      if (isTarget) {
        const ok = applyPlayedMove(selectedSquare, square)
        if (!ok) {
          setStatus({
            kind: 'error',
            message: `Nước không hợp lệ. Đang đến lượt ${turnLabel(turn)}.`,
          })
          clearSelection()
        }
        return
      }
      if (selectSquare(square)) return
      clearSelection()
      return
    }
    selectSquare(square)
  }

  function flipBoard() {
    setOrientation((prev) => (prev === 'white' ? 'black' : 'white'))
  }

  function changeTurn(next: Turn) {
    if (next === turn) return
    setTurn(next)
    setSuggestion(null)
    clearSelection()
    void runSuggest({ fen, turn: next })
  }

  const handlePastedFile = useEffectEvent(handleFile)

  useEffect(() => {
    return () => {
      if (previewUrl?.startsWith('blob:')) URL.revokeObjectURL(previewUrl)
    }
  }, [previewUrl])

  useEffect(() => {
    function onPaste(event: ClipboardEvent) {
      const items = event.clipboardData?.items
      if (!items?.length) return
      for (const item of items) {
        if (!item.type.startsWith('image/')) continue
        const file = item.getAsFile()
        if (!file) continue
        event.preventDefault()
        const named =
          file.name && file.name !== 'image.png'
            ? file
            : new File([file], `clipboard-${Date.now()}.png`, {
                type: file.type || 'image/png',
              })
        void handlePastedFile(named)
        return
      }
    }
    window.addEventListener('paste', onPaste)
    return () => {
      window.removeEventListener('paste', onPaste)
      stopAnalyze()
      stopDetect()
    }
  }, [])

  // Initial suggest like ver1 reset flow
  useEffect(() => {
    void runSuggest({ fen: startingFen(), turn: 'white', note: 'Start — gợi ý cho Trắng.' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const elapsedLabel =
    suggestion?.elapsed_ms != null
      ? `${(suggestion.elapsed_ms / 1000).toFixed(1)}s`
      : thinking
        ? '…'
        : '0s'

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1 className="brand-mark">
            Move <span>Advisor</span> v2
          </h1>
          <p className="brand-sub">
            ⌘V ảnh → bấm quân → bấm ô — Stockfish (xanh) + human-typical/Maia-style (vàng) tự gợi ý.
          </p>
        </div>
        <div className="badge">SF + Human</div>
      </header>

      <main className="workspace">
        <section className="panel">
          <h2>Ảnh bàn cờ</h2>
          <div
            className={`upload-zone ${dragOver ? 'dragover' : ''}`}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              void handleFile(e.dataTransfer.files?.[0])
            }}
          >
            <input
              type="file"
              accept="image/*"
              onChange={(e) => void handleFile(e.target.files?.[0])}
            />
            <div className="upload-copy">
              <strong>Kéo thả, chọn ảnh, hoặc ⌘V</strong>
              <p>Screenshot Chess.com / Lichess</p>
            </div>
          </div>

          {previewUrl ? (
            <div className="preview">
              <img src={previewUrl} alt="Ảnh bàn cờ đã upload" />
            </div>
          ) : null}

          <div className="row" style={{ marginTop: 12, gap: 10, alignItems: 'center' }}>
            <label className="meta">
              Elo human-typical
              <input
                type="number"
                min={600}
                max={2800}
                step={50}
                value={elo}
                onChange={(e) => setElo(Number(e.target.value) || 1500)}
                style={{
                  marginLeft: 8,
                  width: 72,
                  background: 'var(--bg-elevated)',
                  color: 'var(--ink)',
                  border: '1px solid var(--line)',
                  borderRadius: 8,
                  padding: '4px 8px',
                }}
              />
            </label>
            <button
              type="button"
              className="btn"
              disabled={thinking}
              onClick={() => void runSuggest({ note: `Gợi ý lại với Elo ${elo}.` })}
            >
              Gợi ý lại
            </button>
          </div>

          {status.message ? (
            <div
              className={`status ${
                status.kind === 'error'
                  ? 'error'
                  : status.kind === 'loading'
                    ? 'loading'
                    : status.kind === 'ok'
                      ? 'ok'
                      : ''
              }`}
              role="status"
            >
              {status.message}
            </div>
          ) : (
            <p className="empty-hint" style={{ marginTop: 12 }}>
              Dán ảnh để bắt đầu, hoặc đi quân trên bàn (startpos).
            </p>
          )}
        </section>

        <section className="panel">
          <h2>Bàn cờ</h2>
          <div className="board-wrap">
            <Chessboard
              options={{
                id: 'advisor-v2-board',
                position: boardFen,
                pieces: boardPieces,
                boardOrientation: orientation,
                allowDragging: false,
                allowDrawingArrows: false,
                arrows,
                squareStyles,
                clearArrowsOnPositionChange: true,
                animationDurationInMs: 220,
                boardStyle: {
                  borderRadius: '10px',
                  boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
                },
                lightSquareStyle: { backgroundColor: '#d6c3a3' },
                darkSquareStyle: { backgroundColor: '#7a5540' },
                onSquareClick,
              }}
            />
          </div>

          <div className="controls">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <div className="turn-toggle" role="group" aria-label="Đến lượt">
                <button
                  type="button"
                  className={turn === 'white' ? 'active' : ''}
                  onClick={() => changeTurn('white')}
                >
                  Trắng đi
                </button>
                <button
                  type="button"
                  className={turn === 'black' ? 'active' : ''}
                  onClick={() => changeTurn('black')}
                >
                  Đen đi
                </button>
              </div>
              <div className="row">
                <button type="button" className="btn" onClick={undoMove} disabled={!canUndo}>
                  Undo
                </button>
                <button type="button" className="btn" onClick={flipBoard}>
                  Xoay bàn
                </button>
                <button type="button" className="btn" onClick={resetBoard}>
                  Reset bàn
                </button>
              </div>
            </div>

            <p className="meta">
              Bấm nhầm? <strong>Undo</strong>. Đi quân lúc nào cũng được — engine tính lại.
              {' '}Mũi tên <strong style={{ color: '#3ddc84' }}>xanh = Stockfish</strong>,{' '}
              <strong style={{ color: '#e8c56b' }}>vàng = Human</strong> (khi khác nhau vẽ cả hai).
              {lastPlayed ? (
                <>
                  {' '}
                  Vừa đi: <strong>{lastPlayed}</strong>
                </>
              ) : null}
            </p>

            {suggestion ? (
              <div className="dual-suggest">
                <button
                  type="button"
                  className={`suggestion ${focus === 'engine' ? 'focused' : ''}`}
                  onClick={() => setFocus('engine')}
                >
                  <div className="meta">Stockfish · {turnLabel(suggestion.turn)}</div>
                  <div className="suggestion-move">{suggestion.stockfish_best.san}</div>
                  <div className="eval-chip">
                    {suggestion.stockfish_best.eval_text}
                    <span className="meta"> · depth {suggestion.depth}</span>
                  </div>
                  <p className="pv">{suggestion.stockfish_best.pv_san.join(' ')}</p>
                </button>
                <button
                  type="button"
                  className={`suggestion human ${focus === 'human' ? 'focused' : ''}`}
                  onClick={() => setFocus('human')}
                >
                  <div className="meta">Human-typical ~{suggestion.elo_band}</div>
                  <div className="suggestion-move">{suggestion.human_typical.san}</div>
                  <div className="eval-chip">
                    p≈{(suggestion.human_typical.probability ?? 0).toFixed(3)}
                    <span className="meta"> · Maia-style</span>
                  </div>
                  <p className="pv">{suggestion.human_typical.pv_san.join(' ')}</p>
                </button>
              </div>
            ) : (
              <p className="empty-hint">Chưa có gợi ý — upload ảnh hoặc đi một nước.</p>
            )}

            <div className="think-panel">
              <div className="think-head">
                <span className="meta">Suy nghĩ tự động</span>
                <strong className="think-value">
                  {elapsedLabel} / {MAX_THINK_S}s
                </strong>
              </div>
              <div className="think-track" aria-hidden>
                <div
                  className={`think-fill ${thinking ? 'running' : ''}`}
                  style={{ width: `${thinkProgress}%` }}
                />
              </div>
              <div className="think-marks static">
                <span>0s Nhanh</span>
                <span>5s Sâu</span>
                <span>10s Rất sâu</span>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
