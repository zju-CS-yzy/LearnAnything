<template>
  <div v-if="visible" class="merge-review" role="dialog" aria-modal="true" aria-labelledby="merge-review-title">
    <header class="review-header">
      <div>
        <button class="text-button" type="button" @click="$emit('close')">返回图谱</button>
        <h2 id="merge-review-title">概念合并审核</h2>
        <p>{{ subjectName }} 的图谱构建已暂停。完成全部判断后将继续建立语义关系。</p>
      </div>
      <div class="header-actions">
        <button
          v-if="adviceRetryCount"
          class="secondary-action"
          type="button"
          :disabled="advising"
          @click="$emit('request-advice')"
        >{{ advising ? '正在生成建议…' : `生成 / 重试建议（${adviceRetryCount}）` }}</button>
        <button
          v-if="bulkEligibleCount"
          class="secondary-action"
          type="button"
          :disabled="bulkAccepting"
          @click="acceptSuggested"
        >{{ bulkAccepting ? '正在确认…' : `确认高置信建议（${bulkEligibleCount}）` }}</button>
        <div class="review-progress" aria-live="polite">
          <strong>{{ reviewedCount }} / {{ candidates.length }}</strong>
          <span>已审核</span>
        </div>
      </div>
    </header>

    <div v-if="loading" class="review-loading">正在加载合并候选…</div>
    <div v-else-if="error" class="review-error">{{ error }}</div>
    <div v-else class="review-layout">
      <aside class="candidate-list" aria-label="合并候选队列">
        <div class="queue-summary">
          <span>待审核 {{ pendingCount }}</span>
          <span>LLM 已建议 {{ advisedCount }}</span>
        </div>
        <button
          v-for="(candidate, index) in candidates"
          :key="candidate.candidate_id"
          type="button"
          class="candidate-row"
          :class="{ active: index === activeIndex, resolved: candidate.decision }"
          @click="activeIndex = index"
        >
          <span class="candidate-names">{{ candidate.left }} ↔ {{ candidate.right }}</span>
          <span class="candidate-meta">
            {{ Math.round((candidate.confidence || 0) * 100) }}%
            · {{ decisionLabel(candidate.decision) }}
          </span>
          <span class="advisor-badge" :class="advisorTone(candidate)">{{ advisorLabel(candidate) }}</span>
        </button>
      </aside>

      <main v-if="activeCandidate" class="evidence-panel">
        <div class="concept-comparison">
          <section class="concept-column">
            <span class="column-label">概念 A</span>
            <h3>{{ activeCandidate.left }}</h3>
            <ConceptEvidence :profile="activeCandidate.left_profile" />
          </section>
          <div class="comparison-mark" aria-hidden="true">↔</div>
          <section class="concept-column">
            <span class="column-label">概念 B</span>
            <h3>{{ activeCandidate.right }}</h3>
            <ConceptEvidence :profile="activeCandidate.right_profile" />
          </section>
        </div>

        <section class="system-assessment">
          <div>
            <span class="assessment-label">系统判断</span>
            <strong>{{ relationLabel(activeCandidate.relation) }}</strong>
          </div>
          <span class="confidence">置信度 {{ Math.round((activeCandidate.confidence || 0) * 100) }}%</span>
        </section>

        <section
          class="advisor-assessment"
          :class="{ conflict: activeCandidate.advisor_conflict }"
          aria-labelledby="advisor-assessment-title"
        >
          <div class="advisor-heading">
            <div>
              <h3 id="advisor-assessment-title">LLM 预审建议</h3>
              <p>综合概念描述与来源上下文，仅供审核参考。</p>
            </div>
            <span v-if="activeCandidate.advisor" class="advisor-confidence">
              {{ Math.round((activeCandidate.advisor.confidence || 0) * 100) }}%
            </span>
          </div>
          <div v-if="activeCandidate.advisor_status === 'ready' && activeCandidate.advisor" class="advisor-content">
            <div class="advisor-verdict">
              <strong>{{ advisorLabel(activeCandidate) }}</strong>
              <span v-if="activeCandidate.advisor.needs_more_context">需要更多上下文</span>
            </div>
            <RichText :content="activeCandidate.advisor.reason" />
            <div v-if="activeCandidate.advisor.supporting_chunk_ids?.length" class="advisor-sources">
              <span>支持来源</span>
              <code v-for="chunkId in activeCandidate.advisor.supporting_chunk_ids" :key="chunkId">{{ chunkId }}</code>
            </div>
            <div v-if="activeCandidate.advisor_conflict" class="conflict-notice" role="alert">
              该建议与其他候选形成传递冲突，请逐组核对，不会参与批量确认。
            </div>
            <ul v-if="activeCandidate.advisor.conflicts?.length" class="advisor-conflicts">
              <li v-for="conflict in activeCandidate.advisor.conflicts" :key="conflict">{{ conflict }}</li>
            </ul>
          </div>
          <p v-else-if="activeCandidate.advisor_status === 'failed'" class="advisor-unavailable">
            建议生成失败：{{ activeCandidate.advisor_error || 'LLM 暂时不可用' }}。你仍可人工审核，或点击上方按钮重试。
          </p>
          <p v-else class="advisor-unavailable">尚未生成 LLM 建议，可以人工审核或点击上方按钮生成。</p>
          <small v-if="activeCandidate.advisor_model" class="advisor-audit">
            {{ activeCandidate.advisor_model }} · {{ activeCandidate.advisor_prompt_version }}
          </small>
        </section>

        <section class="evidence-section">
          <h3>判断依据</h3>
          <div class="signal-list">
            <span v-for="signal in activeCandidate.signals || []" :key="signal" class="signal">{{ signal }}</span>
          </div>
          <blockquote v-for="item in activeCandidate.evidence || []" :key="`${item.alias}-${item.evidence}`">
            <strong>{{ item.alias }}</strong>
            <RichText :content="item.evidence" inline />
          </blockquote>
          <p v-if="!(activeCandidate.evidence || []).length" class="no-evidence">
            没有直接的原文等价证据，本候选主要由语义相似度召回。
          </p>
        </section>
      </main>

      <aside v-if="activeCandidate" class="decision-panel">
        <h3>本组决策</h3>
        <p v-if="isAdvisorPrefill" class="prefill-note">
          已按 LLM 建议预选；只有点击下方确认后才会计入审核结果。
        </p>
        <label class="decision-option" :class="{ selected: draftDecision === 'merge' }">
          <input v-model="draftDecision" type="radio" value="merge" />
          <span><strong>合并为同一概念</strong><small>两个名称指向完全相同的知识对象</small></span>
        </label>
        <label class="decision-option" :class="{ selected: draftDecision === 'separate' }">
          <input v-model="draftDecision" type="radio" value="separate" />
          <span><strong>保持分离</strong><small>概念相关，但含义或范围不同</small></span>
        </label>

        <label v-if="draftDecision === 'merge'" class="field-label">
          规范名称
          <select v-model="canonicalName">
            <option :value="activeCandidate.left">{{ activeCandidate.left }}</option>
            <option :value="activeCandidate.right">{{ activeCandidate.right }}</option>
          </select>
        </label>
        <label v-else-if="draftDecision === 'separate'" class="field-label">
          可选关系
          <select v-model="relationDecision">
            <option value="">不建立关系</option>
            <option value="RELATED_TO">两者相关</option>
            <option value="LEFT_NARROWER_THAN_RIGHT">A 是 B 的具体概念</option>
            <option value="RIGHT_NARROWER_THAN_LEFT">B 是 A 的具体概念</option>
          </select>
        </label>

        <button class="primary-action" type="button" :disabled="!draftDecision || saving" @click="saveAndNext">
          {{ saving ? '保存中…' : '确认并审核下一组' }}
        </button>
      </aside>
    </div>

    <footer class="review-footer">
      <span v-if="pendingCount">还有 {{ pendingCount }} 组未完成，构建将继续保持暂停。</span>
      <span v-else>全部候选已完成，可以继续构建。</span>
      <button class="submit-action" type="button" :disabled="pendingCount > 0 || submitting" @click="$emit('submit')">
        {{ submitting ? '正在继续构建…' : '提交审核并继续构建' }}
      </button>
    </footer>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import RichText from '../common/RichText.vue'
import ConceptEvidence from './merge-review/ConceptEvidence.vue'
import { advisorLabel, isBulkEligible, recommendationDraft } from './merge-review/mergeAdvice.js'

const props = defineProps({
  visible: Boolean,
  subjectName: { type: String, default: '' },
  candidates: { type: Array, default: () => [] },
  loading: Boolean,
  saving: Boolean,
  submitting: Boolean,
  advising: Boolean,
  bulkAccepting: Boolean,
  error: { type: String, default: '' },
})
const emit = defineEmits(['close', 'save', 'submit', 'request-advice', 'accept-advice'])
const activeIndex = ref(0)
const draftDecision = ref('')
const canonicalName = ref('')
const relationDecision = ref('')
const activeCandidate = computed(() => props.candidates[activeIndex.value] || null)
const reviewedCount = computed(() => props.candidates.filter(item => item.decision).length)
const pendingCount = computed(() => props.candidates.length - reviewedCount.value)
const advisedCount = computed(() => props.candidates.filter(item => item.advisor_status === 'ready').length)
const adviceRetryCount = computed(() => props.candidates.filter(item =>
  !item.decision && ['pending', 'failed'].includes(item.advisor_status || 'pending'),
).length)
const bulkEligibleCount = computed(() => props.candidates.filter(item => isBulkEligible(item)).length)
const isAdvisorPrefill = computed(() => {
  const candidate = activeCandidate.value
  return !candidate?.decision && Boolean(recommendationDraft(candidate))
})

watch(activeCandidate, candidate => {
  const suggested = recommendationDraft(candidate)
  draftDecision.value = candidate?.decision || suggested?.decision || ''
  canonicalName.value = candidate?.canonical_name || suggested?.canonicalName || candidate?.right || ''
  relationDecision.value = candidate?.relation_decision || suggested?.relationDecision || ''
}, { immediate: true })

function decisionLabel(decision) {
  return decision === 'merge' ? '合并' : decision === 'separate' ? '分离' : '待审核'
}
function relationLabel(relation) {
  return ({ SAME_AS: '可能是同一概念', RELATED_TO: '相关概念', NARROWER_THAN: '可能存在层级关系' })[relation] || relation
}
function advisorTone(candidate) {
  if (candidate?.advisor_conflict || candidate?.advisor_status === 'failed') return 'danger'
  if (candidate?.advisor?.decision === 'MERGE') return 'merge'
  if (candidate?.advisor?.decision === 'SEPARATE') return 'separate'
  return 'neutral'
}
function acceptSuggested() {
  if (!bulkEligibleCount.value) return
  if (window.confirm(`确认采用 ${bulkEligibleCount.value} 组置信度不低于 90% 且无冲突的 LLM 建议？其余候选仍需逐组审核。`)) {
    emit('accept-advice')
  }
}
function saveAndNext() {
  if (!activeCandidate.value || !draftDecision.value) return
  emit('save', {
    candidate: activeCandidate.value,
    decision: draftDecision.value,
    canonical_name: draftDecision.value === 'merge' ? canonicalName.value : '',
    relation_decision: draftDecision.value === 'separate' ? relationDecision.value : '',
    onSaved: () => {
      const next = props.candidates.findIndex((item, index) => index > activeIndex.value && !item.decision)
      if (next >= 0) activeIndex.value = next
    },
  })
}
</script>

<style scoped>
.merge-review { position: fixed; inset: 0; z-index: 120; display: grid; grid-template-rows: auto 1fr auto; background: #f6f4ef; color: #292821; }
.review-header { display: flex; justify-content: space-between; align-items: center; padding: 20px 28px; border-bottom: 1px solid #d9d4c9; background: #fff; }
.review-header h2 { margin: 6px 0 3px; font-size: 22px; }
.review-header p { margin: 0; color: #67645d; }
.text-button { border: 0; padding: 0; background: transparent; color: #5b63d9; cursor: pointer; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.secondary-action { min-height: 38px; padding: 0 13px; border: 1px solid #b8b4aa; border-radius: 9px; background: #fff; color: #35342f; font-weight: 650; cursor: pointer; }
.secondary-action:hover { border-color: #676ed9; color: #4e55c7; }
.review-progress { display: grid; text-align: right; }
.review-progress strong { font-size: 22px; font-variant-numeric: tabular-nums; }
.review-progress span { color: #77736a; font-size: 12px; }
.review-layout { min-height: 0; display: grid; grid-template-columns: 280px minmax(440px, 1fr) 320px; }
.candidate-list { overflow-y: auto; border-right: 1px solid #d9d4c9; background: #ebe8e0; padding: 14px; }
.queue-summary { display: flex; justify-content: space-between; padding: 4px 4px 12px; color: #67645d; font-size: 12px; }
.candidate-row { width: 100%; display: grid; gap: 5px; text-align: left; padding: 12px; margin-bottom: 7px; border: 1px solid transparent; border-radius: 12px; background: transparent; color: inherit; cursor: pointer; }
.candidate-row:hover { background: #fff; }
.candidate-row.active { background: #fff; border-color: #787ee5; }
.candidate-row.resolved .candidate-names::before { content: '✓ '; color: #24845d; }
.candidate-names { font-weight: 650; }
.candidate-meta { color: #77736a; font-size: 12px; }
.advisor-badge { justify-self: start; padding: 3px 7px; border-radius: 6px; background: #dedbd3; color: #59564f; font-size: 11px; font-weight: 650; }
.advisor-badge.merge { background: #dcefe5; color: #176443; }
.advisor-badge.separate { background: #e6e5f7; color: #4c50a8; }
.advisor-badge.danger { background: #f8dfdc; color: #913a32; }
.evidence-panel { overflow-y: auto; padding: 28px 34px; }
.concept-comparison { display: grid; grid-template-columns: 1fr auto 1fr; align-items: stretch; gap: 16px; }
.concept-column { min-height: 112px; padding: 18px; border: 1px solid #d9d4c9; border-radius: 14px; background: #fff; }
.column-label, .assessment-label { color: #77736a; font-size: 12px; }
.concept-column h3 { margin: 12px 0 14px; font-size: 20px; }
.comparison-mark { align-self: center; color: #88847a; }
.system-assessment { display: flex; justify-content: space-between; margin-top: 18px; padding: 15px 18px; border-radius: 12px; background: #e9e9fb; }
.system-assessment div { display: grid; gap: 4px; }
.confidence { align-self: center; font-variant-numeric: tabular-nums; }
.advisor-assessment { margin-top: 18px; padding: 18px; border: 1px solid #d4d0c6; border-radius: 14px; background: #fff; }
.advisor-assessment.conflict { border-color: #d49b94; background: #fff9f8; }
.advisor-heading, .advisor-verdict { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.advisor-heading h3 { margin: 0 0 4px; font-size: 16px; }
.advisor-heading p, .advisor-unavailable { margin: 0; color: #66625a; line-height: 1.5; }
.advisor-confidence { min-width: 50px; text-align: right; color: #555dd6; font-weight: 700; font-variant-numeric: tabular-nums; }
.advisor-content { display: grid; gap: 12px; margin-top: 16px; }
.advisor-verdict strong { color: #31343b; }
.advisor-verdict span { color: #8a5c16; font-size: 12px; }
.advisor-sources { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; color: #67645d; font-size: 12px; }
.advisor-sources code { max-width: 230px; overflow: hidden; padding: 4px 6px; border-radius: 5px; background: #ece9e2; text-overflow: ellipsis; white-space: nowrap; }
.conflict-notice { padding: 10px 12px; border-radius: 8px; background: #f7e3e0; color: #81352f; line-height: 1.45; }
.advisor-conflicts { margin: 0; padding-left: 20px; color: #81352f; }
.advisor-unavailable { margin-top: 14px; }
.advisor-audit { display: block; margin-top: 14px; color: #7a766e; }
.evidence-section { margin-top: 28px; }
.signal-list { display: flex; flex-wrap: wrap; gap: 7px; }
.signal { padding: 5px 8px; border-radius: 7px; background: #e5e1d8; font-size: 12px; }
blockquote { display: grid; gap: 5px; margin: 14px 0 0; padding: 14px 16px; border: 1px solid #ddd7ca; border-radius: 12px; background: #fff; }
.no-evidence { color: #716d64; }
.decision-panel { padding: 24px 20px; border-left: 1px solid #d9d4c9; background: #fff; }
.prefill-note { margin: 0 0 16px; padding: 10px 11px; border-radius: 8px; background: #f0effb; color: #4c4f91; font-size: 12px; line-height: 1.45; }
.decision-option { display: flex; gap: 10px; margin-bottom: 10px; padding: 13px; border: 1px solid #d9d4c9; border-radius: 12px; cursor: pointer; }
.decision-option.selected { border-color: #6269d9; background: #f1f1ff; }
.decision-option span { display: grid; gap: 4px; }
.decision-option small { color: #716d64; line-height: 1.35; }
.field-label { display: grid; gap: 7px; margin-top: 18px; font-weight: 600; }
select { min-height: 40px; padding: 0 10px; border: 1px solid #bdb8ae; border-radius: 9px; background: #fff; }
.primary-action, .submit-action { min-height: 42px; border: 0; border-radius: 10px; background: #555dd6; color: #fff; font-weight: 650; cursor: pointer; }
.primary-action { width: 100%; margin-top: 24px; }
button:disabled { opacity: .48; cursor: not-allowed; }
button:focus-visible, select:focus-visible, input:focus-visible { outline: 3px solid rgba(85, 93, 214, .28); outline-offset: 2px; }
.merge-review ::selection { background: #cfd2ff; color: #20213d; }
.candidate-list::-webkit-scrollbar, .evidence-panel::-webkit-scrollbar { width: 10px; }
.candidate-list::-webkit-scrollbar-thumb, .evidence-panel::-webkit-scrollbar-thumb { border: 3px solid transparent; border-radius: 8px; background: #aaa69d; background-clip: padding-box; }
.review-footer { display: flex; justify-content: flex-end; align-items: center; gap: 20px; padding: 14px 28px; border-top: 1px solid #d9d4c9; background: #fff; }
.submit-action { padding: 0 20px; }
.review-loading, .review-error { place-self: center; }
.review-error { color: #a43a3a; }
@media (max-width: 1100px) { .review-header { align-items: flex-start; } .header-actions { flex-wrap: wrap; justify-content: flex-end; } .review-layout { grid-template-columns: 220px 1fr; } .decision-panel { grid-column: 1 / -1; border-left: 0; border-top: 1px solid #d9d4c9; } }
@media (max-width: 720px) { .review-header { padding: 16px; } .header-actions { display: grid; justify-items: stretch; } .review-layout { display: block; overflow-y: auto; } .candidate-list, .evidence-panel { overflow: visible; } .candidate-list { max-height: 260px; overflow-y: auto; border-right: 0; border-bottom: 1px solid #d9d4c9; } .concept-comparison { grid-template-columns: 1fr; } .comparison-mark { display: none; } .review-footer { padding: 12px 16px; } }
</style>
