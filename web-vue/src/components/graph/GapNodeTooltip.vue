<template>
  <aside v-if="visible && gap" class="gap-tooltip" :style="style" @mouseenter="$emit('hold')" @mouseleave="$emit('close')">
        <div class="gap-tooltip-title">
          <span class="gap-symbol">◇</span>
          <div><strong>结构缺口</strong><small>{{ typeLabel(currentType) }}</small></div>
          <span class="gap-confidence">{{ Math.round((gap.confidence || 0) * 100) }}%</span>
        </div>
        <p>{{ gap.reason || '范式链条中缺少一个中间概念。' }}</p>
        <dl>
          <div><dt>缺失链</dt><dd>{{ (gap.missing_types || []).map(typeLabel).join(' → ') }}</dd></div>
          <div><dt>状态</dt><dd>{{ statusLabel(gap.status) }}</dd></div>
        </dl>
        <div v-if="canWrite" class="gap-tooltip-actions">
          <button v-if="gap.status === 'open'" class="primary" @click="$emit('supplement', gap)">AI 补全</button>
          <button v-if="gap.status === 'open'" @click="$emit('ignore', gap)">忽略</button>
          <button v-if="gap.status === 'ignored'" class="primary" @click="$emit('reopen', gap)">重新打开</button>
        </div>
        <small v-else class="readonly-note">只读权限：可查看，但不能处理 Gap</small>
  </aside>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  gap: { type: Object, default: null },
  currentType: { type: String, default: '' },
  position: { type: Object, default: () => ({ x: 0, y: 0 }) },
  typeLabels: { type: Object, default: () => ({}) },
  canWrite: { type: Boolean, default: false },
})
defineEmits(['hold', 'close', 'supplement', 'ignore', 'reopen'])

const style = computed(() => {
  const width = 300
  let left = props.position.x + 18
  let top = props.position.y - 8
  if (left + width > window.innerWidth - 12) left = props.position.x - width - 18
  if (top + 260 > window.innerHeight) top = window.innerHeight - 272
  return { left: `${Math.max(12, left)}px`, top: `${Math.max(12, top)}px` }
})

function typeLabel(type) { return props.typeLabels?.[type] || type }
function statusLabel(status) {
  return { open: '开放', ignored: '已忽略', supplemented: '已补充', obsolete: '已过期' }[status] || status
}
</script>

<style scoped>
.gap-tooltip { position: fixed; z-index: 10020; width: 300px; box-sizing: border-box; padding: 14px; border: 1px solid #efb070; border-radius: 12px; background: var(--bg-card, #fff); color: var(--text-primary, #273543); box-shadow: 0 14px 38px rgba(68,40,14,.2); }
.gap-tooltip-title { display: grid; grid-template-columns: auto 1fr auto; gap: 9px; align-items: center; }
.gap-symbol { display: grid; place-items: center; width: 30px; height: 30px; border: 2px dashed #e67e22; border-radius: 50%; color: #e67e22; }
.gap-tooltip-title div { display: grid; }
.gap-tooltip-title small { color: #b45309; }
.gap-confidence { padding: 3px 7px; border-radius: 999px; background: #fff4e8; color: #9a4d08; font-size: 11px; }
.gap-tooltip p { margin: 12px 0; font-size: 13px; line-height: 1.55; color: var(--text-secondary, #52606c); }
.gap-tooltip dl { margin: 0; display: grid; gap: 6px; }
.gap-tooltip dl div { display: grid; grid-template-columns: 54px 1fr; gap: 7px; font-size: 12px; }
.gap-tooltip dt { color: var(--text-muted, #85919b); }
.gap-tooltip dd { margin: 0; }
.gap-tooltip-actions { display: flex; justify-content: flex-end; gap: 7px; margin-top: 13px; }
.gap-tooltip button { border: 1px solid #d9dee3; border-radius: 7px; padding: 6px 9px; background: transparent; color: inherit; cursor: pointer; }
.gap-tooltip button.primary { border-color: #d96f12; background: #e67e22; color: #fff; }
.readonly-note { display: block; margin-top: 12px; color: var(--text-muted, #85919b); }
.gap-tooltip-enter-active, .gap-tooltip-leave-active { transition: opacity .16s ease, transform .16s ease; }
.gap-tooltip-enter-from, .gap-tooltip-leave-to { opacity: 0; transform: translateY(4px); }
</style>
