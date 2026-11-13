<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import BoardPanel from '../components/BoardPanel.vue'
import { getMoves, getReport } from '../api'

const props = defineProps<{ id: string }>()
const router = useRouter()
const loading = ref(true)
const error = ref('')
const report = ref<Record<string, any> | null>(null)
const moves = ref<Array<Record<string, any>>>([])
const selected = ref(0)

const fen = computed(() => {
  const m = moves.value[selected.value]
  return (m?.fen_before as string) || 'start'
})

onMounted(async () => {
  try {
    report.value = await getReport(props.id)
    moves.value = await getMoves(props.id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})

function fmt(n: unknown, digits = 2) {
  if (n === null || n === undefined) return '—'
  if (typeof n === 'number') return n.toFixed(digits)
  return String(n)
}
</script>

<template>
  <div v-if="loading" class="muted">Loading report…</div>
  <div v-else-if="error" class="danger">{{ error }}</div>
  <div v-else-if="report">
    <p>
      <button type="button" class="secondary" @click="router.push('/')">← New analysis</button>
    </p>

    <div class="disclaimer">{{ report.disclaimer }}</div>

    <div class="grid-2" style="margin-top: 1rem">
      <section class="panel">
        <h2>Board</h2>
        <BoardPanel :fen="fen" />
        <p class="muted" style="margin-top: 0.5rem">
          Ply {{ moves[selected]?.ply }} · {{ moves[selected]?.san }} ·
          {{ moves[selected]?.phase }}
        </p>
      </section>

      <section class="panel">
        <h2>Game metadata</h2>
        <div class="metrics">
          <div class="metric">
            <div class="label">White</div>
            <div class="value">{{ report.metadata?.white }} ({{ report.metadata?.white_elo ?? '?' }})</div>
          </div>
          <div class="metric">
            <div class="label">Black</div>
            <div class="value">{{ report.metadata?.black }} ({{ report.metadata?.black_elo ?? '?' }})</div>
          </div>
          <div class="metric">
            <div class="label">TimeControl</div>
            <div class="value">{{ report.metadata?.time_control ?? 'missing' }}</div>
          </div>
          <div class="metric">
            <div class="label">Synthetic</div>
            <div class="value">{{ report.synthetic_demo ? 'yes' : 'no' }}</div>
          </div>
        </div>

        <h3 style="margin-top: 1rem">Player summaries</h3>
        <div class="metrics">
          <div class="metric" v-for="side in ['white', 'black']" :key="side">
            <div class="label">{{ side }} anomaly %ile</div>
            <div class="value">{{ fmt(report[side]?.anomaly_percentile, 1) }}</div>
            <div class="muted">avg CP {{ fmt(report[side]?.avg_cp_loss, 1) }} · top1 {{ fmt((report[side]?.top1_agreement || 0) * 100, 0) }}%</div>
          </div>
        </div>
        <p class="muted" style="margin-top: 0.5rem">
          {{ report.white?.confidence_note }}
        </p>
      </section>
    </div>

    <section class="panel" style="margin-top: 1rem">
      <h2>Move features</h2>
      <div style="overflow: auto; max-height: 420px">
        <table class="moves">
          <thead>
            <tr>
              <th>#</th>
              <th>SAN</th>
              <th>Rank</th>
              <th>CPΔ</th>
              <th>p(human)</th>
              <th>Surprisal</th>
              <th>Think</th>
              <th>Flag</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(m, i) in moves"
              :key="m.ply"
              :class="{ review: m.review_flag }"
              style="cursor: pointer"
              @click="selected = i"
            >
              <td>{{ m.ply }}</td>
              <td>{{ m.san }}</td>
              <td>{{ m.engine_rank ?? '—' }}</td>
              <td>{{ fmt(m.cp_loss, 0) }}</td>
              <td>{{ fmt(m.maia_probability, 3) }}</td>
              <td>{{ fmt(m.maia_surprisal, 2) }}</td>
              <td>{{ fmt(m.think_time_seconds, 1) }}s</td>
              <td>{{ m.review_flag ? 'review' : '' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel" style="margin-top: 1rem">
      <h2>Limitations</h2>
      <ul class="muted">
        <li v-for="(l, i) in report.limitations || []" :key="i">{{ l }}</li>
      </ul>
      <h3>Data quality</h3>
      <pre class="muted" style="white-space: pre-wrap; font-size: 0.8rem">{{ JSON.stringify(report.data_quality, null, 2) }}</pre>
    </section>
  </div>
</template>
