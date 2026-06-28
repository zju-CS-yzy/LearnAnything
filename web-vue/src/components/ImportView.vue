<template>
  <div class="import-view">
    <header class="view-header">
      <div class="header-title">
        <span class="header-icon">📚</span>
        <span>导入材料</span>
      </div>
      <div class="header-subject">
        <span class="tag">{{ currentSubjectName }}</span>
      </div>
    </header>

    <div class="view-content">
      <div class="import-tabs">
        <div
          class="import-tab"
          :class="{ active: importMode === 'text' }"
          @click="importMode = 'text'"
        >文本导入</div>
        <div
          class="import-tab"
          :class="{ active: importMode === 'file' }"
          @click="importMode = 'file'"
        >文件上传</div>
        <div
          class="import-tab"
          :class="{ active: importMode === 'raw' }"
          @click="importMode = 'raw'"
        >原始资料</div>
      </div>

      <!-- 文本导入 -->
      <div v-if="importMode === 'text'" class="import-panel card">
        <div class="form-group">
          <label>当前学科</label>
          <div class="subject-display">{{ currentSubjectName }} ({{ currentSubject }})</div>
          <div class="hint">文本将导入到当前选中学科的知识库</div>
        </div>
        <div class="form-group">
          <label>文本内容</label>
          <textarea
            v-model="textContent"
            placeholder="粘贴要导入的学习材料..."
            rows="12"
          ></textarea>
        </div>
        <button class="btn btn-primary" :disabled="isLoading" @click="importText">
          <span v-if="isLoading" class="spinner"></span>
          <span v-else>导入文本</span>
        </button>
      </div>

      <!-- 文件上传 -->
      <div v-if="importMode === 'file'" class="import-panel card">
        <div class="form-group">
          <label>当前学科</label>
          <div class="subject-display">{{ currentSubjectName }} ({{ currentSubject }})</div>
          <div class="hint">文件将保存到该学科的原始资料文件夹，并导入知识库</div>
        </div>
        <div class="form-group">
          <label>选择文件</label>
          <div
            class="upload-zone"
            :class="{ 'drag-over': isDragOver }"
            @dragover.prevent="isDragOver = true"
            @dragleave.prevent="isDragOver = false"
            @drop.prevent="handleDrop"
            @click="fileInputRef?.click()"
          >
            <div class="upload-icon">📁</div>
            <div class="upload-text">拖拽文件到此处，或点击上传</div>
            <div class="upload-hint">支持 .txt, .md, .pdf, .png, .jpg</div>
            <input
              ref="fileInputRef"
              type="file"
              style="display: none"
              accept=".txt,.md,.pdf,.png,.jpg,.jpeg"
              @change="handleFileChange"
            />
          </div>
          <div v-if="selectedFile" class="selected-file">
            <span>📄 {{ selectedFile.name }} ({{ formatSize(selectedFile.size) }})</span>
            <button class="btn btn-sm btn-secondary" @click.stop="selectedFile = null">移除</button>
          </div>
        </div>
        <button class="btn btn-primary" :disabled="isLoading || !selectedFile" @click="uploadFile">
          <span v-if="isLoading" class="spinner"></span>
          <span v-else>开始上传</span>
        </button>
      </div>

      <!-- 原始资料管理 -->
      <div v-if="importMode === 'raw'" class="import-panel card">
        <div class="form-group">
          <label>当前学科</label>
          <div class="subject-display">{{ currentSubjectName }} ({{ currentSubject }})</div>
        </div>
        <div class="raw-files-section">
          <div class="section-title">📂 原始资料列表</div>
          <div v-if="rawFiles.length === 0" class="empty-hint">暂无原始资料，请先上传文件</div>
          <div v-else class="raw-files-list">
            <div v-for="f in rawFiles" :key="f.name" class="raw-file-item">
              <span class="file-icon">📄</span>
              <span class="file-name">{{ f.name }}</span>
              <span class="file-size">{{ formatSize(f.size) }}</span>
              <span class="file-time">{{ formatTime(f.modified) }}</span>
            </div>
          </div>
          <button class="btn btn-sm btn-secondary" @click="loadRawFiles" :disabled="isLoadingRaw">
            <span v-if="isLoadingRaw" class="spinner"></span>
            <span v-else">🔄 刷新</span>
          </button>
        </div>
      </div>

      <!-- 导入结果 -->
      <div v-if="importResult" class="result-card card" :class="{ success: importResult.success, error: !importResult.success }">
        <div class="result-title">
          <span v-if="importResult.success">✅ 导入成功</span>
          <span v-else>❌ 导入失败</span>
        </div>
        <div class="result-message">{{ importResult.message }}</div>
        <div v-if="importResult.chunks_added" class="result-stats">
          <span class="stat-item">新增片段：{{ importResult.chunks_added }}</span>
          <span class="stat-item">总文档数：{{ importResult.total_documents }}</span>
        </div>
      </div>

      <!-- 知识库统计 -->
      <div class="stats-section card">
        <div class="stats-title">📊 知识库统计</div>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-value">{{ subjectStats.document_count || 0 }}</div>
            <div class="stat-label">文档片段</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ subjectStats.raw_files_count || 0 }}</div>
            <div class="stat-label">原始资料</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ currentSubject }}</div>
            <div class="stat-label">当前学科</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, onMounted, watch } from 'vue'
import { apiImportText, apiSubjectStats } from '../composables/useApi.js'

// 全局学科状态
const subjectState = inject('subjectState')
const currentSubject = computed(() => subjectState.currentSubject.value)
const currentSubjectName = computed(() => {
  const sub = subjectState.subjects.value.find(s => s.id === currentSubject.value)
  return sub?.name || currentSubject.value
})

const importMode = ref('text')
const textContent = ref('')
const isLoading = ref(false)
const isLoadingRaw = ref(false)
const importResult = ref(null)

const fileInputRef = ref(null)
const selectedFile = ref(null)
const isDragOver = ref(false)
const rawFiles = ref([])

const subjectStats = ref({})

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString()
}

function handleFileChange(e) {
  const file = e.target.files[0]
  if (file) selectedFile.value = file
}

function handleDrop(e) {
  isDragOver.value = false
  const file = e.dataTransfer.files[0]
  if (file) selectedFile.value = file
}

async function importText() {
  if (!textContent.value.trim()) return
  isLoading.value = true
  importResult.value = null

  try {
    const result = await apiImportText(textContent.value, currentSubject.value)
    importResult.value = { ...result, success: true }
    textContent.value = ''
    await loadStats()
  } catch (e) {
    importResult.value = { success: false, message: e.message }
  } finally {
    isLoading.value = false
  }
}

async function uploadFile() {
  if (!selectedFile.value) return
  isLoading.value = true
  importResult.value = null

  const formData = new FormData()
  formData.append('subject', currentSubject.value)
  formData.append('file', selectedFile.value)

  try {
    const resp = await fetch(`${window.location.origin}/api/import/file`, {
      method: 'POST',
      body: formData,
    })
    const result = await resp.json()
    importResult.value = { ...result, success: resp.ok }
    if (resp.ok) {
      selectedFile.value = null
      await loadStats()
      await loadRawFiles()
    }
  } catch (e) {
    importResult.value = { success: false, message: e.message }
  } finally {
    isLoading.value = false
  }
}

async function loadStats() {
  try {
    const stats = await apiSubjectStats(currentSubject.value)
    subjectStats.value = stats
  } catch (e) {
    subjectStats.value = {}
  }
}

async function loadRawFiles() {
  isLoadingRaw.value = true
  try {
    const resp = await fetch(`${window.location.origin}/api/subjects/${currentSubject.value}/raw-files`)
    if (resp.ok) {
      const result = await resp.json()
      rawFiles.value = result.files || []
    }
  } catch (e) {
    console.error('加载原始资料失败:', e)
  } finally {
    isLoadingRaw.value = false
  }
}

// 学科切换时刷新
watch(currentSubject, () => {
  loadStats()
  if (importMode.value === 'raw') {
    loadRawFiles()
  }
})

onMounted(() => {
  loadStats()
})
</script>

<style scoped>
.import-view {
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
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-subject .tag {
  background: var(--bg-active);
  color: var(--accent-primary);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 12px;
}

.view-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  min-height: 0;
}

.import-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  max-width: 800px;
  margin-left: auto;
  margin-right: auto;
}

.import-tab {
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  color: var(--text-secondary);
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  transition: all var(--transition-fast);
}

.import-tab:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.import-tab.active {
  background: var(--accent-primary);
  color: white;
  border-color: var(--accent-primary);
}

.import-panel {
  max-width: 800px;
  margin: 0 auto 20px;
}

.subject-display {
  padding: 8px 12px;
  background: var(--bg-active);
  border-radius: var(--radius-sm);
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

.hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}

/* 上传区域 */
.upload-zone {
  border: 2px dashed var(--border-color);
  border-radius: var(--radius-md);
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: all var(--transition-fast);
  background: var(--bg-input);
}

.upload-zone:hover,
.upload-zone.drag-over {
  border-color: var(--accent-primary);
  background: var(--bg-hover);
}

.upload-icon { font-size: 40px; margin-bottom: 12px; }
.upload-text { font-size: 15px; color: var(--text-primary); margin-bottom: 6px; }
.upload-hint { font-size: 12px; color: var(--text-muted); }

.selected-file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--bg-active);
  border-radius: var(--radius-sm);
  margin-top: 10px;
  font-size: 13px;
}

/* 原始资料 */
.raw-files-section { margin-top: 16px; }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-primary); }
.empty-hint { font-size: 13px; color: var(--text-muted); padding: 20px; text-align: center; }

.raw-files-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.raw-file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--bg-input);
  border-radius: var(--radius-sm);
  font-size: 13px;
}

.file-icon { font-size: 16px; }
.file-name { flex: 1; color: var(--text-primary); }
.file-size { color: var(--text-muted); }
.file-time { color: var(--text-muted); font-size: 11px; }

/* 结果卡片 */
.result-card {
  max-width: 800px;
  margin: 0 auto 20px;
}
.result-card.success { border-left: 3px solid var(--success); }
.result-card.error { border-left: 3px solid var(--error); }

.result-title { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.result-message { font-size: 14px; color: var(--text-secondary); line-height: 1.6; }
.result-stats { display: flex; gap: 16px; margin-top: 10px; font-size: 13px; color: var(--text-muted); }

/* 统计区域 */
.stats-section { max-width: 800px; margin: 0 auto; }
.stats-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--text-primary); }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }

.stat-card {
  background: var(--bg-input);
  border-radius: var(--radius-sm);
  padding: 16px;
  text-align: center;
  border: 1px solid var(--border-color);
}

.stat-value { font-size: 24px; font-weight: 700; color: var(--accent-primary); margin-bottom: 4px; }
.stat-label { font-size: 12px; color: var(--text-muted); }
</style>
