<template>
  <div class="graph-view">
    <!-- 顶部标题栏 -->
    <header class="view-header">
      <div class="header-title">
        <span class="header-icon">🕸️</span>
        <span>知识图谱</span>
      </div>
      <div class="header-subject">
        <span class="tag">{{ currentSubjectName }}</span>
      </div>
    </header>

    <div class="graph-container">
      <!-- 工具栏 -->
      <div class="toolbar">
        <div v-if="viewMode !== 'catalog'" class="toolbar-group">
          <input
            v-model="searchQuery"
            class="search-input"
            placeholder="🔍 搜索节点..."
            @keyup.enter="searchNode"
          />
          <button class="btn btn-sm" @click="searchNode">搜索</button>
        </div>
        <div class="toolbar-group">
          <button
            class="btn btn-sm"
            :class="{ 'btn-primary': viewMode === 'document' }"
            @click="switchViewMode('document')"
            title="文档结构树"
            :aria-pressed="viewMode === 'document'"
          >📄 文档树</button>
          <button
            class="btn btn-sm"
            :class="{ 'btn-primary': viewMode === 'catalog' }"
            @click="switchViewMode('catalog')"
            title="浏览全局去重概念"
            :aria-pressed="viewMode === 'catalog'"
          >📋 全局概念</button>
          <button
            class="btn btn-sm"
            :class="{ 'btn-primary': viewMode === 'concept' }"
            @click="switchViewMode('concept')"
            title="知识图谱"
            :aria-pressed="viewMode === 'concept'"
          >🧩 知识图谱</button>
          <button v-if="viewMode !== 'catalog'" class="btn btn-sm" @click="fitGraph" title="适应窗口">⬜ 适应</button>
          <button v-if="viewMode !== 'catalog'" class="btn btn-sm" @click="resetLayout" title="重置布局">🔄 重置</button>
          <nav
            v-if="viewMode === 'concept' && conceptTreePages.length"
            class="tree-pager"
            aria-label="知识树分页"
          >
            <button
              class="tree-page-button"
              type="button"
              :disabled="currentTreePage <= 0"
              aria-label="上一棵树"
              @click="changeTreePage(currentTreePage - 1)"
            >‹</button>
            <select
              v-model.number="currentTreePage"
              class="tree-page-select"
              aria-label="选择知识树"
              @change="applyTreePage()"
            >
              <option v-for="(tree, index) in conceptTreePages" :key="tree.id" :value="index">
                {{ index + 1 }}. {{ tree.rootLabel }} · {{ tree.nodeCount }} 节点
              </option>
            </select>
            <span class="tree-page-count">{{ currentTreePage + 1 }} / {{ conceptTreePages.length }}</span>
            <button
              class="tree-page-button"
              type="button"
              :disabled="currentTreePage >= conceptTreePages.length - 1"
              aria-label="下一棵树"
              @click="changeTreePage(currentTreePage + 1)"
            >›</button>
          </nav>
          <button class="btn btn-sm btn-primary" @click="openBuildOptions" :disabled="isBuilding">
            <span v-if="isBuilding" class="spinner-inline"></span>
            <span v-else>🏗️ 构建图谱</span>
          </button>
        </div>
        <div class="toolbar-group">
          <span v-if="viewMode === 'catalog'" class="stats">概念: {{ conceptTable.length }}</span>
          <span v-else class="stats">节点: {{ nodeCount }} | 边: {{ edgeCount }}</span>
        </div>
      </div>

      <!-- 画布 + 图例 + 详情面板（M3-LAYOUT: 工具栏下方的独立行） -->
      <div v-show="viewMode !== 'catalog'" class="graph-body">
      <div class="canvas-wrapper" :style="canvasWrapperStyle">
        <div ref="cyContainer" class="cy-container"></div>

        <GapSummaryPanel
          v-if="viewMode === 'concept'"
          :summary="gapSummary"
          :gaps="filteredGaps"
          :status="gapStatus"
          :missing-type="gapMissingType"
          :min-confidence="gapMinConfidence"
          :type-labels="paradigmConfig?.types || {}"
          :loading="gapsLoading"
          :reconciling="gapsReconciling"
          :can-write="canWriteGaps"
          :error="gapError"
          @update:status="gapStatus = $event"
          @update:missing-type="gapMissingType = $event"
          @update:min-confidence="gapMinConfidence = $event"
          @select="focusGap"
          @supplement="openGapSupplement"
          @ignore="ignoreGap"
          @reopen="reopenGap"
          @refresh="refreshGapOverlay"
          @reconcile="reconcileGapData"
        />

        <div v-if="gapCompletionNotice" class="gap-completion-notice" role="status" aria-live="polite">
          <span>
            已补充 {{ supplementedNodeIds(gapCompletionNotice).length }} 个真实概念节点
          </span>
          <button type="button" @click="focusSupplementedGap(gapCompletionNotice)">重新定位</button>
          <button type="button" class="notice-close" aria-label="关闭提示" @click="gapCompletionNotice = null">×</button>
        </div>

        <GapNodeTooltip
          :visible="gapTooltipVisible"
          :gap="gapTooltipGap"
          :current-type="gapTooltipType"
          :position="gapTooltipPosition"
          :type-labels="paradigmConfig?.types || {}"
          :can-write="canWriteGaps"
          @hold="holdGapTooltip"
          @close="closeGapTooltip"
          @supplement="openGapSupplement"
          @ignore="ignoreGap"
          @reopen="reopenGap"
        />

        <div class="legend">
          <div class="legend-title">图例</div>
          <div v-if="viewMode === 'document'" class="legend-item">
            <span class="legend-shape circle" style="background: #3498db;"></span>
            <span>知识片段</span>
          </div>
          <div
            v-for="(label, type) in (viewMode === 'concept' ? paradigmConfig?.types || {} : {})"
            :key="`node-${type}`"
            class="legend-item"
          >
            <span class="legend-shape rect" :style="{ background: getConceptTypeColor(type) }"></span>
            <span>{{ label }}</span>
          </div>
          <div v-if="viewMode === 'concept'" class="legend-item">
            <span class="legend-shape gap-placeholder"></span>
            <span>待补充 Gap</span>
          </div>
          <div v-if="viewMode === 'document'" class="legend-item">
            <span class="legend-line" style="border-color: #3498db;"></span>
            <span>层级关系</span>
          </div>
          <div v-if="viewMode === 'document'" class="legend-item">
            <span class="legend-line" style="border-color: #95a5a6; border-style: dashed;"></span>
            <span>相邻关系</span>
          </div>
          <!-- LA-052: 动态渲染范式关系图例 -->
          <div v-for="(label, type) in (viewMode === 'concept' ? paradigmConfig?.relations || {} : {})" :key="type" class="legend-item">
            <span class="legend-line" :style="getLegendLineStyle(type)"></span>
            <span>{{ label }} ({{ type }})</span>
          </div>
        </div>
      </div>

      <!-- 右侧信息面板 -->
      <NodeDetailPanel
        :node="selectedNode"
        :concepts="selectedNodeConcepts"
        :concepts-loading="conceptsLoading"
        :is-extracting="isExtracting"
        :is-chunk-node="isChunkNodeType(selectedNode?.type)"
        :links="conceptNodeLinks"
        @close="selectedNode = null"
        @extract="extractConcepts"
        @expand="expandNeighbors"
        @focus="focusNode"
        @navigate-to-chunk="navigateToChunk"
        @share="handleShareNode"
      />
      </div>

      <ConceptTable
        v-if="viewMode === 'catalog'"
        :concepts="conceptTable"
        :type-labels="paradigmConfig?.types || {}"
        :relation-labels="paradigmConfig?.relations || {}"
        :type-colors="conceptTypeColors"
        @select="showConceptDetail"
      />
    </div>

    <!-- 构建配置覆盖层 -->
    <BuildOptions
      :visible="showBuildOptions"
      :is-building="isRebuilding"
      :progress="buildProgress"
      @close="showBuildOptions = false"
      @confirm="confirmBuild"
    />

    <!-- 概念详情弹窗 -->
    <div v-if="showConceptModal" class="modal-overlay" @click.self="showConceptModal = false">
      <div class="modal-content" v-if="selectedConcept">
        <div class="modal-header">
          <h3>📖 {{ selectedConcept.name }}</h3>
          <button class="btn-icon" @click="showConceptModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="modal-section">
            <span
              class="type-badge"
              :style="{ background: getConceptTypeColor(selectedConcept.concept_type), color: '#fff' }"
            >{{ typeLabel(selectedConcept.concept_type) }}</span>
          </div>
          <div v-if="selectedConcept.aliases && selectedConcept.aliases.length > 1" class="modal-section">
            <div class="modal-label">别名</div>
            <div class="modal-aliases">{{ selectedConcept.aliases.join(' | ') }}</div>
          </div>
          <div v-if="selectedConcept.source_chunks && selectedConcept.source_chunks.length > 0" class="modal-section">
            <div class="modal-label">来源 Chunk ({{ selectedConcept.source_chunk_count }} 个)</div>
            <div class="modal-source-list">
              <span
                v-for="chunk in selectedConcept.source_chunks"
                :key="chunk"
                class="modal-source-tag"
                @click="navigateToChunk(chunk)"
              >{{ chunk }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- LA-035-P10: 悬浮预览卡片 -->
    <GraphNodeTooltip
      v-model:visible="tooltipVisible"
      :node="tooltipNode"
      :position="tooltipPosition"
    />

    <GapSupplementModal
      v-if="showGapSupplement && activeGap"
      :visible="true"
      :gap="activeGap"
      :source-concept="conceptById(activeGap.source_id)"
      :target-concept="conceptById(activeGap.target_id)"
      :concepts="conceptTable"
      :type-labels="paradigmConfig?.types || {}"
      :proposal="gapProposal"
      :proposal-history="gapProposalHistory"
      :loading="gapProposalLoading"
      :submitting="gapActionPending"
      :external-searching="gapExternalSearching"
      :external-importing="gapExternalImporting"
      :error="gapActionError"
      @close="closeGapSupplement"
      @generate="generateGapProposal"
      @accept="acceptGapProposal"
      @reject="rejectGapProposal"
      @search-external="searchGapExternalEvidence"
      @import-external="importGapExternalEvidence"
      @deactivate-external="deactivateGapExternalEvidence"
      @acquire-fulltext="acquireGapExternalFulltext"
      @manual-submit="supplementGap"
    />

    <MergeReviewWorkspace
      :visible="showMergeReview"
      :subject-name="currentSubjectName"
      :candidates="mergeCandidates"
      :loading="mergeReviewLoading"
      :saving="mergeReviewSaving"
      :submitting="mergeReviewSubmitting"
      :advising="mergeAdviceLoading"
      :bulk-accepting="mergeAdviceAccepting"
      :error="mergeReviewError"
      @close="showMergeReview = false"
      @save="saveMergeDecision"
      @submit="submitMergeReview"
      @request-advice="requestMergeAdvice"
      @accept-advice="acceptMergeAdvice"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, inject, nextTick } from 'vue'
import cytoscape from 'cytoscape'
import cola from 'cytoscape-cola'
import dagre from 'cytoscape-dagre'
import {
  CONCEPT_TYPE_COLORS,
  buildCyStyles,
  getConceptTypeBorderColor,
  getConceptTypeColor,
} from './GraphStyles.js'
import { runTreeLayout, runConceptLayout, generateNodeLabel, buildUMLCardLabel } from './GraphLayout.js'
import {
  applyConceptTreePage,
  clearConceptTreePage,
  filterGapsForConceptTree,
  findConceptTreePage,
} from './ConceptTreePaging.js'
import {
  clearConfigCache,
  getRelationLabel,
  getRelationStyle,
  loadParadigmConfig,
} from './ParadigmConfig.js'
import NodeDetailPanel from './NodeDetailPanel.vue'
import BuildOptions from './BuildOptions.vue'
import ConceptTable from './ConceptTable.vue'
import GraphNodeTooltip from './GraphNodeTooltip.vue'
import GapSummaryPanel from './GapSummaryPanel.vue'
import GapNodeTooltip from './GapNodeTooltip.vue'
import GapSupplementModal from './GapSupplementModal.vue'
import MergeReviewWorkspace from './MergeReviewWorkspace.vue'
import {
  buildGapReplacementIndex,
  buildVirtualGapElements,
  edgeMatchesGapIndex,
  filterGaps,
  stripEvidenceField,
  supplementedNodeIds,
  summarizeGaps,
  virtualGapNodeId,
} from './gapGraph.js'
import { withMediaAuth } from '../../utils/media.js'
import { busOn } from '../../utils/eventBus.js'
import {
  apiAcceptGapProposal, apiCreateGapProposal,
  apiAcquireGapExternalFulltext, apiDeactivateGapExternalEvidence,
  apiGetGapProposal, apiGetLatestGapProposal, apiIgnoreGap, apiListAllGaps,
  apiImportGapExternalEvidence, apiListGapProposals, apiReconcileGaps, apiRejectGapProposal,
  apiReopenGap, apiSearchGapExternalEvidence, apiSupplementGap,
} from '../../composables/useApi.js'

cytoscape.use(cola)
cytoscape.use(dagre)

// LA-051-P2-FIX: 认证 headers 辅助函数
function getAuthHeaders() {
  const saved = localStorage.getItem('la_current_user')
  const user = saved ? JSON.parse(saved) : null
  const userId = user?.user_id || 'default'
  const token = localStorage.getItem('la_auth_token') || ''
  return {
    'X-User-ID': userId,
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
  }
}

// ========== 全局学科状态 ==========
const subjectState = inject('subjectState')
const currentSubject = computed(() => subjectState.currentSubject.value)
const currentSubjectName = computed(() => {
  const sub = subjectState.subjects.value.find(s => s.id === currentSubject.value)
  return sub?.name || currentSubject.value
})
const currentSubjectInfo = computed(() => subjectState.subjects.value.find(s => s.id === currentSubject.value))
const canWriteGaps = computed(() => ['owner', 'maintainer'].includes(currentSubjectInfo.value?.role))

// ========== DOM 引用 ==========
const cyContainer = ref(null)

// ========== Cytoscape 实例 ==========
let cy = null

// ========== 状态 ==========
const nodes = ref([])
const edges = ref([])
const conceptTable = ref([])
const conceptTypeColors = CONCEPT_TYPE_COLORS
const selectedNode = ref(null)
const searchQuery = ref('')
const isBuilding = ref(false)
const isLoading = ref(false)
const nodeCount = ref(0)
const edgeCount = ref(0)
const conceptTreePages = ref([])
const currentTreePage = ref(0)

// Gap Flow M2: API records + frontend-only Cytoscape placeholders.
const gaps = ref([])
const gapStatus = ref('open')
const gapMissingType = ref('')
const gapMinConfidence = ref(0)
const gapsLoading = ref(false)
const gapsReconciling = ref(false)
const gapError = ref('')
const activeGap = ref(null)
const showGapSupplement = ref(false)
const gapActionPending = ref(false)
const gapActionError = ref('')
const gapProposal = ref(null)
const gapProposalHistory = ref([])
const gapProposalLoading = ref(false)
const gapExternalSearching = ref(false)
const gapExternalImporting = ref(false)
const gapTooltipVisible = ref(false)
const gapTooltipGap = ref(null)
const gapTooltipType = ref('')
const gapTooltipPosition = ref({ x: 0, y: 0 })
const gapCompletionNotice = ref(null)
let gapTooltipTimer = null
let gapRenderTimer = null
let gapLoadSequence = 0
let gapProposalPollTimer = null
const openFilteredGaps = computed(() => filterGaps(
  gaps.value.filter(gap => gap.status === 'open'),
  {
    missingType: gapMissingType.value,
    minConfidence: gapMinConfidence.value,
  },
))
const currentTreeAllGaps = computed(() => filterGapsForConceptTree(
  gaps.value,
  conceptTreePages.value[currentTreePage.value],
  cy,
))
const filteredGaps = computed(() => filterGaps(
  currentTreeAllGaps.value.filter(gap => gap.status === gapStatus.value),
  {
  missingType: gapMissingType.value,
  minConfidence: gapMinConfidence.value,
  },
))
const gapSummary = computed(() => summarizeGaps(currentTreeAllGaps.value))

// 视图模式：document 文档树 / catalog 全局概念 / concept 知识图谱
const viewMode = ref('concept')

// 构建选项
const showBuildOptions = ref(false)
const isRebuilding = ref(false)
const buildProgress = ref('')
const showMergeReview = ref(false)
const mergeBuildId = ref('')
const mergeCandidates = ref([])
const mergeReviewLoading = ref(false)
const mergeReviewSaving = ref(false)
const mergeReviewSubmitting = ref(false)
const mergeAdviceLoading = ref(false)
const mergeAdviceAccepting = ref(false)
const mergeReviewError = ref('')

// Phase 2: 概念分解
const selectedNodeConcepts = ref([])
const conceptsLoading = ref(false)
const isExtracting = ref(false)
const conceptNodeLinks = ref([])
const selectedParadigm = ref('theory')

// 概念弹窗
const selectedConcept = ref(null)
const showConceptModal = ref(false)

// LA-052: 范式配置（动态获取）
const paradigmConfig = ref(null)

// 图例行样式辅助函数
function getLegendLineStyle(relType) {
  const style = getRelationStyle(relType)
  if (!style) return {}
  return {
    borderColor: style.color,
    borderStyle: style.lineStyle === 'dashed' ? 'dotted' : style.lineStyle || 'solid',
  }
}
const tooltipVisible = ref(false)
const tooltipNode = ref(null)
const tooltipPosition = ref({ x: 0, y: 0 })
let tooltipTimer = null
let offGraphCommand = null  // LA-UI-001 M4: 图谱命令监听解绑函数

// 画布区域动态样式：避让右侧 absolute 定位的 NodeDetailPanel
const canvasWrapperStyle = computed(() => {
  // NodeDetailPanel 有节点时宽 300px，空状态时宽 200px
  const panelWidth = selectedNode.value ? 300 : 200
  return { marginRight: panelWidth + 'px' }
})

// LA-UI-001 M4-FIX2: 节点激活统一入口——
// tap 点击与 M4 命令联动共用同一路径（完整详情 + 关联加载 + 邻接高亮）
function activateNode(node) {
  const nodeType = node.data('type') || ''
  if (nodeType === 'virtual_gap') {
    const rp = node.renderedPosition()
    const containerRect = cy.container().getBoundingClientRect()
    showGapTooltip(node, {
      x: containerRect.left + rp.x,
      y: containerRect.top + rp.y,
    })
    return
  }
  selectedNode.value = {
    id: node.id(),
    label: node.data('label'),
    type: nodeType,
    chunk_type: node.data('type'),
    source: node.data('source'),
    page_number: node.data('page_number'),
    heading_path: node.data('heading_path') || '',
    text: node.data('text') || '',
    description: node.data('description') || '',
    parent_hint: node.data('parent_hint') || '',
    source_chunks: node.data('source_chunks') || '',
    source_refs: node.data('source_refs') || [],
    // LA-035: 图片节点字段
    image_path: node.data('image_path') || '',
    thumbnail_path: node.data('thumbnail_path') || '',
    width: node.data('width') || 0,
    height: node.data('height') || 0,
    // LA-035-P11: 多媒体引用（详情面板显示）
    media_refs: node.data('media_refs') || [],
  }
  if (isChunkNodeType(nodeType)) {
    loadConcepts(node.id())
  } else {
    selectedNodeConcepts.value = []
    loadConceptNodeLinks(node.id())
  }
  highlightNeighbors(node)
}

// ========== 初始化 Cytoscape ==========
function initCy() {
  if (!cyContainer.value) return

  cy = cytoscape({
    container: cyContainer.value,
    elements: [],
    style: buildCyStyles(),
    layout: { name: 'null' },
    minZoom: 0.1,
    maxZoom: 3,
  })

  window.cy = cy

  // 事件绑定
  cy.on('tap', 'node', (e) => {
    activateNode(e.target)
  })

  // LA-035-P10: 鼠标悬停显示预览卡片
  // P39-FIX: 支持文档树节点（heading/paragraph/document）显示 tooltip
  cy.on('mouseover', 'node', (e) => {
    const node = e.target
    const nodeType = node.data('type') || ''
    if (nodeType === 'virtual_gap') {
      if (tooltipTimer) clearTimeout(tooltipTimer)
      tooltipVisible.value = false
      const rp = node.renderedPosition()
      const containerRect = cy.container().getBoundingClientRect()
      showGapTooltip(node, {
        x: containerRect.left + rp.x,
        y: containerRect.top + rp.y,
      })
      return
    }
    // 对 chunk 节点（child/parent/markdown/heading/paragraph/document）和概念节点都显示 tooltip
    // 图片节点用特殊处理：将 imageUrl 转换为 media_refs 供 tooltip 显示
    let mediaRefs = node.data('media_refs') || []
    if ((nodeType === 'image' || nodeType === 'image_pseudo') && mediaRefs.length === 0) {
      // 优先使用已转换的 imageUrl（/api/images/... 格式），其次使用原始路径
      const imgUrl = node.data('imageUrl') || ''
      const imgPath = node.data('image_path') || node.data('thumbnail_path') || ''
      if (imgUrl) {
        mediaRefs = [{
          type: 'image',
          path: imgUrl,
          thumbnail_path: imgUrl,
          caption: node.data('label') || '图片',
        }]
      } else if (imgPath) {
        mediaRefs = [{
          type: 'image',
          path: imgPath,
          thumbnail_path: node.data('thumbnail_path') || imgPath,
          caption: node.data('label') || '图片',
        }]
      }
    }

    if (tooltipTimer) clearTimeout(tooltipTimer)

    const rp = node.renderedPosition()
    const containerRect = cy.container().getBoundingClientRect()
    tooltipPosition.value = {
      x: containerRect.left + rp.x,
      y: containerRect.top + rp.y,
    }

    tooltipNode.value = {
      id: node.id(),
      label: node.data('label'),
      name: node.data('label'),
      type: nodeType,
      description: node.data('description') || '',
      text: node.data('text') || '',  // P39-FIX: 传递 text 供 tooltip 显示
      source_chunks: node.data('source_chunks') || [],
      media_refs: mediaRefs,
    }
    console.log('[GraphView] tooltipNode set, text length=', (tooltipNode.value.text || '').length, 'type=', nodeType)
    tooltipVisible.value = true
  })

  cy.on('mouseout', 'node', (e) => {
    const node = e.target
    const nodeType = node.data('type') || ''
    if (nodeType === 'virtual_gap') {
      scheduleGapTooltipClose()
      return
    }

    // 延迟关闭，允许鼠标移入 tooltip
    tooltipTimer = setTimeout(() => {
      tooltipVisible.value = false
    }, 200)
  })

  cy.on('tap', (e) => {
    if (e.target === cy) {
      selectedNode.value = null
      tooltipVisible.value = false
      gapTooltipVisible.value = false
      clearHighlight()
    }
  })

  cy.on('dbltap', 'node', async (e) => {
    await expandNode(e.target.id())
  })
}

// ========== 数据加载 ==========
async function loadAllNodes({ preferredConceptNodeId = null, preferredTreeRootId = null } = {}) {
  isLoading.value = true
  try {
    if (!cy) return
    cy.elements().remove()
    conceptTreePages.value = []
    currentTreePage.value = 0
    console.log('[GraphView] loadAllNodes start, viewMode=', viewMode.value)

    if (viewMode.value === 'document') {
      // LA-035-P19: 文档结构树视图 - 只加载 Chunk 节点 + 结构边
      await loadChunkNodes()
      console.log('[GraphView] after loadChunkNodes, nodes=', cy.nodes().length, 'edges=', cy.edges().length)
      await loadEdges()
      console.log('[GraphView] after loadEdges, nodes=', cy.nodes().length, 'edges=', cy.edges().length)
      if (cy.nodes().length > 0) {
        runTreeLayout(cy)
        console.log('[GraphView] after runTreeLayout, nodes=', cy.nodes().length, 'edges=', cy.edges().length)
      }
    } else if (viewMode.value === 'concept') {
      // LA-035-P19: 知识图谱视图 - 只加载 CanonicalConcept + 语义边
      // LA-052: 先加载范式配置，用于动态渲染边样式和图例
      try {
        paradigmConfig.value = await loadParadigmConfig(currentSubject.value)
        console.log('[GraphView] LA-052: 范式配置加载完成:', paradigmConfig.value?.paradigm_id)
      } catch (e) {
        console.warn('[GraphView] LA-052: 范式配置加载失败，使用 fallback:', e)
        paradigmConfig.value = null
      }
      await loadConceptNodes()
      await loadSemanticEdges()
      await loadGapData({ render: false })
      renderGapElements()
      layoutConceptGraph({
        preservePage: false,
        preferredNodeId: preferredConceptNodeId,
        preferredRootId: preferredTreeRootId,
      })
    } else {
      // 全局概念是与图谱并列的目录视图，不初始化画布元素。
      try {
        paradigmConfig.value = await loadParadigmConfig(currentSubject.value)
      } catch (e) {
        console.warn('[GraphView] 范式配置加载失败，使用 fallback:', e)
        paradigmConfig.value = null
      }
      await loadConceptCatalog()
    }

    await nextTick()
    if (cy) {
      cy.resize()
    }

    nodeCount.value = cy?.nodes().length || 0
    edgeCount.value = cy?.edges().length || 0
    console.log('[GraphView] loadAllNodes final, nodes=', nodeCount.value, 'edges=', edgeCount.value)
  } catch (e) {
    console.error('[GraphView] 加载图谱失败:', e)
  } finally {
    isLoading.value = false
  }
}

function removeGapElements() {
  if (!cy) return
  cy.elements('[?isGapElement]').remove()
}

async function loadGapData({ render = true } = {}) {
  if (viewMode.value !== 'concept') return
  const sequence = ++gapLoadSequence
  const subject = currentSubject.value
  gapsLoading.value = true
  gapError.value = ''
  try {
    const listed = await apiListAllGaps(subject, { status: null })
    if (sequence !== gapLoadSequence || subject !== currentSubject.value) return
    gaps.value = listed.items || []
    if (render) relayoutGapElements()
  } catch (error) {
    if (sequence !== gapLoadSequence) return
    gaps.value = []
    gapError.value = readableError(error, 'Gap 数据加载失败')
    if (render) relayoutGapElements()
  } finally {
    if (sequence === gapLoadSequence) gapsLoading.value = false
  }
}

async function refreshGapOverlay() {
  await loadGapData()
}

function renderGapElements() {
  if (!cy || viewMode.value !== 'concept') return
  removeGapElements()
  cy.nodes('.gap-supplemented-node').removeClass('gap-supplemented-node')
  cy.edges('.gap-skip-edge').style('display', 'element').removeClass('gap-skip-edge')
  const { nodes: gapNodes, edges: gapEdges, replacedPairs } = buildVirtualGapElements(
    openFilteredGaps.value,
    paradigmConfig.value?.types || {},
  )
  if (gapNodes.length) cy.add(gapNodes)
  if (gapEdges.length) cy.add(gapEdges)
  gaps.value.forEach(gap => {
    if (gap.status === 'supplemented') {
      nodesForCanonicalIds(supplementedNodeIds(gap)).addClass('gap-supplemented-node')
    }
  })
  const replacementIndex = buildGapReplacementIndex(replacedPairs)
  cy.edges().forEach(edge => {
    if (edgeMatchesGapIndex(edge.data(), replacementIndex)) {
      edge.addClass('gap-skip-edge').style('display', 'none')
    }
  })
  nodeCount.value = cy.nodes().length
  edgeCount.value = cy.edges().length
}

function relayoutGapElements() {
  if (!cy || viewMode.value !== 'concept') return
  renderGapElements()
  layoutConceptGraph()
  nodeCount.value = cy.nodes().length
  edgeCount.value = cy.edges().length
}

function clearTreePageFilter() {
  clearConceptTreePage(cy)
}

function treePageForNode(nodeId) {
  return findConceptTreePage(conceptTreePages.value, cy, nodeId)
}

function layoutConceptGraph({
  preservePage = true,
  preferredNodeId = null,
  preferredRootId = null,
} = {}) {
  if (!cy || viewMode.value !== 'concept') return
  const previousTree = conceptTreePages.value[currentTreePage.value]
  clearTreePageFilter()
  const result = runConceptLayout(cy, { supplementedGaps: gaps.value })
  conceptTreePages.value = result?.trees || []

  let nextPage = preferredRootId
    ? conceptTreePages.value.findIndex(tree => tree.rootOriginalId === preferredRootId)
    : -1
  if (nextPage < 0 && preferredNodeId) nextPage = treePageForNode(preferredNodeId)
  if (nextPage < 0 && preservePage && previousTree) {
    nextPage = conceptTreePages.value.findIndex(tree =>
      tree.rootOriginalId === previousTree.rootOriginalId,
    )
  }
  currentTreePage.value = nextPage >= 0 ? nextPage : 0
  applyTreePage()
}

function applyTreePage({ fit = true } = {}) {
  if (!cy || viewMode.value !== 'concept') return
  clearTreePageFilter()
  if (!conceptTreePages.value.length) return

  currentTreePage.value = Math.min(
    Math.max(0, currentTreePage.value),
    conceptTreePages.value.length - 1,
  )
  const tree = conceptTreePages.value[currentTreePage.value]
  const pageNodes = applyConceptTreePage(cy, tree)

  if (fit && pageNodes?.length) cy.fit(pageNodes, 60)
}

function changeTreePage(index) {
  if (!conceptTreePages.value.length) return
  currentTreePage.value = Math.min(Math.max(0, index), conceptTreePages.value.length - 1)
  selectedNode.value = null
  tooltipVisible.value = false
  gapTooltipVisible.value = false
  applyTreePage()
}

function revealTreePageForNode(nodeId, { fit = false } = {}) {
  const page = treePageForNode(nodeId)
  if (page < 0) return false
  if (page !== currentTreePage.value) {
    currentTreePage.value = page
    applyTreePage({ fit })
  }
  return true
}

function currentTreeContainsCanonical(nodeId) {
  const tree = conceptTreePages.value[currentTreePage.value]
  if (!tree || !nodeId) return false
  return tree.nodeIds.some(id => {
    const node = cy.getElementById(id)
    return node.length && (node.data('originalId') || id) === nodeId
  })
}

function nodesForCanonicalIds(ids) {
  const wanted = new Set(ids || [])
  if (!cy || !wanted.size) return cy ? cy.collection() : null
  return cy.nodes().filter(node => wanted.has(node.data('originalId') || node.id()))
}

async function reconcileGapData() {
  if (!canWriteGaps.value || gapsReconciling.value) return
  gapsReconciling.value = true
  gapError.value = ''
  try {
    await apiReconcileGaps(
      currentSubject.value,
      paradigmConfig.value?.paradigm_id || null,
      true,
    )
    await refreshGapOverlay()
  } catch (error) {
    gapError.value = readableError(error, 'Gap 检测失败')
  } finally {
    gapsReconciling.value = false
  }
}

async function focusGap(selection) {
  const gap = selection?.gap || selection
  if (!gap) return
  if (gap.status === 'supplemented') {
    await focusSupplementedGap(gap)
    return
  }
  const clickPosition = selection?.position
  revealTreePageForNode(virtualGapNodeId(gap.gap_id, 0), { fit: false })
  const first = cy ? cy.getElementById(virtualGapNodeId(gap.gap_id, 0)) : null
  activeGap.value = gap
  gapTooltipGap.value = gap
  gapTooltipType.value = gap.missing_types?.[0] || ''
  if (clickPosition) {
    gapTooltipPosition.value = clickPosition
    if (first?.length) {
      first.select()
      cy.animate({ fit: { eles: first, padding: 110 }, duration: 350 })
    }
  } else if (first?.length) {
    first.select()
    cy.animate({ fit: { eles: first, padding: 110 }, duration: 350 })
    const rp = first.renderedPosition()
    const rect = cy.container().getBoundingClientRect()
    gapTooltipPosition.value = { x: rect.left + rp.x, y: rect.top + rp.y }
  } else {
    gapTooltipPosition.value = { x: window.innerWidth / 2, y: window.innerHeight / 2 }
  }
  gapTooltipVisible.value = true
}

async function focusSupplementedGap(gap) {
  if (!cy || !gap) return false
  const canonicalIds = supplementedNodeIds(gap)
  const primaryId = canonicalIds[0]
  if (primaryId && !currentTreeContainsCanonical(primaryId)) {
    revealTreePageForNode(primaryId, { fit: false })
  }
  const pathMatched = cy.nodes().filter(node =>
    (node.data('supplementedGapIds') || []).includes(gap.gap_id) &&
    node.style('display') !== 'none',
  )
  const matched = nodesForCanonicalIds(canonicalIds).filter(node =>
    node.style('display') !== 'none',
  )
  if (!matched?.length) {
    gapError.value = '补充记录存在，但对应概念节点尚未加载；请刷新图谱后重试。'
    return false
  }

  gapTooltipVisible.value = false
  cy.nodes().unselect()
  cy.nodes('.gap-completion-focus').removeClass('gap-completion-focus')
  let exactNodes = cy.collection()
  canonicalIds.forEach(id => {
    const node = cy.getElementById(id)
    if (node.length && node.style('display') !== 'none') exactNodes = exactNodes.union(node)
  })
  const focusNodes = pathMatched.length
    ? pathMatched
    : (exactNodes.length ? exactNodes : matched)
  matched.addClass('gap-completion-focus')
  focusNodes.select()

  const primary = focusNodes.first()
  activateNode(primary)
  await nextTick()
  cy.resize()
  cy.animate({ fit: { eles: focusNodes, padding: 120 }, duration: 420 })
  return true
}

function showGapTooltip(node, position) {
  if (gapTooltipTimer) clearTimeout(gapTooltipTimer)
  gapTooltipGap.value = node.data('gap')
  gapTooltipType.value = node.data('gapType') || ''
  gapTooltipPosition.value = position
  gapTooltipVisible.value = true
}
function scheduleGapTooltipClose() {
  if (gapTooltipTimer) clearTimeout(gapTooltipTimer)
  gapTooltipTimer = setTimeout(() => { gapTooltipVisible.value = false }, 220)
}
function holdGapTooltip() { if (gapTooltipTimer) clearTimeout(gapTooltipTimer) }
function closeGapTooltip() { gapTooltipVisible.value = false }
function conceptById(conceptId) {
  if (!conceptId) return null
  return conceptTable.value.find(item => item.id === conceptId) || null
}

async function openGapSupplement(gap) {
  if (!canWriteGaps.value) return
  activeGap.value = gap
  gapActionError.value = ''
  gapProposal.value = null
  gapProposalHistory.value = []
  gapExternalSearching.value = false
  gapExternalImporting.value = false
  gapTooltipVisible.value = false
  showGapSupplement.value = true
  gapProposalLoading.value = true
  try {
    const [result, history] = await Promise.all([
      apiGetLatestGapProposal(currentSubject.value, gap.gap_id),
      apiListGapProposals(currentSubject.value, gap.gap_id),
    ])
    if (!showGapSupplement.value || activeGap.value?.gap_id !== gap.gap_id) return
    gapProposal.value = result.proposal || null
    gapProposalHistory.value = history.items || []
    if (!gapProposal.value) {
      gapProposalLoading.value = false
      await generateGapProposal()
    } else if (gapProposal.value.status === 'generating') {
      scheduleGapProposalPoll(gapProposal.value.proposal_id)
    }
  } catch (error) {
    gapActionError.value = readableError(error, '补全建议加载失败')
  } finally {
    gapProposalLoading.value = false
  }
}
function closeGapSupplement() {
  if (gapActionPending.value || gapExternalImporting.value) return
  clearGapProposalPoll()
  showGapSupplement.value = false
  activeGap.value = null
  gapProposal.value = null
  gapProposalHistory.value = []
  gapProposalLoading.value = false
  gapExternalSearching.value = false
  gapExternalImporting.value = false
  gapActionError.value = ''
}

function clearGapProposalPoll() {
  if (gapProposalPollTimer) clearTimeout(gapProposalPollTimer)
  gapProposalPollTimer = null
}

function scheduleGapProposalPoll(proposalId) {
  clearGapProposalPoll()
  gapProposalPollTimer = setTimeout(async () => {
    const gap = activeGap.value
    if (!showGapSupplement.value || !gap || gapProposal.value?.proposal_id !== proposalId) return
    try {
      const proposal = await apiGetGapProposal(
        currentSubject.value, gap.gap_id, proposalId,
      )
      if (!showGapSupplement.value || activeGap.value?.gap_id !== gap.gap_id) return
      gapProposal.value = proposal
      if (proposal.status === 'generating') scheduleGapProposalPoll(proposalId)
      else gapProposalHistory.value = (
        await apiListGapProposals(currentSubject.value, gap.gap_id)
      ).items || []
    } catch (error) {
      gapActionError.value = readableError(error, '补全建议状态刷新失败')
    }
  }, 1200)
}

async function generateGapProposal() {
  const gap = activeGap.value
  if (!gap || gapProposalLoading.value || gapActionPending.value) return
  clearGapProposalPoll()
  gapProposalLoading.value = true
  gapActionError.value = ''
  try {
    gapProposal.value = await apiCreateGapProposal(
      currentSubject.value, gap.gap_id, gap.version,
    )
    gapProposalHistory.value = (
      await apiListGapProposals(currentSubject.value, gap.gap_id)
    ).items || []
    scheduleGapProposalPoll(gapProposal.value.proposal_id)
  } catch (error) {
    gapActionError.value = readableError(error, 'AI 补全建议生成失败')
  } finally {
    gapProposalLoading.value = false
  }
}

async function acceptGapProposal(concepts) {
  const gap = activeGap.value
  const proposal = gapProposal.value
  if (!gap || !proposal || gapActionPending.value) return
  gapActionPending.value = true
  gapActionError.value = ''
  let completedGap = null
  try {
    const result = await apiAcceptGapProposal(
      currentSubject.value,
      gap.gap_id,
      proposal.proposal_id,
      gap.version,
      concepts,
    )
    completedGap = result?.gap || null
  } catch (error) {
    gapActionError.value = readableError(error, 'AI 补全写入失败')
  } finally {
    gapActionPending.value = false
  }
  if (completedGap) {
    closeGapSupplement()
    await refreshConceptGraphAfterGapAction(completedGap)
  }
}

async function rejectGapProposal() {
  const gap = activeGap.value
  const proposal = gapProposal.value
  if (!gap || !proposal || gapActionPending.value) return
  gapActionPending.value = true
  gapActionError.value = ''
  try {
    gapProposal.value = await apiRejectGapProposal(
      currentSubject.value, gap.gap_id, proposal.proposal_id,
    )
  } catch (error) {
    gapActionError.value = readableError(error, '拒绝建议失败')
  } finally {
    gapActionPending.value = false
  }
}

async function searchGapExternalEvidence(queries = []) {
  const gap = activeGap.value
  const proposal = gapProposal.value
  if (!gap || !proposal || gapExternalSearching.value || gapExternalImporting.value) return
  gapExternalSearching.value = true
  gapActionError.value = ''
  try {
    const result = await apiSearchGapExternalEvidence(
      currentSubject.value, gap.gap_id, proposal.proposal_id, queries,
    )
    if (!showGapSupplement.value || activeGap.value?.gap_id !== gap.gap_id) return
    gapProposal.value = result.proposal
  } catch (error) {
    gapActionError.value = readableError(error, '公开资料检索失败')
  } finally {
    gapExternalSearching.value = false
  }
}

async function importGapExternalEvidence(resultIds) {
  const gap = activeGap.value
  const proposal = gapProposal.value
  if (!gap || !proposal || !resultIds?.length || gapExternalImporting.value) return
  clearGapProposalPoll()
  gapExternalImporting.value = true
  gapActionError.value = ''
  try {
    const result = await apiImportGapExternalEvidence(
      currentSubject.value,
      gap.gap_id,
      proposal.proposal_id,
      gap.version,
      resultIds,
    )
    if (!showGapSupplement.value || activeGap.value?.gap_id !== gap.gap_id) return
    gapProposal.value = result.proposal
    gapProposalHistory.value = (
      await apiListGapProposals(currentSubject.value, gap.gap_id)
    ).items || []
    scheduleGapProposalPoll(result.proposal.proposal_id)
  } catch (error) {
    gapActionError.value = readableError(error, '外部资料加入知识库失败')
  } finally {
    gapExternalImporting.value = false
  }
}

async function deactivateGapExternalEvidence(chunkId) {
  const gap = activeGap.value
  const proposal = gapProposal.value
  if (!gap || !proposal || !chunkId || gapExternalImporting.value) return
  clearGapProposalPoll()
  gapExternalImporting.value = true
  gapActionError.value = ''
  try {
    const result = await apiDeactivateGapExternalEvidence(
      currentSubject.value, gap.gap_id, proposal.proposal_id, gap.version, chunkId,
    )
    if (!showGapSupplement.value || activeGap.value?.gap_id !== gap.gap_id) return
    gapProposal.value = result.proposal
    gapProposalHistory.value = (await apiListGapProposals(currentSubject.value, gap.gap_id)).items || []
    scheduleGapProposalPoll(result.proposal.proposal_id)
  } catch (error) {
    gapActionError.value = readableError(error, '外部资料停用失败')
  } finally {
    gapExternalImporting.value = false
  }
}

async function acquireGapExternalFulltext(resultId) {
  const gap = activeGap.value
  const proposal = gapProposal.value
  if (!gap || !proposal || !resultId || gapExternalImporting.value) return
  clearGapProposalPoll()
  gapExternalImporting.value = true
  gapActionError.value = ''
  try {
    const result = await apiAcquireGapExternalFulltext(
      currentSubject.value, gap.gap_id, proposal.proposal_id, gap.version, resultId,
    )
    if (!showGapSupplement.value || activeGap.value?.gap_id !== gap.gap_id) return
    gapProposal.value = result.proposal
    gapProposalHistory.value = (await apiListGapProposals(currentSubject.value, gap.gap_id)).items || []
    scheduleGapProposalPoll(result.proposal.proposal_id)
  } catch (error) {
    gapActionError.value = readableError(error, '开放全文获取或解析失败')
  } finally {
    gapExternalImporting.value = false
  }
}

async function supplementGap(concepts) {
  if (!activeGap.value || gapActionPending.value) return
  gapActionPending.value = true
  gapActionError.value = ''
  try {
    const completedGap = await apiSupplementGap(
      currentSubject.value,
      activeGap.value.gap_id,
      activeGap.value.version,
      concepts,
    )
    showGapSupplement.value = false
    activeGap.value = null
    await refreshConceptGraphAfterGapAction(completedGap)
  } catch (error) {
    gapActionError.value = readableError(error, '补充失败')
  } finally {
    gapActionPending.value = false
  }
}

async function ignoreGap(gap) {
  if (!canWriteGaps.value || gapActionPending.value) return
  gapActionPending.value = true
  try {
    await apiIgnoreGap(currentSubject.value, gap.gap_id, gap.version)
    gapTooltipVisible.value = false
    await refreshGapOverlay()
  } catch (error) {
    gapError.value = readableError(error, '忽略失败')
  } finally { gapActionPending.value = false }
}

async function reopenGap(gap) {
  if (!canWriteGaps.value || gapActionPending.value) return
  gapActionPending.value = true
  try {
    await apiReopenGap(currentSubject.value, gap.gap_id, gap.version)
    gapTooltipVisible.value = false
    await refreshGapOverlay()
  } catch (error) {
    gapError.value = readableError(error, '重新打开失败')
  } finally { gapActionPending.value = false }
}

async function refreshConceptGraphAfterGapAction(completedGap) {
  if (!cy || !completedGap) return
  const completedIds = supplementedNodeIds(completedGap)
  const previousRootId = conceptTreePages.value[currentTreePage.value]?.rootOriginalId || null
  await loadAllNodes({
    preferredConceptNodeId: completedIds[0] || null,
    preferredTreeRootId: previousRootId,
  })
  gapCompletionNotice.value = completedGap
  await focusSupplementedGap(completedGap)
}

function readableError(error, fallback) {
  const message = error?.message || ''
  const jsonStart = message.indexOf('{')
  if (jsonStart >= 0) {
    try { return JSON.parse(message.slice(jsonStart)).detail || fallback }
    catch { /* fall through */ }
  }
  return message || fallback
}

// P34-FIX: 为文档树节点构建 UML 卡片标签
// P38-FIX: 限制文字长度避免溢出，增大 lineHeight 和 padding
function buildChunkCard(label, chunkType, text) {
  const typeLabels = {
    heading: '【标题】',
    paragraph: '【段落】',
    document: '【文档】',
    child: '【片段】',
    markdown: '【片段】',
    image: '【图片】',
    image_pseudo: '【图片】',
    formula_pseudo: '【公式】',
  }
  const typeLabel = typeLabels[chunkType] || '【片段】'

  // 限制标题长度，确保在卡片宽度内不换行
  const titleMaxChars = 12
  let title = (label || '未命名').slice(0, titleMaxChars)
  if ((label || '').length > titleMaxChars) title += '…'

  // 限制描述长度，确保不换行（中文字符约 10px 宽，卡片宽度约 140px，每行约 12-14 字符）
  const descMaxChars = chunkType === 'paragraph' ? 22 : 14
  const descRaw = (text || '').replace(/\s+/g, ' ').trim()
  let desc = descRaw.slice(0, descMaxChars)
  if (descRaw.length > descMaxChars) desc += '…'

  let cardLabel = `${title}\n━━━━━━\n${typeLabel}`
  if (desc) {
    cardLabel += `\n━━━━━━\n${desc}`
  }

  // 基于最宽行计算卡片宽度（10px 字体 ≈ 10px/字符 + 20px 内边距）
  const allLines = cardLabel.split('\n')
  const maxChars = Math.max(...allLines.map(l => l.length))
  const nodeWidth = Math.max(110, maxChars * 10 + 20)

  // 基于实际行数计算卡片高度（无自动换行，\n 行数 = 实际渲染行数）
  const lineHeight = 16  // 10px 字体 + 行间距
  const padding = 24     // 上下各 12px
  const cardHeight = Math.max(56, allLines.length * lineHeight + padding)

  return { cardLabel, cardHeight, nodeWidth }
}

// P41-FIX: 计算图片 URL（参考 NodeDetailPanel 逻辑）
function getChunkImageUrl(imagePath) {
  if (!imagePath) return ''
  const idx = imagePath.indexOf('_v1_images')
  if (idx !== -1) {
    const before = imagePath.substring(0, idx)
    const sepIdx = Math.max(before.lastIndexOf('/'), before.lastIndexOf('\\'))
    const subject = sepIdx !== -1 ? before.substring(sepIdx + 1) : before
    const filename = imagePath.substring(imagePath.lastIndexOf('/') + 1).split('\\').pop()
    return withMediaAuth(`${window.location.origin}/api/images/${subject.replace('_v1_images', '')}/${filename}`)
  }
  return ''
}

async function loadChunkNodes() {
  try {
    // P30-FIX: limit 从 500 增大到 5000，避免大文档 chunk 节点被截断
    // LA-051-P2-FIX: 添加认证 headers
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/nodes?limit=5000`,
      { headers: getAuthHeaders() }
    )
    if (!resp.ok) {
      console.warn('[GraphView] Nodes API failed:', resp.status)
      return
    }
    const data = await resp.json()
    const chunkNodes = (data.nodes || []).map(n => {
      const label = generateNodeLabel(n.text, n.heading_path, n.id)
      const chunkType = n.chunk_type || 'child'
      let { cardLabel, cardHeight, nodeWidth } = buildChunkCard(label, chunkType, n.text)
      // P41-FIX: 为图片 chunk 计算预览 URL
      const imageUrl = (chunkType === 'image' || chunkType === 'image_pseudo')
        ? getChunkImageUrl(n.image_path || n.thumbnail_path)
        : ''
      // LA-035-P43: 图片节点高度根据实际比例自适应
      if ((chunkType === 'image' || chunkType === 'image_pseudo') && n.width && n.height) {
        const aspectRatio = n.height / n.width
        const imgHeight = Math.round(nodeWidth * aspectRatio)
        cardHeight = Math.max(60, Math.min(300, imgHeight))  // 最小 60px，最大 300px
      }
      // Cytoscape background-image 需要 'none' 而非空字符串作为无效值
      const bgImage = imageUrl || 'none'
      return {
        data: {
          id: n.id,
          label: label,
          cardLabel: cardLabel,
          cardHeight: cardHeight,
          nodeWidth: nodeWidth,
          type: chunkType,
          chunkType: chunkType,
          source: n.source,
          page_number: n.page_number,
          text: n.text || '',
          heading_path: n.heading_path || '',
          // LA-035: 图片字段
          image_path: n.image_path || '',
          thumbnail_path: n.thumbnail_path || '',
          imageUrl: imageUrl,  // 用于 tooltip / 详情面板
          bgImage: bgImage,    // P41-FIX: 用于 Cytoscape background-image（'none' 或 URL）
          width: n.width || 0,
          height: n.height || 0,
        }
      }
    })
    if (chunkNodes.length > 0 && cy) {
      cy.add(chunkNodes)
    }
  } catch (e) {
    console.error('[GraphView] 加载 chunk 节点失败:', e)
  }
}

async function loadEdges() {
  try {
    // P30-FIX: limit 从 200 增大到 5000，避免 BELONGS_TO 边被截断
    const url = `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/edges?limit=5000`
    console.log('[GraphView] loadEdges URL:', url)
    // LA-051-P2-FIX: 添加认证 headers
    const resp = await fetch(url, { headers: getAuthHeaders() })
    if (!resp.ok) {
      console.warn('[GraphView] Edges API failed:', resp.status)
      return
    }
    const data = await resp.json()
    console.log('[GraphView] loadEdges API response, total edges returned:', data.count, 'edges array length:', (data.edges || []).length)

    // P32-FIX: 收集已加载的节点ID，用于验证边的有效性
    const loadedNodeIds = new Set()
    cy.nodes().forEach(n => loadedNodeIds.add(n.id()))
    console.log('[GraphView] loadedNodeIds count:', loadedNodeIds.size)

    const allEdges = (data.edges || [])
      .filter(edge => edge.type === 'BELONGS_TO')  // P30-FIX: 文档树只加载层级边
      .filter(edge => {
        // P32-FIX: 跳过悬空边（source 或 target 节点未加载）
        const valid = loadedNodeIds.has(edge.source) && loadedNodeIds.has(edge.target)
        if (!valid) {
          console.warn('[GraphView] skipping dangling edge:', edge.source, '->', edge.target)
        }
        return valid
      })
      .map(edge => ({
        data: {
          id: `${edge.source}-${edge.type}-${edge.target}`,
          source: edge.source,
          target: edge.target,
          type: edge.type,
        }
      }))
    console.log('[GraphView] loadEdges after filter, BELONGS_TO edges:', allEdges.length)

    if (allEdges.length > 0 && cy) {
      const added = cy.add(allEdges)
      console.log('[GraphView] loadEdges cy.add result, added elements:', added.length, 'cy.edges() after add:', cy.edges().length)
    } else {
      console.log('[GraphView] loadEdges skipped cy.add, allEdges.length=', allEdges.length, 'cy exists=', !!cy)
    }
  } catch (e) {
    console.error('[GraphView] 加载边失败:', e)
  }
}

async function loadConceptNodes() {
  try {
    const rawConcepts = await loadConceptCatalog()
    const conceptNodes = rawConcepts.filter(c => !cy?.getElementById(c.id).length).map(c => {
      // 解析 source_chunks（后端返回的可能是数组、JSON 字符串或逗号分隔字符串）
      let sourceChunks = []
      const sc = c.source_chunks || []
      if (Array.isArray(sc)) {
        sourceChunks = sc
      } else if (typeof sc === 'string' && sc) {
        try {
          const parsed = JSON.parse(sc)
          sourceChunks = Array.isArray(parsed) ? parsed : [sc]
        } catch {
          sourceChunks = sc.split(',').map(s => s.trim()).filter(Boolean)
        }
      }

      // 解析 source_refs（后端返回的可能是数组）
      let sourceRefs = []
      const sr = c.source_refs || []
      if (Array.isArray(sr)) {
        sourceRefs = sr
      } else if (typeof sr === 'string' && sr) {
        try {
          const parsed = JSON.parse(sr)
          sourceRefs = Array.isArray(parsed) ? parsed : [sr]
        } catch {
          sourceRefs = [sr]
        }
      }

      // LA-052 FIX: 正确解析 media_refs，防止字符串遍历导致颜色错乱
      let mediaRefs = c.media_refs || []
      // 防御：media_refs 可能是 JSON 字符串
      if (typeof mediaRefs === 'string') {
        try {
          const parsed = JSON.parse(mediaRefs)
          mediaRefs = Array.isArray(parsed) ? parsed : []
        } catch {
          mediaRefs = []
        }
      }
      if (!Array.isArray(mediaRefs)) {
        mediaRefs = []
      }

      let hasImage = false
      let hasTable = false
      let hasFormula = false
      mediaRefs.forEach(ref => {
        // 防御：ref 可能是字符串
        if (typeof ref === 'string') return
        const t = (ref?.type || ref?.media_type || '').toLowerCase()
        if (t.includes('image') || t.includes('图片') || t.includes('fig')) hasImage = true
        else if (t.includes('table') || t.includes('表格') || t.includes('tab')) hasTable = true
        else if (t.includes('formula') || t.includes('公式') || t.includes('math') || t.includes('equation')) hasFormula = true
        // 移除默认归类为图片的 else 分支
      })

      // 根据媒体类型确定边框颜色
      // 媒体类型优先：有图片→橙色，有表格→蓝色，有公式→紫色，多种→灰色
      let borderColor = getConceptTypeBorderColor(c.type || 'concept')
      if (mediaRefs.length > 1 && [hasImage, hasTable, hasFormula].filter(Boolean).length > 1) {
        borderColor = '#7f8c8d' // 多种混合 → 灰色
      } else if (hasImage) {
        borderColor = '#e67e22' // 图片 → 橙色
      } else if (hasTable) {
        borderColor = '#3498db' // 表格 → 蓝色
      } else if (hasFormula) {
        borderColor = '#9b59b6' // 公式 → 紫色
      }

      // 根据内容多少计算节点宽度
      const { cardLabel, cardHeight, nodeWidth } = buildUMLCardLabel(
        c.name || '', c.type || 'concept', c.description || '', mediaRefs
      )
      return {
        data: {
          id: c.id,
          label: c.name,
          cardLabel: cardLabel,
          cardHeight: cardHeight,
          nodeWidth: nodeWidth,
          borderColor: borderColor,
          type: c.type || 'concept',
          description: c.description || '',
          parent_hint: c.parent_hint || '',
          source_chunks: sourceChunks,
          source_chunk_count: sourceChunks.length,
          source_refs: sourceRefs,
          media_refs: mediaRefs,
          has_media: mediaRefs.length > 0,
          hasImage: hasImage,
          hasTable: hasTable,
          hasFormula: hasFormula,
        },
        // LA-052 FIX: 虚拟节点直接设置 style，绕过 CSS 选择器
        ...(c.is_virtual ? {
          style: {
            width: 24,
            height: 24,
            shape: 'ellipse',
            'border-width': 2,
            'border-style': 'dashed',
            'border-color': '#E67E22',
            'background-color': 'rgba(230, 126, 34, 0.15)',
            'font-size': '9px',
            color: '#E67E22',
            label: c.name,
          }
        } : {})
      }
    })
    if (conceptNodes.length > 0 && cy) {
      cy.add(conceptNodes)
      // LA-052 FIX: 使用 ele.style() 设置虚拟节点样式（优先级高于 CSS 选择器）
      cy.nodes().forEach(n => {
        if (n.data('isVirtual') === true) {
          n.style({
            'width': 24,
            'height': 24,
            'shape': 'ellipse',
            'border-width': 2,
            'border-style': 'dashed',
            'border-color': '#E67E22',
            'background-color': 'rgba(230, 126, 34, 0.15)',
            'font-size': '9px',
            'color': '#E67E22',
          })
        }
      })
      // LA-052 DEBUG: 检查添加的节点数据
      console.log('[GraphView] loadConceptNodes: 添加了', conceptNodes.length, '个节点')
      const sample = conceptNodes[0]
      console.log('[GraphView] 第一个节点数据:', {
        id: sample.data.id,
        label: sample.data.label,
        type: sample.data.type,
        nodeWidth: sample.data.nodeWidth,
        cardHeight: sample.data.cardHeight,
        isVirtual: sample.data.isVirtual,
      })
    }
  } catch (e) {
    console.error('[GraphView] 加载概念节点失败:', e)
  }
}

async function loadConceptCatalog() {
  conceptTable.value = []
  const url = `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/concepts`
  const resp = await fetch(url, { headers: getAuthHeaders() })
  if (!resp.ok) {
    console.warn('[GraphView] 概念节点 API 失败:', resp.status)
    return []
  }
  const data = await resp.json()
  const rawConcepts = data.concepts || []
  const normalizedConcepts = rawConcepts.map(concept => ({
    ...concept,
    description: stripEvidenceField(concept.description),
    concept_type: concept.concept_type || concept.type || 'concept',
    source_chunk_count: concept.source_chunk_count ?? (concept.source_chunks || []).length,
  }))
  conceptTable.value = normalizedConcepts
  return normalizedConcepts
}

async function loadSemanticEdges() {
  try {
    const url = `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/concept-links`
    // LA-051-P2-FIX: 添加认证 headers
    const resp = await fetch(url, { headers: getAuthHeaders() })
    if (!resp.ok) {
      console.warn('[GraphView] 语义连接 API 失败:', resp.status)
      return
    }
    const data = await resp.json()
    const semEdges = (data.edges || []).map(edge => {
      const id = `${edge.source}-${edge.type}-${edge.target}`
      return {
        data: {
          id,
          source: edge.source,
          target: edge.target,
          type: edge.type,
          label: getRelationLabel(edge.type),
          confidence: edge.confidence || 0,
        }
      }
    }).filter(edge => !cy?.getElementById(edge.data.id).length &&
      cy?.getElementById(edge.data.source).length && cy?.getElementById(edge.data.target).length)
    if (semEdges.length > 0 && cy) {
      cy.add(semEdges)
    }
  } catch (e) {
    console.error('[GraphView] 加载语义连接失败:', e)
  }
}

async function expandNode(nodeId) {
  try {
    // LA-051-P2-FIX: 添加认证 headers
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/subgraph/${nodeId}?depth=1`,
      { headers: getAuthHeaders() }
    )
    if (!resp.ok) return
    const data = await resp.json()

    const newNodes = []
    for (const n of data.nodes || []) {
      if (!cy.getElementById(n.id).length) {
        newNodes.push({
          data: {
            id: n.id,
            label: n.label || n.id.slice(0, 12),
            type: n.chunk_type || 'child',
            source: n.source,
            page_number: n.page_number,
            text: n.text || '',
          }
        })
      }
    }
    if (newNodes.length > 0) cy.add(newNodes)

    const newEdges = []
    for (const e of data.edges || []) {
      const edgeId = `${e.source}-${e.type}-${e.target}`
      if (!cy.getElementById(edgeId).length) {
        newEdges.push({
          data: {
            id: edgeId,
            source: e.source,
            target: e.target,
            type: e.type,
          }
        })
      }
    }
    if (newEdges.length > 0) cy.add(newEdges)

    cy.getElementById(nodeId).data('isCenter', true)
    // LA-057 FIX: 根据当前视图模式调用正确的布局函数
    if (viewMode.value === 'document') {
      runTreeLayout(cy)
    } else {
      layoutConceptGraph()
    }
  } catch (e) {
    console.error('展开节点失败:', e)
  }
}

// ========== 交互功能 ==========
function highlightNeighbors(node) {
  clearHighlight()

  const highlightIds = new Set([node.id()])

  // 处理副本
  const originalId = node.data('originalId')
  if (originalId) {
    highlightIds.add(originalId)
    const mapping = cy.scratch('originalToCopies') || {}
    const copies = mapping[originalId] || []
    copies.forEach(id => highlightIds.add(id))
  }

  const mapping = cy.scratch('originalToCopies') || {}
  for (const [oid, copies] of Object.entries(mapping)) {
    if (oid === node.id() || copies.includes(node.id())) {
      copies.forEach(id => highlightIds.add(id))
      highlightIds.add(oid)
    }
  }

  // 收集邻居
  highlightIds.forEach(id => {
    const n = cy.getElementById(id)
    if (n.length > 0) {
      n.neighborhood().forEach(nn => {
        if (nn.isNode()) highlightIds.add(nn.id())
      })
    }
  })

  cy.nodes().forEach(n => {
    if (!highlightIds.has(n.id())) {
      n.animate({ opacity: 0.2 }, { duration: 200 })
    }
  })
  cy.edges().forEach(e => {
    const s = e.source().id()
    const t = e.target().id()
    if (!highlightIds.has(s) || !highlightIds.has(t)) {
      e.animate({ opacity: 0.1 }, { duration: 200 })
    }
  })
}

function clearHighlight() {
  if (!cy) return
  cy.nodes().forEach(n => n.animate({ opacity: 1 }, { duration: 200 }))
  cy.edges().forEach(e => e.animate({ opacity: 1 }, { duration: 200 }))
}

function fitGraph() {
  const conceptNodes = cy.nodes().filter(n => {
    const type = n.data('type')
    return type && type !== 'child' && type !== 'parent' && n.style('display') !== 'none'
  })
  if (conceptNodes.length > 0) {
    cy.fit(conceptNodes, 50)
  } else {
    cy.fit(50)
  }
}

function resetLayout() {
  if (!cy || viewMode.value === 'catalog') return
  if (viewMode.value === 'document') {
    runTreeLayout(cy)
  } else {
    layoutConceptGraph()
  }
}

function switchViewMode(mode) {
  if (viewMode.value === mode) return
  gapTooltipVisible.value = false
  showGapSupplement.value = false
  viewMode.value = mode
  loadAllNodes()
}

async function expandNeighbors() {
  if (!selectedNode.value) return
  await expandNode(selectedNode.value.id)
}

function focusNode() {
  if (!selectedNode.value) return
  const node = cy.getElementById(selectedNode.value.id)
  if (node.length) {
    cy.animate({
      fit: { eles: node, padding: 100 },
      duration: 500,
    })
  }
}

function searchNode() {
  if (!searchQuery.value || !cy) return
  const query = searchQuery.value.toLowerCase()

  const matches = cy.nodes().filter(n => {
    const label = (n.data('label') || '').toLowerCase()
    const id = (n.id() || '').toLowerCase()
    const text = (n.data('text') || '').toLowerCase()
    const desc = (n.data('description') || '').toLowerCase()
    return label.includes(query) || id.includes(query) || text.includes(query) || desc.includes(query)
  })

  if (matches.length > 0) {
    const first = matches[0]
    revealTreePageForNode(first.data('originalId') || first.id(), { fit: false })
    first.select()
    selectedNode.value = {
      id: first.id(),
      label: first.data('label'),
      type: first.data('type'),
      source: first.data('source'),
      page_number: first.data('page_number'),
      heading_path: first.data('heading_path') || '',
      text: first.data('text') || '',
      description: first.data('description') || '',
    }
    focusNode()
    highlightNeighbors(first)
  }
}

// ========== Phase 2: 概念操作 ==========
// P39-FIX: isChunkNodeType 需要包含所有 chunk 类型（heading/paragraph/document/markdown/image_pseudo 等）
function isChunkNodeType(nodeType) {
  if (!nodeType) return true
  const chunkTypes = ['child', 'parent', 'markdown', 'heading', 'paragraph', 'document', 'image', 'image_pseudo', 'formula_pseudo']
  return chunkTypes.includes(nodeType)
}

function typeLabel(type) {
  const map = {
    'definition': '定义', 'law': '规律', 'application': '应用', 'extension': '扩展',
    'requirement': '需求', 'sub_requirement': '子需求',
    'technology': '技术', 'sub_technology': '子技术', 'concept': '概念',
  }
  return map[type] || type
}

async function loadConcepts(chunkId) {
  selectedNodeConcepts.value = []
  conceptsLoading.value = true
  try {
    // LA-051-P2-FIX: 添加认证 headers
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/chunk/${chunkId}/concepts`,
      { headers: getAuthHeaders() }
    )
    if (resp.ok) {
      const data = await resp.json()
      selectedNodeConcepts.value = data.concepts || []
    }
  } catch (e) {
    console.error('[GraphView] 加载概念失败:', e)
  } finally {
    conceptsLoading.value = false
  }
}

async function loadConceptNodeLinks(nodeId) {
  conceptNodeLinks.value = []
  try {
    // LA-051-P2-FIX: 添加认证 headers
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/subgraph/${nodeId}?depth=1`,
      { headers: getAuthHeaders() }
    )
    if (!resp.ok) return
    const data = await resp.json()
    const links = []
    for (const e of data.edges || []) {
      const targetNode = data.nodes.find(n => n.id === e.target)
      const sourceNode = data.nodes.find(n => n.id === e.source)
      if (e.source === nodeId) {
        links.push({ direction: 'out', type: e.type, targetName: targetNode?.label || e.target })
      } else if (e.target === nodeId) {
        links.push({ direction: 'in', type: e.type, targetName: sourceNode?.label || e.source })
      }
    }
    conceptNodeLinks.value = links
  } catch (e) {
    console.error('[GraphView] 加载概念关联失败:', e)
  }
}

async function extractConcepts() {
  if (!selectedNode.value) return
  const chunkId = selectedNode.value.id
  isExtracting.value = true
  try {
    // LA-051-P2-FIX: 添加认证 headers
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/extract/${chunkId}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({ paradigm: selectedParadigm.value }),
      }
    )
    if (resp.ok) {
      const data = await resp.json()
      selectedNodeConcepts.value = data.concepts || []
      alert(`提取完成！共识别 ${data.concepts_extracted} 个概念`)
    } else {
      alert(`提取失败: ${await resp.text()}`)
    }
  } catch (e) {
    alert('提取失败，请检查网络连接')
  } finally {
    isExtracting.value = false
  }
}

// ========== 构建配置 ==========
function openBuildOptions() {
  showBuildOptions.value = true
}

async function loadMergeCandidates(buildId) {
  mergeReviewLoading.value = true
  mergeReviewError.value = ''
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/builds/${buildId}/merge-candidates`,
      { headers: getAuthHeaders() },
    )
    if (!resp.ok) throw new Error(await resp.text())
    const data = await resp.json()
    mergeCandidates.value = data.candidates || []
    showMergeReview.value = true
  } catch (error) {
    mergeReviewError.value = `无法加载审核队列：${error.message}`
  } finally {
    mergeReviewLoading.value = false
  }
}

async function restorePendingMergeReview() {
  if (!canWriteGaps.value || !currentSubject.value) return
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/merge-review/pending`,
      { headers: getAuthHeaders() },
    )
    if (!resp.ok) return
    const data = await resp.json()
    if (data.build?.build_id) {
      mergeBuildId.value = data.build.build_id
      await loadMergeCandidates(data.build.build_id)
    }
  } catch {
    // A pending review is optional UI state; normal graph loading must continue.
  }
}

async function saveMergeDecision(payload) {
  mergeReviewSaving.value = true
  mergeReviewError.value = ''
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/builds/${mergeBuildId.value}/merge-candidates/${payload.candidate.candidate_id}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          decision: payload.decision,
          canonical_name: payload.canonical_name,
          relation_decision: payload.relation_decision,
        }),
      },
    )
    if (!resp.ok) throw new Error(await resp.text())
    const saved = await resp.json()
    const index = mergeCandidates.value.findIndex(item => item.candidate_id === saved.candidate_id)
    if (index >= 0) mergeCandidates.value[index] = saved
    payload.onSaved?.()
  } catch (error) {
    mergeReviewError.value = `保存审核结果失败：${error.message}`
  } finally {
    mergeReviewSaving.value = false
  }
}

async function requestMergeAdvice() {
  mergeAdviceLoading.value = true
  mergeReviewError.value = ''
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/builds/${mergeBuildId.value}/merge-review/advice`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ force: false }),
      },
    )
    if (!resp.ok) throw new Error(await resp.text())
    const data = await resp.json()
    mergeCandidates.value = data.candidates || []
  } catch (error) {
    mergeReviewError.value = `生成 LLM 预审建议失败：${error.message}`
  } finally {
    mergeAdviceLoading.value = false
  }
}

async function acceptMergeAdvice() {
  mergeAdviceAccepting.value = true
  mergeReviewError.value = ''
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/builds/${mergeBuildId.value}/merge-review/accept-advisor`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ threshold: 0.9 }),
      },
    )
    if (!resp.ok) throw new Error(await resp.text())
    const data = await resp.json()
    mergeCandidates.value = data.candidates || []
  } catch (error) {
    mergeReviewError.value = `确认高置信建议失败：${error.message}`
  } finally {
    mergeAdviceAccepting.value = false
  }
}

async function submitMergeReview() {
  mergeReviewSubmitting.value = true
  mergeReviewError.value = ''
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/builds/${mergeBuildId.value}/merge-review/submit`,
      { method: 'POST', headers: getAuthHeaders() },
    )
    if (!resp.ok) throw new Error(await resp.text())
    showMergeReview.value = false
    clearConfigCache()
    paradigmConfig.value = null
    cy.elements().remove()
    await loadAllNodes()
    window.alert('合并审核已提交，知识图谱构建完成。')
  } catch (error) {
    mergeReviewError.value = `继续构建失败：${error.message}`
  } finally {
    mergeReviewSubmitting.value = false
  }
}

async function confirmBuild(options) {
  isRebuilding.value = true
  buildProgress.value = '正在构建结构层...'

  try {
    // LA-051-P2-FIX: 添加认证 headers
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/build`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          paradigm: options.paradigm,
          force_rebuild: options.forceRebuild,
          with_semantic: options.withSemantic,
          with_dedupe: options.withDedupe,
          granularity: options.granularity,
          llm_provider: options.llmProvider === 'auto' ? null : options.llmProvider,
        }),
      }
    )

    if (!resp.ok) throw new Error(await resp.text())
    const data = await resp.json()

    if (resp.status === 202 && data.status === 'waiting_merge_review') {
      showBuildOptions.value = false
      mergeBuildId.value = data.build_id
      buildProgress.value = `概念提取完成，等待审核 ${data.merge_review?.pending_candidates || 0} 组合并候选`
      await loadMergeCandidates(data.build_id)
      return
    }

    showBuildOptions.value = false
    // The build can change the subject paradigm. Never reuse the pre-build
    // cache, otherwise theory edges are classified with engineering rules.
    clearConfigCache()
    paradigmConfig.value = null
    cy.elements().remove()
    await loadAllNodes()

    alert(`图谱构建完成！\n结构层：${data.chunks_total || 0} 个 chunk\n语义层：${data.semantic?.chunks_extracted || 0} 个 chunk 提取成功\n去重：${data.dedupe?.canonical_concepts || 0} 个规范概念`)
  } catch (e) {
    alert('构建失败: ' + e.message)
  } finally {
    isRebuilding.value = false
    buildProgress.value = ''
  }
}

function showConceptDetail(concept) {
  selectedConcept.value = concept
  showConceptModal.value = true
}

// LA-UI-001 M3: 节点分享到群聊（左→右）
function handleShareNode(node) {
  if (!node) return
  const detail = {
    title: node.label || (node.text || '').slice(0, 30) || node.id,
    preview: node.description || (node.text || '').slice(0, 200),
    conceptType: node.type || '',
    data: { node_id: node.id, concept_type: node.type || '' },
    sourceView: 'graph',
  }
  window.dispatchEvent(new CustomEvent('share-to-chat', { detail }))
}

function navigateToChunk(chunkId) {
  // LA-035-P19: 切换到文档树视图并高亮指定 chunk
  if (!cy) return
  if (viewMode.value !== 'document') {
    switchViewMode('document')
  }
  // 等待文档树加载完成
  nextTick(() => {
    const target = cy.getElementById(chunkId)
    if (target.length > 0) {
      cy.animate({
        fit: { eles: target, padding: 100 },
        duration: 500,
      })
      target.select()
      showConceptModal.value = false
    } else {
      alert(`Chunk ${chunkId} 不在当前视图中`)
    }
  })
}

// LA-UI-001 M4: 图谱命令处理（CommandExecutor → graph-command，设计文档 §3.2）
function handleGraphCommand(payload) {
  if (!payload || payload.action !== 'highlight_nodes') return
  highlightNodesByCommand(payload)
}

function highlightNodesByCommand(payload) {
  const ids = payload.node_ids || []
  const labels = (payload.labels || []).map(l => String(l).toLowerCase()).filter(Boolean)

  const tryMatch = () => {
    if (!cy) return 0
    const matches = cy.nodes().filter(n => {
      if (ids.includes(n.id())) return true
      const label = (n.data('label') || '').toLowerCase()
      if (!label) return false
      // 概念名匹配：等值或互为子串（label 可能被截断）
      return labels.some(q => label === q || label.includes(q) || q.includes(label))
    })
    if (!matches.length) return 0
    cy.nodes().unselect()
    matches.select()
    const first = matches[0]
    // LA-UI-001 M4-FIX2: 与点击节点走完全相同的激活路径
    // （完整详情/关联加载/邻接高亮），并只聚焦首节点（多节点 fit 会拉低缩放）
    activateNode(first)
    cy.animate({ fit: { eles: first, padding: 100 }, duration: 500 })
    console.log('[GraphView] M4 命令高亮节点:', matches.length)
    return matches.length
  }

  if (tryMatch() > 0) return
  // 当前视图未命中（如概念节点在文档树视图不可见）：切到概念视图后轮询重试
  if (viewMode.value !== 'concept') {
    switchViewMode('concept')
    let attempts = 0
    const timer = setInterval(() => {
      attempts += 1
      if (tryMatch() > 0 || attempts >= 10) clearInterval(timer)
    }, 300)
  }
}

// ========== 生命周期 ==========
onMounted(async () => {
  initCy()
  await loadAllNodes()
  await restorePendingMergeReview()
  // LA-UI-001 M4: 注册图谱命令监听
  offGraphCommand = busOn('graph-command', handleGraphCommand)
})

onUnmounted(() => {
  gapLoadSequence += 1
  clearGapProposalPoll()
  if (gapTooltipTimer) clearTimeout(gapTooltipTimer)
  if (gapRenderTimer) clearTimeout(gapRenderTimer)
  if (offGraphCommand) {
    offGraphCommand()
    offGraphCommand = null
  }
  if (cy) {
    cy.destroy()
    cy = null
  }
})

watch(currentSubject, () => {
  clearGapProposalPoll()
  showGapSupplement.value = false
  activeGap.value = null
  gapProposal.value = null
  gapCompletionNotice.value = null
  // LA-052: 切换学科时清除范式配置缓存
  clearConfigCache()
  paradigmConfig.value = null
  if (cy) {
    cy.elements().remove()
    loadAllNodes()
  }
  restorePendingMergeReview()
})

watch(gapStatus, () => {
  gapTooltipVisible.value = false
})

watch([gapMissingType, gapMinConfidence], () => {
  if (gapRenderTimer) clearTimeout(gapRenderTimer)
  gapRenderTimer = setTimeout(() => {
    relayoutGapElements()
  }, 120)
})
</script>

<style scoped>
.graph-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.view-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: var(--header-height, 48px);
  border-bottom: 1px solid var(--border-color, #e0e0e0);
  flex-shrink: 0;
  background: var(--bg-card, #fff);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary, #2c3e50);
}

.header-subject .tag {
  background: var(--bg-active, #ecf0f1);
  color: var(--accent-primary, #3498db);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: var(--font-size-xs);
}

.graph-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  min-width: 0;
}

/* 工具栏 */
.toolbar {
  /* M3-LAYOUT: 常驻顶栏，宽度随分隔栏伸缩，内部组件均匀填满 */
  margin: 12px 12px 8px;
  align-self: stretch;
  justify-content: space-between;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  flex-shrink: 0;
  overflow-x: auto;
  scrollbar-width: thin;
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.search-input {
  padding: 6px 10px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 4px;
  font-size: var(--font-size-sm);
  width: 180px;
}

.search-input:focus {
  outline: none;
  border-color: var(--accent-primary, #3498db);
}

.stats {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  white-space: nowrap;
}

.tree-pager {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 4px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 6px;
  background: var(--bg-card, #fff);
}

.tree-page-button {
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text-primary, #2c3e50);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}

.tree-page-button:hover:not(:disabled) { background: var(--bg-hover, #f1f3f5); }
.tree-page-button:disabled { opacity: 0.32; cursor: default; }
.tree-page-button:focus-visible,
.tree-page-select:focus-visible { outline: 2px solid var(--accent-primary, #3498db); outline-offset: 1px; }

.tree-page-select {
  width: 188px;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--text-primary, #2c3e50);
  font-size: var(--font-size-xs);
  cursor: pointer;
}

.tree-page-count {
  min-width: 48px;
  color: var(--text-muted, #7f8c8d);
  font-size: 11px;
  text-align: center;
}

/* 画布 */
/* M3-LAYOUT: 工具栏下方的画布行，面板 absolute 定位于此 */
.graph-body {
  flex: 1;
  display: flex;
  position: relative;
  min-height: 0;
  overflow: hidden;
}

.canvas-wrapper {
  flex: 1;
  position: relative;
  background: var(--bg-canvas, #f8f9fa);
}

.cy-container {
  width: 100%;
  height: 100%;
}

.gap-completion-notice {
  position: absolute;
  top: 14px;
  left: 50%;
  z-index: 13;
  display: flex;
  align-items: center;
  gap: 9px;
  max-width: min(520px, calc(100% - 28px));
  padding: 9px 10px 9px 12px;
  border: 1px solid #a8d8bc;
  border-radius: 9px;
  background: #f1faf5;
  color: #205f39;
  box-shadow: 0 8px 22px rgba(30, 91, 55, 0.14);
  font-size: 12px;
  transform: translateX(-50%);
}

.gap-completion-notice span { line-height: 1.4; }
.gap-completion-notice button {
  flex: 0 0 auto;
  border: 1px solid #72bd91;
  border-radius: 6px;
  padding: 4px 7px;
  background: #fff;
  color: #205f39;
  cursor: pointer;
}
.gap-completion-notice button:hover { background: #e1f5e9; }
.gap-completion-notice button:focus-visible { outline: 2px solid #258b55; outline-offset: 2px; }
.gap-completion-notice .notice-close { border-color: transparent; background: transparent; font-size: 16px; line-height: 1; }

/* 图例 */
.legend {
  position: absolute;
  bottom: 12px;
  left: 12px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: var(--font-size-xs);
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.legend-title {
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--text-primary, #2c3e50);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  color: var(--text-secondary, #555);
}

.legend-shape {
  width: 12px;
  height: 12px;
  display: inline-block;
}

.legend-shape.circle { border-radius: 50%; }
.legend-shape.rect { border-radius: 2px; }
.legend-shape.diamond {
  transform: rotate(45deg);
  width: 9px;
  height: 9px;
  margin: 1.5px;
}

.legend-shape.gap-placeholder {
  box-sizing: border-box;
  border: 2px dashed #e67e22;
  border-radius: 50%;
  background: #fff8f0;
}

.legend-line {
  width: 16px;
  height: 0;
  border-top: 2px solid;
  display: inline-block;
}

/* 按钮 */
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

.btn:hover { background: var(--bg-hover, #f0f0f0); }

.btn-primary {
  background: var(--accent-primary, #3498db);
  color: #fff;
  border-color: var(--accent-primary, #3498db);
}

.btn-primary:hover { background: #2980b9; }

.btn-secondary {
  background: var(--bg-active, #ecf0f1);
  color: var(--text-primary, #2c3e50);
  border: 1px solid var(--border-color, #e0e0e0);
}

.btn-secondary:hover { background: var(--bg-hover, #f8f9fa); }

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

/* Spinner */
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

/* 范式选择 */
.paradigm-select {
  padding: 4px 8px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 4px;
  font-size: var(--font-size-xs);
  background: var(--bg-card, #fff);
  color: var(--text-primary, #2c3e50);
  cursor: pointer;
  outline: none;
}

.paradigm-select:focus {
  border-color: var(--accent-primary, #3498db);
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal-content {
  background: var(--bg-card, #fff);
  border-radius: 8px;
  width: 100%;
  max-width: 480px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  animation: modalSlide 0.2s ease;
}

@keyframes modalSlide {
  from { opacity: 0; transform: translateY(-20px); }
  to { opacity: 1; transform: translateY(0); }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.modal-header h3 {
  margin: 0;
  font-size: var(--font-size-md);
  color: var(--text-primary, #2c3e50);
}

.modal-body {
  padding: 20px;
}

.modal-section {
  margin-bottom: 16px;
}

.modal-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.modal-aliases {
  font-size: var(--font-size-sm);
  color: var(--text-secondary, #555);
  line-height: 1.5;
  word-break: break-all;
}

.modal-sources {
  font-size: var(--font-size-sm);
  color: var(--text-primary, #2c3e50);
}

.modal-source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.modal-source-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--font-size-xs);
  background: var(--bg-hover, #f0f0f0);
  color: var(--text-secondary, #555);
  cursor: pointer;
  transition: all 0.2s;
}

.modal-source-tag:hover {
  background: var(--primary-color, #3498db);
  color: #fff;
}

.type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--font-size-xs);
  font-weight: 600;
}
</style>
