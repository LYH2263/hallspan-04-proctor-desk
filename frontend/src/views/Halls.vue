<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

interface Hall {
  id: number; code: string; name: string
  rows: number; cols: number; min_manhattan: number
  front_rows: number; desk_rows: number; desk_cols: number; desk_col: number
}
const rows = ref<Hall[]>([])
const drafts = ref<Record<number, Hall>>({})
const errors = ref<Record<number, string>>({})
const savedAt = ref<Record<number, string>>({})
const saving = ref<Record<number, boolean>>({})

async function load() {
  rows.value = await api('/halls')
  drafts.value = {}
  for (const r of rows.value) drafts.value[r.id] = { ...r }
}
onMounted(load)

// 监考桌只贴后墙：纵向位置不可任意指定，行高决定它从最后一行向前占几行
function backHint(h: Hall) {
  if (!h.desk_rows || !h.desk_cols) return '未配桌（与现网一致）'
  const top = h.rows - h.desk_rows
  return `贴后墙 · 占第 ${top}–${h.rows - 1} 行、第 ${h.desk_col}–${h.desk_col + h.desk_cols - 1} 列`
}

async function save(h: Hall) {
  const d = drafts.value[h.id]
  errors.value[h.id] = ''
  saving.value[h.id] = true
  try {
    const res = await api(`/halls/${h.id}/config`, {
      method: 'PUT',
      body: JSON.stringify({
        rows: d.rows, cols: d.cols, min_manhattan: d.min_manhattan,
        front_rows: d.front_rows, desk_rows: d.desk_rows,
        desk_cols: d.desk_cols, desk_col: d.desk_col,
      }),
    })
    Object.assign(h, res.hall)
    drafts.value[h.id] = { ...h }
    savedAt.value[h.id] = res.plan
      ? `已保存，并按新桌尺寸重排方案（#${res.plan.id}，历史方案保留）`
      : '已保存（尚无方案，未自动生成）'
  } catch (e: any) {
    // 保存失败：考室、方案、统计都停在保存前，这里只提示原因
    let msg = String(e.message || e)
    try {
      const body = JSON.parse(msg)
      msg = typeof body.detail === 'string'
        ? body.detail
        : Array.isArray(body.detail)
          ? body.detail.map((x: any) => x.msg).join('；')
          : msg
    } catch { /* plain text body */ }
    errors.value[h.id] = msg
  } finally {
    saving.value[h.id] = false
  }
}
</script>

<template>
  <h1>考室</h1>
  <p class="sub">考室网格、前排区与监考桌占格 · 监考桌只能整块贴后墙，不可悬于考室中部</p>

  <div class="card" v-for="h in rows" :key="h.id">
    <div class="hall-head">
      <strong>{{ h.name }}（{{ h.code }}）</strong>
      <span class="muted">{{ backHint(drafts[h.id]) }}</span>
    </div>
    <div class="cfg-grid">
      <label>行数<input type="number" min="1" v-model.number="drafts[h.id].rows"></label>
      <label>列数<input type="number" min="1" v-model.number="drafts[h.id].cols"></label>
      <label>最小曼哈顿间距<input type="number" min="1" v-model.number="drafts[h.id].min_manhattan"></label>
      <label>前排行数（第 0 行起）<input type="number" min="0" v-model.number="drafts[h.id].front_rows"></label>
      <label>监考桌行数（高度）<input type="number" min="0" v-model.number="drafts[h.id].desk_rows"></label>
      <label>监考桌列数（宽度）<input type="number" min="0" v-model.number="drafts[h.id].desk_cols"></label>
      <label>监考桌起始列<input type="number" min="0" v-model.number="drafts[h.id].desk_col"></label>
    </div>
    <p class="muted cfg-note">
      监考桌固定贴在最大行号那一侧，占整块矩形，矩形内不落考生；桌高填 0、宽填 0 表示未配桌。
    </p>
    <div class="cfg-actions">
      <button class="btn" :disabled="saving[h.id]" @click="save(h)">
        {{ saving[h.id] ? '保存中…' : '保存配置' }}
      </button>
      <span v-if="errors[h.id]" class="cfg-err">保存失败：{{ errors[h.id] }} —— 考室、方案与统计停在保存前</span>
      <span v-else-if="savedAt[h.id]" class="cfg-ok">{{ savedAt[h.id] }}</span>
    </div>
  </div>
</template>

<style scoped>
.hall-head { display: flex; gap: 0.75rem; align-items: baseline; margin-bottom: 0.6rem; }
.cfg-grid {
  display: grid; gap: 0.6rem;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
}
.cfg-grid label {
  display: flex; flex-direction: column; gap: 0.25rem;
  font-size: 0.78rem; color: var(--hs-muted);
  font-family: "Segoe UI", "PingFang SC", sans-serif;
}
.cfg-grid input {
  padding: 0.35rem 0.45rem; border: 1px solid #b0a890; border-radius: 2px;
  font-size: 0.9rem; background: #fff;
}
.cfg-note { font-size: 0.75rem; margin: 0.55rem 0; }
.cfg-actions { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
.cfg-err { color: var(--hs-bad); font-size: 0.8rem; font-weight: 700; }
.cfg-ok { color: var(--hs-ok); font-size: 0.8rem; }
</style>
