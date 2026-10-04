<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<any>(null)
const candidates = ref<any[]>([])
const violKeys = ref<Set<string>>(new Set())
async function run() {
  data.value = await api('/seating/run?hall_id=1', { method: 'POST' })
  try {
    const v = await api('/seating/violations?hall_id=1')
    const keys = new Set<string>()
    for (const x of v.violations || []) {
      if (x.a_id != null) keys.add(String(x.a_id))
      if (x.b_id != null) keys.add(String(x.b_id))
    }
    violKeys.value = keys
  } catch { violKeys.value = new Set() }
}
onMounted(async () => {
  candidates.value = await api('/candidates')
  await run()
})
const gridStyle = computed(() => data.value ? ({ gridTemplateColumns: `repeat(${data.value.cols}, 72px)` }) : {})
const cells = computed(() => {
  if (!data.value) return []
  const map = new Map<string, any>()
  for (const a of data.value.assignments || []) map.set(a.row + ',' + a.col, a)
  const blocked = new Set((data.value.blocked || []).map((p: number[]) => p[0] + ',' + p[1]))
  const frontRows = data.value.front_rows || 0
  const out: any[] = []
  for (let r = 0; r < data.value.rows; r++) {
    for (let c = 0; c < data.value.cols; c++) {
      const key = r + ',' + c
      if (blocked.has(key)) {
        // 监考桌占格：整块矩形，不落考生
        out.push({ desk: true, row: r, col: c })
      } else if (map.has(key)) {
        out.push(map.get(key))
      } else {
        out.push({ empty: true, row: r, col: c, front: r < frontRows })
      }
    }
  }
  return out
})
function isViol(cell: any) {
  if (cell.empty) return false
  const id = cell.candidate_id ?? cell.id
  return id != null && violKeys.value.has(String(id))
}
function paperClass(pid: number) {
  return pid % 2 === 0 ? 'b' : 'a'
}
</script>
<template>
  <h1>考场课桌网格</h1>
  <p class="sub">课桌网格为主视图 · 左侧考生名册夹板 · 违规课桌高亮</p>
  <button class="btn" @click="run">重新排座</button>
  <div class="hs-classroom" style="margin-top:0.85rem">
    <aside class="hs-clipboard">
      <h2>考生名册</h2>
      <div v-for="c in candidates" :key="c.id" class="hs-roster-row">
        <div>
          <div>{{ c.name }}</div>
          <div class="hs-ticket">{{ c.ticket_no }}</div>
        </div>
        <div>卷{{ c.paper_id }}</div>
      </div>
    </aside>
    <div class="hs-desk-stage" v-if="data">
      <div class="wall-label">前排 · 讲台侧（第 0 行起{{ data.front_rows ? `，前 ${data.front_rows} 行为前排区` : '' }}）</div>
      <div class="hs-grid-board" :style="gridStyle">
        <div
          v-for="(cell,i) in cells" :key="i"
          class="hs-desk"
          :class="{ empty: cell.empty, 'hs-viol': isViol(cell), 'hs-invigilator': cell.desk, 'hs-front-zone': cell.empty && cell.front }"
        >
          <template v-if="cell.desk">
            <span class="hs-desk-mark">监考桌</span>
          </template>
          <template v-else-if="!cell.empty">
            <span class="hs-paper-tag" :class="paperClass(cell.paper_id)">卷{{ cell.paper_id }}</span>
            <div>{{ cell.name }}</div>
          </template>
          <template v-else>·</template>
        </div>
      </div>
      <div class="wall-label back">后墙 · 最大行号侧（监考桌整块贴此墙，不悬于考室中部）</div>
      <div class="hs-legend">
        <span><i class="lg lg-desk"></i>监考桌占格（矩形内不落考生）</span>
        <span v-if="data.front_rows"><i class="lg lg-front"></i>前排区</span>
        <span><i class="lg lg-empty"></i>空区</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wall-label {
  font-family: "Segoe UI", "PingFang SC", sans-serif;
  font-size: 0.72rem; color: var(--hs-muted);
  letter-spacing: 0.05em; padding: 0.15rem 0.4rem;
}
.wall-label.back { border-top: 3px solid var(--hs-wood); margin-top: 0.55rem; padding-top: 0.3rem; }
.hs-desk.hs-invigilator {
  background: repeating-linear-gradient(45deg, #6b5a36, #6b5a36 6px, #57492d 6px, #57492d 12px);
  border-color: #3f3520; color: #f3e9cf;
  box-shadow: inset 0 0 0 2px rgba(255, 240, 200, 0.25), 1px 2px 0 rgba(30,42,54,0.2);
}
.hs-desk-mark {
  font-weight: 800; font-size: 0.66rem; letter-spacing: 0.05em;
  writing-mode: horizontal-tb;
}
.hs-desk.hs-front-zone { background: rgba(43, 108, 176, 0.08); }
.hs-legend {
  display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.6rem;
  font-family: "Segoe UI", "PingFang SC", sans-serif; font-size: 0.74rem;
  color: var(--hs-muted);
}
.hs-legend .lg {
  display: inline-block; width: 13px; height: 13px; border-radius: 2px;
  margin-right: 0.3rem; vertical-align: -2px; border: 1px solid #7a8a98;
}
.lg-desk {
  background: repeating-linear-gradient(45deg, #6b5a36, #6b5a36 4px, #57492d 4px, #57492d 8px);
  border-color: #3f3520;
}
.lg-front { background: rgba(43, 108, 176, 0.18); }
.lg-empty { background: transparent; border-style: dashed; }
</style>
