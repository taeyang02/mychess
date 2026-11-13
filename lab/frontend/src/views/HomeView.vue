<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Chess } from 'chess.js'
import BoardPanel from '../components/BoardPanel.vue'
import { suggest, type SuggestResponse } from '../api'

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

const fen = ref(START)
const elo = ref(1500)
const depth = ref(12)
const busy = ref(false)
const error = ref('')
const result = ref<SuggestResponse | null>(null)
const highlight = ref<'engine' | 'human'>('engine')

const arrows = computed(() => {
  const r = result.value
  if (!r) return [] as { from: string; to: string; color: string }[]
  const pick = highlight.value === 'engine' ? r.stockfish_best : r.human_typical
  if (!pick?.uci || pick.uci.length < 4) return []
  return [
    {
      from: pick.uci.slice(0, 2),
      to: pick.uci.slice(2, 4),
      color: highlight.value === 'engine' ? '#3d9b7a' : '#d4a017',
    },
  ]
})

async function runSuggest() {
  error.value = ''
  busy.value = true
  try {
    result.value = await suggest({
      fen: fen.value,
      elo: elo.value,
      depth: depth.value,
      multipv: 5,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

function reset() {
  fen.value = START
  result.value = null
  error.value = ''
}

function playUci(uci: string) {
  try {
    const board = new Chess(fen.value)
    const move = board.move({
      from: uci.slice(0, 2),
      to: uci.slice(2, 4),
      promotion: uci.length > 4 ? (uci[4] as 'q' | 'r' | 'b' | 'n') : undefined,
    })
    if (!move) return
    fen.value = board.fen()
    void runSuggest()
  } catch {
    error.value = 'Illegal move'
  }
}

watch(elo, () => {
  if (result.value) void runSuggest()
})
</script>

<template>
  <div class="grid-2">
    <section class="panel">
      <h2>Board</h2>
      <BoardPanel :fen="fen" />
      <p class="muted" style="margin-top: 0.5rem">FEN</p>
      <textarea v-model="fen" style="min-height: 72px" />
      <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.75rem; align-items: center">
        <label class="muted">Elo
          <input v-model.number="elo" type="number" min="600" max="2800" step="50" style="width: 5rem; margin-left: 0.35rem" />
        </label>
        <label class="muted">depth
          <input v-model.number="depth" type="number" min="6" max="20" style="width: 4rem; margin-left: 0.35rem" />
        </label>
        <button type="button" :disabled="busy" @click="runSuggest">
          {{ busy ? 'Thinking…' : 'Suggest' }}
        </button>
        <button type="button" class="secondary" @click="reset">Reset</button>
      </div>
      <p v-if="error" class="danger">{{ error }}</p>
    </section>

    <section class="panel">
      <h2>Dual suggestions</h2>
      <p class="muted">Hai cột tách biệt — không gộp thành một nước “né detect”.</p>

      <div v-if="result" class="metrics" style="margin-top: 0.75rem">
        <button
          type="button"
          class="metric"
          :style="highlight === 'engine' ? 'outline: 2px solid var(--accent)' : ''"
          @click="highlight = 'engine'"
        >
          <div class="label">Stockfish best</div>
          <div class="value">{{ result.stockfish_best.san }}</div>
          <div class="muted">{{ result.stockfish_best.eval_text }} · depth {{ result.engine.depth }}</div>
          <button type="button" style="margin-top: 0.4rem" @click.stop="playUci(result.stockfish_best.uci)">Play</button>
        </button>
        <button
          type="button"
          class="metric"
          :style="highlight === 'human' ? 'outline: 2px solid var(--warn)' : ''"
          @click="highlight = 'human'"
        >
          <div class="label">Human-typical ~{{ result.elo_band }}</div>
          <div class="value">{{ result.human_typical.san }}</div>
          <div class="muted">p≈{{ (result.human_typical.probability ?? 0).toFixed(3) }} · Maia-style</div>
          <button type="button" style="margin-top: 0.4rem" @click.stop="playUci(result.human_typical.uci)">Play</button>
        </button>
      </div>

      <div v-if="result" class="grid-2" style="margin-top: 1rem; grid-template-columns: 1fr 1fr">
        <div>
          <h3>Engine lines</h3>
          <ul class="muted">
            <li v-for="line in result.stockfish_lines" :key="'e'+line.uci">
              {{ line.rank }}. {{ line.san }} <span>({{ line.eval_text }})</span>
            </li>
          </ul>
        </div>
        <div>
          <h3>Human-typical lines</h3>
          <ul class="muted">
            <li v-for="line in result.human_lines" :key="'h'+line.uci">
              {{ line.rank }}. {{ line.san }} <span>(p={{ (line.probability ?? 0).toFixed(3) }})</span>
            </li>
          </ul>
        </div>
      </div>

      <div v-if="result" class="disclaimer">{{ result.disclaimer }}</div>
      <p v-else class="muted">Nhập FEN hoặc để startpos → bấm Suggest.</p>
    </section>
  </div>
</template>
