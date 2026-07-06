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

        <div class="info-section">
          <div class="info-label">内容预览</div>
          <div class="info-text">{{ node.text || node.description || '（暂无内容）' }}</div>
        </div>

        <!-- 概念节点专属 -->
        <div v-if="node.description && !node.text" class="info-section">
          <div class="info-label">概念描述</div>
          <div class="info-text">{{ node.description }}</div>
        </div>

        <div v-if="node.parent_hint" class="info-section">
          <div class="info-label">父级关联</div>
          <div class="info-text">{{ node.parent_hint }}</div>
        </div>

        <div v-if="node.source_chunks" class="info-section">
          <div class="info-label">来源 Chunk</div>
          <div class="info-text mono">{{ node.source_chunks }}</div>
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
          <button class="btn btn-sm btn-primary" @click="$emit('expand')">🔍 展开邻居</button>
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

defineProps({
  node: { type: Object, default: null },
  concepts: { type: Array, default: () => [] },
  conceptsLoading: { type: Boolean, default: false },
  isExtracting: { type: Boolean, default: false },
  isChunkNode: { type: Boolean, default: true },
  links: { type: Array, default: () => [] },
})

defineEmits(['close', 'extract', 'expand', 'focus'])

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
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.info-header h3 {
  margin: 0;
  font-size: var(--font-size-md);
  color: var(--text-primary, #2c3e50);
}

.info-section {
  margin-bottom: 14px;
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

/* 概念分解 */
.concept-section {
  border-top: 1px dashed var(--border-color, #e0e0e0);
  padding-top: 12px;
}

.concept-label {
  display: flex;
  align-items: center;
  gap: 8px;
}

.concept-actions { margin-bottom: 10px; }

.concept-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.concept-item {
  padding: 10px 12px;
  border-radius: 6px;
  border-left: 3px solid #3498db;
  background: var(--bg-hover, #f8f9fa);
  transition: all 0.2s ease;
}

.concept-item:hover {
  background: var(--bg-active, #ecf0f1);
  transform: translateX(2px);
}

.concept-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.concept-name {
  font-weight: 600;
  font-size: var(--font-size-sm);
  color: var(--text-primary, #2c3e50);
}

.concept-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  background: #f0f0f0;
  color: #666;
  flex-shrink: 0;
}

.concept-relation { margin-bottom: 4px; }

.relation-tag {
  font-size: 11px;
  color: var(--text-muted, #7f8c8d);
  font-style: italic;
}

.concept-desc {
  font-size: 12px;
  color: var(--text-secondary, #555);
  line-height: 1.4;
  margin-top: 4px;
}

.concept-empty {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  padding: 8px 0;
  text-align: center;
  font-style: italic;
}

/* 语义关联 */
.concept-links {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.concept-link-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: var(--bg-elevated, #f8f9fa);
  border-radius: 4px;
  font-size: var(--font-size-xs);
}

.link-direction {
  font-weight: 700;
  color: var(--text-secondary, #666);
}

.link-type {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
}

.link-type.link-solution {
  background: #e67e22;
  color: #fff;
}

.link-type.link-depends_on {
  background: #9b59b6;
  color: #fff;
}

.link-target {
  color: var(--text-primary, #2c3e50);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spinner-inline {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(0, 0, 0, 0.1);
  border-top-color: var(--accent-primary, #3498db);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
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

.btn:hover {
  background: var(--bg-hover, #f0f0f0);
}

.btn-primary {
  background: var(--accent-primary, #3498db);
  color: #fff;
  border-color: var(--accent-primary, #3498db);
}

.btn-primary:hover {
  background: #2980b9;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-sm {
  padding: 4px 10px;
  font-size: var(--font-size-xs);
}

.btn-icon {
  background: none;
  border: none;
  font-size: var(--font-size-md);
  cursor: pointer;
  color: var(--text-muted, #7f8c8d);
  padding: 4px;
}

.btn-icon:hover {
  color: var(--text-primary, #2c3e50);
}
</style>
