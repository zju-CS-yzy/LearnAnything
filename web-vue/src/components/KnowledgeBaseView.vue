<template>
  <div class="kb-view">
    <header class="view-header">
      <div class="header-title">
        <span class="header-icon">🗂️</span>
        <span>知识库</span>
      </div>
      <div class="header-subject">
        <span class="tag">{{ currentSubjectName }}</span>
      </div>
    </header>

    <div class="view-content">
      <!-- 统计卡片 -->
      <div class="stats-section card">
        <div class="stats-title">📊 知识库统计</div>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-value">{{ childChunksCount }}</div>
            <div class="stat-label">知识片段</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ rawFilesCount }}</div>
            <div class="stat-label">原始资料</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ parentChunksCount }}</div>
            <div class="stat-label">来源页数</div>
          </div>
        </div>
      </div>

      <!-- 知识片段列表 -->
      <div class="chunks-section card">
        <div class="section-header">
          <div class="section-title">📚 知识片段列表</div>
          <button class="btn btn-sm btn-secondary" @click="loadChunks" :disabled="isLoading">
            <span v-if="isLoading" class="spinner"></span>
            <span v-else>🔄 刷新</span>
          </button>
        </div>

        <div v-if="isLoading && chunks.length === 0" class="loading-hint">加载中...</div>

        <div v-else-if="chunks.length === 0" class="empty-hint">暂无知识片段，请先导入材料</div>

        <div v-else class="chunks-table-wrapper">
          <table class="chunks-table">
            <thead>
              <tr>
                <th class="col-id">ID</th>
                <th class="col-source">来源</th>
                <th class="col-page">页码</th>
                <th class="col-context">上下文路径</th>
                <th class="col-text">内容</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="chunk in chunks" :key="chunk.id">
                <td class="col-id">{{ chunk.id }}</td>
                <td class="col-source">
                  <span
                    class="source-link"
                    :title="getSourceTooltip(chunk)"
                    @click="showSourceDetail(chunk)"
                  >{{ chunk.metadata?.source || '—' }}</span>
                </td>
                <td class="col-page">{{ formatPageNumbers(chunk.metadata) }}</td>
                <td class="col-context">
                  <span class="context-path">{{ chunk.metadata?.heading_path || '—' }}</span>
                </td>
                <td class="col-text">
                  <div class="chunk-text">{{ chunk.text }}</div>
                </td>
              </tr>
            </tbody>
          </table>

          <div class="pagination" v-if="totalChunks > limit">
            <button class="btn btn-sm btn-secondary" :disabled="offset === 0" @click="prevPage">
              ← 上一页
            </button>
            <span class="page-info">{{ offset + 1 }} - {{ Math.min(offset + chunks.length, totalChunks) }} / {{ totalChunks }}</span>
            <button class="btn btn-sm btn-secondary" :disabled="offset + limit >= totalChunks" @click="nextPage">
              下一页 →
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 来源详情弹窗 -->
    <div v-if="sourceDetail" class="modal-overlay" @click="sourceDetail = null">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>📄 来源详情</h3>
          <button class="btn-icon" @click="sourceDetail = null">✕</button>
        </div>
        <div class="modal-body">
          <div class="detail-item">
            <div class="detail-label">原始文件名</div>
            <div class="detail-value">{{ sourceDetail.source }}</div>
          </div>
          <div class="detail-item">
            <div class="detail-label">学科</div>
            <div class="detail-value">{{ sourceDetail.subject }}</div>
          </div>
          <div class="detail-item">
            <div class="detail-label">页码</div>
            <div class="detail-value">{{ sourceDetail.page_number }}</div>
          </div>
          <div class="detail-item">
            <div class="detail-label">上下文路径</div>
            <div class="detail-value">{{ sourceDetail.heading_path }}</div>
          </div>
          <div v-if="sourceDetail.parent_ids && sourceDetail.parent_ids.length > 0" class="detail-item">
            <div class="detail-label">关联页 ID</div>
            <div class="detail-value path">{{ sourceDetail.parent_ids.join(', ') }}</div>
          </div>
          <div v-if="sourceDetail.raw_path" class="detail-item">
            <div class="detail-label">知识库存储路径</div>
            <div class="detail-value path">{{ sourceDetail.raw_path }}</div>
          </div>
          <div v-if="sourceDetail.file_path" class="detail-item">
            <div class="detail-label">处理时临时路径</div>
            <div class="detail-value path">{{ sourceDetail.file_path }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, onMounted, watch } from 'vue'

// 全局学科状态
const subjectState = inject('subjectState')
const currentSubject = computed(() => subjectState.currentSubject.value)
const currentSubjectName = computed(() => {
  const sub = subjectState.subjects.value.find(s => s.id === currentSubject.value)
  return sub?.name || currentSubject.value
})

const chunks = ref([])
const totalChunks = ref(0)
const childChunksCount = ref(0)
const parentChunksCount = ref(0)
const rawFilesCount = ref(0)
const isLoading = ref(false)
const limit = ref(50)
const offset = ref(0)
const sourceDetail = ref(null)

function formatPageNumbers(metadata) {
  if (!metadata) return '—'
  // child chunk 使用 page_numbers (数组)
  const pages = metadata.page_numbers
  if (Array.isArray(pages)) {
    if (pages.length === 1) return pages[0]
    return pages.join(', ')
  }
  // parent chunk 使用 page_number (单值)
  if (metadata.page_number !== undefined) return metadata.page_number
  return '—'
}

function getSourceTooltip(chunk) {
  const meta = chunk.metadata || {}
  const pages = formatPageNumbers(meta)
  return `点击查看详情\n文件名: ${meta.source || '—'}\n学科: ${meta.subject || '—'}\n页码: ${pages}`
}

function showSourceDetail(chunk) {
  const meta = chunk.metadata || {}
  sourceDetail.value = {
    source: meta.source || '—',
    subject: meta.subject || '—',
    page_number: formatPageNumbers(meta),
    raw_path: meta.raw_path,
    file_path: meta.file_path,
    heading_path: meta.heading_path || '—',
    parent_ids: meta.parent_ids || [],
  }
}

async function loadChunks() {
  isLoading.value = true
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-base/${currentSubject.value}/chunks?limit=${limit.value}&offset=${offset.value}`
    )
    if (resp.ok) {
      const data = await resp.json()
      chunks.value = data.chunks || []
      totalChunks.value = data.total || 0
    }
  } catch (e) {
    console.error('加载知识片段失败:', e)
  } finally {
    isLoading.value = false
  }
}

async function loadStats() {
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-base/${currentSubject.value}/stats`
    )
    if (resp.ok) {
      const data = await resp.json()
      childChunksCount.value = data.document_count || 0
      totalChunks.value = data.total_chunks || 0
      parentChunksCount.value = data.parent_chunks || 0
      rawFilesCount.value = data.raw_files_count || 0
    }
  } catch (e) {
    console.error('加载统计失败:', e)
  }
}

function prevPage() {
  if (offset.value >= limit.value) {
    offset.value -= limit.value
    loadChunks()
  }
}

function nextPage() {
  if (offset.value + limit.value < totalChunks.value) {
    offset.value += limit.value
    loadChunks()
  }
}

watch(currentSubject, () => {
  offset.value = 0
  loadChunks()
  loadStats()
})

onMounted(() => {
  loadChunks()
  loadStats()
})
</script>

<style scoped>
.kb-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.view-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: var(--header-height);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary);
}

.header-subject .tag {
  background: var(--bg-active);
  color: var(--accent-primary);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
}

.view-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  min-height: 0;
}

/* 统计 */
.stats-section {
  max-width: 900px;
  margin: 0 auto 20px;
}

.stats-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text-primary);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}

.stat-card {
  background: var(--bg-input);
  border-radius: var(--radius-sm);
  padding: 16px;
  text-align: center;
  border: 1px solid var(--border-color);
}

.stat-value {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--accent-primary);
  margin-bottom: 4px;
}

.stat-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

/* 知识片段列表 */
.chunks-section {
  max-width: 900px;
  margin: 0 auto;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary);
}

.loading-hint, .empty-hint {
  text-align: center;
  padding: 40px;
  color: var(--text-muted);
  font-size: var(--font-size-md);
}

.chunks-table-wrapper {
  overflow-x: auto;
}

.chunks-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.chunks-table th {
  text-align: left;
  padding: 10px 12px;
  background: var(--bg-active);
  color: var(--text-secondary);
  font-weight: 600;
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border-color);
  white-space: nowrap;
}

.chunks-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
  vertical-align: top;
}

.chunks-table tr:hover td {
  background: var(--bg-hover);
}

.col-id { width: 80px; font-family: monospace; font-size: var(--font-size-xs); color: var(--text-muted); }
.col-source { width: 140px; }
.col-page { width: 60px; text-align: center; }
.col-context { width: 140px; }
.col-text { min-width: 260px; }

.context-path {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
}

.source-link {
  color: var(--accent-primary);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.source-link:hover {
  color: var(--accent-secondary);
}

.chunk-text {
  max-height: 120px;
  overflow-y: auto;
  line-height: 1.6;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  word-break: break-word;
}

/* 分页 */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.page-info {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  margin: 0;
  font-size: var(--font-size-md);
  color: var(--text-primary);
}

.modal-body {
  padding: 20px;
}

.detail-item {
  margin-bottom: 16px;
}

.detail-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-value {
  font-size: var(--font-size-md);
  color: var(--text-primary);
  word-break: break-all;
}

.detail-value.path {
  font-family: monospace;
  font-size: var(--font-size-xs);
  background: var(--bg-input);
  padding: 8px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
}

.btn-sm {
  padding: 6px 12px;
  font-size: var(--font-size-sm);
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-color);
  border-top-color: var(--accent-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
