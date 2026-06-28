<template>
  <div class="import-view">
    <header class="view-header">
      <div class="header-title">
        <span class="header-icon">📚</span>
        <span>导入材料</span>
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
      </div>

      <!-- 文本导入 -->
      <div v-if="importMode === 'text'" class="import-panel card">
        <div class="form-group">
          <label>学科</label>
          <input v-model="subject" placeholder="generic" />
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
          <label>学科</label>
          <input v-model="subject" placeholder="generic" />
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
              accept=".txt,.md,.pdf,.png,.jpg"
              @change="handleFileChange"
            />
          </div>
          <div v-if="selectedFile" class="selected-file">
            <span>📄 {{ selectedFile.name }}</span>
            <button class="btn btn-sm btn-secondary" @click="selectedFile = null">移除</button>
          </div>
        </div>
        <button class="btn btn-primary" :disabled="isLoading || !selectedFile" @click="uploadFile">
          <span v-if="isLoading" class="spinner"></span>
          <span v-else>开始上传</span>
        </button>
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
            <div class="stat-value">{{ subjectStats.status || '—' }}</div>
            <div class="stat-label">状态</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { apiImportText, apiSubjectStats } from '../composables/useApi.js'

const importMode = ref('text')
const subject = ref('generic')
const textContent = ref('')
const isLoading = ref(false)
const importResult = ref(null)

const fileInputRef = ref(null)
const selectedFile = ref(null)
const isDragOver = ref(false)

const subjectStats = ref({})

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
    const result = await apiImportText(textContent.value, subject.value)
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
  formData.append('subject', subject.value)
  formData.append('file', selectedFile.value)

  try {
    const resp = await fetch('/api/import/file', {
      method: 'POST',
      body: formData,
    })
    const result = await resp.json()
    importResult.value = { ...result, success: resp.ok }
    if (resp.ok) selectedFile.value = null
    await loadStats()
  } catch (e) {
    importResult.value = { success: false, message: e.message }
  } finally {
    isLoading.value = false
  }
}

async function loadStats() {
  try {
    const stats = await apiSubjectStats(subject.value)
    subjectStats.value = stats
  } catch (e) {
    subjectStats.value = {}
  }
}

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

.upload-icon {
  font-size: 40px;
  margin-bottom: 12px;
}

.upload-text {
  font-size: 15px;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.upload-hint {
  font-size: 12px;
  color: var(--text-muted);
}

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

/* 结果卡片 */
.result-card {
  max-width: 800px;
  margin: 0 auto 20px;
}

.result-card.success {
  border-left: 3px solid var(--success);
}

.result-card.error {
  border-left: 3px solid var(--error);
}

.result-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}

.result-message {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.result-stats {
  display: flex;
  gap: 16px;
  margin-top: 10px;
  font-size: 13px;
  color: var(--text-muted);
}

/* 统计区域 */
.stats-section {
  max-width: 800px;
  margin: 0 auto;
}

.stats-title {
  font-size: 16px;
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
  font-size: 24px;
  font-weight: 700;
  color: var(--accent-primary);
  margin-bottom: 4px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
