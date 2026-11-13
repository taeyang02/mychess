import type { PieceRenderObject } from 'react-chessboard'

const images = import.meta.glob('./assets/pieces/*.svg', {
  eager: true,
  import: 'default',
  query: '?url',
}) as Record<string, string>

export const boardPieces: PieceRenderObject = Object.fromEntries(
  Object.entries(images).map(([path, url]) => [
    path.slice(-6, -4),
    () => (
      <img src={url} alt="" draggable={false} className="board-piece-image" />
    ),
  ]),
)
