<template>
  <div class="quiz-view">
    <header class="view-header">
      <div class="header-title">
        <span class="header-icon">📝</span>
        <span>出题</span>
      </div>
      <!-- LA-UI-001: 出题 / 题库列表 切换 -->
      <div class="view-toggle">
        <button
          :class="{ active: viewMode === 'generate' }"
          @click="viewMode = 'generate'"
        >生成题目</button>
        <button
          :class="{ active: viewMode === 'bank' }"
          @click="switchToBank"
        >题库列表</button>
      </div>
    </header>

    <!-- ========== 题库列表 ========== -->
    <div v-if="viewMode === 'bank'" class="view-content">
      <div class="bank-stats card" v-if="bankStats">
        <span class="stat-chip">共 {{ bankStats.total }} 题</span>
        <span class="stat-chip ok">已确认 {{ bankStats.approved }}</span>
        <span class="stat-chip pending">待确认 {{ bankStats.pending }}</span>
        <span v-for="(n, t) in bankStats.by_type" :key="t" class="stat-chip type">{{ typeLabel(t) }} {{ n }}</span>
      </div>

      <div class="bank-filter card">
        <input v-model="bankTopicFilter" placeholder="按主题筛选..." @input="loadBank(true)" />
        <select v-model="bankApprovedFilter" @change="loadBank(true)">
          <option :value="null">全部状态</option>
          <option :value="true">已确认</option>
          <option :value="false">待确认</option>
        </select>
        <button class="btn btn-secondary" @click="loadBank(true)">刷新</button>
      </div>

      <div v-if="bankLoading" class="bank-empty card">加载中…</div>
      <div v-else-if="!bankQuestions.length" class="bank-empty card">
        题库暂无题目——生成题目后勾选保存即可入库
      </div>

      <div v-else class="bank-list">
        <div v-for="q in bankQuestions" :key="q.id" class="question-item bank-item">
          <div class="question-header">
            <span class="question-type tag">{{ typeLabel(q.type) }}</span>
            <span v-if="q.bloom_level" class="bloom-tag" :class="'bloom-' + q.bloom_level">
              {{ bloomLabel(q.bloom_level) }}
            </span>
            <span v-if="q.topic" class="bank-topic">{{ q.topic }}</span>
            <span class="bank-status" :class="q.is_approved ? 'ok' : 'pending'">
              {{ q.is_approved ? '已确认' : '待确认' }}
            </span>
            <span class="bank-usage">使用 {{ q.used_count }} 次</span>
            <span class="bank-actions">
              <button v-if="!q.is_approved" class="bank-btn ok" @click="approveBank(q)">确认</button>
              <button class="bank-btn del" @click="deleteBank(q)">删除</button>
            </span>
          </div>
          <RichText class="question-text" :content="q.question" />
          <div v-if="q.options && q.options.length" class="question-options">
            <div v-for="(opt, j) in q.options" :key="j" class="option-item">
              <span class="option-label">{{ ['A', 'B', 'C', 'D', 'E', 'F'][j] || j }}</span>
              <RichText class="option-text" :content="String(opt).replace(/^[A-Fa-f][\.．、]\s*/, '')" inline :markdown="false" />
            </div>
          </div>
          <div class="question-answer">
            <span class="answer-label">答案：</span>
            <RichText class="answer-text" :content="Array.isArray(q.answer) ? q.answer.join('、') : q.answer" inline :markdown="false" />
          </div>
          <div v-if="q.explanation" class="question-explanation">
            <span class="explanation-label">解析：</span>
            <RichText class="explanation-text" :content="q.explanation" inline />
          </div>
        </div>

        <div v-if="bankQuestions.length < bankTotal" class="bank-more">
          <button class="btn btn-secondary" :disabled="bankLoading" @click="loadBank(false)">
            加载更多（{{ bankQuestions.length }} / {{ bankTotal }}）
          </button>
        </div>
      </div>
    </div>

    <!-- ========== 生成题目 ========== -->
    <div v-else class="view-content">
      <div class="quiz-form card">
        <div class="form-group">
          <label>出题主题</label>
          <input v-model="topic" placeholder="例如：RAG 技术、Transformer 机制..." />
        </div>
        <div class="form-group">
          <label>当前学科</label>
          <div class="subject-display">{{ currentSubject }}</div>
        </div>
        <div class="form-group">
          <label>题目数量</label>
          <input v-model.number="count" type="number" min="1" max="20" />
        </div>
        <button class="btn btn-primary" :disabled="isLoading" @click="generateQuiz">
          <span v-if="isLoading" class="spinner"></span>
          <span v-else>生成题目</span>
        </button>
      </div>

      <div v-if="quizResult" class="quiz-result card">
        <div class="result-header">
          <div class="result-title">{{ quizResult.topic }}</div>
          <div class="result-subtitle">{{ quizResult.subject_name }} · {{ quizResult.questions.length }} 道题</div>
        </div>

        <!-- 保存到题库操作栏 -->
        <div class="save-bar">
          <label class="checkbox-label">
            <input type="checkbox" v-model="selectAll" @change="toggleSelectAll" />
            <span>全选</span>
          </label>
          <button
            class="btn btn-secondary"
            :disabled="selectedQuestions.length === 0 || isSaving"
            @click="saveToBank"
          >
            <span v-if="isSaving" class="spinner"></span>
            <span v-else>保存 {{ selectedQuestions.length }} 题到题库</span>
          </button>
        </div>

        <div class="questions-list">
          <div
            v-for="(q, i) in quizResult.questions"
            :key="q.id"
            class="question-item"
            :class="{ selected: selectedIds.has(q.id) }"
          >
            <div class="question-header">
              <label class="checkbox-label">
                <input
                  type="checkbox"
                  :value="q.id"
                  v-model="selectedIdList"
                />
                <span class="question-number">{{ i + 1 }}</span>
              </label>
              <span class="question-type tag">{{ q.type }}</span>
              <span v-if="q.bloom_level" class="bloom-tag" :class="'bloom-' + q.bloom_level">
                {{ bloomLabel(q.bloom_level) }}
              </span>
            </div>
            <RichText class="question-text" :content="q.question" />
            <div v-if="q.options && q.options.length" class="question-options">
              <div v-for="(opt, j) in q.options" :key="j" class="option-item">
                <span class="option-label">{{ ['A', 'B', 'C', 'D', 'E', 'F'][j] || j }}</span>
                <RichText class="option-text" :content="String(opt).replace(/^[A-Fa-f][\.．、]\s*/, '')" inline :markdown="false" />
              </div>
            </div>
            <div class="question-answer">
              <span class="answer-label">答案：</span>
              <RichText class="answer-text" :content="Array.isArray(q.answer) ? q.answer.join('、') : q.answer" inline :markdown="false" />
            </div>
            <div class="question-explanation">
              <span class="explanation-label">解析：</span>
              <RichText class="explanation-text" :content="q.explanation" inline />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, watch } from 'vue'
import RichText from './common/RichText.vue'
import {
  apiQuiz, apiQuizBankSave, apiQuizBankList, apiQuizBankStats,
  apiQuizBankApprove, apiQuizBankDelete,
} from '../composables/useApi.js'

// 全局学科状态
const subjectState = inject('subjectState')
const currentSubject = computed(() => subjectState.currentSubject.value)

const topic = ref('RAG 技术')
const count = ref(5)
const isLoading = ref(false)
const isSaving = ref(false)
const quizResult = ref(null)
const selectedIdList = ref([])
const selectAll = ref(false)

// ========== LA-UI-001: 题库列表 ==========
const viewMode = ref('generate')  // generate | bank
const bankQuestions = ref([])
const bankTotal = ref(0)
const bankStats = ref(null)
const bankLoading = ref(false)
const bankTopicFilter = ref('')
const bankApprovedFilter = ref(null)
const BANK_PAGE_SIZE = 50

const typeLabels = {
  single_choice: '单选',
  multiple_choice: '多选',
  true_false: '判断',
  fill_blank: '填空',
  short_answer: '简答',
}
function typeLabel(t) {
  return typeLabels[t] || t || '题目'
}

function switchToBank() {
  viewMode.value = 'bank'
  loadBank(true)
  loadBankStats()
}

async function loadBankStats() {
  try {
    bankStats.value = await apiQuizBankStats(currentSubject.value)
  } catch (e) {
    console.warn('[QuizView] 题库统计加载失败:', e)
  }
}

async function loadBank(reset = false) {
  if (bankLoading.value) return
  bankLoading.value = true
  try {
    const offset = reset ? 0 : bankQuestions.value.length
    const res = await apiQuizBankList(
      currentSubject.value,
      bankTopicFilter.value || null,
      bankApprovedFilter.value,
      BANK_PAGE_SIZE,
      offset,
    )
    bankTotal.value = res.total || 0
    if (reset) {
      bankQuestions.value = res.questions || []
    } else {
      bankQuestions.value = [...bankQuestions.value, ...(res.questions || [])]
    }
  } catch (e) {
    console.error('[QuizView] 题库列表加载失败:', e)
  } finally {
    bankLoading.value = false
  }
}

async function approveBank(q) {
  try {
    await apiQuizBankApprove(q.id)
    q.is_approved = true
    loadBankStats()
  } catch (e) {
    alert('确认失败: ' + e.message)
  }
}

async function deleteBank(q) {
  if (!confirm(`确定删除这道题目吗？\n\n${q.question.slice(0, 50)}...`)) return
  try {
    await apiQuizBankDelete(q.id)
    bankQuestions.value = bankQuestions.value.filter(x => x.id !== q.id)
    bankTotal.value = Math.max(0, bankTotal.value - 1)
    loadBankStats()
  } catch (e) {
    alert('删除失败: ' + e.message)
  }
}

// 切换学科后如正在题库页则刷新
watch(currentSubject, () => {
  if (viewMode.value === 'bank') {
    loadBank(true)
    loadBankStats()
  }
})

const selectedIds = computed(() => new Set(selectedIdList.value))

const selectedQuestions = computed(() => {
  if (!quizResult.value) return []
  return quizResult.value.questions.filter(q => selectedIds.value.has(q.id))
})

// Bloom 认知层次标签映射
const bloomLabels = {
  remember: '记忆',
  understand: '理解',
  apply: '应用',
  analyze: '分析',
  evaluate: '评估',
  create: '创造',
}

function bloomLabel(level) {
  return bloomLabels[level] || level
}

function toggleSelectAll() {
  if (selectAll.value && quizResult.value) {
    selectedIdList.value = quizResult.value.questions.map(q => q.id)
  } else {
    selectedIdList.value = []
  }
}

async function generateQuiz() {
  if (!topic.value.trim()) return
  isLoading.value = true
  quizResult.value = null
  selectedIdList.value = []
  selectAll.value = false

  try {
    const result = await apiQuiz(topic.value, currentSubject.value, count.value)
    quizResult.value = result
  } catch (e) {
    alert('出题失败: ' + e.message)
  } finally {
    isLoading.value = false
  }
}

async function saveToBank() {
  if (selectedQuestions.value.length === 0) return
  isSaving.value = true

  try {
    const result = await apiQuizBankSave(
      selectedQuestions.value,
      currentSubject.value,
      topic.value,
      true,
    )
    // LA-UI-001: 后端去重——展示实际保存与跳过数量
    alert(result.message || `已保存 ${result.saved} 道题目到题库`)
    selectedIdList.value = []
    selectAll.value = false
  } catch (e) {
    alert('保存失败: ' + e.message)
  } finally {
    isSaving.value = false
  }
}
</script>

<style scoped>
.quiz-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.view-header {
  display: flex;
  align-items: center;
  justify-content: space-between;  /* LA-UI-001: 标题与页签切换分两端，避免挨挤 */
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

.view-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  min-height: 0;
}

.quiz-form {
  max-width: 600px;
  margin: 0 auto 24px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: var(--font-size-md);
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.form-group input {
  width: 100%;
}

.quiz-result {
  max-width: 800px;
  margin: 0 auto;
}

.result-header {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color);
}

.result-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.result-subtitle {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  margin-top: 4px;
}

.save-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 10px 14px;
  background: var(--bg-input);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: var(--font-size-md);
  color: var(--text-secondary);
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
}

.questions-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.question-item {
  padding: 16px;
  background: var(--bg-input);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  transition: border-color 0.2s;
}

.question-item.selected {
  border-color: var(--accent-primary);
  background: var(--bg-active);
}

.question-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.question-number {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-primary);
  color: white;
  border-radius: 50%;
  font-size: var(--font-size-xs);
  font-weight: 600;
}

.question-type {
  font-size: var(--font-size-xs);
}

/* Bloom 认知层次标签 */
.bloom-tag {
  margin-left: auto;
  font-size: var(--font-size-xs);
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid transparent;
}

.bloom-remember {
  background: #f0f0f0;
  color: #666;
  border-color: #ddd;
}

.bloom-understand {
  background: #e3f2fd;
  color: #1976d2;
  border-color: #bbdefb;
}

.bloom-apply {
  background: #e8f5e9;
  color: #388e3c;
  border-color: #c8e6c9;
}

.bloom-analyze {
  background: #fff3e0;
  color: #f57c00;
  border-color: #ffe0b2;
}

.bloom-evaluate {
  background: #fce4ec;
  color: #c2185b;
  border-color: #f8bbd9;
}

.bloom-create {
  background: #f3e5f5;
  color: #7b1fa2;
  border-color: #e1bee7;
}

.question-text {
  font-size: var(--font-size-md);
  line-height: 1.6;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.question-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.option-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-card);
  border-radius: var(--radius-sm);
}

.option-label {
  font-weight: 600;
  color: var(--accent-primary);
  min-width: 20px;
}

.question-answer,
.question-explanation {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-color);
}

.answer-label,
.explanation-label {
  font-weight: 600;
  color: var(--text-secondary);
}

.answer-text {
  color: var(--success);
  font-weight: 500;
}

.explanation-text {
  color: var(--text-secondary);
}

/* ========== LA-UI-001: 题库列表 ========== */
.view-toggle {
  display: flex;
  gap: 4px;
}
.view-toggle button {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  padding: 5px 14px;
  cursor: pointer;
}
.view-toggle button.active {
  background: var(--bg-active);
  color: var(--accent-primary);
  border-color: var(--accent-primary);
}

.bank-stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 14px;
  margin-bottom: 12px;
}
.stat-chip {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-hover);
  border-radius: 10px;
  padding: 2px 10px;
}
.stat-chip.ok { color: var(--success); }
.stat-chip.pending { color: #e0a35c; }
.stat-chip.type { color: var(--accent-primary); }

.bank-filter {
  display: flex;
  gap: 10px;
  padding: 10px 14px;
  margin-bottom: 12px;
  align-items: center;
}
.bank-filter input {
  flex: 1;
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  padding: 6px 10px;
}
.bank-filter select {
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  padding: 6px 10px;
}

.bank-empty {
  padding: 32px;
  text-align: center;
  color: var(--text-muted);
  font-size: var(--font-size-sm);
}

.bank-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.bank-item .question-header {
  flex-wrap: wrap;
}

.bank-topic {
  font-size: 12px;
  color: var(--text-secondary);
  border: 1px solid var(--border-light);
  border-radius: 4px;
  padding: 0 6px;
}

.bank-status {
  font-size: 12px;
  border-radius: 4px;
  padding: 0 6px;
}
.bank-status.ok { color: var(--success); border: 1px solid var(--success); }
.bank-status.pending { color: #e0a35c; border: 1px solid #e0a35c; }

.bank-usage {
  font-size: 11px;
  color: var(--text-muted);
}

.bank-actions {
  margin-left: auto;
  display: flex;
  gap: 6px;
}
.bank-btn {
  background: none;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  font-size: 12px;
  padding: 2px 10px;
  cursor: pointer;
  color: var(--text-secondary);
}
.bank-btn.ok:hover { color: var(--success); border-color: var(--success); }
.bank-btn.del:hover { color: #e06c75; border-color: #e06c75; }

.bank-more {
  text-align: center;
  padding: 8px 0 16px;
}
</style>
