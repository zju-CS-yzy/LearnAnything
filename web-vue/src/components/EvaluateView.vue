<template>
  <div class="evaluate-view">
    <header class="view-header">
      <div class="header-title">
        <span class="header-icon">📊</span>
        <span>能力评测</span>
      </div>
    </header>

    <div class="view-content">
      <!-- 步骤1：开始评测 -->
      <div v-if="step === 'start'" class="eval-start card">
        <div class="form-group">
          <label>评测主题</label>
          <input v-model="topic" placeholder="例如：RAG 技术" />
        </div>
        <div class="form-group">
          <label>学科</label>
          <input v-model="subject" placeholder="generic" />
        </div>
        <div class="form-group">
          <label>测评模式</label>
          <select v-model="evalMode" class="form-select">
            <option value="generate">🆕 生成新题</option>
            <option value="bank">📚 从题库抽题</option>
            <option value="mixed">🔀 混合模式</option>
          </select>
          <div class="mode-hint">{{ modeHint }}</div>
        </div>
        <div class="form-group">
          <label>题目数量</label>
          <input v-model.number="count" type="number" min="1" max="10" />
        </div>
        <button class="btn btn-primary" :disabled="isLoading" @click="startEval">
          <span v-if="isLoading" class="spinner"></span>
          <span v-else>开始评测</span>
        </button>
      </div>

      <!-- 步骤2：答题 -->
      <div v-if="step === 'quiz'" class="eval-quiz">
        <div class="quiz-progress">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: (currentIndex / questions.length * 100) + '%' }"></div>
          </div>
          <span class="progress-text">{{ currentIndex + 1 }} / {{ questions.length }}</span>
        </div>

        <div class="question-card card" v-if="currentQuestion">
          <div class="question-type tag">{{ currentQuestion.type }}</div>
          <div class="question-text">{{ currentQuestion.question }}</div>
          <div v-if="currentQuestion.options && currentQuestion.options.length" class="options-list">
            <div
              v-for="(opt, i) in currentQuestion.options"
              :key="i"
              class="option-choice"
              :class="{ selected: userAnswers[currentIndex] === opt }"
              @click="userAnswers[currentIndex] = String.fromCharCode(65 + i)"
            >
              <span class="choice-label">{{ ['A', 'B', 'C', 'D', 'E', 'F'][i] || i }}</span>
              <span class="choice-text">{{ opt }}</span>
            </div>
          </div>
          <div v-else class="answer-input">
            <textarea
              v-model="userAnswers[currentIndex]"
              placeholder="请输入你的答案..."
              rows="3"
            ></textarea>
          </div>
        </div>

        <div class="quiz-nav">
          <button
            class="btn btn-secondary"
            :disabled="currentIndex === 0"
            @click="currentIndex--"
          >上一题</button>
          <button
            v-if="currentIndex < questions.length - 1"
            class="btn btn-primary"
            @click="currentIndex++"
          >下一题</button>
          <button
            v-else
            class="btn btn-primary"
            :disabled="isSubmitting"
            @click="submitEval"
          >
            <span v-if="isSubmitting" class="spinner"></span>
            <span v-else>提交答案</span>
          </button>
        </div>
      </div>

      <!-- 步骤3：结果报告 -->
      <div v-if="step === 'result'" class="eval-result card">
        <div class="score-circle">
          <div class="score-number">{{ report.percentage }}%</div>
          <div class="score-label">{{ report.level }}</div>
        </div>
        <div class="score-detail">
          {{ report.correct_count }} / {{ report.total_questions }} 正确 · 得分 {{ report.total_score }} / {{ report.max_score }}
        </div>
        <div class="summary">{{ report.summary }}</div>

        <div v-if="report.strong_areas.length" class="areas-section">
          <div class="areas-title strong">✅ 优势领域</div>
          <div class="areas-list">
            <span v-for="area in report.strong_areas" :key="area" class="area-tag">{{ area }}</span>
          </div>
        </div>

        <div v-if="report.weak_areas.length" class="areas-section">
          <div class="areas-title weak">⚠️ 薄弱环节</div>
          <div class="areas-list">
            <span v-for="area in report.weak_areas" :key="area" class="area-tag">{{ area }}</span>
          </div>
        </div>

        <div class="details-section">
          <div class="details-title">答题详情</div>
          <div class="details-list">
            <div
              v-for="d in report.details"
              :key="d.id"
              class="detail-item"
              :class="{ correct: d.is_correct, wrong: !d.is_correct }"
            >
              <div class="detail-header">
                <span class="detail-status">{{ d.is_correct ? '✅' : '❌' }}</span>
                <span class="detail-question">{{ d.question }}</span>
              </div>
              <div class="detail-answers">
                <span :class="{ 'user-correct': d.is_correct, 'user-wrong': !d.is_correct }">
                  你的答案：{{ d.user_answer || '(未作答)' }}
                </span>
                <span class="correct-answer">正确答案：{{ d.correct_answer }}</span>
              </div>
              <div class="detail-feedback">{{ d.feedback }}</div>
            </div>
          </div>
        </div>

        <button class="btn btn-primary" @click="restart" style="margin-top: 20px;">
          重新评测
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { apiEvalStart, apiEvalSubmit } from '../composables/useApi.js'

const step = ref('start')
const topic = ref('RAG 技术')
const subject = ref('generic')
const count = ref(5)
const evalMode = ref('generate')
const isLoading = ref(false)
const isSubmitting = ref(false)

const modeHint = computed(() => {
  const hints = {
    generate: '基于知识库实时生成新题目',
    bank: '从已保存的题库中随机抽取',
    mixed: '一半题库题目 + 一半生成题目',
  }
  return hints[evalMode.value] || ''
})

const sessionId = ref('')
const questions = ref([])
const userAnswers = ref([])
const currentIndex = ref(0)
const report = ref(null)

const currentQuestion = computed(() => questions.value[currentIndex.value])

async function startEval() {
  if (!topic.value.trim()) return
  isLoading.value = true

  try {
    const result = await apiEvalStart(topic.value, subject.value, count.value, evalMode.value)
    sessionId.value = result.session_id
    questions.value = result.questions
    userAnswers.value = new Array(questions.value.length).fill('')
    currentIndex.value = 0
    step.value = 'quiz'
  } catch (e) {
    alert('开始评测失败: ' + e.message)
  } finally {
    isLoading.value = false
  }
}

async function submitEval() {
  isSubmitting.value = true

  try {
    const result = await apiEvalSubmit(sessionId.value, userAnswers.value)
    report.value = result
    step.value = 'result'
  } catch (e) {
    alert('提交失败: ' + e.message)
  } finally {
    isSubmitting.value = false
  }
}

function restart() {
  step.value = 'start'
  sessionId.value = ''
  questions.value = []
  userAnswers.value = []
  currentIndex.value = 0
  report.value = null
}
</script>

<style scoped>
.evaluate-view {
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

.eval-start {
  max-width: 600px;
  margin: 0 auto;
}

.form-select {
  width: 100%;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 14px;
}

.mode-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}

/* 答题进度 */
.quiz-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: 800px;
  margin: 0 auto 20px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--bg-input);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent-gradient);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 13px;
  color: var(--text-muted);
  flex-shrink: 0;
}

/* 题目卡片 */
.question-card {
  max-width: 800px;
  margin: 0 auto 20px;
}

.question-type {
  margin-bottom: 10px;
}

.question-text {
  font-size: 16px;
  line-height: 1.7;
  color: var(--text-primary);
  margin-bottom: 16px;
}

.options-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-choice {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.option-choice:hover {
  background: var(--bg-hover);
  border-color: var(--border-light);
}

.option-choice.selected {
  background: var(--bg-active);
  border-color: var(--accent-primary);
}

.choice-label {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-card);
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.option-choice.selected .choice-label {
  background: var(--accent-primary);
  color: white;
}

.answer-input textarea {
  width: 100%;
}

/* 导航按钮 */
.quiz-nav {
  display: flex;
  justify-content: space-between;
  max-width: 800px;
  margin: 0 auto;
}

/* 结果报告 */
.eval-result {
  max-width: 800px;
  margin: 0 auto;
}

.score-circle {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: var(--accent-gradient);
  margin: 0 auto 16px;
  color: white;
}

.score-number {
  font-size: 32px;
  font-weight: 700;
}

.score-label {
  font-size: 14px;
  opacity: 0.9;
}

.score-detail {
  text-align: center;
  font-size: 14px;
  color: var(--text-muted);
  margin-bottom: 16px;
}

.summary {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  margin-bottom: 20px;
  padding: 12px;
  background: var(--bg-input);
  border-radius: var(--radius-sm);
}

.areas-section {
  margin-bottom: 16px;
}

.areas-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
}

.areas-title.strong { color: var(--success); }
.areas-title.weak { color: var(--warning); }

.areas-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.area-tag {
  padding: 4px 10px;
  background: var(--bg-input);
  border-radius: 4px;
  font-size: 13px;
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
}

.details-section {
  margin-top: 20px;
}

.details-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-primary);
}

.details-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-item {
  padding: 12px;
  background: var(--bg-input);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--border-color);
}

.detail-item.correct { border-left-color: var(--success); }
.detail-item.wrong { border-left-color: var(--error); }

.detail-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 6px;
}

.detail-question {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.4;
}

.detail-answers {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  margin-bottom: 6px;
}

.user-correct { color: var(--success); }
.user-wrong { color: var(--error); }
.correct-answer { color: var(--success); opacity: 0.8; }

.detail-feedback {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.4;
  padding-top: 6px;
  border-top: 1px dashed var(--border-color);
}
</style>
