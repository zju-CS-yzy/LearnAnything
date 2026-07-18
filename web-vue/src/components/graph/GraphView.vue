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
        <div class="toolbar-group">
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
          >📄 文档树</button>
          <button 
            class="btn btn-sm" 
            :class="{ 'btn-primary': viewMode === 'concept' }"
            @click="switchViewMode('concept')" 
            title="知识图谱"
          >🧩 知识图谱</button>
          <button class="btn btn-sm" @click="fitGraph" title="适应窗口">⬜ 适应</button>
          <button class="btn btn-sm" @click="resetLayout" title="重置布局">🔄 重置</button>
          <button class="btn btn-sm btn-primary" @click="openBuildOptions" :disabled="isBuilding">
            <span v-if="isBuilding" class="spinner-inline"></span>
            <span v-else>🏗️ 构建图谱</span>
          </button>
        </div>
        <div class="toolbar-group">
          <span class="stats">节点: {{ nodeCount }} | 边: {{ edgeCount }}</span>
        </div>
      </div>

      <!-- 画布 + 图例 -->
      <div class="canvas-wrapper">
        <div ref="cyContainer" class="cy-container"></div>

        <div class="legend">
          <div class="legend-title">图例</div>
          <div class="legend-item">
            <span class="legend-shape circle" style="background: #3498db;"></span>
            <span>知识片段</span>
          </div>
          <div class="legend-item">
            <span class="legend-shape diamond" style="background: #e74c3c;"></span>
            <span>需求节点</span>
          </div>
          <div class="legend-item">
            <span class="legend-shape rect" style="background: #3498db;"></span>
            <span>技术节点</span>
          </div>
          <div class="legend-item">
            <span class="legend-shape rect" style="background: #2ecc71;"></span>
            <span>其他概念</span>
          </div>
          <div class="legend-item">
            <span class="legend-line" style="border-color: #3498db;"></span>
            <span>层级关系</span>
          </div>
          <div class="legend-item">
            <span class="legend-line" style="border-color: #95a5a6; border-style: dashed;"></span>
            <span>相邻关系</span>
          </div>
          <div class="legend-item">
            <span class="legend-line" style="border-color: #e67e22;"></span>
            <span>解决 (SOLUTION)</span>
          </div>
          <div class="legend-item">
            <span class="legend-line" style="border-color: #9b59b6; border-style: dotted;"></span>
            <span>依赖 (DEPENDS_ON)</span>
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
      />
    </div>

    <!-- 概念表格 -->
    <ConceptTable
      :concepts="conceptTable"
      @select="showConceptDetail"
    />

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
            <span class="type-badge" :class="'type-' + selectedConcept.concept_type">{{ typeLabel(selectedConcept.concept_type) }}</span>
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, inject, nextTick } from 'vue'
import cytoscape from 'cytoscape'
import cola from 'cytoscape-cola'
import dagre from 'cytoscape-dagre'
import { buildCyStyles } from './GraphStyles.js'
import { runTreeLayout, runConceptLayout, generateNodeLabel, buildUMLCardLabel } from './GraphLayout.js'
import NodeDetailPanel from './NodeDetailPanel.vue'
import BuildOptions from './BuildOptions.vue'
import ConceptTable from './ConceptTable.vue'
import GraphNodeTooltip from './GraphNodeTooltip.vue'

cytoscape.use(cola)
cytoscape.use(dagre)

// ========== 全局学科状态 ==========
const subjectState = inject('subjectState')
const currentSubject = computed(() => subjectState.currentSubject.value)
const currentSubjectName = computed(() => {
  const sub = subjectState.subjects.value.find(s => s.id === currentSubject.value)
  return sub?.name || currentSubject.value
})

// ========== DOM 引用 ==========
const cyContainer = ref(null)

// ========== Cytoscape 实例 ==========
let cy = null

// ========== 状态 ==========
const nodes = ref([])
const edges = ref([])
const selectedNode = ref(null)
const searchQuery = ref('')
const isBuilding = ref(false)
const isLoading = ref(false)
const nodeCount = ref(0)
const edgeCount = ref(0)

// LA-035-P19: 视图模式 — 'document' 文档结构树 / 'concept' 知识图谱
const viewMode = ref('concept')

// 构建选项
const showBuildOptions = ref(false)
const isRebuilding = ref(false)
const buildProgress = ref('')

// Phase 2: 概念分解
const selectedNodeConcepts = ref([])
const conceptsLoading = ref(false)
const isExtracting = ref(false)
const conceptNodeLinks = ref([])
const selectedParadigm = ref('theory')

// 概念弹窗
const selectedConcept = ref(null)
const showConceptModal = ref(false)

// LA-035-P10: 悬浮预览卡片状态
const tooltipVisible = ref(false)
const tooltipNode = ref(null)
const tooltipPosition = ref({ x: 0, y: 0 })
let tooltipTimer = null

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
    const node = e.target
    const nodeType = node.data('type') || ''
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
  })

  // LA-035-P10: 鼠标悬停显示预览卡片（仅概念节点）
  cy.on('mouseover', 'node', (e) => {
    const node = e.target
    const nodeType = node.data('type') || ''
    // 只对概念节点显示 tooltip
    if (['child', 'parent', 'markdown'].includes(nodeType)) return

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
      source_chunks: node.data('source_chunks') || [],
      media_refs: node.data('media_refs') || [],
    }
    tooltipVisible.value = true
  })

  cy.on('mouseout', 'node', (e) => {
    const node = e.target
    const nodeType = node.data('type') || ''
    if (['child', 'parent', 'markdown'].includes(nodeType)) return

    // 延迟关闭，允许鼠标移入 tooltip
    tooltipTimer = setTimeout(() => {
      tooltipVisible.value = false
    }, 200)
  })

  cy.on('tap', (e) => {
    if (e.target === cy) {
      selectedNode.value = null
      tooltipVisible.value = false
      clearHighlight()
    }
  })

  cy.on('dbltap', 'node', async (e) => {
    await expandNode(e.target.id())
  })
}

// ========== 数据加载 ==========
async function loadAllNodes() {
  isLoading.value = true
  try {
    if (!cy) return
    cy.elements().remove()

    if (viewMode.value === 'document') {
      // LA-035-P19: 文档结构树视图 — 只加载 Chunk 节点 + 结构边
      await loadChunkNodes()
      await loadEdges()
      if (cy.nodes().length > 0) {
        runTreeLayout(cy)
      }
    } else {
      // LA-035-P19: 知识图谱视图 — 只加载 CanonicalConcept + 语义边
      await loadConceptNodes()
      await loadSemanticEdges()
      if (cy.nodes().length > 0) {
        runConceptLayout(cy)
      }
    }

    await nextTick()
    if (cy) {
      cy.resize()
    }

    nodeCount.value = cy.nodes().length
    edgeCount.value = cy.edges().length
  } catch (e) {
    console.error('[GraphView] 加载图谱失败:', e)
  } finally {
    isLoading.value = false
  }
}

async function loadChunkNodes() {
  try {
    // P30-FIX: limit 从 500 增大到 1000，避免大文档 chunk 节点被截断
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/nodes?limit=1000`
    )
    if (!resp.ok) {
      console.warn('[GraphView] Nodes API failed:', resp.status)
      return
    }
    const data = await resp.json()
    const chunkNodes = (data.nodes || []).map(n => ({
      data: {
        id: n.id,
        label: generateNodeLabel(n.text, n.heading_path, n.id),
        type: n.chunk_type || 'child',
        chunkType: n.chunk_type || 'child',
        source: n.source,
        page_number: n.page_number,
        text: n.text || '',
        heading_path: n.heading_path || '',
        // LA-035: 图片字段
        image_path: n.image_path || '',
        thumbnail_path: n.thumbnail_path || '',
        width: n.width || 0,
        height: n.height || 0,
      }
    }))
    if (chunkNodes.length > 0 && cy) {
      cy.add(chunkNodes)
    }
  } catch (e) {
    console.error('[GraphView] 加载 chunk 节点失败:', e)
  }
}

async function loadEdges() {
  try {
    // P30-FIX: limit 从 200 增大到 1000，避免 BELONGS_TO 边被截断
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/edges?limit=1000`
    )
    if (!resp.ok) {
      console.warn('[GraphView] Edges API failed:', resp.status)
      return
    }
    const data = await resp.json()
    const allEdges = (data.edges || [])
      .filter(edge => edge.type === 'BELONGS_TO')  // P30-FIX: 文档树只加载层级边，过滤同级顺序边
      .map(edge => ({
        data: {
          id: `${edge.source}-${edge.type}-${edge.target}`,
          source: edge.source,
          target: edge.target,
          type: edge.type,
        }
      }))
    if (allEdges.length > 0 && cy) {
      cy.add(allEdges)
    }
  } catch (e) {
    console.error('[GraphView] 加载边失败:', e)
  }
}

async function loadConceptNodes() {
  try {
    const url = `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/concepts?limit=2000`
    const resp = await fetch(url)
    if (!resp.ok) {
      console.warn('[GraphView] 概念节点 API 失败:', resp.status)
      return
    }
    const data = await resp.json()
    const conceptNodes = (data.concepts || []).map(c => {
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

      // LA-035-P10: 解析 media_refs，计算内容类型和边框颜色
      const mediaRefs = c.media_refs || []
      let hasImage = false
      let hasTable = false
      let hasFormula = false
      mediaRefs.forEach(ref => {
        const t = (ref.type || ref.media_type || '').toLowerCase()
        if (t.includes('image') || t.includes('图片') || t.includes('fig')) hasImage = true
        else if (t.includes('table') || t.includes('表格') || t.includes('tab')) hasTable = true
        else if (t.includes('formula') || t.includes('公式') || t.includes('math') || t.includes('equation')) hasFormula = true
        else hasImage = true // 默认归类为图片
      })

      // 根据媒体类型确定边框颜色
      const typeBorderColors = {
        'requirement': '#c0392b',
        'sub_requirement': '#c0392b',
        'technology': '#2980b9',
        'sub_technology': '#2980b9',
        'concept': '#27ae60',
        'definition': '#27ae60',
        'law': '#27ae60',
        'application': '#27ae60',
        'extension': '#27ae60',
      }
      // 媒体类型优先：有图片→橙色，有表格→蓝色，有公式→紫色，多种→灰色
      let borderColor = typeBorderColors[c.type || 'concept'] || '#27ae60'
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
          // LA-035: 多媒体引用
          media_refs: mediaRefs,
          has_media: mediaRefs.length > 0,
          hasImage: hasImage,
          hasTable: hasTable,
          hasFormula: hasFormula,
        }
      }
    })
    if (conceptNodes.length > 0 && cy) {
      cy.add(conceptNodes)
    }
  } catch (e) {
    console.error('[GraphView] 加载概念节点失败:', e)
  }
}

async function loadSemanticEdges() {
  try {
    const url = `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/concept-links?limit=2000`
    const resp = await fetch(url)
    if (!resp.ok) {
      console.warn('[GraphView] 语义连接 API 失败:', resp.status)
      return
    }
    const data = await resp.json()
    const semEdges = (data.edges || []).map(edge => ({
      data: {
        id: `${edge.source}-${edge.type}-${edge.target}`,
        source: edge.source,
        target: edge.target,
        type: edge.type,
        label: edge.type === 'SOLUTION' ? '解决' : '依赖',
        confidence: edge.confidence || 0,
      }
    }))
    if (semEdges.length > 0 && cy) {
      cy.add(semEdges)
    }
  } catch (e) {
    console.error('[GraphView] 加载语义连接失败:', e)
  }
}

async function expandNode(nodeId) {
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/subgraph/${nodeId}?depth=1`
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
    runTreeLayout(cy)
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
    return type && type !== 'child' && type !== 'parent'
  })
  if (conceptNodes.length > 0) {
    cy.fit(conceptNodes, 50)
  } else {
    cy.fit(50)
  }
}

function resetLayout() {
  if (viewMode.value === 'document') {
    runTreeLayout(cy)
  } else {
    runConceptLayout(cy)
  }
}

function switchViewMode(mode) {
  if (viewMode.value === mode) return
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
function isChunkNodeType(nodeType) {
  if (!nodeType) return true
  return ['child', 'parent'].includes(nodeType)
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
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/chunk/${chunkId}/concepts`
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
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/subgraph/${nodeId}?depth=1`
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
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/extract/${chunkId}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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

async function confirmBuild(options) {
  isRebuilding.value = true
  buildProgress.value = '正在构建结构层...'

  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/build`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paradigm: options.paradigm,
          force_rebuild: options.forceRebuild,
          with_semantic: options.withSemantic,
        }),
      }
    )

    if (!resp.ok) throw new Error(await resp.text())
    const data = await resp.json()

    showBuildOptions.value = false
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

// ========== 生命周期 ==========
onMounted(() => {
  initCy()
  loadAllNodes()
})

onUnmounted(() => {
  if (cy) {
    cy.destroy()
    cy = null
  }
})

watch(currentSubject, () => {
  if (cy) {
    cy.elements().remove()
    loadAllNodes()
  }
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
  overflow: hidden;
  position: relative;
}

/* 工具栏 */
.toolbar {
  position: absolute;
  top: 12px;
  left: 12px;
  right: 320px;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 6px;
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

/* 画布 */
.canvas-wrapper {
  flex: 1;
  position: relative;
  background: var(--bg-canvas, #f8f9fa);
}

.cy-container {
  width: 100%;
  height: 100%;
}

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
