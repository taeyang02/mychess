import { Chess, type Square } from 'chess.js'
import type { Turn } from './api'

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

export function startingFen(): string {
  return START_FEN
}

export function normalizeFen(fen: string, turn: Turn): string {
  const parts = fen.trim().split(/\s+/)
  const placement = parts[0] || '8/8/8/8/8/8/8/8'
  const side = turn === 'white' ? 'w' : 'b'
  const castling = parts[2] || '-'
  const ep = parts[3] || '-'
  const half = parts[4] || '0'
  const full = parts[5] || '1'
  return `${placement} ${side} ${castling} ${ep} ${half} ${full}`
}

export function placementOnly(fen: string): string {
  return fen.trim().split(/\s+/)[0] || '8/8/8/8/8/8/8/8'
}

export function tryLoadBoard(fen: string, turn: Turn): Chess | null {
  try {
    return new Chess(normalizeFen(fen, turn))
  } catch {
    try {
      const placement = placementOnly(fen)
      return new Chess(`${placement} ${turn === 'white' ? 'w' : 'b'} - - 0 1`)
    } catch {
      return null
    }
  }
}

export type PlayedMove = {
  fen: string
  turn: Turn
  san: string
  uci: string
  before: string
}

export type LegalTarget = {
  to: string
  capture: boolean
}

/** Legal destination squares for a piece on `from`. */
export function getLegalTargets(
  fen: string,
  turn: Turn,
  from: string,
): LegalTarget[] {
  const board = tryLoadBoard(fen, turn)
  if (!board) return []

  const piece = board.get(from as Square)
  if (!piece) return []
  const side = turn === 'white' ? 'w' : 'b'
  if (piece.color !== side) return []

  try {
    const moves = board.moves({ square: from as Square, verbose: true })
    return moves.map((m) => ({
      to: m.to,
      capture: Boolean(m.captured),
    }))
  } catch {
    return []
  }
}

/** Play a legal chess move; returns null if illegal. */
export function playLegalMove(
  fen: string,
  turn: Turn,
  source: string,
  target: string,
  promotion: 'q' | 'r' | 'b' | 'n' = 'q',
): PlayedMove | null {
  const board = tryLoadBoard(fen, turn)
  if (!board) return null

  try {
    const move = board.move({
      from: source as Square,
      to: target as Square,
      promotion,
    })
    if (!move) return null
    const nextTurn: Turn = board.turn() === 'w' ? 'white' : 'black'
    return {
      fen: board.fen(),
      turn: nextTurn,
      san: move.san,
      uci: move.lan,
      before: move.before,
    }
  } catch {
    return null
  }
}
