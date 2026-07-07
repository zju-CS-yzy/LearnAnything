<template>
  <div class="info-panel" :class="{ open: !!node }">
    <div v-if="node" class="info-content">
      <div class="info-header">
        <h3>📄 节点详情</h3>
        <button class="btn-icon" @click="$emit('close')">✕</button>
      </div>

      <div class="info-body">
        <!-- 基本信息 -->
        <div class="info-section">
          <div class="info-label">ID</div>
          <div class="info-value mono">{{ node.id }}</div>
        </div>

        <!-- 来源和页码（仅 chunk 节点显示） -->
        <div v-if="isChunkNode" class="info-section">
          <div class="info-label">来源</div>
          <div class="info-value">{{ node.source || '-' }}</div>
        </div>

        <div v-if="isChunkNode" class="info-section">
          <div class="info-label">页码</div>
          <div class="info-value">{{ node.page_number || '-' }}</div>
        </div>

        <!-- 概念节点标识（非 chunk 节点显示） -->
        <div v-if="!isChunkNode" class="info-section">
          <div class="info-label">节点类型</div>
          <div class="info-value">
            <span class="type-badge" :class="'type-' + (node.type || 'concept')">{{ typeLabel(node.type) }}</span>
          </div>
        </div>

        <!-- 概念描述 -->
        <div v-if="node.description" class="info-section">
          <div class="info-label">概念描述</div>
          <div class="info-text">{{ node.description }}</div>
        </div>

        <div v-if="node.parent_hint" class="info-section">
          <div class="info-label">父级关联</div>
          <div class="info-text">{{ node.parent_hint }}</div>
        </div>

        <!-- 来源引用（人类可读） -->
        <div v-if="sourceRefsArray.length > 0" class="info-section">
          <div class="info-label">来源引用 ({{ sourceRefsArray.length }} 个)</div>
          <div class="source-ref-list">
            <div
              v-for="(ref, idx) in sourceRefsArray"
              :key="idx"
              class="source-ref-item"
            >
              <span class="source-ref-num">{{ idx + 1 }}.</span>
              <span class="source-ref-text">{{ ref }}</span>
            </div>
          </div>
        </div>

        <!-- 来源 Chunk ID（技术参考，折叠显示） -->
        <div v-if="sourceChunksArray.length > 0" class="info-section">
          <details class="source-chunk-details">
            <summary class="source-chunk-summary">来源 Chunk ID ({{ sourceChunksArray.length }} 个)</summary>
            <div class="source-chunk-list">
              <span
                v-for="chunk in sourceChunksArray"
                :key="chunk"
                class="source-chunk-tag"
                @click="$emit('navigate-to-chunk', chunk)"
              >{{ chunk }}</span>
            </div>
          </details>
        </div>

        <!-- 概念分解（仅 chunk 节点） -->
        <div v-if="isChunkNode" class="info-section concept-section">
          <div class="info-label concept-label">
            <span>🧩 概念分解</span>
            <span v-if="conceptsLoading" class="spinner-inline"></span>
          </div>

          <div v-if="concepts.length === 0 && !conceptsLoading && !isExtracting" class="concept-actions">
            <button class="btn btn-sm btn-primary" @click="$emit('extract')" :disabled="isExtracting">
              <span v-if="isExtracting">⏳ 提取中...</span>
              <span v-else>🔬 提取概念</span>
            </button>
          </div>

          <div v-if="concepts.length > 0" class="concept-list">
            <div
              v-for="c in concepts"
              :key="c.id"
              class="concept-item"
              :class="'relation-' + (c.relation || '').toLowerCase()"
            >
              <div class="concept-header">
                <span class="concept-name">{{ c.name }}</span>
                <span class="concept-badge" :class="'type-' + c.type">{{ typeLabel(c.type) }}</span>
              </div>
              <div class="concept-relation">
                <span class="relation-tag">{{ relationLabel(c.relation) }}</span>
              </div>
              <div v-if="c.description" class="concept-desc">{{ c.description }}</div>
            </div>
          </div>

          <div v-if="concepts.length === 0 && !conceptsLoading && !isExtracting" class="concept-empty">
            尚未提取概念。点击上方按钮进行语义分析。
          </div>
        </div>

        <!-- 语义关联（仅概念节点） -->
        <div v-if="!isChunkNode && links.length > 0" class="info-section concept-section">
          <div class="info-label concept-label">
            <span>🔗 语义关联</span>
          </div>
          <div class="concept-links">
            <div v-for="(link, idx) in links" :key="idx" class="concept-link-item">
              <span class="link-direction">{{ link.direction === 'out' ? '→' : '←' }}</span>
              <span class="link-type" :class="'link-' + link.type.toLowerCase()">{{ link.type }}</span>
              <span class="link-target">{{ link.targetName }}</span>
            </div>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="info-actions">
          <button class="btn btn-sm" @click="$emit('focus')">🎯 聚焦</button>
        </div>
      </div>
    </div>

    <div v-else class="info-empty">
      <div class="empty-icon">👆</div>
      <div class="empty-text">点击节点查看详情</div>
      <div class="empty-hint">双击节点展开子树</div>
    </div>
  </div>
</template>

<script setup>
/**
 * NodeDetailPanel — 节点详情面板
 * 显示选中节点的基本信息、概念分解、语义关联
 */

import { computed } from 'vue'

const props = defineProps({
  node: { type: Object, default: null },
  concepts: { type: Array, default: () => [] },
  conceptsLoading: { type: Boolean, default: false },
  isExtracting: { type: Boolean, default: false },
  isChunkNode: { type: Boolean, default: true },
  links: { type: Array, default: () => [] },
})

defineEmits(['close', 'extract', 'expand', 'focus', 'navigate-to-chunk'])

// 解析 source_refs（人类可读的来源引用字符串数组）
const sourceRefsArray = computed(() => {
  const refs = props.node?.source_refs
  if (!refs) return []
  if (Array.isArray(refs)) return refs
  // 尝试 JSON 解析
  try {
    const parsed = JSON.parse(refs)
    if (Array.isArray(parsed)) return parsed
  } catch { /* ignore */ }
  return []
})

// 解析 source_chunks（可能是数组或字符串）
const sourceChunksArray = computed(() => {
  const sc = props.node?.source_chunks
  if (!sc) return []
  if (Array.isArray(sc)) return sc
  // 尝试 JSON 解析
  try {
    const parsed = JSON.parse(sc)
    if (Array.isArray(parsed)) return parsed
  } catch { /* ignore */ }
  // 按逗号分隔
  return String(sc).split(',').map(s => s.trim()).filter(Boolean)
})

function typeLabel(type) {
  const map = {
    'definition': '定义',
    'law': '规律',
    'application': '应用',
    'extension': '扩展',
    'requirement': '需求',
    'sub_requirement': '子需求',
    'technology': '技术',
    'sub_technology': '子技术',
    'concept': '概念',
    'child': '知识片段',
    'parent': '父节点',
  }
  return map[type] || type || '概念'
}

function relationLabel(relation) {
  const map = {
    'DEFINES': '定义了',
    'HAS_LAW': '阐述了',
    'APPLIES_TO': '应用于',
    'EXTENDS': '扩展了',
  }
  return map[relation] || relation
}
</script>

<style scoped>
.info-panel {
  width: 300px;
  border-left: 1px solid var(--border-color, #e0e0e0);
  background: var(--bg-card, #fff);
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
}

.info-panel:not(.open) {
  width: 200px;
}

.info-content {
  padding: 16px;
  overflow-y: auto;
  height: 100%;
}

.info-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.info-header h3 {
  font-size: var(--font-size-md);
  margin: 0;
  color: var(--text-primary, #2c3e50);
}

.info-section {
  margin-bottom: 12px;
}

.info-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.info-value {
  font-size: var(--font-size-sm);
  color: var(--text-primary, #2c3e50);
  word-break: break-all;
}

.info-value.mono {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
}

.info-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary, #555);
  max-height: 200px;
  overflow-y: auto;
  padding: 8px;
  background: var(--bg-hover, #f8f9fa);
  border-radius: 4px;
}

.source-chunk-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.source-chunk-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--font-size-xs);
  background: var(--bg-hover, #f0f0f0);
  color: var(--text-secondary, #555);
  cursor: pointer;
  transition: all 0.2s;
}

.source-chunk-tag:hover {
  background: var(--primary-color, #3498db);
  color: #fff;
}

/* 来源引用（人类可读） */
.source-ref-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 4px;
}

.source-ref-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 6px 10px;
  background: var(--bg-hover, #f8f9fa);
  border-radius: 4px;
  font-size: var(--font-size-sm);
  line-height: 1.5;
}

.source-ref-num {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--primary-color, #3498db);
  font-size: var(--font-size-xs);
}

.source-ref-text {
  color: var(--text-secondary, #555);
  word-break: break-all;
}

/* Chunk ID 折叠详情 */
.source-chunk-details {
  margin-top: 4px;
}

.source-chunk-summary {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  cursor: pointer;
  user-select: none;
}

.source-chunk-summary:hover {
  color: var(--primary-color, #3498db);
}

.info-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color, #e0e0e0);
}

.info-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 24px;
  text-align: center;
  color: var(--text-muted, #7f8c8d);
}

.empty-icon { font-size: 32px; margin-bottom: 8px; }
.empty-text { font-size: var(--font-size-md); font-weight: 600; margin-bottom: 4px; }
.empty-hint { font-size: var(--font-size-xs); }

.type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--font-size-xs);
  font-weight: 600;
}

.type-definition { background: #e8f4f8; color: #2980b9; }
.type-law { background: #f0f8e8; color: #27ae60; }
.type-application { background: #f8f0e8; color: #e67e22; }
.type-extension { background: #f8e8f0; color: #8e44ad; }
.type-requirement { background: #ffe8e8; color: #c0392b; }
.type-sub_requirement { background: #fff0e8; color: #d35400; }
.type-technology { background: #e8f0ff; color: #2980b9; }
.type-sub_technology { background: #e8f8ff; color: #16a085; }
.type-concept { background: #f0f0f0; color: #7f8c8d; }

/* 概念分解 */
.concept-section { margin-top: 16px; }
.concept-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.concept-actions { margin-top: 8px; }
.concept-empty {
  font-size: var(--font-size-sm);
  color: var(--text-muted, #7f8c8d);
  padding: 12px;
  background: var(--bg-hover, #f8f9fa);
  border-radius: 4px;
  text-align: center;
}

.concept-list { margin-top: 8px; }
.concept-item {
  padding: 8px 12px;
  margin-bottom: 6px;
  border-radius: 6px;
  background: var(--bg-hover, #f8f9fa);
  border-left: 3px solid #ccc;
}
.concept-item.relation-defines { border-left-color: #3498db; }
.concept-item.relation-has_law { border-left-color: #27ae60; }
.concept-item.relation-applies_to { border-left-color: #e67e22; }
.concept-item.relation-extends { border-left-color: #8e44ad; }

.concept-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2px;
}
.concept-name { font-weight: 600; font-size: var(--font-size-sm); }
.concept-badge {
  font-size: var(--font-size-xs);
  padding: 1px 6px;
  border-radius: 3px;
  background: #e0e0e0;
}
.concept-relation { margin-top: 2px; }
.relation-tag {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
}
.concept-desc {
  font-size: var(--font-size-xs);
  color: var(--text-secondary, #555);
  margin-top: 4px;
  line-height: 1.4;
}

/* 语义关联 */
.concept-links { margin-top: 8px; }
.concept-link-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: var(--font-size-sm);
}
.link-direction { color: var(--text-muted, #7f8c8d); font-weight: 600; }
.link-type {
  font-size: var(--font-size-xs);
  padding: 1px 6px;
  border-radius: 3px;
  background: #e0e0e0;
}
.link-solution { background: #e8f4f8; color: #2980b9; }
.link-depends_on { background: #ffe8e8; color: #c0392b; }
.link-target { color: var(--text-secondary, #555); }
</style>
