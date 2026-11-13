<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { Chessground } from 'chessground'
import type { Api } from 'chessground/api'

const props = defineProps<{ fen: string }>()
const el = ref<HTMLElement | null>(null)
let ground: Api | null = null

onMounted(() => {
  if (!el.value) return
  ground = Chessground(el.value, {
    fen: props.fen,
    viewOnly: true,
    coordinates: true,
    animation: { enabled: true, duration: 180 },
  })
})

watch(
  () => props.fen,
  (fen) => ground?.set({ fen }),
)

onUnmounted(() => {
  ground?.destroy()
  ground = null
})
</script>

<template>
  <div class="board-wrap">
    <div ref="el" class="cg-wrap" />
  </div>
</template>
