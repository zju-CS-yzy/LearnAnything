<template>
  <section class="gap-panel" :class="{ collapsed }" aria-label="知识缺口面板">
    <button class="gap-panel-header" type="button" @click="collapsed = !collapsed">
      <span class="gap-title"><span class="gap-mark">◇</span> 结构缺口</span>
      <span class="gap-total" title="当前树开放 Gap 数量">
        {{ summary?.by_status?.open || 0 }}
      </span>
      <span class="gap-chevron">{{ collapsed ? '▾' : '▴' }}</span>
    </button>

    <div v-if="!collapsed" class="gap-panel-body">
      <div class="status-row">
        <button
          v-for="item in statusOptions"
          :key="item.value"
          class="status-pill"
          :class="{ active: status === item.value }"
          type="button"
          @click="$emit('update:status', item.value)"
        >
          {{ item.label }} {{ statusCount(item.value) }}
        </button>
      </div>

      <p v-if="status === 'supplemented'" class="gap-status-note">
        已补充记录对应图中的真实概念节点；点击记录即可定位，虚拟 Gap 不再重复显示。
      </p>

      <label class="filter-row">
        <span>缺失类型</span>
        <select :value="missingType" @change="$emit('update:missingType', $event.target.value)">
          <option value="">全部类型</option>
          <option v-for="type in missingTypes" :key="type" :value="type">
            {{ typeLabel(type) }} · {{ summary?.open_by_missing_type?.[type] || 0 }}
          </option>
        </select>
      </label>

      <label class="filter-row confidence-row">
        <span>置信度 ≥ {{ Number(minConfidence).toFixed(1) }}</span>
        <input
          type="range" min="0" max="1" step="0.1" :value="minConfidence"
          @input="$emit('update:minConfidence', Number($event.target.value))"
        />
      </label>

      <p v-if="error" class="gap-error">{{ error }}</p>
      <p v-else-if="loading" class="gap-empty">正在加载缺口…</p>
      <p v-else-if="!gaps.length" class="gap-empty">当前筛选下没有 Gap</p>

      <div v-else class="gap-list">
        <div
          v-for="gap in gaps"
          :key="gap.gap_id"
          class="gap-list-entry"
        >
          <button
            type="button"
            class="gap-list-item"
            @click="$emit('select', gap)"
          >
            <span class="gap-list-main">
              <strong>{{ (gap.missing_types || []).map(typeLabel).join(' → ') }}</strong>
              <small v-if="gap.status === 'supplemented'">
                已写入 {{ supplementedCount(gap) }} 个概念节点 · 点击定位
              </small>
              <small v-else>{{ gap.reason || '结构链条存在缺失层' }}</small>
            </span>
            <span class="confidence">{{ Math.round((gap.confidence || 0) * 100) }}%</span>
          </button>
          <div class="gap-inline-actions">
            <span>{{ statusLabel(gap.status) }}</span>
            <button v-if="canWrite && gap.status === 'open'" type="button" @click="supplementGap(gap)">AI 补全</button>
            <button v-if="canWrite && gap.status === 'open'" type="button" @click="ignoreGap(gap)">忽略</button>
            <button v-if="canWrite && gap.status === 'ignored'" type="button" @click="reopenGap(gap)">重新打开</button>
          </div>
        </div>
      </div>

      <div class="panel-actions">
        <button type="button" class="quiet-btn" :disabled="loading" @click="$emit('refresh')">刷新</button>
        <button
          v-if="canWrite"
          type="button" class="primary-btn" :disabled="reconciling"
          @click="$emit('reconcile')"
        >{{ reconciling ? '检测中…' : '重新检测' }}</button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  summary: { type: Object, default: null },
  gaps: { type: Array, default: () => [] },
  status: { type: String, default: 'open' },
  missingType: { type: String, default: '' },
  minConfidence: { type: Number, default: 0 },
  typeLabels: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  reconciling: { type: Boolean, default: false },
  canWrite: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const emit = defineEmits([
  'update:status', 'update:missingType', 'update:minConfidence',
  'select', 'refresh', 'reconcile', 'supplement', 'ignore', 'reopen',
])

const collapsed = ref(false)
const statusOptions = [
  { value: 'open', label: '开放' },
  { value: 'ignored', label: '已忽略' },
  { value: 'supplemented', label: '已补充' },
  { value: 'obsolete', label: '已过期' },
]
const missingTypes = computed(() => Object.keys(props.summary?.open_by_missing_type || {}).sort())

function supplementGap(gap) { emit('supplement', gap) }
function ignoreGap(gap) { emit('ignore', gap) }
function reopenGap(gap) { emit('reopen', gap) }

function supplementedCount(gap) {
  return new Set((gap.supplemented_by || []).filter(Boolean)).size
}

function statusCount(status) {
  return props.summary?.by_status?.[status] || 0
}

function typeLabel(type) {
  return props.typeLabels?.[type] || type
}

function statusLabel(status) {
  return { open: '开放', ignored: '已忽略', supplemented: '已补充', obsolete: '已过期' }[status] || status
}
</script>

<style scoped>
.gap-panel { position: absolute; top: 12px; left: 12px; z-index: 12; width: min(320px, calc(100% - 24px)); border: 1px solid var(--border-color, #dfe5ea); border-radius: 12px; background: color-mix(in srgb, var(--bg-card, #fff) 94%, transparent); box-shadow: 0 10px 28px rgba(28,42,55,.14); backdrop-filter: blur(8px); overflow: hidden; }
.gap-panel-header { width: 100%; display: grid; grid-template-columns: 1fr auto auto; align-items: center; gap: 9px; border: 0; padding: 11px 13px; color: var(--text-primary, #243342); background: transparent; cursor: pointer; text-align: left; }
.gap-title { display: flex; align-items: center; gap: 7px; font-weight: 700; }
.gap-mark { color: #e67e22; font-size: 20px; line-height: 1; }
.gap-total { min-width: 24px; padding: 2px 7px; border-radius: 999px; background: #fff4e8; color: #b45309; font-size: 12px; text-align: center; }
.gap-chevron { color: var(--text-muted, #82909d); }
.gap-panel-body { padding: 0 13px 13px; border-top: 1px solid var(--border-color, #edf0f2); }
.status-row { display: flex; gap: 5px; overflow-x: auto; padding: 10px 0 8px; }
.status-pill { flex: 0 0 auto; border: 1px solid var(--border-color, #dfe5ea); border-radius: 999px; padding: 4px 8px; background: transparent; color: var(--text-secondary, #5a6875); font-size: 11px; cursor: pointer; }
.status-pill.active { border-color: #e67e22; background: #fff4e8; color: #9a4d08; }
.gap-status-note { margin: 0 0 8px; padding: 7px 8px; border: 1px solid #b9dfc8; border-radius: 7px; background: #f0faf4; color: #23663d; font-size: 11px; line-height: 1.45; }
.filter-row { display: grid; grid-template-columns: 80px 1fr; align-items: center; gap: 8px; margin: 7px 0; color: var(--text-secondary, #5b6874); font-size: 12px; }
.filter-row select { min-width: 0; padding: 6px 8px; border: 1px solid var(--border-color, #dfe5ea); border-radius: 7px; background: var(--bg-card, #fff); color: inherit; }
.confidence-row { grid-template-columns: 112px 1fr; }
.confidence-row input { accent-color: #e67e22; }
.gap-list { max-height: 238px; overflow-y: auto; margin-top: 8px; display: grid; gap: 6px; }
.gap-list-entry { display: grid; gap: 4px; }
.gap-list-item { width: 100%; display: flex; align-items: center; gap: 8px; padding: 8px 9px; border: 1px solid var(--border-color, #e7eaed); border-radius: 8px; background: var(--bg-card, #fff); color: inherit; text-align: left; cursor: pointer; }
.gap-list-item:hover { border-color: #efb070; background: #fffaf4; }
.gap-list-main { min-width: 0; display: grid; gap: 2px; flex: 1; }
.gap-list-main strong { font-size: 12px; }
.gap-list-main small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-muted, #7f8b95); }
.confidence { font-size: 11px; color: #b45309; }
.gap-inline-actions { display: flex; align-items: center; justify-content: flex-end; gap: 6px; padding: 0 4px 3px; color: var(--text-muted, #7f8b95); font-size: 11px; }
.gap-inline-actions button { border: 1px solid #efb070; border-radius: 6px; padding: 4px 7px; background: #fff8f0; color: #9a4d08; cursor: pointer; }
.gap-empty, .gap-error { margin: 10px 0; font-size: 12px; color: var(--text-muted, #7f8b95); }
.gap-error { color: #b42318; }
.panel-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 7px; margin-top: 10px; }
.quiet-btn, .primary-btn { border-radius: 7px; padding: 6px 10px; font-size: 12px; cursor: pointer; }
.quiet-btn { border: 1px solid var(--border-color, #dfe5ea); background: transparent; color: inherit; }
.primary-btn { border: 1px solid #d96f12; background: #e67e22; color: #fff; }
button:disabled { opacity: .55; cursor: not-allowed; }
</style>
