<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const s = ref<any>({})
onMounted(async () => { s.value = await api('/seating/stats?hall_id=1') })
</script>
<template>
  <h1>统计</h1>
  <p class="sub">排座占用与违规汇总</p>
  <div class="card" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem">
    <div><div class="muted">已排座</div><div class="stat">{{ s.seated }}</div></div>
    <div><div class="muted">未排上</div><div class="stat">{{ s.unplaced }}</div></div>
    <div><div class="muted">违规数</div><div class="stat">{{ s.violations }}</div></div>
    <div><div class="muted">监考桌占格</div><div class="stat">{{ s.blocked ?? 0 }}</div></div>
    <div><div class="muted">可坐容量</div><div class="stat">{{ s.capacity }}</div></div>
  </div>
  <p class="muted" style="font-size:.78rem">
    可坐容量已按去掉整块监考桌矩形对齐；图上空区与未排人数同口径。
  </p>
</template>
