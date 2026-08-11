<template>
  <div class="question-card">
    <div class="qc-header">
      <span class="qc-icon">{{ isEval ? '📊' : '📝' }}</span>
      <span class="qc-title">{{ isEval ? '测评选题卡' : '题目卡片' }}</span>
      <span class="qc-count">{{ questions.length }} 题</span>
      <span v-if="topic" class="qc-topic">「{{ topic }}」</span>
      <span v-if="isEval && submitted" class="qc-done-tag">已提交</span>
      <span v-else-if="isEval && !evalSessionId" class="qc-expired-tag">已结束，仅供回顾</span>
    </div>

    <!-- 测验模式：选择保存操作栏（与出题界面交互一致） -->
    <div v-if="!isEval" class="qc-save-bar">
      <label class="qc-checkbox-label" @click.stop>
        <input type="checkbox" v-model="selectAll" @change="toggleSelectAll" />
        <span>全选</span>
      </label>
      <span class="qc-selected-hint">已选 {{ selectedQuestions.length }} / {{ questions.length }} 题</span>
    </div>

    <!-- 测评模式：作答进度提示 -->
    <div v-else-if="evalActive" class="qc-save-bar">
      <span class="qc-selected-hint">已答 {{ answeredCount }} / {{ questions.length }} 题，完成后点击底部提交</span>
    </div>

    <div class="qc-list">
      <div
        v-for="(q, i) in questions"
        :key="q.id ?? i"
        class="qc-item"
        :class="{ selected: !isEval && selectedSet.has(q.id ?? i) }"
      >
        <div class="qc-item-head" @click="toggleExpand(i)">
          <label v-if="!isEval" class="qc-checkbox-label" @click.stop>
            <input
              type="checkbox"
              :value="q.id ?? i"
              v-model="selectedList"
              :disabled="inBankFlags[i]"
              @click.stop
            />
          </label>
          <span class="qc-index">{{ q.id ?? i + 1 }}</span>
          <span class="qc-type-tag">{{ typeLabel(q.type) }}</span>
          <span v-if="q.bloom_level" class="qc-bloom" :class="'bloom-' + q.bloom_level">
            {{ bloomLabel(q.bloom_level) }}
          </span>
          <span v-if="!isEval && inBankFlags[i]" class="qc-inbank">已在题库</span>
          <span class="qc-stem-preview">{{ q.question }}</span>
          <!-- 测评提交后的对错标记 -->
          <span v-if="isEval && submitted && detailFor(q, i)" class="qc-verdict">
            {{ detailFor(q, i).is_correct ? '✅' : '❌' }}
          </span>
          <span class="qc-expand-icon">{{ expanded[i] ? '▲' : '▼' }}</span>
        </div>

        <div v-if="expanded[i]" class="qc-item-body">
          <div class="qc-stem">{{ q.question }}</div>

          <!-- 测评作答中：选项点选（单字母答案，与评测页一致） -->
          <template v-if="isEval && evalActive">
            <div v-if="q.options && q.options.length" class="qc-choices">
              <div
                v-for="(opt, j) in q.options"
                :key="j"
                class="qc-choice"
                :class="{ chosen: answers[i] === letter(j) }"
                @click="answers[i] = letter(j)"
              >
                <span class="qc-choice-label">{{ letter(j) }}</span>
                <span class="qc-choice-text">{{ stripPrefix(opt) }}</span>
              </div>
            </div>
            <textarea
              v-else
              class="qc-answer-input"
              v-model="answers[i]"
              placeholder="请输入你的答案..."
              rows="2"
            ></textarea>
          </template>

          <!-- 非作答态：只读选项列表 -->
          <div v-else-if="q.options && q.options.length" class="qc-options">
            <div v-for="(opt, j) in q.options" :key="j" class="qc-option">{{ opt }}</div>
          </div>

          <!-- 测评提交后：该题评分反馈 -->
          <div v-if="isEval && submitted && detailFor(q, i)" class="qc-answer-block">
            <div class="qc-answer-row">
              <span class="qc-label">你的答案</span>
              <span class="qc-answer-text">{{ detailFor(q, i).user_answer || '（未作答）' }}</span>
            </div>
            <div class="qc-answer-row">
              <span class="qc-label">参考答案</span>
              <span class="qc-answer-text">{{ detailFor(q, i).correct_answer }}</span>
            </div>
            <div class="qc-answer-row">
              <span class="qc-label">得分</span>
              <span class="qc-answer-text">{{ detailFor(q, i).score }} / {{ detailFor(q, i).max_score }}</span>
            </div>
            <div v-if="detailFor(q, i).feedback" class="qc-answer-row">
              <span class="qc-label">反馈</span>
              <span class="qc-explanation-text">{{ detailFor(q, i).feedback }}</span>
            </div>
          </div>

          <!-- 测验模式/测评回顾：答案显隐 -->
          <template v-else-if="!evalActive">
            <button class="qc-answer-toggle" @click.stop="toggleAnswer(i)">
              {{ showAnswer[i] ? '隐藏答案与解析' : '查看答案与解析' }}
            </button>
            <div v-if="showAnswer[i]" class="qc-answer-block">
              <div class="qc-answer-row">
                <span class="qc-label">答案</span>
                <span class="qc-answer-text">{{ formatAnswer(q) }}</span>
              </div>
              <div v-if="q.explanation" class="qc-answer-row">
                <span class="qc-label">解析</span>
                <span class="qc-explanation-text">{{ q.explanation }}</span>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <div class="qc-footer">
      <!-- 测验模式：保存到题库 -->
      <template v-if="!isEval">
        <button
          class="qc-save-btn"
          :disabled="selectedQuestions.length === 0 || saving"
          @click="saveToBank"
        >
          {{ saving ? '保存中…' : `💾 保存 ${selectedQuestions.length} 题到题库` }}
        </button>
        <span v-if="saveMsg" class="qc-save-ok">{{ saveMsg }}</span>
        <span v-if="saveError" class="qc-save-error">{{ saveError }}</span>
      </template>

      <!-- 测评模式：提交评分 -->
      <template v-else-if="evalActive">
        <button
          class="qc-save-btn qc-submit-btn"
          :disabled="submitting"
          @click="submitEval"
        >
          {{ submitting ? '评分中…' : '📤 提交测评' }}
        </button>
        <span v-if="submitError" class="qc-save-error">{{ submitError }}</span>
      </template>

      <!-- 测评已提交/已结束：无操作 -->
      <span v-else-if="isEval && submitted" class="qc-selected-hint">评分结果见下方结果卡片</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { apiQuizBankSave, apiQuizBankCheck, apiEvalSubmit } from '../../composables/useApi.js'

const props = defineProps({
  questions: { type: Array, required: true },
  subject: { type: String, default: 'generic' },
  topic: { type: String, default: '' },
  // LA-UI-001 M2: quiz=题卡（保存题库）| evaluate=测评卡（作答提交）
  mode: { type: String, default: 'quiz' },
  // 测评会话ID（历史恢复的测评卡为空 → 只读回顾）
  evalSessionId: { type: String, default: '' },
  // 提交时回写群聊结果卡片所需的群聊会话ID
  dialogSessionId: { type: String, default: '' },
})

const emit = defineEmits(['eval-result'])

const isEval = computed(() => props.mode === 'evaluate')
// 测评作答中 = 测评模式 + 有有效会话 + 未提交
const evalActive = computed(() => isEval.value && props.evalSessionId && !submitted.value)

// 测评模式默认全部展开（作答态）；测验模式默认折叠
const expanded = reactive(
  Object.fromEntries(props.questions.map((_, i) => [i, props.mode === 'evaluate']))
)
const showAnswer = reactive({})

// ========== 测验模式：选择保存 ==========
const selectedList = ref(props.questions.map((q, i) => q.id ?? i))
const selectAll = ref(true)
const saving = ref(false)
const saveMsg = ref('')
const saveError = ref('')
// LA-UI-001: 逐题"已在题库"标记（保存前预检 + 保存后更新）
const inBankFlags = ref(props.questions.map(() => false))

const selectedSet = computed(() => new Set(selectedList.value))
const selectedQuestions = computed(() =>
  props.questions.filter((q, i) => selectedSet.value.has(q.id ?? i))
)

// 挂载时预检：已在题库的题目取消勾选并禁用复选框
onMounted(async () => {
  if (props.mode !== 'quiz' || !props.questions.length) return
  try {
    const res = await apiQuizBankCheck(
      props.questions.map(q => q.question || ''),
      props.subject,
    )
    const dups = res.duplicates || []
    inBankFlags.value = props.questions.map((_, i) => !!dups[i])
    if (dups.some(Boolean)) {
      selectedList.value = props.questions
        .map((q, i) => ({ id: q.id ?? i, dup: !!dups[i] }))
        .filter(x => !x.dup)
        .map(x => x.id)
      selectAll.value = selectedList.value.length > 0 &&
        selectedList.value.length === props.questions.length
    }
  } catch (e) {
    console.warn('[QuestionCard] 题库重复预检失败（不阻塞保存）:', e)
  }
})

// ========== 测评模式：作答提交 ==========
const answers = reactive({})
const submitting = ref(false)
const submitted = ref(false)
const submitError = ref('')
const resultDetails = ref([])

const answeredCount = computed(() =>
  props.questions.filter((_, i) => String(answers[i] || '').trim()).length
)

function detailFor(q, i) {
  const qid = q.id ?? i + 1
  return resultDetails.value.find(d => d.id === qid) || resultDetails.value[i] || null
}

function letter(j) {
  return String.fromCharCode(65 + j)
}

function stripPrefix(opt) {
  return String(opt).replace(/^[A-Fa-f][\.．、]\s*/, '')
}

async function submitEval() {
  if (submitting.value || submitted.value) return
  submitting.value = true
  submitError.value = ''
  try {
    const answerList = props.questions.map((_, i) => String(answers[i] || ''))
    const result = await apiEvalSubmit(
      props.evalSessionId,
      answerList,
      props.dialogSessionId || null,
    )
    resultDetails.value = result.details || []
    submitted.value = true
    // 通知 ChatView 追加结果卡片消息
    emit('eval-result', result)
  } catch (e) {
    submitError.value = '提交失败: ' + (e.message || e)
  } finally {
    submitting.value = false
  }
}

// ========== 共用 ==========
const typeLabels = {
  single_choice: '单选',
  multiple_choice: '多选',
  true_false: '判断',
  fill_blank: '填空',
  short_answer: '简答',
}

const bloomLabels = {
  remember: '记忆',
  understand: '理解',
  apply: '应用',
  analyze: '分析',
  evaluate: '评估',
  create: '创造',
}

function typeLabel(t) {
  return typeLabels[t] || '题目'
}

function bloomLabel(level) {
  return bloomLabels[level] || level
}

function formatAnswer(q) {
  if (Array.isArray(q.answer)) return q.answer.join('、')
  return q.answer ?? '—'
}

function toggleExpand(i) {
  expanded[i] = !expanded[i]
}

function toggleAnswer(i) {
  showAnswer[i] = !showAnswer[i]
}

function toggleSelectAll() {
  if (selectAll.value) {
    // 全选只覆盖未入库的题目
    selectedList.value = props.questions
      .map((q, i) => ({ id: q.id ?? i, dup: inBankFlags.value[i] }))
      .filter(x => !x.dup)
      .map(x => x.id)
  } else {
    selectedList.value = []
  }
}

async function saveToBank() {
  if (selectedQuestions.value.length === 0 || saving.value) return
  saving.value = true
  saveMsg.value = ''
  saveError.value = ''
  try {
    // 与出题界面一致：群聊保存的题目直接置为已确认
    const result = await apiQuizBankSave(
      selectedQuestions.value,
      props.subject,
      props.topic || '群聊出题',
      true,
    )
    saveMsg.value = result.message
      ? `✓ ${result.message}`
      : `✓ 已保存 ${result.saved ?? selectedQuestions.value.length} 题`
    // 将本次提交的题目标记为已在题库并取消勾选（含被后端去重跳过的）
    const savedTexts = new Set(selectedQuestions.value.map(q => q.question))
    inBankFlags.value = props.questions.map(
      (q, i) => inBankFlags.value[i] || savedTexts.has(q.question)
    )
    selectedList.value = []
    selectAll.value = false
  } catch (e) {
    saveError.value = '保存失败: ' + (e.message || e)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.question-card {
  margin-top: 10px;
  background: var(--bg-input);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.qc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--bg-hover);
  border-bottom: 1px solid var(--border-color);
}

.qc-icon { font-size: 15px; }
.qc-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.qc-count {
  font-size: 11px;
  color: var(--accent-primary);
  background: var(--bg-active);
  border-radius: 10px;
  padding: 1px 8px;
}
.qc-topic { font-size: 12px; color: var(--text-secondary); }

.qc-done-tag {
  font-size: 11px;
  color: #7ec699;
  border: 1px solid #7ec699;
  border-radius: 4px;
  padding: 0 6px;
}
.qc-expired-tag {
  font-size: 11px;
  color: var(--text-muted);
  border: 1px solid var(--border-light);
  border-radius: 4px;
  padding: 0 6px;
}

.qc-save-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 14px;
  border-bottom: 1px solid var(--border-color);
}

.qc-checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
}
.qc-checkbox-label input[type="checkbox"] {
  width: 14px;
  height: 14px;
  cursor: pointer;
}

.qc-selected-hint { font-size: 11px; color: var(--text-muted); }

.qc-list { padding: 6px 10px; }

.qc-item {
  border-bottom: 1px solid var(--border-color);
  border-left: 2px solid transparent;
  padding: 6px 0 6px 4px;
  transition: border-color 0.15s, background 0.15s;
}
.qc-item:last-child { border-bottom: none; }
.qc-item.selected {
  border-left-color: var(--accent-primary);
  background: var(--bg-hover);
}

.qc-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 4px;
  border-radius: var(--radius-sm);
}
.qc-item-head:hover { background: var(--bg-active); }

.qc-index {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--bg-active);
  color: var(--accent-primary);
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.qc-type-tag {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-secondary);
  border: 1px solid var(--border-light);
  border-radius: 4px;
  padding: 0 5px;
}

.qc-bloom {
  flex-shrink: 0;
  font-size: 11px;
  border-radius: 4px;
  padding: 0 5px;
  color: var(--accent-primary);
  background: var(--bg-active);
}

.qc-stem-preview {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.qc-verdict { flex-shrink: 0; font-size: 13px; }
.qc-expand-icon { flex-shrink: 0; font-size: 10px; color: var(--text-muted); }

/* LA-UI-001: 已在题目标记 */
.qc-inbank {
  flex-shrink: 0;
  font-size: 11px;
  color: #7ec699;
  border: 1px solid #7ec699;
  border-radius: 4px;
  padding: 0 5px;
}
.qc-checkbox-label input[type="checkbox"]:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.qc-item-body {
  padding: 8px 8px 10px 34px;
}

.qc-stem {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
  margin-bottom: 8px;
}

.qc-options { margin-bottom: 8px; }
.qc-option {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  padding-left: 8px;
}

/* 测评作答：选项点选 */
.qc-choices { margin-bottom: 8px; display: flex; flex-direction: column; gap: 6px; }
.qc-choice {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  transition: border-color 0.15s, background 0.15s;
}
.qc-choice:hover { border-color: var(--accent-primary); }
.qc-choice.chosen {
  border-color: var(--accent-primary);
  background: var(--bg-active);
  color: var(--text-primary);
}
.qc-choice-label {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--accent-primary);
}

.qc-answer-input {
  width: 100%;
  box-sizing: border-box;
  background: var(--bg-main);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  padding: 8px 10px;
  resize: vertical;
  margin-bottom: 8px;
}
.qc-answer-input:focus { outline: none; border-color: var(--accent-primary); }

.qc-answer-toggle {
  background: none;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: var(--accent-primary);
  font-size: 12px;
  padding: 3px 10px;
  cursor: pointer;
}
.qc-answer-toggle:hover { border-color: var(--accent-primary); }

.qc-answer-block {
  margin-top: 8px;
  padding: 8px 10px;
  background: var(--bg-hover);
  border-radius: var(--radius-sm);
}

.qc-answer-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 4px;
}
.qc-answer-row:last-child { margin-bottom: 0; }

.qc-label {
  flex-shrink: 0;
  color: var(--accent-primary);
  font-weight: 600;
}

.qc-answer-text { color: var(--text-primary); font-weight: 600; }
.qc-explanation-text { color: var(--text-secondary); }

.qc-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-top: 1px solid var(--border-color);
}

.qc-save-btn {
  background: var(--bg-active);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 12px;
  padding: 4px 12px;
  cursor: pointer;
}
.qc-save-btn:hover:not(:disabled) {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.qc-save-btn:disabled { opacity: 0.6; cursor: default; }

.qc-submit-btn {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}

.qc-save-ok { font-size: 12px; color: #7ec699; }
.qc-save-error { font-size: 12px; color: #e06c75; }
</style>
