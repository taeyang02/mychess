<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { importPgn, startAnalysis } from '../api'

const router = useRouter()
const pgn = ref('')
const depth = ref(10)
const multipv = ref(5)
const busy = ref(false)
const error = ref('')
const warnings = ref<string[]>([])

const SAMPLE = `[Event "Synthetic Anti-Cheat Lab Example"]
[Site "offline-lab"]
[Date "2024.01.15"]
[White "HonestPlayerA"]
[Black "HonestPlayerB"]
[Result "1-0"]
[WhiteElo "1620"]
[BlackElo "1580"]
[TimeControl "600+0"]
[Annotator "synthetic-demo — not a real rated game"]

1. e4 {[%clk 0:10:00]} e5 {[%clk 0:09:55]} 2. Nf3 {[%clk 0:09:45]} Nc6 {[%clk 0:09:40]}
3. Bc4 {[%clk 0:09:30]} Bc5 {[%clk 0:09:20]} 4. c3 {[%clk 0:09:00]} Nf6 {[%clk 0:08:50]}
5. d3 {[%clk 0:08:30]} d6 {[%clk 0:08:20]} 6. O-O {[%clk 0:08:00]} O-O {[%clk 0:07:50]} *`

function loadSample() {
  pgn.value = SAMPLE
}

async function run() {
  error.value = ''
  warnings.value = []
  busy.value = true
  try {
    const imp = await importPgn(pgn.value)
    warnings.value = imp.warnings || []
    const job = await startAnalysis(imp.game_id, depth.value, multipv.value)
    await router.push({ name: 'analysis', params: { id: job.analysis_id } })
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="grid-2">
    <section class="panel">
      <h2>Import PGN</h2>
      <p class="muted">
        Offline lab — paste PGN with optional <code>[%clk]</code>. Advisor Move-from-image stays on the original app.
      </p>
      <textarea v-model="pgn" placeholder="Paste PGN text…" />
      <div style="display: flex; gap: 0.5rem; margin-top: 0.75rem; flex-wrap: wrap">
        <button type="button" class="secondary" @click="loadSample">Load synthetic sample</button>
        <label class="muted">depth
          <input v-model.number="depth" type="number" min="6" max="16" style="width: 4rem; margin-left: 0.35rem" />
        </label>
        <label class="muted">MultiPV
          <input v-model.number="multipv" type="number" min="3" max="8" style="width: 4rem; margin-left: 0.35rem" />
        </label>
        <button type="button" :disabled="busy || !pgn.trim()" @click="run">
          {{ busy ? 'Analyzing…' : 'Analyze offline' }}
        </button>
      </div>
      <p v-if="error" class="danger">{{ error }}</p>
      <ul v-if="warnings.length" class="warn">
        <li v-for="(w, i) in warnings" :key="i">{{ w }}</li>
      </ul>
    </section>

    <section class="panel">
      <h2>What this v2 screen does</h2>
      <ul class="muted">
        <li>Stockfish MultiPV offline metrics (CP loss, top-N agreement)</li>
        <li>Elo-band human-policy surrogate (Maia-ready interface)</li>
        <li>Think-time extraction from clocks when present</li>
        <li>Anomaly percentile vs synthetic honest priors — <strong>not</strong> P(cheat)</li>
        <li>Expert-review flags with explicit uncertainty</li>
      </ul>
      <div class="disclaimer">
        No live-game coaching. No evasion tooling. Single-game results never justify a cheat label.
      </div>
    </section>
  </div>
</template>
