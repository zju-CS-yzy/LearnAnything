<template>
  <div class="quiz-view">
    <header class="view-header">
      <div class="header-title">
        <span class="header-icon">📝</span>
        <span>出题</span>
      </div>
    </header>

    <div class="view-content">
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
            </div>
            <div class="question-text">{{ q.question }}</div>
            <div v-if="q.options && q.options.length" class="question-options">
              <div v-for="(opt, j) in q.options" :key="j" class="option-item">
                <span class="option-label">{{ ['A', 'B', 'C', 'D', 'E', 'F'][j] || j }}</span>
                <span class="option-text">{{ opt.replace(/^[A-Fa-f][\.．、]\s*/, '') }}</span>
              </div>
            </div>
            <div class="question-answer">
              <span class="answer-label">答案：</span>
              <span class="answer-text">{{ q.answer }}</span>
            </div>
            <div class="question-explanation">
              <span class="explanation-label">解析：</span>
              <span class="explanation-text">{{ q.explanation }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject } from 'vue'
import { apiQuiz, apiQuizBankSave } from '../composables/useApi.js'

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

const selectedIds = computed(() => new Set(selectedIdList.value))

const selectedQuestions = computed(() => {
  if (!quizResult.value) return []
  return quizResult.value.questions.filter(q => selectedIds.value.has(q.id))
})

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
    alert(`已保存 ${result.saved} 道题目到题库`)
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
</style>
