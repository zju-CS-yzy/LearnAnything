<template>
  <Teleport to="body">
    <div v-if="visible && gap" class="gap-review-overlay" @click.self="requestClose">
      <section class="gap-review" role="dialog" aria-modal="true" aria-labelledby="gap-review-title">
        <header class="review-header">
          <div>
            <h2 id="gap-review-title">补全结构缺口</h2>
            <p>AI 只生成待审核建议；确认前不会修改知识图谱。</p>
          </div>
          <button class="close-button" type="button" aria-label="关闭" @click="requestClose">
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" /></svg>
          </button>
        </header>

        <div class="knowledge-chain" aria-label="待补全知识链">
          <div v-if="sourceConcept" class="chain-node endpoint">
            <span>{{ typeLabel(sourceConcept.type || sourceConcept.concept_type) }}</span>
            <strong>{{ sourceConcept.name }}</strong>
          </div>
          <template v-for="(missingType, index) in gap.missing_types || []" :key="`${missingType}-${index}`">
            <span class="chain-arrow">→</span>
            <div class="chain-node missing">
              <span>缺失节点 {{ index + 1 }}</span>
              <strong>{{ typeLabel(missingType) }}</strong>
            </div>
          </template>
          <template v-if="targetConcept">
            <span class="chain-arrow">→</span>
            <div class="chain-node endpoint">
              <span>{{ typeLabel(targetConcept.type || targetConcept.concept_type) }}</span>
              <strong>{{ targetConcept.name }}</strong>
            </div>
          </template>
        </div>

        <div v-if="loading || proposalStatus === 'generating'" class="generation-state" aria-live="polite">
          <span class="generation-pulse" aria-hidden="true"></span>
          <div>
            <strong>正在核对范式与本地资料</strong>
            <p>系统正在读取上下游概念、邻接关系和来源 Chunk，并验证逐字证据。</p>
          </div>
        </div>

        <template v-else-if="proposalStatus === 'ready'">
          <div class="proposal-summary">
            <div>
              <strong>AI 建议已就绪</strong>
              <p>{{ proposalPayload.explanation || '请检查下面的概念与证据后再确认。' }}</p>
            </div>
            <span class="confidence-value">{{ confidencePercent(proposalPayload.overall_confidence) }}%</span>
          </div>

          <div class="proposal-list">
            <article
              v-for="(concept, index) in proposalConcepts"
              :key="`${concept.slot_index}-${concept.name}`"
              class="proposal-concept"
            >
              <div class="concept-heading">
                <div>
                  <span class="type-tag">{{ typeLabel(concept.concept_type) }}</span>
                  <h3>{{ reviewForms[index]?.name }}</h3>
                </div>
                <span class="concept-confidence">置信度 {{ confidencePercent(concept.confidence) }}%</span>
              </div>

              <div v-if="concept.existing_match" class="reuse-note">
                图谱中已有“{{ concept.existing_match.name }}”，确认后只修复关系，不创建重复节点。
              </div>

              <template v-if="editing && !concept.existing_match">
                <label>概念名称<input v-model.trim="reviewForms[index].name" maxlength="255" /></label>
                <label>描述<textarea v-model.trim="reviewForms[index].description" maxlength="4000" rows="3"></textarea></label>
                <label>别名（每行一个）<textarea v-model="reviewForms[index].aliasText" rows="2"></textarea></label>
              </template>
              <p v-else class="concept-description">{{ reviewForms[index]?.description }}</p>

              <details class="evidence-details">
                <summary>查看本地证据（{{ concept.evidence?.length || 0 }}）</summary>
                <blockquote v-for="item in concept.evidence || []" :key="`${item.chunk_id}-${item.quote}`">
                  <p>{{ item.quote }}</p>
                  <cite>Chunk {{ item.chunk_id }}</cite>
                </blockquote>
              </details>
            </article>
          </div>

          <aside v-if="duplicateCandidates.length" class="risk-note">
            <strong>发现名称相近的既有概念</strong>
            <p>系统没有自动合并这些候选。确认前请留意是否存在语义重复。</p>
            <ul>
              <li v-for="item in duplicateCandidates" :key="`${item.slot_index}-${item.canonical_id}`">
                {{ item.name }} · 相似度 {{ confidencePercent(item.similarity) }}%
              </li>
            </ul>
          </aside>

          <section v-if="importedExternalCandidates.length" class="evidence-governance">
            <div>
              <strong>本轮使用的外部证据</strong>
              <p>停用后会从当前学科检索库移除，并重新核验这条建议。</p>
            </div>
            <article v-for="item in importedExternalCandidates" :key="item.result_id">
              <span><b>{{ item.title }}</b><small>Chunk {{ item.chunk_id }}</small></span>
              <button type="button" :disabled="busy" @click="$emit('deactivate-external', item.chunk_id)">停用</button>
            </article>
          </section>
        </template>

        <div v-else-if="proposalStatus === 'needs_external_evidence'" class="evidence-missing">
          <strong>本地资料不足，暂不能写入图谱</strong>
          <p>系统没有找到能够逐字核验全部补全节点的证据。你可以检索公开学术资料，选择摘要加入当前学科后重新生成建议。</p>
          <ul v-if="proposalPayload.validation_errors?.length">
            <li v-for="item in proposalPayload.validation_errors" :key="item">{{ item }}</li>
          </ul>
          <div v-if="externalSearchQueries.length" class="search-suggestions">
            <span>{{ proposalPayload.recommended_search_queries?.length ? '建议后续检索' : '系统生成的兜底检索词' }}</span>
            <code v-for="query in externalSearchQueries" :key="query">{{ query }}</code>
          </div>
          <div class="external-search-actions">
            <button
              type="button"
              class="external-search-button"
              :disabled="busy || !externalSearchQueries.length"
              @click="$emit('search-external', externalSearchQueries)"
            >{{ externalSearching ? '正在检索公开资料…' : (externalCandidates.length ? '重新检索' : '检索公开资料') }}</button>
            <span>检索由独立学术数据源执行，不会把联网权限交给补全模型。</span>
          </div>

          <div v-if="externalCandidates.length" class="external-results">
            <section v-if="importedExternalCandidates.length" class="imported-results">
              <div class="imported-results-heading">
                <div>
                  <strong>已加入知识库</strong>
                  <p>这些摘要已形成可追踪 Chunk，并已送入本轮补全上下文。</p>
                </div>
                <span>{{ importedExternalCandidates.length }}</span>
              </div>
              <article v-for="item in importedExternalCandidates" :key="item.result_id" class="imported-result">
                <div class="external-result-body">
                  <span class="source-meta">
                    <b>{{ providerSummary(item) }}</b>
                    <span v-if="item.year">{{ item.year }}</span>
                    <span v-if="item.venue">{{ item.venue }}</span>
                  </span>
                  <strong class="source-title">{{ item.title }}</strong>
                  <span v-if="item.abstract" class="source-abstract">{{ item.abstract }}</span>
                  <span class="imported-chunk">Chunk {{ item.chunk_id }}</span>
                </div>
                <div class="source-actions">
                  <a v-if="item.url" class="source-link" :href="item.url" target="_blank" rel="noopener noreferrer">查看来源</a>
                  <button type="button" class="text-action danger" :disabled="busy" @click="$emit('deactivate-external', item.chunk_id)">停用资料</button>
                </div>
              </article>
            </section>

            <div v-if="searchableExternalCandidates.length" class="external-results-heading">
              <div>
                <strong>可作为证据的摘要</strong>
                <p>只会导入你勾选的题录与摘要，不会自动下载论文全文。</p>
              </div>
              <span>{{ selectedExternalIds.length }} / {{ evidenceReadyCandidates.length }} 已选</span>
            </div>
            <article
              v-for="item in evidenceReadyCandidates"
              :key="item.result_id"
              class="external-result"
              :class="{ selected: selectedExternalIds.includes(item.result_id) }"
            >
              <label class="external-result-select">
                <input
                  v-model="selectedExternalIds"
                  type="checkbox"
                  :value="item.result_id"
                  :disabled="busy"
                />
                <span class="external-result-body">
                  <span class="source-meta">
                    <b>{{ providerSummary(item) }}</b>
                    <span class="relevance-badge" :class="`relevance-${item.relevance_level || 'unknown'}`">{{ relevanceLabel(item) }}</span>
                    <span v-if="item.year">{{ item.year }}</span>
                    <span v-if="item.venue">{{ item.venue }}</span>
                  </span>
                  <strong class="source-title">{{ item.title }}</strong>
                  <span v-if="item.authors?.length" class="source-authors">{{ item.authors.slice(0, 4).join('、') }}</span>
                  <span class="source-abstract">{{ item.abstract }}</span>
                  <span v-if="item.relevance_reason" class="relevance-reason">{{ item.relevance_reason }}</span>
                </span>
              </label>
              <div class="source-actions">
                <a v-if="item.url" class="source-link" :href="item.url" target="_blank" rel="noopener noreferrer">查看来源</a>
                <button v-if="item.open_access_url" type="button" class="text-action" :disabled="busy" @click="$emit('acquire-fulltext', item.result_id)">获取开放全文</button>
              </div>
            </article>
            <div v-if="searchableExternalCandidates.length && !evidenceReadyCandidates.length" class="external-empty-state">
              <strong>本次没有找到可核验摘要</strong>
              <span>下方题录仍可用于查阅，但不会被写入知识库或作为补全证据。</span>
            </div>
            <button
              v-if="evidenceReadyCandidates.length"
              type="button"
              class="external-import-button"
              :disabled="busy || !selectedExternalIds.length"
              @click="$emit('import-external', [...selectedExternalIds])"
            >{{ externalImporting ? '正在入库并重新生成…' : '加入知识库并重新生成' }}</button>

            <details v-if="metadataOnlyCandidates.length" class="metadata-only-results">
              <summary>
                <span>仅有题录，暂不能作为证据</span>
                <b>{{ metadataOnlyCandidates.length }}</b>
              </summary>
              <p>这些结果没有可核验摘要。你仍可打开来源核对，系统不会允许选择或导入。</p>
              <div class="metadata-only-list">
                <article v-for="item in metadataOnlyCandidates" :key="item.result_id" class="metadata-only-result">
                  <div class="external-result-body">
                    <span class="source-meta">
                      <b>{{ providerSummary(item) }}</b>
                      <span class="relevance-badge" :class="`relevance-${item.relevance_level || 'unknown'}`">{{ relevanceLabel(item) }}</span>
                      <span v-if="item.year">{{ item.year }}</span>
                      <span v-if="item.venue">{{ item.venue }}</span>
                    </span>
                    <strong class="source-title">{{ item.title }}</strong>
                    <span v-if="item.authors?.length" class="source-authors">{{ item.authors.slice(0, 4).join('、') }}</span>
                    <span class="source-unavailable">尚未获得摘要，不能作为补全证据。</span>
                  </div>
                  <div class="source-actions">
                    <a v-if="item.url" class="source-link" :href="item.url" target="_blank" rel="noopener noreferrer">查看来源</a>
                    <button v-if="item.open_access_url" type="button" class="text-action" :disabled="busy" @click="$emit('acquire-fulltext', item.result_id)">获取开放全文</button>
                  </div>
                </article>
              </div>
            </details>
          </div>
          <p v-else-if="!externalSearching" class="phase-note">搜索结果会先展示给你审核；只有被选中的摘要会形成可追踪 Chunk。</p>
        </div>

        <div v-else-if="proposalStatus === 'failed'" class="error-state">
          <strong>这次建议生成失败</strong>
          <p>{{ proposal?.error || 'LLM 或本地检索暂时不可用。你可以重试，Gap 数据没有发生变化。' }}</p>
        </div>

        <div v-else-if="proposalStatus === 'stale'" class="error-state">
          <strong>建议已经过期</strong>
          <p>Gap 在建议生成后发生了变化，请关闭窗口刷新，或针对最新 Gap 重新生成。</p>
        </div>

        <div v-else-if="proposalStatus === 'rejected'" class="error-state neutral-state">
          <strong>这条建议已被拒绝</strong>
          <p>Gap 仍然保持开放。你可以重新生成建议，或暂时保留它。</p>
        </div>

        <p v-if="error" class="review-error" role="alert">{{ error }}</p>

        <details v-if="proposalHistory.length" class="proposal-history">
          <summary>建议与审核记录 <span>{{ proposalHistory.length }}</span></summary>
          <ol>
            <li v-for="item in proposalHistory" :key="item.proposal_id">
              <span class="history-marker" :class="`history-${item.status}`"></span>
              <div>
                <strong>{{ statusLabel(item.status) }}</strong>
                <small>{{ formatTime(item.created_at) }} · {{ item.provider || '系统' }} {{ item.model || '' }}</small>
                <p v-if="item.error">{{ item.error }}</p>
                <p v-else-if="item.proposal?.explanation">{{ item.proposal.explanation }}</p>
                <span v-if="importedCount(item)" class="history-evidence">外部证据 {{ importedCount(item) }} 项</span>
              </div>
            </li>
          </ol>
        </details>

        <details class="manual-fallback" :open="manualOpen" @toggle="manualOpen = $event.target.open">
          <summary>高级：手动补充</summary>
          <form @submit.prevent="submitManual">
            <p>仅在你已有可靠资料、或 AI 服务不可用时使用。类型和顺序仍由范式锁定。</p>
            <section v-for="(missingType, index) in gap.missing_types || []" :key="`manual-${missingType}-${index}`">
              <strong>{{ index + 1 }}. {{ typeLabel(missingType) }}</strong>
              <div class="manual-mode">
                <button type="button" :class="{ active: manualForms[index].mode === 'new' }" @click="manualForms[index].mode = 'new'">创建概念</button>
                <button type="button" :class="{ active: manualForms[index].mode === 'existing' }" @click="manualForms[index].mode = 'existing'">修复到已有概念</button>
              </div>
              <select v-if="manualForms[index].mode === 'existing'" v-model="manualForms[index].canonical_id" required>
                <option value="" disabled>请选择 {{ typeLabel(missingType) }}</option>
                <option v-for="concept in conceptsOfType(missingType)" :key="concept.id" :value="concept.id">{{ concept.name }}</option>
              </select>
              <template v-else>
                <input v-model.trim="manualForms[index].name" required maxlength="255" placeholder="概念名称" />
                <textarea v-model.trim="manualForms[index].description" required maxlength="4000" rows="2" placeholder="概念描述与资料依据"></textarea>
              </template>
            </section>
            <button class="manual-submit" type="submit" :disabled="busy">确认手动补充</button>
          </form>
        </details>

        <footer class="review-actions">
          <button type="button" class="secondary" :disabled="busy" @click="requestClose">保留 Gap</button>
          <button
            v-if="proposalStatus === 'ready'"
            type="button"
            class="secondary"
            :disabled="busy"
            @click="editing = !editing"
          >{{ editing ? '取消编辑' : '编辑建议' }}</button>
          <button
            v-if="['ready', 'needs_external_evidence'].includes(proposalStatus)"
            type="button"
            class="danger-quiet"
            :disabled="busy"
            @click="$emit('reject')"
          >拒绝建议</button>
          <button
            v-if="['ready', 'failed', 'stale', 'rejected', 'superseded', 'needs_external_evidence'].includes(proposalStatus)"
            type="button"
            class="secondary"
            :disabled="busy"
            @click="$emit('generate')"
          >重新生成</button>
          <button
            v-if="proposalStatus === 'ready'"
            type="button"
            class="primary"
            :disabled="busy || !reviewIsValid"
            @click="acceptProposal"
          >{{ submitting ? '正在写入…' : '确认并写入图谱' }}</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { buildGapSearchQueries, stripEvidenceField } from './gapGraph.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  gap: { type: Object, default: null },
  sourceConcept: { type: Object, default: null },
  targetConcept: { type: Object, default: null },
  concepts: { type: Array, default: () => [] },
  typeLabels: { type: Object, default: () => ({}) },
  proposal: { type: Object, default: null },
  proposalHistory: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  submitting: { type: Boolean, default: false },
  externalSearching: { type: Boolean, default: false },
  externalImporting: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits([
  'close', 'generate', 'accept', 'reject', 'manual-submit',
  'search-external', 'import-external',
  'deactivate-external', 'acquire-fulltext',
])
const reviewForms = reactive([])
const manualForms = reactive([])
const editing = ref(false)
const manualOpen = ref(false)
const selectedExternalIds = ref([])

const proposalStatus = computed(() => props.proposal?.status || (props.loading ? 'generating' : ''))
const proposalPayload = computed(() => props.proposal?.proposal || {})
const proposalConcepts = computed(() => proposalPayload.value.concepts || [])
const duplicateCandidates = computed(() => props.proposal?.duplicate_candidates || [])
const externalCandidates = computed(() => (props.proposal?.source_recommendations || [])
  .filter(item => item?.result_id))
const importedExternalCandidates = computed(() => externalCandidates.value.filter(item => item.status === 'imported'))
const searchableExternalCandidates = computed(() => externalCandidates.value.filter(item => item.status !== 'imported'))
const evidenceReadyCandidates = computed(() => searchableExternalCandidates.value.filter(item => item.evidence_ready && item.abstract))
const metadataOnlyCandidates = computed(() => searchableExternalCandidates.value.filter(item => !item.evidence_ready || !item.abstract))
const externalSearchQueries = computed(() => buildGapSearchQueries({
  recommended: proposalPayload.value.recommended_search_queries || [],
  sourceConcept: props.sourceConcept,
  targetConcept: props.targetConcept,
  missingTypes: props.gap?.missing_types || [],
  typeLabels: props.typeLabels,
}))
const busy = computed(() => props.submitting || props.externalSearching || props.externalImporting)
const reviewIsValid = computed(() => reviewForms.length === proposalConcepts.value.length && reviewForms.every(item => item.name.trim() && item.description.trim()))

watch(() => [props.proposal?.proposal_id, props.proposal?.status], seedReviewForms, { immediate: true })
watch(() => props.proposal?.proposal_id, () => { selectedExternalIds.value = [] })
watch(externalCandidates, candidates => {
  const available = new Set(candidates.filter(item => item.status !== 'imported' && item.evidence_ready).map(item => item.result_id))
  selectedExternalIds.value = selectedExternalIds.value.filter(id => available.has(id))
})
watch(() => [props.visible, props.gap?.gap_id], seedManualForms, { immediate: true })

function seedReviewForms() {
  editing.value = false
  reviewForms.splice(0, reviewForms.length, ...proposalConcepts.value.map(concept => ({
    name: concept.name || '',
    concept_type: concept.concept_type,
    description: stripEvidenceField(concept.description),
    aliasText: (concept.aliases || []).join('\n'),
  })))
}
function seedManualForms() {
  manualOpen.value = false
  manualForms.splice(0, manualForms.length, ...((props.gap?.missing_types || []).map(type => ({
    mode: 'new', canonical_id: '', name: '', description: '', concept_type: type,
  }))))
}
function typeLabel(type) { return props.typeLabels?.[type] || type || '概念' }
function confidencePercent(value) { return Math.round(Math.max(0, Math.min(Number(value) || 0, 1)) * 100) }
function providerLabel(provider) {
  return ({ crossref: 'Crossref', openalex: 'OpenAlex' })[provider] || provider || '学术数据源'
}
function providerSummary(item) {
  const providers = (item.providers?.length ? item.providers : [item.provider]).filter(Boolean)
  const label = [...new Set(providers)].map(providerLabel).join(' + ') || '学术数据源'
  if (item.abstract_provider && item.abstract_provider !== item.provider) {
    return `${label} · ${providerLabel(item.abstract_provider)} 摘要`
  }
  return label
}
function relevanceLabel(item) {
  const labels = { high: '高相关', medium: '中相关', low: '低相关', unknown: '待判断' }
  const score = Math.round((Number(item.relevance_score) || 0) * 100)
  return `${labels[item.relevance_level] || labels.unknown}${score ? ` ${score}%` : ''}`
}
function statusLabel(status) {
  return ({
    generating: '生成中', ready: '待确认', needs_external_evidence: '需要外部证据',
    applying: '写入中', accepted: '已接受', rejected: '已拒绝', superseded: '已被新建议替代',
    failed: '生成失败', stale: '已过期',
  })[status] || status
}
function formatTime(value) {
  if (!value) return '时间未知'
  try { return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) }
  catch { return value }
}
function importedCount(proposal) {
  return (proposal?.source_recommendations || []).filter(item => item?.status === 'imported').length
}
function conceptsOfType(type) { return props.concepts.filter(item => item.type === type && !item.is_virtual) }
function requestClose() { if (!busy.value) emit('close') }
function acceptProposal() {
  if (!reviewIsValid.value) return
  emit('accept', reviewForms.map(item => ({
    name: item.name.trim(),
    concept_type: item.concept_type,
    description: item.description.trim(),
    aliases: item.aliasText.split(/\r?\n/).map(alias => alias.trim()).filter(Boolean),
  })))
}
function submitManual() {
  emit('manual-submit', manualForms.map((form, index) => form.mode === 'existing'
    ? { canonical_id: form.canonical_id }
    : {
        name: form.name,
        concept_type: props.gap.missing_types[index],
        description: form.description,
        evidence: null,
      }))
}
</script>

<style scoped>
.gap-review-overlay { position: fixed; inset: 0; z-index: 10030; display: grid; place-items: center; padding: 24px; background: rgba(20, 28, 36, .58); }
.gap-review { width: min(780px, 96vw); max-height: 92vh; overflow-y: auto; box-sizing: border-box; border-radius: 16px; background: var(--bg-card, #fff); color: var(--text-primary, #243342); box-shadow: 0 28px 80px rgba(12, 20, 28, .32); scrollbar-color: #b9c4cc transparent; }
.review-header { position: sticky; top: 0; z-index: 2; display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 22px 24px 16px; background: var(--bg-card, #fff); border-bottom: 1px solid var(--border-color, #e2e7ea); }
.review-header h2 { margin: 0 0 6px; font-size: 22px; letter-spacing: -.02em; }
.review-header p { margin: 0; color: var(--text-secondary, #566573); font-size: 13px; }
.close-button { display: grid; place-items: center; width: 34px; height: 34px; border: 0; border-radius: 10px; background: var(--bg-hover, #eef2f4); color: inherit; cursor: pointer; }
.close-button svg { width: 18px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; }
.knowledge-chain { display: flex; align-items: stretch; gap: 8px; overflow-x: auto; padding: 18px 24px 6px; }
.chain-node { flex: 0 0 150px; display: grid; align-content: center; gap: 4px; min-height: 58px; padding: 10px 12px; border-radius: 12px; }
.chain-node span { color: var(--text-secondary, #566573); font-size: 11px; }
.chain-node strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.chain-node.endpoint { background: var(--bg-hover, #edf2f4); }
.chain-node.missing { background: #fff3e5; color: #8a430a; outline: 1px dashed #df8a38; outline-offset: -1px; }
.chain-node.missing span { color: #9f581e; }
.chain-arrow { display: grid; place-items: center; color: #8b98a3; }
.generation-state, .proposal-summary, .evidence-missing, .error-state { margin: 18px 24px; padding: 18px; border-radius: 14px; background: var(--bg-hover, #eef2f4); }
.generation-state { display: flex; align-items: center; gap: 16px; }
.generation-pulse { width: 16px; height: 16px; flex: 0 0 auto; border-radius: 50%; background: #d97016; box-shadow: 0 6px 18px rgba(217, 112, 22, .3); animation: breathe 1.4s ease-out infinite; }
.generation-state p, .proposal-summary p, .evidence-missing p, .error-state p { margin: 5px 0 0; color: var(--text-secondary, #566573); font-size: 13px; line-height: 1.55; }
.proposal-summary { display: flex; align-items: center; justify-content: space-between; gap: 20px; background: #edf7f1; color: #234e35; }
.proposal-summary p { color: #466a55; }
.confidence-value { font-variant-numeric: tabular-nums; font-size: 24px; font-weight: 750; }
.proposal-list { display: grid; gap: 14px; padding: 0 24px 18px; }
.proposal-concept { padding: 17px 18px; border-radius: 14px; background: var(--bg-main, #f7f9fa); }
.concept-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.concept-heading h3 { margin: 8px 0 0; font-size: 18px; }
.type-tag { display: inline-flex; padding: 3px 8px; border-radius: 999px; background: #e7edf9; color: #365b9b; font-size: 11px; font-weight: 700; }
.concept-confidence { color: var(--text-secondary, #566573); font-size: 12px; font-variant-numeric: tabular-nums; }
.concept-description { max-width: 70ch; margin: 13px 0; line-height: 1.65; }
.reuse-note { margin-top: 13px; padding: 10px 12px; border-radius: 10px; background: #e8f5ed; color: #296240; font-size: 12px; line-height: 1.5; }
.proposal-concept label { display: grid; gap: 6px; margin-top: 12px; color: var(--text-secondary, #566573); font-size: 12px; }
.proposal-concept input, .proposal-concept textarea, .manual-fallback input, .manual-fallback textarea, .manual-fallback select { box-sizing: border-box; width: 100%; padding: 9px 11px; border: 1px solid var(--border-color, #d4dce1); border-radius: 10px; background: var(--bg-card, #fff); color: inherit; font: inherit; }
.proposal-concept textarea, .manual-fallback textarea { resize: vertical; }
.evidence-details { margin-top: 12px; font-size: 12px; }
.evidence-details summary, .manual-fallback > summary { color: #8a4a12; cursor: pointer; font-weight: 650; }
.evidence-details blockquote { margin: 10px 0 0; padding: 11px 13px; border: 0; border-radius: 10px; background: var(--bg-card, #fff); }
.evidence-details blockquote p { margin: 0 0 7px; line-height: 1.55; }
.evidence-details cite { color: var(--text-secondary, #566573); font-style: normal; }
.risk-note { margin: 0 24px 18px; padding: 14px 16px; border-radius: 12px; background: #fff3e5; color: #744019; }
.risk-note p { margin: 5px 0; font-size: 12px; }
.risk-note ul, .evidence-missing ul { margin: 8px 0 0; padding-left: 20px; font-size: 12px; }
.evidence-missing { background: #fff3e5; color: #744019; }
.error-state { background: #fff0ef; color: #8d2923; }
.neutral-state { background: var(--bg-hover, #eef2f4); color: var(--text-primary, #243342); }
.search-suggestions { display: grid; gap: 7px; margin-top: 15px; }
.search-suggestions span { font-size: 12px; font-weight: 700; }
.search-suggestions code { padding: 8px 10px; border-radius: 8px; background: rgba(255, 255, 255, .64); white-space: normal; }
.phase-note { font-size: 11px !important; }
.external-search-actions { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
.external-search-actions span { color: #7b5a3e; font-size: 11px; line-height: 1.45; }
.external-search-button, .external-import-button { border: 0; border-radius: 9px; padding: 9px 13px; background: #b85b10; color: #fff; font: inherit; font-size: 12px; font-weight: 700; cursor: pointer; }
.external-results { display: grid; gap: 10px; margin-top: 16px; padding-top: 15px; border-top: 1px solid rgba(116, 64, 25, .18); }
.external-results-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.external-results-heading p { margin-top: 3px; font-size: 11px; }
.external-results-heading > span { flex: 0 0 auto; color: #7b5a3e; font-size: 11px; font-variant-numeric: tabular-nums; }
.imported-results { display: grid; gap: 8px; margin-bottom: 4px; padding: 12px; border: 1px solid #b9ddc7; border-radius: 11px; background: #f0f8f3; }
.imported-results-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; color: #285e3d; }
.imported-results-heading p { margin: 3px 0 0; color: #4d705b; font-size: 11px; }
.imported-results-heading > span { min-width: 24px; padding: 2px 7px; border-radius: 999px; background: #d9eee1; text-align: center; font-size: 10px; font-variant-numeric: tabular-nums; }
.imported-result { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: start; gap: 12px; padding-top: 9px; border-top: 1px solid rgba(40, 94, 61, .14); }
.imported-chunk { overflow: hidden; color: #557363; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.external-result { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: start; gap: 12px; padding: 12px; border: 1px solid rgba(116, 64, 25, .16); border-radius: 11px; background: rgba(255, 255, 255, .68); }
.external-result.selected { border-color: #c96a1b; box-shadow: inset 3px 0 #c96a1b; }
.external-result-select { display: grid; grid-template-columns: 18px minmax(0, 1fr); align-items: start; min-width: 0; gap: 11px; cursor: pointer; }
.external-result-select input[type="checkbox"] { box-sizing: border-box; width: 18px; min-width: 18px; height: 18px; margin: 2px 0 0; padding: 0; border-radius: 4px; accent-color: #b85b10; }
.external-result-body { display: grid; min-width: 0; max-width: 100%; gap: 5px; }
.source-meta { display: flex; flex-wrap: wrap; gap: 7px; color: #7b5a3e; font-size: 10px; }
.relevance-badge { padding: 1px 6px; border-radius: 999px; font-weight: 700; }
.relevance-high { background: #dcefe3; color: #286141; }
.relevance-medium { background: #fff0ce; color: #825510; }
.relevance-low { background: #f7dedd; color: #8d2923; }
.relevance-unknown { background: #e8ecef; color: #566573; }
.relevance-reason { color: #7b5a3e; font-size: 10px; line-height: 1.45; }
.source-title { color: #4e2c13; font-size: 13px; line-height: 1.4; overflow-wrap: anywhere; }
.source-authors { color: #6e5e52; font-size: 11px; overflow-wrap: anywhere; }
.source-abstract { display: -webkit-box; overflow: hidden; color: #5e5148; font-size: 11px; line-height: 1.5; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.source-unavailable { color: #8d2923; font-size: 11px; line-height: 1.45; }
.source-link { display: inline-flex; align-items: center; align-self: start; min-height: 28px; padding: 0 2px; color: #8a4a12; font-size: 11px; font-weight: 650; white-space: nowrap; text-underline-offset: 3px; }
.source-actions { display: grid; justify-items: end; gap: 4px; }
.text-action { border: 0; padding: 3px 2px; background: transparent; color: #8a4a12; font: inherit; font-size: 10px; font-weight: 700; cursor: pointer; }
.text-action.danger { color: #9e3029; }
.external-import-button { justify-self: end; margin-top: 2px; }
.external-empty-state { display: grid; gap: 4px; padding: 13px 14px; border: 1px dashed rgba(116, 64, 25, .24); border-radius: 10px; color: #6e5e52; }
.external-empty-state strong { color: #4e2c13; font-size: 12px; }
.external-empty-state span { font-size: 11px; line-height: 1.5; }
.metadata-only-results { margin-top: 4px; padding-top: 12px; border-top: 1px solid rgba(116, 64, 25, .15); }
.metadata-only-results > summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #654126; cursor: pointer; font-size: 12px; font-weight: 700; list-style: none; }
.metadata-only-results > summary::-webkit-details-marker { display: none; }
.metadata-only-results > summary::before { content: '›'; color: #9a6b45; font-size: 17px; line-height: 1; transition: transform .16s ease; }
.metadata-only-results[open] > summary::before { transform: rotate(90deg); }
.metadata-only-results > summary span { flex: 1; }
.metadata-only-results > summary b { min-width: 24px; padding: 2px 7px; border-radius: 999px; background: rgba(116, 64, 25, .09); text-align: center; font-size: 10px; font-variant-numeric: tabular-nums; }
.metadata-only-results > p { margin: 8px 0 10px; color: #7b5a3e; font-size: 11px; line-height: 1.5; }
.metadata-only-list { display: grid; gap: 8px; }
.metadata-only-result { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: start; gap: 12px; padding: 11px 12px; border: 1px solid rgba(116, 64, 25, .14); border-radius: 8px; background: rgba(255, 255, 255, .42); }
.review-error { margin: 0 24px 16px; color: #a32f29; font-size: 13px; }
.evidence-governance { display: grid; gap: 9px; margin: 0 24px 18px; padding: 14px 16px; border: 1px solid #b9ddc7; border-radius: 12px; background: #f0f8f3; color: #285e3d; }
.evidence-governance p { margin: 3px 0 0; color: #4d705b; font-size: 11px; }
.evidence-governance article { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 9px; border-top: 1px solid rgba(40, 94, 61, .14); }
.evidence-governance article > span { display: grid; min-width: 0; gap: 3px; }
.evidence-governance b { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.evidence-governance small { color: #557363; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 9px; }
.evidence-governance button { flex: 0 0 auto; border: 0; background: transparent; color: #9e3029; font: inherit; font-size: 10px; font-weight: 700; cursor: pointer; }
.proposal-history { margin: 0 24px 18px; padding: 13px 15px; border: 1px solid var(--border-color, #dce2e6); border-radius: 12px; background: var(--bg-card, #fff); }
.proposal-history > summary { display: flex; align-items: center; justify-content: space-between; cursor: pointer; font-size: 12px; font-weight: 700; }
.proposal-history > summary span { min-width: 24px; padding: 2px 7px; border-radius: 999px; background: var(--bg-hover, #eef2f4); text-align: center; font-size: 10px; }
.proposal-history ol { display: grid; gap: 0; margin: 12px 0 0; padding: 0; list-style: none; }
.proposal-history li { display: grid; grid-template-columns: 12px minmax(0, 1fr); gap: 10px; padding: 10px 0; border-top: 1px solid var(--border-color, #e2e7ea); }
.history-marker { width: 8px; height: 8px; margin-top: 4px; border-radius: 50%; background: #8b98a3; }
.history-ready, .history-accepted { background: #2d8a57; }
.history-needs_external_evidence { background: #d97016; }
.history-failed, .history-rejected { background: #bd463d; }
.proposal-history li > div { display: grid; gap: 3px; }
.proposal-history small { color: var(--text-secondary, #566573); font-size: 10px; }
.proposal-history p { display: -webkit-box; overflow: hidden; margin: 2px 0 0; color: var(--text-secondary, #566573); font-size: 11px; line-height: 1.45; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.history-evidence { color: #285e3d; font-size: 10px; font-weight: 700; }
.manual-fallback { margin: 0 24px 18px; padding: 13px 15px; border-radius: 12px; background: var(--bg-hover, #eef2f4); }
.manual-fallback form > p { color: var(--text-secondary, #566573); font-size: 12px; }
.manual-fallback form section { display: grid; gap: 8px; padding: 12px 0; border-top: 1px solid var(--border-color, #dce2e6); }
.manual-mode { display: flex; gap: 7px; }
.manual-mode button, .manual-submit { border: 0; border-radius: 8px; padding: 7px 10px; background: var(--bg-card, #fff); color: inherit; cursor: pointer; }
.manual-mode button.active { background: #d97016; color: #fff; }
.manual-submit { justify-self: end; margin-top: 10px; background: #d97016; color: #fff; }
.review-actions { position: sticky; bottom: 0; display: flex; justify-content: flex-end; gap: 9px; padding: 15px 24px 20px; background: var(--bg-card, #fff); border-top: 1px solid var(--border-color, #e2e7ea); }
.review-actions button { border-radius: 10px; padding: 9px 13px; font-weight: 650; cursor: pointer; }
.review-actions .secondary { border: 1px solid var(--border-color, #d4dce1); background: transparent; color: inherit; }
.review-actions .danger-quiet { border: 0; background: #fff0ef; color: #9e3029; }
.review-actions .primary { border: 0; background: #d97016; color: #fff; box-shadow: 0 7px 18px rgba(184, 84, 8, .22); }
button:disabled { opacity: .52; cursor: not-allowed; }
button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible, summary:focus-visible { outline: 3px solid rgba(57, 117, 196, .32); outline-offset: 2px; }
::selection { background: #f2b77f; color: #3d2008; }
@keyframes breathe { 50% { transform: scale(.68); filter: blur(.4px); } }
@media (prefers-reduced-motion: reduce) { .generation-pulse { animation: none; } }
@media (max-width: 680px) {
  .gap-review-overlay { padding: 0; align-items: end; }
  .gap-review { width: 100%; max-height: 96vh; border-radius: 16px 16px 0 0; }
  .review-header, .knowledge-chain, .proposal-list, .review-actions { padding-left: 16px; padding-right: 16px; }
  .generation-state, .proposal-summary, .evidence-missing, .error-state, .risk-note, .manual-fallback, .review-error { margin-left: 16px; margin-right: 16px; }
  .review-actions { flex-wrap: wrap; }
  .review-actions .primary { width: 100%; order: -1; }
  .external-search-actions, .external-results-heading { align-items: stretch; flex-direction: column; }
  .external-result { grid-template-columns: 1fr; }
  .imported-result { grid-template-columns: 1fr; }
  .metadata-only-result { grid-template-columns: 1fr; }
  .source-actions { justify-items: start; }
  .evidence-governance article { align-items: flex-start; }
}
</style>
