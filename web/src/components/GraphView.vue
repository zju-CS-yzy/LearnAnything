<template>
  <div class="graph-view">
    <div class="toolbar">
      <div class="toolbar-group">
        <button class="btn btn-sm" @click="fitGraph" title="适应窗口">⬜ 适应</button>
        <button class="btn btn-sm btn-primary" @click="openBuildOptions" :disabled="isBuilding">
          <span v-if="isBuilding">🔄 构建中...</span>
          <span v-else>🚀 构建图谱</span>
        </button>
      </div>
      <div class="toolbar-group search-box">
        <input v-model="searchQuery" @input="onSearchInput" placeholder="🔍 搜索节点..." class="search-input" />
        <button class="btn btn-sm" @click="clearSearch" v-if="searchQuery">❌</button>
      </div>
      <div class="toolbar-group stats">
        <span>节点: {{ nodeCount }}</span>
        <span>边: {{ edgeCount }}</span>
      </div>
    </div>

    <div class="graph-wrapper">
      <div class="loading-overlay" v-if="loading">
        <div class="loading-spinner">⏳</div>
        <div class="loading-text">加载图谱...</div>
      </div>
      <div class="error-overlay" v-if="error">
        <div class="error-text">❌ 加载失败</div>
        <div class="error-detail">{{ error }}</div>
        <button class="btn btn-primary" @click="loadAllNodes">重试</button>
      </div>
      <div class="graph-container" ref="graphContainer"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'

cytoscape.use(dagre)

const props = defineProps({
  subject: { type: String, default: 'generic' }
})

const emit = defineEmits(['node-selected'])

const graphContainer = ref(null)
const loading = ref(false)
const error = ref(null)
const nodeCount = ref(0)
const edgeCount = ref(0)
const searchQuery = ref('')
const isBuilding = ref(false)

let cy = null
let searchTimer = null

onMounted(() => {
  initCytoscape()
  loadAllNodes()
})

onUnmounted(() => {
  if (cy) {
    cy.destroy()
    cy = null
  }
})

function initCytoscape() {
  if (!graphContainer.value) return
  cy = cytoscape({
    container: graphContainer.value,
    style: [
      {
        selector: 'node',
        style: {
          'label': 'data(cardLabel)',
          'text-wrap': 'wrap',
          'text-max-width': '110px',
          'text-valign': 'center',
          'text-halign': 'center',
          'font-size': '12px',
          'color': '#fff',
          'text-outline-color': 'rgba(0,0,0,0.6)',
          'text-outline-width': 2,
          'width': 160,
          'height': 'data(cardHeight)',
          'padding': '18px',
          'border-width': 2,
          'border-color': 'rgba(255,255,255,0.5)',
          'shape': 'round-rectangle',
          'corner-radius': 8,
        }
      },
      {
        selector: 'node[type="requirement"]',
        style: { 'background-color': '#3b82f6' }
      },
      {
        selector: 'node[type="sub_requirement"]',
        style: { 'background-color': '#60a5fa' }
      },
      {
        selector: 'node[type="technology"]',
        style: { 'background-color': '#10b981' }
      },
      {
        selector: 'node[type="sub_technology"]',
        style: { 'background-color': '#6ee7b7' }
      },
      {
        selector: 'node[type="concept"]',
        style: { 'background-color': '#8b5cf6' }
      },
      {
        selector: 'edge',
        style: {
          'width': 2,
          'target-arrow-shape': 'triangle',
          'arrow-scale': 1.2,
          'curve-style': 'straight',
        }
      },
      {
        selector: 'edge[type="SOLUTION"]',
        style: {
          'line-color': '#ef4444',
          'target-arrow-color': '#ef4444',
        }
      },
      {
        selector: 'edge[type="DEPENDS_ON"]',
        style: {
          'line-color': '#3b82f6',
          'target-arrow-color': '#3b82f6',
          'line-style': 'dashed',
        }
      },
      {
        selector: 'node[isCopy = "1"]',
        style: {
          'border-style': 'dashed',
          'border-color': '#ff9f43',
          'border-width': 3,
        }
      },
      {
        selector: 'edge[isCopyEdge = "1"]',
        style: {
          'line-style': 'dashed',
          'line-color': '#ff9f43',
          'target-arrow-color': '#ff9f43',
        }
      },
    ],
    minZoom: 0.05,
    maxZoom: 3,
    wheelSensitivity: 0.3,
    selectionType: 'single',
    boxSelectionEnabled: false,
  })

  cy.on('tap', 'node', (evt) => {
    const n = evt.target
    emit('node-selected', {
      name: n.data('label'),
      type: n.data('type'),
      description: n.data('description'),
      source_chunks: n.data('source_chunks'),
    })
  })

  cy.on('tap', (evt) => {
    if (evt.target === cy) {
      emit('node-selected', null)
    }
  })
}

async function loadAllNodes() {
  if (cy) {
    cy.elements().remove()
  }

  try {
    loading.value = true
    error.value = null
    console.log('[GraphView] 开始加载图谱...')

    await loadConceptNodes()
    await loadSemanticEdges()

    if (cy.nodes().length > 0) {
      runConceptLayout()
    }

    await nextTick()
    if (cy) cy.resize()
  } catch (err) {
    error.value = err.message
    console.error('[GraphView] 加载失败:', err)
  } finally {
    loading.value = false
  }
}

async function loadConceptNodes() {
  try {
    const url = `${window.location.origin}/api/knowledge-graph/${props.subject}/concepts?limit=2000`
    console.log('[GraphView] 加载概念节点:', url)
    const resp = await fetch(url)
    if (!resp.ok) {
      console.warn('概念节点 API 失败:', resp.status)
      return
    }
    const data = await resp.json()

    const nodes = (data.concepts || []).map(c => {
      const { cardLabel, cardHeight } = buildUMLCardLabel(c.name || '', c.type || 'concept', c.description || '')
      return {
        data: {
          id: c.id,
          label: c.name,
          cardLabel: cardLabel,
          cardHeight: cardHeight,
          type: c.type || 'concept',
          description: c.description || '',
          source_chunks: c.source_chunks || '',
        }
      }
    })

    if (nodes.length > 0 && cy) {
      cy.add(nodes)
      nodeCount.value = cy.nodes().length
      console.log(`[GraphView] 加载 ${nodes.length} 个概念节点`)
    }
  } catch (e) {
    console.error('加载概念节点失败:', e)
  }
}

async function loadSemanticEdges() {
  try {
    const url = `${window.location.origin}/api/knowledge-graph/${props.subject}/concept-links?limit=2000`
    console.log('[GraphView] 加载语义边:', url)
    const resp = await fetch(url)
    if (!resp.ok) {
      console.warn('语义边 API 失败:', resp.status)
      return
    }
    const data = await resp.json()

    const edges = (data.edges || []).map(e => ({
      data: {
        id: `${e.source}-${e.type}-${e.target}`,
        source: e.source,
        target: e.target,
        type: e.type,
        label: e.type === 'SOLUTION' ? '解决' : '依赖',
      }
    }))

    if (edges.length > 0 && cy) {
      cy.add(edges)
      edgeCount.value = cy.edges().length
      console.log(`[GraphView] 加载 ${edges.length} 条语义边`)
    }
  } catch (e) {
    console.error('加载语义边失败:', e)
  }
}

function runConceptLayout() {
  const nodes = cy.nodes()
  const edges = cy.edges().filter(e => e.style('display') !== 'none')

  if (nodes.length === 0) return

  const all = nodes.union(edges)
  all.layout({
    name: 'dagre',
    rankDir: 'LR',
    rankSep: 250,
    nodeSep: 80,
    edgeSep: 20,
    padding: 20,
    fit: false,
    animate: false,
  }).run()

  const bbox = all.boundingBox()
  const container = cy.container()
  const zoom = Math.min(
    container.clientWidth / bbox.w,
    container.clientHeight / bbox.h,
    0.5
  )
  cy.zoom(Math.max(Math.min(zoom, 0.5), 0.15))
  cy.center(all)

  console.log(`[GraphView] 布局完成: ${nodes.length} 节点, ${edges.length} 边`)
}

function buildUMLCardLabel(name, type, description) {
  const typeLabel = type === 'requirement' ? '需求' :
    type === 'sub_requirement' ? '子需求' :
    type === 'technology' ? '技术' :
    type === 'sub_technology' ? '子技术' : '概念'

  const title = name.substring(0, 12)
  const desc = (description || '').substring(0, 60)
  const descLines = []
  for (let i = 0; i < desc.length; i += 15) {
    descLines.push(desc.substring(i, i + 15))
  }
  const descText = descLines.join('\n')

  const cardLabel = `${title}\n━━━━━━\n${typeLabel}\n━━━━━━\n${descText}`
  const descLineCount = Math.max(descLines.length, 1)
  const cardHeight = Math.max(80, 5 * 16 + (descLineCount - 1) * 16 + 36)

  return { cardLabel, cardHeight }
}

function fitGraph() {
  if (cy) cy.fit()
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    performSearch()
  }, 300)
}

function performSearch() {
  if (!cy) return
  const query = searchQuery.value.toLowerCase()

  if (!query) {
    cy.nodes().style('opacity', 1)
    cy.edges().style('opacity', 1)
    return
  }

  cy.nodes().forEach(n => {
    const label = (n.data('label') || '').toLowerCase()
    const desc = (n.data('description') || '').toLowerCase()
    if (label.includes(query) || desc.includes(query)) {
      n.style('opacity', 1)
    } else {
      n.style('opacity', 0.2)
    }
  })

  cy.edges().style('opacity', 0.1)
}

function clearSearch() {
  searchQuery.value = ''
  if (cy) {
    cy.nodes().style('opacity', 1)
    cy.edges().style('opacity', 1)
  }
}

function openBuildOptions() {
  // TODO
}
</script>

<style scoped>
.graph-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: #1e1e2e;
  border-bottom: 1px solid #313244;
  gap: 12px;
  flex-shrink: 0;
}

.toolbar-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

.search-box {
  flex: 1;
  max-width: 300px;
}

.search-input {
  width: 100%;
  padding: 6px 12px;
  border: 1px solid #313244;
  border-radius: 4px;
  background: #313244;
  color: #cdd6f4;
}

.stats {
  color: #cdd6f4;
  font-size: 12px;
  gap: 16px;
}

.graph-wrapper {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.graph-container {
  width: 100%;
  height: 100%;
  background: #1e1e2e;
}

.loading-overlay, .error-overlay {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(30, 30, 46, 0.9);
  z-index: 10;
}

.loading-spinner {
  font-size: 48px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.loading-text, .error-text {
  margin-top: 16px;
  color: #cdd6f4;
  font-size: 16px;
}

.error-detail {
  margin-top: 8px;
  color: #f38ba8;
  font-size: 12px;
  max-width: 400px;
  text-align: center;
}

.btn {
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.2s;
}

.btn-sm {
  padding: 4px 8px;
  font-size: 12px;
}

.btn-primary {
  background: #3b82f6;
  color: white;
}

.btn-primary:hover {
  background: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
