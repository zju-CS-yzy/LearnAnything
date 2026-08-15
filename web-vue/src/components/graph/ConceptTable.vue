<template>
  <section class="concept-table-wrapper" aria-labelledby="concept-catalog-title">
    <div class="table-header">
      <div>
        <h3 id="concept-catalog-title">全局概念</h3>
        <p>跨文档合并后的概念目录，可按类型筛选并追溯来源。</p>
      </div>
      <span class="table-count">{{ concepts.length }} 个概念</span>
    </div>

    <div class="concept-toolbar">
      <div class="toolbar-group">
        <input
          v-model="searchQuery"
          class="search-input"
          placeholder="🔍 搜索概念..."
          @keyup.enter="filter"
        />
        <button class="btn btn-sm" @click="filter">搜索</button>
      </div>
      <div class="toolbar-group">
        <span class="stats">显示 {{ filtered.length }} / {{ concepts.length }} 个概念</span>
      </div>
    </div>

    <div v-if="availableTypes.length" class="type-filters" aria-label="按概念类型筛选">
      <button
        class="filter-chip"
        :class="{ active: selectedType === '' }"
        :aria-pressed="selectedType === ''"
        @click="selectedType = ''"
      >全部 {{ concepts.length }}</button>
      <button
        v-for="item in availableTypes"
        :key="item.type"
        class="filter-chip"
        :class="{ active: selectedType === item.type }"
        :aria-pressed="selectedType === item.type"
        @click="selectedType = item.type"
      >
        <span class="filter-dot" :style="{ background: colorFor(item.type) }"></span>
        {{ typeLabel(item.type) }} {{ item.count }}
      </button>
    </div>

    <div v-if="filtered.length" class="table-scroll">
      <table class="concept-table">
        <thead>
          <tr>
            <th>概念名称</th>
            <th>说明</th>
            <th>别名</th>
            <th>类型</th>
            <th>关系</th>
            <th>来源</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in paginated"
            :key="c.id"
            tabindex="0"
            @click="$emit('select', c)"
            @keyup.enter="$emit('select', c)"
          >
            <td class="name-cell">{{ c.name }}</td>
            <td class="description-cell">{{ c.description || '—' }}</td>
            <td class="alias-cell">
              <span v-if="c.aliases" class="alias-tags">{{ c.aliases.slice(0, 3).join(' | ') }}</span>
            </td>
            <td>
              <span class="type-badge" :style="{ background: colorFor(c.concept_type) }">{{ typeLabel(c.concept_type) }}</span>
            </td>
            <td>{{ relationLabel(c.relation) }}</td>
            <td>{{ c.source_chunk_count }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else class="empty-state" role="status">
      <strong>{{ concepts.length ? '没有匹配的概念' : '尚未生成全局概念' }}</strong>
      <span>{{ concepts.length ? '尝试清除搜索词或切换类型。' : '完成图谱构建后，去重概念会显示在这里。' }}</span>
    </div>

    <!-- 分页 -->
    <div v-if="filtered.length" class="pagination">
      <button class="btn btn-sm" :disabled="page <= 1" @click="page--">上一页</button>
      <span class="page-info">第 {{ page }} / {{ totalPages }} 页</span>
      <button class="btn btn-sm" :disabled="page >= totalPages" @click="page++">下一页</button>
      <select v-model="pageSize" class="page-size-select">
        <option :value="10">10/页</option>
        <option :value="20">20/页</option>
        <option :value="50">50/页</option>
        <option :value="100">100/页</option>
      </select>
    </div>
  </section>
</template>

<script setup>
/**
 * ConceptTable — 全局概念表格（去重后）
 * 支持搜索、分页
 */
import { ref, computed, watch } from 'vue'

const props = defineProps({
  concepts: { type: Array, default: () => [] },
  typeLabels: { type: Object, default: () => ({}) },
  relationLabels: { type: Object, default: () => ({}) },
  typeColors: { type: Object, default: () => ({}) },
})

defineEmits(['select'])

const searchQuery = ref('')
const page = ref(1)
const pageSize = ref(20)
const selectedType = ref('')

const availableTypes = computed(() => {
  const counts = new Map()
  props.concepts.forEach(c => {
    const type = c.concept_type || 'concept'
    counts.set(type, (counts.get(type) || 0) + 1)
  })
  return [...counts.entries()].map(([type, count]) => ({ type, count }))
})

const filtered = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return props.concepts.filter(c => {
    if (selectedType.value && c.concept_type !== selectedType.value) return false
    if (!query) return true
    const name = (c.name || '').toLowerCase()
    const aliases = (c.aliases || []).join(' ').toLowerCase()
    const type = (c.concept_type || '').toLowerCase()
    return name.includes(query) || aliases.includes(query) || type.includes(query)
  })
})

const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))

const paginated = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filtered.value.slice(start, start + pageSize.value)
})

watch(() => props.concepts, () => { page.value = 1 })
watch(searchQuery, () => { page.value = 1 })
watch(pageSize, () => { page.value = 1 })
watch(selectedType, () => { page.value = 1 })

function filter() { /* 搜索按钮触发，逻辑由 computed 自动处理 */ }

function typeLabel(type) {
  const map = {
    'requirement': '需求',
    'sub_requirement': '子需求',
    'technology': '技术',
    'sub_technology': '子技术',
    'concept': '概念',
  }
  return props.typeLabels[type] || map[type] || type
}

function relationLabel(relation) {
  const map = {
    'DEFINES': '定义了',
    'HAS_LAW': '阐述了',
    'APPLIES_TO': '应用于',
    'EXTENDS': '扩展了',
  }
  return props.relationLabels[relation] || map[relation] || relation || '—'
}

function colorFor(type) {
  return props.typeColors[type] || props.typeColors.concept || '#237A45'
}
</script>

<style scoped>
.concept-table-wrapper {
  background: var(--bg-card, #fff);
  padding: 20px 24px 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.table-header h3 {
  margin: 0;
  font-size: var(--font-size-md);
  color: var(--text-primary, #2c3e50);
}

.table-header p {
  margin: 4px 0 0;
  color: var(--text-muted, #7f8c8d);
  font-size: var(--font-size-xs);
}

.table-count {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
}

.concept-toolbar {
  display: flex;
  gap: 12px;
  padding: 10px 0;
  align-items: center;
  flex-wrap: wrap;
}

.type-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 0 0 14px;
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 5px 10px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 6px;
  background: var(--bg-card, #fff);
  color: var(--text-secondary, #555);
  font-size: var(--font-size-xs);
  cursor: pointer;
}

.filter-chip:hover,
.filter-chip.active {
  border-color: var(--accent-primary, #3498db);
  background: var(--bg-active, #ecf0f1);
  color: var(--text-primary, #2c3e50);
}

.filter-chip:focus-visible,
.concept-table tbody tr:focus-visible {
  outline: 2px solid var(--accent-primary, #3498db);
  outline-offset: -2px;
}

.filter-dot {
  width: 9px;
  height: 9px;
  border-radius: 3px;
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.search-input {
  padding: 6px 10px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 4px;
  font-size: var(--font-size-sm);
  width: 180px;
}

.stats {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  white-space: nowrap;
}

.table-scroll {
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
}

.concept-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-xs);
}

.concept-table thead {
  position: sticky;
  top: 0;
  background: var(--bg-active, #ecf0f1);
}

.concept-table th {
  text-align: left;
  padding: 8px 10px;
  font-weight: 600;
  color: var(--text-muted, #7f8c8d);
  border-bottom: 2px solid var(--border-color, #e0e0e0);
  white-space: nowrap;
}

.concept-table td {
  padding: 10px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
  vertical-align: top;
}

.concept-table tbody tr:hover {
  background: var(--bg-hover, #f8f9fa);
  cursor: pointer;
}

.name-cell {
  font-weight: 600;
  color: var(--text-primary, #2c3e50);
  max-width: 150px;
  word-break: break-all;
}

.description-cell {
  min-width: 220px;
  max-width: 420px;
  color: var(--text-secondary, #555);
  line-height: 1.45;
}

.alias-cell { max-width: 200px; }

.alias-tags {
  font-size: 10px;
  color: var(--text-muted, #7f8c8d);
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.type-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  display: inline-block;
  color: #fff;
  font-weight: 600;
  white-space: nowrap;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--text-muted, #7f8c8d);
}

.empty-state strong {
  color: var(--text-primary, #2c3e50);
  font-size: var(--font-size-md);
}

.pagination {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  justify-content: center;
  border-top: 1px solid var(--border-color, #e0e0e0);
  background: var(--bg-hover, #f8f9fa);
}

.page-info {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
}

.page-size-select {
  padding: 4px 8px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 4px;
  font-size: var(--font-size-xs);
  background: var(--bg-card, #fff);
  color: var(--text-primary, #2c3e50);
  cursor: pointer;
}

.btn {
  padding: 6px 12px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 4px;
  background: var(--bg-card, #fff);
  color: var(--text-primary, #2c3e50);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all 0.2s;
}

.btn:hover { background: var(--bg-hover, #f0f0f0); }

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-sm {
  padding: 4px 10px;
  font-size: var(--font-size-xs);
}

@media (max-width: 900px) {
  .concept-table-wrapper { padding: 16px 12px 12px; }
  .table-header { align-items: flex-start; }
  .description-cell { min-width: 180px; }
}
</style>
