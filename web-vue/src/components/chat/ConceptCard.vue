<template>
  <!-- LA-UI-001 M3: 概念卡片（左侧视图分享到群聊的元素） -->
  <div class="concept-card">
    <div class="cc-header">
      <span class="cc-icon">🧩</span>
      <span class="cc-title">{{ title }}</span>
      <span v-if="conceptType" class="cc-type">{{ conceptType }}</span>
    </div>
    <div v-if="preview" class="cc-preview">{{ preview }}</div>
    <div v-if="actions && actions.length" class="cc-actions">
      <button
        v-for="(act, i) in actions"
        :key="i"
        class="cc-action-btn"
        @click="$emit('action', act)"
      >
        {{ act.label }}
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  preview: { type: String, default: '' },
  conceptType: { type: String, default: '' },
  // [{ label: '详细解释', action: 'ask_tutor' }, ...]
  actions: { type: Array, default: () => [] },
})

defineEmits(['action'])
</script>

<style scoped>
.concept-card {
  margin-top: 10px;
  background: var(--bg-input);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.cc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--bg-hover);
  border-bottom: 1px solid var(--border-color);
}

.cc-icon { font-size: 15px; }
.cc-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.cc-type {
  font-size: 11px;
  color: var(--text-secondary);
  border: 1px solid var(--border-light);
  border-radius: 4px;
  padding: 0 5px;
}

.cc-preview {
  padding: 10px 14px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.cc-actions {
  display: flex;
  gap: 8px;
  padding: 8px 14px;
  border-top: 1px solid var(--border-color);
  flex-wrap: wrap;
}

.cc-action-btn {
  background: var(--bg-active);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: var(--accent-primary);
  font-size: 12px;
  padding: 4px 12px;
  cursor: pointer;
}
.cc-action-btn:hover { border-color: var(--accent-primary); }
</style>
