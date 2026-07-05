<template>
  <div class="graph-view">
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
          <button class="btn btn-sm" @click="showChunkView" title="文档视图">📄 文档</button>
          <button class="btn btn-sm" @click="showConceptView" title="概念视图">🧩 概念</button>
          <button class="btn btn-sm" @click="fitGraph" title="适应窗口">⬜ 适应</button>
          <button class="btn btn-sm" @click="resetLayout" title="重置布局">🔄 重置</button>
          <button class="btn btn-sm btn-primary" @click="openBuildOptions" :disabled="isBuilding">
            <span v-if="isBuilding" class="spinner-inline"></span>
            <span v-else>🏗️ 构建图谱</span>
          </button>
        </div>
        <div class="toolbar-group">
          <select v-model="selectedParadigm" class="paradigm-select" title="选择分解范式">
            <option value="theory">理论归纳</option>
            <option value="engineering">工程分解</option>
            <option value="hierarchical">层级归纳</option>
          </select>
          <button class="btn btn-sm btn-secondary" @click="batchExtract" :disabled="isBatchExtracting">
            <span v-if="isBatchExtracting" class="spinner-inline"></span>
            <span v-else>🧠 批量提取</span>
          </button>
          <button class="btn btn-sm btn-secondary" @click="dedupeConcepts" :disabled="isDeduping">
            <span v-if="isDeduping" class="spinner-inline"></span>
            <span v-else>🔗 去重</span>
          </button>
        </div>
        <div class="toolbar-group">
          <span class="stats">
            节点: {{ nodeCount }} | 边: {{ edgeCount }}
          </span>
        </div>
      </div>

      <!-- 图谱画布 -->
      <div class="canvas-wrapper">
        <div ref="cyContainer" class="cy-container"></div>

        <!-- 图例 -->
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

      <!-- 信息面板 -->
      <div class="info-panel" :class="{ open: selectedNode }">
        <div v-if="selectedNode" class="info-content">
          <div class="info-header">
            <h3>📄 节点详情</h3>
            <button class="btn-icon" @click="selectedNode = null">✕</button>
          </div>

          <div class="info-body">
            <div class="info-section">
              <div class="info-label">ID</div>
              <div class="info-value mono">{{ selectedNode.id }}</div>
            </div>

            <div class="info-section">
              <div class="info-label">来源</div>
              <div class="info-value">{{ selectedNode.source || '-' }}</div>
            </div>

            <div class="info-section">
              <div class="info-label">页码</div>
              <div class="info-value">{{ selectedNode.page_number || '-' }}</div>
            </div>

            <div class="info-section">
              <div class="info-label">内容预览</div>
              <div class="info-text">{{ selectedNode.text || selectedNode.description || '（暂无内容）' }}</div>
            </div>

            <!-- 概念节点专属信息 -->
            <div v-if="selectedNode.description && !selectedNode.text" class="info-section">
              <div class="info-label">概念描述</div>
              <div class="info-text">{{ selectedNode.description }}</div>
            </div>

            <div v-if="selectedNode.parent_hint" class="info-section">
              <div class="info-label">父级关联</div>
              <div class="info-text">{{ selectedNode.parent_hint }}</div>
            </div>

            <div v-if="selectedNode.source_chunks" class="info-section">
              <div class="info-label">来源 Chunk</div>
              <div class="info-text mono">{{ selectedNode.source_chunks }}</div>
            </div>

            <!-- 概念分解（仅对 chunk 节点显示） -->
            <div v-if="isChunkNodeType(selectedNode.type)" class="info-section concept-section">
              <div class="info-label concept-label">
                <span>🧩 概念分解</span>
                <span v-if="conceptsLoading" class="spinner-inline"></span>
              </div>

              <!-- 概念提取按钮 -->
              <div v-if="selectedNodeConcepts.length === 0 && !conceptsLoading" class="concept-actions">
                <button class="btn btn-sm btn-primary" @click="extractConcepts" :disabled="isExtracting">
                  <span v-if="isExtracting">⏳ 提取中...</span>
                  <span v-else>🔬 提取概念</span>
                </button>
              </div>

              <!-- 概念列表 -->
              <div v-if="selectedNodeConcepts.length > 0" class="concept-list">
                <div
                  v-for="c in selectedNodeConcepts"
                  :key="c.id"
                  class="concept-item"
                  :class="'relation-' + c.relation.toLowerCase()"
                >
                  <div class="concept-header">
                    <span class="concept-name">{{ c.name }}</span>
                    <span class="concept-badge" :class="'type-' + c.type">
                      {{ typeLabel(c.type) }}
                    </span>
                  </div>
                  <div class="concept-relation">
                    <span class="relation-tag">{{ relationLabel(c.relation) }}</span>
                  </div>
                  <div v-if="c.description" class="concept-desc">{{ c.description }}</div>
                </div>
              </div>

              <div v-if="selectedNodeConcepts.length === 0 && !conceptsLoading && !isExtracting" class="concept-empty">
                尚未提取概念。点击上方按钮进行语义分析。
              </div>
            </div>

            <!-- 概念节点关联信息（仅对概念节点显示） -->
            <div v-if="!isChunkNodeType(selectedNode.type) && conceptNodeLinks.length > 0" class="info-section concept-section">
              <div class="info-label concept-label">
                <span>🔗 语义关联</span>
              </div>
              <div class="concept-links">
                <div v-for="(link, idx) in conceptNodeLinks" :key="idx" class="concept-link-item">
                  <span class="link-direction">{{ link.direction === 'out' ? '→' : '←' }}</span>
                  <span class="link-type" :class="'link-' + link.type.toLowerCase()">{{ link.type }}</span>
                  <span class="link-target">{{ link.targetName }}</span>
                </div>
              </div>
            </div>

            <div class="info-actions">
              <button class="btn btn-sm btn-primary" @click="expandNeighbors">
                🔍 展开邻居
              </button>
              <button class="btn btn-sm" @click="focusNode">
                🎯 聚焦
              </button>
            </div>
          </div>
        </div>

        <div v-else class="info-empty">
          <div class="empty-icon">👆</div>
          <div class="empty-text">点击节点查看详情</div>
          <div class="empty-hint">双击节点展开子树</div>
        </div>
      </div>
    </div>

    <!-- 概念表格工具栏 -->
    <div class="concept-toolbar" v-if="conceptTable.length > 0">
      <div class="toolbar-group">
        <input
          v-model="conceptSearchQuery"
          class="search-input"
          placeholder="🔍 搜索概念..."
          @keyup.enter="filterConcepts"
        />
        <button class="btn btn-sm" @click="filterConcepts">搜索</button>
      </div>
      <div class="toolbar-group">
        <span class="stats">显示 {{ filteredConcepts.length }} / {{ conceptTable.length }} 个概念</span>
      </div>
    </div>

    <!-- Phase 2: 全局概念表格 -->
    <div v-if="filteredConcepts.length > 0" class="concept-table-wrapper">
      <div class="table-header">
        <h3>📋 全局概念表（去重后）</h3>
        <span class="table-count">共 {{ conceptTable.length }} 个概念</span>
      </div>
      <div class="table-scroll">
        <table class="concept-table">
          <thead>
            <tr>
              <th>概念名称</th>
              <th>别名</th>
              <th>类型</th>
              <th>关系</th>
              <th>来源</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in paginatedConcepts" :key="c.id" @click="showConceptDetail(c)">
              <td class="name-cell">{{ c.name }}</td>
              <td class="alias-cell">
                <span v-if="c.aliases" class="alias-tags">{{ c.aliases.slice(0, 3).join(' | ') }}</span>
              </td>
              <td><span class="type-badge" :class="'type-' + c.concept_type">{{ typeLabel(c.concept_type) }}</span></td>
              <td>{{ relationLabel(c.relation) }}</td>
              <td>{{ c.source_chunk_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <!-- 分页 -->
      <div class="pagination">
        <button class="btn btn-sm" :disabled="currentPage <= 1" @click="currentPage--">上一页</button>
        <span class="page-info">第 {{ currentPage }} / {{ totalPages }} 页</span>
        <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="currentPage++">下一页</button>
        <select v-model="pageSize" class="page-size-select">
          <option :value="10">10/页</option>
          <option :value="20">20/页</option>
          <option :value="50">50/页</option>
          <option :value="100">100/页</option>
        </select>
      </div>
    </div>
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
            <span class="relation-tag">{{ relationLabel(selectedConcept.relation) }}</span>
          </div>
          <div class="modal-section" v-if="selectedConcept.aliases && selectedConcept.aliases.length > 1">
            <div class="modal-label">别名</div>
            <div class="modal-aliases">{{ selectedConcept.aliases.join(' | ') }}</div>
          </div>
          <div class="modal-section" v-if="selectedConcept.source_chunks">
            <div class="modal-label">来源 Chunk</div>
            <div class="modal-sources">{{ selectedConcept.source_chunk_count }} 个 chunk</div>
          </div>
        </div>
      </div>
    </div>

    <!-- ========== 图谱构建选项面板 ========== -->
    <div v-if="showBuildOptions" class="build-options-overlay">
      <div class="build-options-panel">
        <div class="build-options-header">
          <h2>🏗️ 图谱生成配置</h2>
          <p class="build-options-subtitle">选择参数后一键生成完整的知识图谱</p>
        </div>

        <div class="build-options-body">
          <!-- 范式选择 -->
          <div class="option-section">
            <div class="option-label">
              <span class="option-icon">🧩</span>
              <span>分解范式</span>
              <span class="option-required">必选</span>
            </div>
            <p class="option-desc">选择适合你知识库内容类型的分解策略，不同范式会产生不同的概念提取结果</p>
            <div class="paradigm-cards">
              <div
                v-for="p in paradigmList"
                :key="p.id"
                class="paradigm-card"
                :class="{ active: buildOptions.paradigm === p.id }"
                @click="buildOptions.paradigm = p.id"
              >
                <div class="paradigm-radio">
                  <div class="radio-dot" :class="{ checked: buildOptions.paradigm === p.id }"></div>
                </div>
                <div class="paradigm-info">
                  <div class="paradigm-name">{{ p.name }}</div>
                  <div class="paradigm-desc">{{ p.description }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- 分解粒度 -->
          <div class="option-section">
            <div class="option-label">
              <span class="option-icon">🔬</span>
              <span>分解粒度</span>
              <span class="option-tag experimental">实验性</span>
            </div>
            <p class="option-desc">控制概念提取的精细程度（当前版本此参数仅做记录，不影响实际提取）</p>
            <div class="granularity-slider">
              <div class="slider-labels">
                <span :class="{ active: buildOptions.granularity === 'coarse' }">粗</span>
                <span :class="{ active: buildOptions.granularity === 'medium' }">中</span>
                <span :class="{ active: buildOptions.granularity === 'fine' }">细</span>
              </div>
              <input
                type="range"
                min="0"
                max="2"
                step="1"
                :value="['coarse','medium','fine'].indexOf(buildOptions.granularity)"
                @input="buildOptions.granularity = ['coarse','medium','fine'][$event.target.value]"
                class="slider-input"
              />
            </div>
          </div>

          <!-- 附加选项 -->
          <div class="option-section">
            <div class="option-label">
              <span class="option-icon">⚙️</span>
              <span>附加选项</span>
            </div>
            <div class="checkbox-group">
              <label class="checkbox-item">
                <input type="checkbox" v-model="buildOptions.withSemantic" />
                <span class="checkbox-text">构建语义层（自动提取概念并建立语义关系）</span>
              </label>
              <label class="checkbox-item">
                <input type="checkbox" v-model="buildOptions.withDedupe" />
                <span class="checkbox-text">执行概念去重（合并相似概念，生成规范概念表）</span>
              </label>
              <label class="checkbox-item">
                <input type="checkbox" v-model="buildOptions.forceRebuild" />
                <span class="checkbox-text">强制重建（删除已有图谱数据后重新生成）</span>
              </label>
            </div>
          </div>

          <!-- 评估参数占比（预留折叠面板） -->
          <div class="option-section collapsed">
            <div class="option-label" style="cursor: pointer;" @click="$event.currentTarget.parentElement.classList.toggle('collapsed')">
              <span class="option-icon">📊</span>
              <span>评估参数权重</span>
              <span class="option-tag experimental">预留</span>
              <span class="collapse-arrow">▶</span>
            </div>
            <div class="collapsed-content">
              <p class="option-desc">调整语义质量评估各维度的权重占比（当前为默认配置）</p>
              <div class="weight-bars">
                <div class="weight-item">
                  <span class="weight-name">稳定性</span>
                  <div class="weight-bar"><div class="weight-fill" style="width: 25%"></div></div>
                  <span class="weight-value">25%</span>
                </div>
                <div class="weight-item">
                  <span class="weight-name">覆盖度</span>
                  <div class="weight-bar"><div class="weight-fill" style="width: 25%"></div></div>
                  <span class="weight-value">25%</span>
                </div>
                <div class="weight-item">
                  <span class="weight-name">忠实度</span>
                  <div class="weight-bar"><div class="weight-fill" style="width: 25%"></div></div>
                  <span class="weight-value">25%</span>
                </div>
                <div class="weight-item">
                  <span class="weight-name">多样性</span>
                  <div class="weight-bar"><div class="weight-fill" style="width: 15%"></div></div>
                  <span class="weight-value">15%</span>
                </div>
                <div class="weight-item">
                  <span class="weight-name">连接覆盖</span>
                  <div class="weight-bar"><div class="weight-fill" style="width: 10%"></div></div>
                  <span class="weight-value">10%</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 进度提示 -->
        <div v-if="isRebuilding" class="build-progress">
          <span class="spinner-inline"></span>
          <span>{{ buildProgress || '正在生成图谱...' }}</span>
        </div>

        <!-- 操作按钮 -->
        <div class="build-options-footer">
          <button class="btn btn-lg" @click="closeBuildOptions" :disabled="isRebuilding">取消</button>
          <button class="btn btn-lg btn-primary" @click="confirmBuild" :disabled="isRebuilding">
            <span v-if="isRebuilding" class="spinner-inline"></span>
            <span v-else>🚀 开始生成</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, inject } from 'vue'
import cytoscape from 'cytoscape'
import cola from 'cytoscape-cola'
import dagre from 'cytoscape-dagre'

cytoscape.use(cola)
cytoscape.use(dagre)

// 全局学科状态
const subjectState = inject('subjectState')
const currentSubject = computed(() => subjectState.currentSubject.value)
const currentSubjectName = computed(() => {
  const sub = subjectState.subjects.value.find(s => s.id === currentSubject.value)
  return sub?.name || currentSubject.value
})

// DOM 引用
const cyContainer = ref(null)

// 状态
let cy = null
const nodes = ref([])
const edges = ref([])
const selectedNode = ref(null)
const searchQuery = ref('')
const isBuilding = ref(false)
const isLoading = ref(false)
const nodeCount = ref(0)
const edgeCount = ref(0)

// ========== 图谱构建选项面板状态 ==========
const showBuildOptions = ref(false)
const isRebuilding = ref(false)
const buildProgress = ref('')
const buildOptions = ref({
  paradigm: 'theory',
  granularity: 'medium',
  withSemantic: true,
  withDedupe: true,
  forceRebuild: false,
})
const paradigmList = ref([])

// 加载范式列表
async function loadParadigms() {
  try {
    const resp = await fetch(`${window.location.origin}/api/knowledge-graph/paradigms`)
    if (resp.ok) {
      const data = await resp.json()
      paradigmList.value = data.paradigms || []
    }
  } catch (e) {
    console.error('[GraphView] 加载范式列表失败:', e)
    // 回退到硬编码
    paradigmList.value = [
      { id: 'theory', name: '理论归纳', description: '适合理论学科（物理、数学等）：定义→规律→应用→扩展' },
      { id: 'engineering', name: '工程分解', description: '适合技术类知识：需求→技术→子需求→子技术' },
      { id: 'hierarchical', name: '层级归纳', description: '适合通用知识：事实→概念→方法→评价' },
    ]
  }
}

function openBuildOptions() {
  loadParadigms()
  showBuildOptions.value = true
}

function closeBuildOptions() {
  showBuildOptions.value = false
  buildProgress.value = ''
}

async function confirmBuild() {
  isRebuilding.value = true
  buildProgress.value = '正在构建结构层...'

  try {
    // 调用构建 API（结构层 + 语义层 + 去重）
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/build`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paradigm: buildOptions.value.paradigm,
          force_rebuild: buildOptions.value.forceRebuild,
          with_semantic: buildOptions.value.withSemantic,
        }),
      }
    )

    if (!resp.ok) {
      const err = await resp.text()
      throw new Error(err)
    }

    const data = await resp.json()

    // 更新进度
    if (data.semantic) {
      buildProgress.value = `语义层构建完成：处理了 ${data.semantic.chunks_processed} 个 chunk，提取 ${data.semantic.chunks_extracted} 个成功`
    }
    if (data.dedupe) {
      buildProgress.value += ` | 去重完成：${data.dedupe.canonical_concepts || 0} 个规范概念`
    }

    // 关闭选项面板，刷新图谱
    showBuildOptions.value = false
    cy.elements().remove()
    await loadAllNodes()

    alert(`图谱构建完成！\n结构层：${data.chunks_total || 0} 个 chunk\n语义层：${data.semantic?.chunks_extracted || 0} 个 chunk 提取成功\n去重：${data.dedupe?.canonical_concepts || 0} 个规范概念`)
  } catch (e) {
    console.error('构建图谱失败:', e)
    alert('构建失败: ' + e.message)
  } finally {
    isRebuilding.value = false
    buildProgress.value = ''
  }
}

// Phase 2: 概念分解状态
const selectedNodeConcepts = ref([])
const conceptsLoading = ref(false)
const isExtracting = ref(false)
const conceptNodeLinks = ref([])  // 概念节点的关联边信息

// Phase 2: 批量提取和去重状态
const isBatchExtracting = ref(false)
const isDeduping = ref(false)
const batchResult = ref(null)
const dedupeResult = ref(null)
const conceptTable = ref([])
const selectedParadigm = ref('theory')

// Phase 2: 概念表格搜索和分页
const conceptSearchQuery = ref('')
const filteredConcepts = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const selectedConcept = ref(null)
const showConceptModal = ref(false)

// 计算分页后的概念
const paginatedConcepts = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredConcepts.value.slice(start, end)
})
const totalPages = computed(() => {
  return Math.max(1, Math.ceil(filteredConcepts.value.length / pageSize.value))
})

watch(conceptTable, () => {
  filterConcepts()
  currentPage.value = 1
})
watch(conceptSearchQuery, () => {
  filterConcepts()
  currentPage.value = 1
})
watch(pageSize, () => {
  currentPage.value = 1
})

// 颜色配置
const COLORS = {
  child: '#3498db',
  concept: '#2ecc71',
  belongs_to: '#3498db',
  adjacent_to: '#95a5a6',
  selected: '#f39c12',
  highlight: '#e74c3c',
  solution: '#e67e22',
  depends_on: '#9b59b6',
}

/**
 * 从 chunk text 生成简洁的节点标题
 * 策略：
 * 1. 如果 text 以 # 开头（Markdown 标题），提取标题
 * 2. 否则取 text 的前 20 个中文字符或 30 个英文字符
 * 3. 清理特殊字符
 */
function generateNodeLabel(text, headingPath, fallback) {
  if (!text) return fallback || '未知节点'

  // 尝试提取 Markdown 标题
  const headerMatch = text.match(/^#+\s+(.+?)(?:\n|$)/m)
  if (headerMatch) {
    return headerMatch[1].trim().slice(0, 30)
  }

  // 尝试提取 heading_path 中的最后一级
  if (headingPath) {
    const parts = headingPath.split('>').map(p => p.trim()).filter(Boolean)
    if (parts.length > 0) {
      return parts[parts.length - 1].slice(0, 30)
    }
  }

  // 清理 text：去除 Markdown 标记、多余空格
  let clean = text
    .replace(/[#*`\[\]\(\)]/g, '')
    .replace(/\s+/g, ' ')
    .trim()

  // 取前30个字符（中英文混合）
  if (clean.length > 30) {
    clean = clean.slice(0, 30) + '...'
  }

  return clean || fallback || '未知节点'
}

// ========== Cytoscape 初始化 ==========

function initCy() {
  if (!cyContainer.value) return

  cy = cytoscape({
    container: cyContainer.value,
    elements: [],
    style: [
      // 节点样式（所有节点都是 child）
      {
        selector: 'node',
        style: {
          'label': 'data(label)',
          'text-valign': 'center',
          'text-halign': 'center',
          'font-size': '11px',
          'color': '#fff',
          'text-outline-color': '#2c3e50',
          'text-outline-width': 1,
          'width': 28,
          'height': 28,
          'border-width': 2,
          'border-color': '#2c3e50',
          'background-color': COLORS.child,
          'shape': 'ellipse',
        }
      },
      {
        selector: 'node[?isCenter]',
        style: {
          'border-width': 4,
          'border-color': COLORS.selected,
          'width': 38,
          'height': 38,
        }
      },
      {
        selector: 'node:selected',
        style: {
          'border-width': 4,
          'border-color': COLORS.selected,
        }
      },
      // 概念节点样式（UML 类图卡片风格）
      {
        selector: 'node[type="concept"], node[type="requirement"], node[type="sub_requirement"], node[type="technology"], node[type="sub_technology"]',
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
          'width': 160,               // 固定宽度，避免过宽
          'height': 'data(cardHeight)',  // 根据描述长度自适应高度
          'padding': '18px',          // 内边距
          'border-width': 2,
          'border-color': 'rgba(255,255,255,0.5)',
          'shape': 'round-rectangle',
          'corner-radius': 8,
        }
      },
      {
        selector: 'node[type="requirement"], node[type="sub_requirement"]',
        style: {
          'background-color': '#e74c3c',
          'border-color': '#c0392b',
        }
      },
      {
        selector: 'node[type="technology"], node[type="sub_technology"]',
        style: {
          'background-color': '#3498db',
          'border-color': '#2980b9',
        }
      },
      {
        selector: 'node[type="concept"]',
        style: {
          'background-color': '#2ecc71',
          'border-color': '#27ae60',
        }
      },
      {
        selector: 'edge[type="BELONGS_TO"]',
        style: {
          'line-color': COLORS.belongs_to,
          'target-arrow-color': COLORS.belongs_to,
          'line-style': 'solid',
        }
      },
      {
        selector: 'edge[type="ADJACENT_TO"]',
        style: {
          'line-color': COLORS.adjacent_to,
          'target-arrow-color': COLORS.adjacent_to,
          'line-style': 'dashed',
        }
      },
      // 语义层连接边样式（从左到右弧线）
      {
        selector: 'edge[type="SOLUTION"], edge[type="DEPENDS_ON"]',
        style: {
          'curve-style': 'straight',
          'control-point-distances': 50,
          'control-point-weights': 0.5,
          'target-arrow-shape': 'triangle',
          'arrow-scale': 0.8,
          'width': 1.5,
        }
      },
      {
        selector: 'edge[type="SOLUTION"]',
        style: {
          'line-color': COLORS.solution,
          'target-arrow-color': COLORS.solution,
          'line-style': 'solid',
          'width': 2,
        }
      },
      {
        selector: 'edge[type="DEPENDS_ON"]',
        style: {
          'line-color': COLORS.depends_on,
          'target-arrow-color': COLORS.depends_on,
          'line-style': 'dashed',
          'width': 1.5,
        }
      },
      // 副本节点样式（与原始节点相同但带虚线边框）
      {
        selector: 'node[isCopy = 1]',
        style: {
          'border-style': 'dashed',
          'border-width': 2,
          'border-color': '#f39c12',
          'opacity': 0.9,
        }
      },
      // 副本边样式（虚线）
      {
        selector: 'edge[isCopyEdge = 1]',
        style: {
          'line-style': 'dashed',
          'line-color': '#f39c12',
          'width': 1.5,
        }
      },
    ],
    layout: {
      name: 'null',  // 禁用初始布局，由 runLayout() 控制
    },
    minZoom: 0.1,
    maxZoom: 3,
  })

  // 挂载到 window 以便调试
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
      text: node.data('text') || '',
      description: node.data('description') || '',
      parent_hint: node.data('parent_hint') || '',
      source_chunks: node.data('source_chunks') || '',
    }
    // 仅 chunk 节点加载"概念分解"；概念节点加载关联信息
    if (isChunkNodeType(nodeType)) {
      loadConcepts(node.id())
    } else {
      selectedNodeConcepts.value = []
      loadConceptNodeLinks(node.id())
    }
    // 高亮邻居
    highlightNeighbors(node)
  })

  cy.on('tap', (e) => {
    if (e.target === cy) {
      selectedNode.value = null
      clearHighlight()
    }
  })

  cy.on('dbltap', 'node', async (e) => {
    const nodeId = e.target.id()
    await expandNode(nodeId)
  })
}

// ========== 数据加载 ==========

async function loadAllNodes() {
  isLoading.value = true
  try {
    if (!cy) {
      console.error('[GraphView] Cytoscape not initialized')
      return
    }

    // 清空已有元素
    cy.elements().remove()

    // 加载 chunk 节点和边（基础文档结构视图）
    await loadChunkNodes()
    await loadEdges()

    // 加载概念节点和语义边
    await loadConceptNodes()
    await loadSemanticEdges()

    // 运行布局：优先概念视图（若存在概念节点）
    if (cy.nodes().length > 0) {
      const conceptNodes = cy.nodes().filter(n => {
        const t = n.data('type')
        return t && !['child', 'parent', 'markdown'].includes(t)
      })
      console.log('[GraphView] 布局选择：总节点=', cy.nodes().length, '概念节点=', conceptNodes.length)
      if (conceptNodes.length > 0) {
        console.log('[GraphView] 切换到概念视图')
        runConceptLayout()
      } else {
        console.log('[GraphView] 切换到文档视图')
        runLayout()
      }
    }

    // 确保 cytoscape 在容器可见后正确渲染
    await nextTick()
    if (cy) {
      cy.resize()
      cy.fit()
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
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/nodes?limit=500`
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
        source: n.source,
        page_number: n.page_number,
        text: n.text || '',
        heading_path: n.heading_path || '',
      }
    }))

    if (chunkNodes.length > 0 && cy) {
      cy.add(chunkNodes)
      nodeCount.value = chunkNodes.length
    }
  } catch (e) {
    console.error('[GraphView] 加载 chunk 节点失败:', e)
  }
}

async function loadEdges() {
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/edges?limit=200`
    )
    if (!resp.ok) {
      console.warn('[GraphView] Edges API failed:', resp.status)
      return
    }
    const data = await resp.json()

    const allEdges = (data.edges || []).map(edge => ({
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
    edgeCount.value = allEdges.length
  } catch (e) {
    console.error('[GraphView] 加载边失败:', e)
  }
}

// UML 类图风格卡片标签构建
// 根据描述长度自适应计算节点高度，不截断描述
function buildUMLCardLabel(name, type, description) {
  const typeLabel = getTypeLabel(type)
  // 标题限制在 12 字符内
  const title = name.substring(0, 12)
  // 描述不截断，按每行 15 字换行
  const desc = description || ''
  const descLines = []
  for (let i = 0; i < desc.length; i += 15) {
    descLines.push(desc.substring(i, i + 15))
  }
  const descText = descLines.join('\n')
  // UML 格式：标题 + 分隔线 + 类型 + 分隔线 + 描述
  const cardLabel = `${title}\n━━━━━━\n${typeLabel}\n━━━━━━\n${descText}`

  // 计算高度：基础 80px + 每行 16px（12px字体+行距）
  const fixedLines = 5  // 标题 + 分隔 + 类型 + 分隔 + 至少1行描述（或空）
  const descLineCount = Math.max(descLines.length, 1)
  const totalLines = fixedLines + descLineCount - 1  // -1 because descLineCount already includes at least 1
  const lineHeight = 16
  const padding = 36  // 18px * 2
  const cardHeight = Math.max(80, totalLines * lineHeight + padding)

  return { cardLabel, cardHeight }
}

// 类型标签映射
function getTypeLabel(type) {
  const map = {
    'requirement': '【需求】',
    'sub_requirement': '【子需求】',
    'technology': '【技术】',
    'sub_technology': '【子技术】',
    'concept': '【概念】',
  }
  return map[type] || '【概念】'
}

// ========== Phase 2.5: 概念节点与语义连接加载 ==========

async function loadConceptNodes() {
  /**
   * 加载去重后的 Concept 节点到图谱中。
   */
  try {
    const url = `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/concepts?limit=2000`
    console.log('[GraphView] 加载概念节点:', url)
    const resp = await fetch(url)
    if (!resp.ok) {
      console.warn('[GraphView] 概念节点 API 失败:', resp.status, await resp.text())
      return
    }
    const data = await resp.json()
    console.log('[GraphView] 概念节点 API 返回:', data.count, '个概念')

    const conceptNodes = (data.concepts || []).map(c => {
      // 构建 UML 类图风格的卡片标签，同时计算合适的高度
      const { cardLabel, cardHeight } = buildUMLCardLabel(c.name || '', c.type || 'concept', c.description || '')

      return {
        data: {
          id: c.id,
          label: c.name,
          cardLabel: cardLabel,
          cardHeight: cardHeight,
          type: c.type || 'concept',
          description: c.description || '',
          parent_hint: c.parent_hint || '',
          source_chunks: c.source_chunks || '',
        }
      }
    })

    if (conceptNodes.length > 0 && cy) {
      cy.add(conceptNodes)
      nodeCount.value = cy.nodes().length
      console.log(`[GraphView] 加载 ${conceptNodes.length} 个概念节点，总节点数=${nodeCount.value}`)
    } else {
      console.warn('[GraphView] 概念节点为空，未添加到图谱')
    }
  } catch (e) {
    console.error('[GraphView] 加载概念节点失败:', e)
  }
}

async function loadSemanticEdges() {
  /**
   * 加载概念间的语义连接边（SOLUTION / DEPENDS_ON）。
   */
  try {
    const url = `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/concept-links?limit=2000`
    console.log('[GraphView] 加载语义边:', url)
    const resp = await fetch(url)
    if (!resp.ok) {
      console.warn('[GraphView] 语义连接 API 失败:', resp.status, await resp.text())
      return
    }
    const data = await resp.json()
    console.log('[GraphView] 语义边完整响应:', JSON.stringify(data, null, 2))
    console.log('[GraphView] 语义边 API 返回:', data.count, '条边, edges数组长度=', (data.edges || []).length)

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
      edgeCount.value = cy.edges().length
      console.log(`[GraphView] 加载 ${semEdges.length} 条语义连接边，总边数=${edgeCount.value}`)

      // 检查悬挂边（source/target 节点不存在的边）
      const danglingSources = new Set()
      const danglingTargets = new Set()
      semEdges.forEach(e => {
        if (!cy.getElementById(e.data.source).length) danglingSources.add(e.data.source)
        if (!cy.getElementById(e.data.target).length) danglingTargets.add(e.data.target)
      })
      if (danglingSources.size > 0 || danglingTargets.size > 0) {
        console.warn(`[GraphView] 悬挂边检测: ${danglingSources.size} 个缺失 source, ${danglingTargets.size} 个缺失 target`)
        console.warn('缺失 source 样本:', [...danglingSources].slice(0, 5))
        console.warn('缺失 target 样本:', [...danglingTargets].slice(0, 5))
      } else {
        console.log('[GraphView] 所有语义边均已正确连接节点')
      }
    } else {
      console.warn('[GraphView] 语义边为空, semEdges.length=', semEdges.length, 'cy存在=', !!cy)
    }
  } catch (e) {
    console.error('[GraphView] 加载语义连接失败:', e)
  }
}

async function expandNode(nodeId) {
  // 展开节点：加载该节点的子图并合并
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/subgraph/${nodeId}?depth=1`
    )
    if (!resp.ok) return
    const data = await resp.json()

    // 添加新节点
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
    if (newNodes.length > 0) {
      cy.add(newNodes)
      nodeCount.value = cy.nodes().length
    }

    // 添加新边
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
    if (newEdges.length > 0) {
      cy.add(newEdges)
      edgeCount.value = cy.edges().length
    }

    // 以该节点为中心重新布局
    cy.getElementById(nodeId).data('isCenter', true)
    runLayout()
  } catch (e) {
    console.error('展开节点失败:', e)
  }
}

// ========== 交互功能 ==========

function highlightNeighbors(node) {
  clearHighlight()

  // 收集需要高亮的节点集合（含副本）
  const highlightIds = new Set([node.id()])

  // 如果点击的是副本，找到原始节点和其他副本
  const originalId = node.data('originalId')
  if (originalId) {
    highlightIds.add(originalId)
    const mapping = cy.scratch('originalToCopies') || {}
    const copies = mapping[originalId] || []
    copies.forEach(id => highlightIds.add(id))
  }

  // 如果点击的是原始节点，找到所有副本
  const mapping = cy.scratch('originalToCopies') || {}
  for (const [oid, copies] of Object.entries(mapping)) {
    if (oid === node.id() || copies.includes(node.id())) {
      copies.forEach(id => highlightIds.add(id))
      highlightIds.add(oid)
    }
  }

  // 收集邻居节点
  const neighbors = node.neighborhood()
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
  cy.nodes().forEach(n => n.animate({ opacity: 1 }, { duration: 200 }))
  cy.edges().forEach(e => e.animate({ opacity: 1 }, { duration: 200 }))
}

function runLayout() {
  /**
   * 自定义树形布局算法
   * 原则：
   * 1. 单向的树，根节点在最左侧
   * 2. 同层节点在横向位置上并列
   * 3. 叶节点在最右侧，上下相邻叶节点间隔相同
   * 4. 有子节点的节点，纵向位置位于其所有下层节点的中部
   * 5. 不同树共享子节点时，复制子节点到各自的树中
   */

  const chunkNodes = cy.nodes().filter(n => {
    const t = n.data('type')
    return t === 'child' || t === 'markdown'
  })
  const chunkEdges = cy.edges().filter(e => {
    const t = e.data('type')
    return t === 'BELONGS_TO' || t === 'ADJACENT_TO'
  })

  if (chunkNodes.length === 0) return

  // 1. 构建子节点映射和父节点映射
  const childrenMap = {}
  const parentMap = {}
  chunkEdges.forEach(e => {
    const s = e.source().id()
    const t = e.target().id()
    childrenMap[s] = childrenMap[s] || []
    childrenMap[s].push(t)
    parentMap[t] = parentMap[t] || []
    parentMap[t].push(s)
  })

  // 2. 找到所有根节点（入度为0）
  const rootIds = []
  chunkNodes.forEach(n => {
    const nid = n.id()
    if (!parentMap[nid] || parentMap[nid].length === 0) {
      rootIds.push(nid)
    }
  })

  // 3. 复制共享子节点（入度 > 1 的节点）
  // 清除之前的副本
  cy.nodes('[isCopy = 1]').remove()
  cy.edges('[isCopyEdge = 1]').remove()

  const copyNodes = []
  const copyEdges = []
  const originalToCopies = {} // originalId -> [treeId -> copyId]

  // 对每个根节点，DFS 遍历其子树，遇到共享子节点时创建副本
  rootIds.forEach((rootId, treeIdx) => {
    const visitedInTree = new Set() // 在这个树中已经访问过的原始节点
    const stack = [{ originalId: rootId, parentTreeNodeId: null }]

    while (stack.length > 0) {
      const { originalId, parentTreeNodeId } = stack.pop()

      // 确定这个树中的节点ID
      let treeNodeId
      if (visitedInTree.has(originalId)) {
        // 共享子节点，创建副本
        if (!originalToCopies[originalId]) {
          originalToCopies[originalId] = {}
        }
        if (!originalToCopies[originalId][treeIdx]) {
          const copyId = `${originalId}_tree${treeIdx}`
          originalToCopies[originalId][treeIdx] = copyId

          // 创建副本节点
          const origNode = cy.getElementById(originalId)
          copyNodes.push({
            data: {
              id: copyId,
              label: origNode.data('label'),
              type: origNode.data('type'),
              source: origNode.data('source'),
              page_number: origNode.data('page_number'),
              text: origNode.data('text'),
              heading_path: origNode.data('heading_path'),
              originalId: originalId,
              isCopy: 1,
            }
          })
        }
        treeNodeId = originalToCopies[originalId][treeIdx]
      } else {
        treeNodeId = originalId
        visitedInTree.add(originalId)
      }

      // 添加边
      if (parentTreeNodeId) {
        copyEdges.push({
          data: {
            id: `${parentTreeNodeId}_to_${treeNodeId}`,
            source: parentTreeNodeId,
            target: treeNodeId,
            type: 'BELONGS_TO',
            isCopyEdge: visitedInTree.has(originalId) && originalId !== treeNodeId ? 1 : 0,
          }
        })
      }

      // 添加子节点到栈
      const childIds = childrenMap[originalId] || []
      // 反向遍历，保持原始顺序
      for (let i = childIds.length - 1; i >= 0; i--) {
        stack.push({ originalId: childIds[i], parentTreeNodeId: treeNodeId })
      }
    }
  })

  // 添加副本到图中
  if (copyNodes.length > 0) cy.add(copyNodes)
  if (copyEdges.length > 0) cy.add(copyEdges)

  // 4. 计算布局位置
  // 构建树内父子关系（使用原始边 + 副本边）
  const treeChildren = {}
  chunkEdges.forEach(e => {
    const s = e.source().id()
    const t = e.target().id()
    treeChildren[s] = treeChildren[s] || []
    treeChildren[s].push(t)
  })
  copyEdges.forEach(e => {
    const s = e.data.source
    const t = e.data.target
    treeChildren[s] = treeChildren[s] || []
    treeChildren[s].push(t)
  })

  const layerWidth = 250
  const nodeGap = 60
  const treeGap = 120

  // 计算每个节点的子树高度（叶节点数）- 使用 memoization
  const subtreeHeight = {}
  function calcHeight(nodeId) {
    if (subtreeHeight[nodeId] !== undefined) return subtreeHeight[nodeId]
    const children = treeChildren[nodeId] || []
    if (children.length === 0) {
      subtreeHeight[nodeId] = 1
      return 1
    }
    const count = children.reduce((sum, cid) => sum + calcHeight(cid), 0)
    subtreeHeight[nodeId] = count
    return count
  }

  // 分配位置（后序遍历）
  const positions = {}
  function assignPos(nodeId, depth, startY) {
    const x = depth * layerWidth
    const children = treeChildren[nodeId] || []

    if (children.length === 0) {
      // 叶节点
      positions[nodeId] = { x, y: startY }
      return startY + nodeGap
    }

    // 有子节点：先给所有子节点分配位置
    let currentY = startY
    const childCenters = []

    children.forEach(childId => {
      const childEndY = assignPos(childId, depth + 1, currentY)
      // 子节点的中心 y 位置
      childCenters.push((currentY + childEndY - nodeGap) / 2)
      currentY = childEndY
    })

    // 父节点的 y = 所有子节点 y 范围的中点
    const firstY = childCenters[0]
    const lastY = childCenters[childCenters.length - 1]
    positions[nodeId] = { x, y: (firstY + lastY) / 2 }

    return currentY
  }

  // 为每棵树分配位置
  let currentY = 0
  rootIds.forEach((rootId, treeIdx) => {
    // 找到这个根节点在树中的ID（可能是原始ID或副本ID）
    let treeRootId = rootId
    if (originalToCopies[rootId] && originalToCopies[rootId][treeIdx]) {
      treeRootId = originalToCopies[rootId][treeIdx]
    }

    const treeHeight = calcHeight(treeRootId) * nodeGap
    assignPos(treeRootId, 0, currentY)
    currentY += treeHeight + treeGap
  })

  // 5. 应用位置
  Object.entries(positions).forEach(([nodeId, pos]) => {
    const node = cy.getElementById(nodeId)
    if (node.length > 0) {
      node.position(pos)
    }
  })

  // 6. 适应视图
  const allNodes = cy.nodes().filter(n => {
    const t = n.data('type')
    return t === 'child' || t === 'markdown' || n.data('isCopy') === 1
  })

  if (allNodes.length > 0) {
    const bbox = allNodes.boundingBox()
    const container = cy.container()
    const containerW = container.clientWidth
    const containerH = container.clientHeight

    // 计算 zoom：让宽度占满容器的 90%
    const zoomByWidth = (containerW * 0.9) / bbox.w
    const zoomByHeight = (containerH * 0.8) / bbox.h
    const zoom = Math.min(zoomByWidth, zoomByHeight, 1.0)

    cy.zoom(Math.max(zoom, 0.1))
    cy.pan({ x: 30, y: 30 })
  }
}

function runConceptLayout() {
  // 概念节点布局（单独调用，叠加在 chunk 节点上）
  // === 步骤0: 清除之前可能创建的副本 ===
  cy.nodes().filter(n => n.data('isCopy') === '1').remove()
  cy.edges().filter(e => e.data('isCopyEdge') === '1').remove()

  const allConceptNodes = cy.nodes().filter(n => {
    const t = n.data('type')
    return t && t !== 'child' && t !== 'parent' && t !== 'markdown'
  })

  const semanticEdges = cy.edges().filter(e => {
    const t = e.data('type')
    return t === 'SOLUTION' || t === 'DEPENDS_ON'
  })

  // 收集边列表
  const edgeList = []
  semanticEdges.forEach(e => {
    edgeList.push({
      source: e.source().id(),
      target: e.target().id(),
      type: e.data('type'),
      edgeRef: e
    })
  })

  // 计算节点连通性
  const connectedNodeIds = new Set()
  edgeList.forEach(e => {
    connectedNodeIds.add(e.source)
    connectedNodeIds.add(e.target)
  })

  const treeNodes = allConceptNodes.filter(n => connectedNodeIds.has(n.id()))
  const orphanNodes = allConceptNodes.filter(n => !connectedNodeIds.has(n.id()))

  // 隐藏 chunk 节点和 chunk 边
  cy.nodes().forEach(n => {
    const t = n.data('type')
    if (t === 'child' || t === 'parent' || t === 'markdown') {
      n.style('display', 'none')
    }
  })
  cy.edges().forEach(e => {
    const t = e.data('type')
    if (t !== 'SOLUTION' && t !== 'DEPENDS_ON') {
      e.style('display', 'none')
    }
  })

  // ===== 步骤1: 分树（Forest Detection）=====
  // 找到根节点（入度为0）
  const nodeInDegree = {}
  edgeList.forEach(e => {
    nodeInDegree[e.target] = (nodeInDegree[e.target] || 0) + 1
  })

  const rootIds = new Set()
  treeNodes.forEach(n => {
    const nid = n.id()
    if (!nodeInDegree[nid] || nodeInDegree[nid] === 0) {
      rootIds.add(nid)
    }
  })

  // BFS 分树（双向遍历，找到每个连通分量）
  const trees = [] // 每棵树是 Set(nodeId)
  const assigned = new Set()

  rootIds.forEach(rootId => {
    const treeNodeIds = new Set()
    const queue = [rootId]

    while (queue.length > 0) {
      const nid = queue.shift()
      if (treeNodeIds.has(nid)) continue
      treeNodeIds.add(nid)

      edgeList.forEach(e => {
        if (e.source === nid && !treeNodeIds.has(e.target)) {
          queue.push(e.target)
        }
        if (e.target === nid && !treeNodeIds.has(e.source)) {
          queue.push(e.source)
        }
      })
    }

    trees.push(treeNodeIds)
    treeNodeIds.forEach(id => assigned.add(id))
  })

  // 处理未分配的节点（环中的节点等）
  const unassignedIds = new Set()
  treeNodes.forEach(n => {
    if (!assigned.has(n.id())) {
      unassignedIds.add(n.id())
    }
  })
  if (unassignedIds.size > 0) {
    trees.push(unassignedIds)
  }

  console.log(`[runConceptLayout] 分树结果：共 ${trees.length} 棵树`)

  // ===== 步骤2: 对每棵树独立处理（副本 + dagre 布局）=====
  const treeBboxes = []
  const treeGap = 200

  for (let i = 0; i < trees.length; i++) {
    const treeNodeIds = trees[i]
    if (treeNodeIds.size === 0) continue

    // 收集这棵树的 cytoscape 节点
    const treeCyNodes = []
    treeNodeIds.forEach(id => {
      const el = cy.getElementById(id)
      if (el.length > 0) treeCyNodes.push(el)
    })

    // 收集这棵树内部的边（两端都在树内）
    const treeEdgeList = []
    edgeList.forEach(e => {
      if (treeNodeIds.has(e.source) && treeNodeIds.has(e.target)) {
        treeEdgeList.push(e)
      }
    })

    // 对这棵树内部处理多父节点（创建副本）
    const treeCopyNodes = []
    const treeCopyEdges = []

    // 统计树内每个节点的入度
    const treeInDegree = {}
    treeEdgeList.forEach(e => {
      treeInDegree[e.target] = (treeInDegree[e.target] || 0) + 1
    })

    // 为入度 > 1 的节点创建副本
    treeNodeIds.forEach(nid => {
      const edges = treeEdgeList.filter(e => e.target === nid)
      if (edges.length <= 1) return

      // 保留第一条边连接原始节点，其他边连接副本
      for (let j = 1; j < edges.length; j++) {
        const copyId = `${nid}_copy${j}_tree${i}`
        const originalNode = cy.getElementById(nid)

        treeCopyNodes.push({
          data: {
            id: copyId,
            label: originalNode.data('label'),
            cardLabel: originalNode.data('cardLabel'),
            cardHeight: originalNode.data('cardHeight'),
            type: originalNode.data('type'),
            description: originalNode.data('description'),
            parent_hint: originalNode.data('parent_hint'),
            source_chunks: originalNode.data('source_chunks'),
            originalId: nid,
            isCopy: '1',
          }
        })

        // 隐藏原始边，创建指向副本的新边
        edges[j].edgeRef.style('display', 'none')
        treeCopyEdges.push({
          data: {
            id: `${edges[j].source}_${edges[j].type}_${copyId}`,
            source: edges[j].source,
            target: copyId,
            type: edges[j].type,
            label: edges[j].type === 'SOLUTION' ? '解决' : '依赖',
            isCopyEdge: '1',
          }
        })
      }
    })

    // 添加副本节点和边到 cytoscape
    if (treeCopyNodes.length > 0) {
      cy.add(treeCopyNodes)
      console.log(`[runConceptLayout] 树${i}: 创建 ${treeCopyNodes.length} 个副本`)
    }
    if (treeCopyEdges.length > 0) {
      cy.add(treeCopyEdges)
    }

    // 构建这棵树的 cytoscape collection（包含原始节点、副本节点、原始边、副本边）
    let treeCollection = cy.collection()

    // 添加所有节点（原始 + 副本）
    treeCyNodes.forEach(n => { treeCollection = treeCollection.union(n) })
    treeCopyNodes.forEach(n => {
      const el = cy.getElementById(n.data.id)
      if (el.length > 0) treeCollection = treeCollection.union(el)
    })

    // 添加所有边（原始边 + 副本边）
    treeEdgeList.forEach(e => {
      if (e.edgeRef.style('display') !== 'none') {
        treeCollection = treeCollection.union(e.edgeRef)
      }
    })
    treeCopyEdges.forEach(e => {
      const el = cy.getElementById(e.data.id)
      if (el.length > 0) treeCollection = treeCollection.union(el)
    })

    // 独立 dagre 布局
    treeCollection.layout({
      name: 'dagre',
      rankDir: 'LR',
      rankSep: 250,
      nodeSep: 80,
      edgeSep: 20,
      padding: 20,
      fit: false,
      animate: false,
    }).run()

    // 计算这棵树布局后的 bbox
    treeBboxes.push(treeCollection.boundingBox())
  }

  // ===== 步骤3: 按从上到下排列各棵树 =====
  let currentY = 0
  for (let i = 0; i < trees.length; i++) {
    const bbox = treeBboxes[i]
    const treeNodeIds = trees[i]
    if (treeNodeIds.size === 0) continue

    const dy = currentY - bbox.y1

    // 平移这棵树的所有节点（原始 + 副本）
    treeNodeIds.forEach(id => {
      const node = cy.getElementById(id)
      if (node.length > 0) {
        node.position('y', node.position('y') + dy)
      }
      // 平移副本节点
      const copies = cy.nodes(`[originalId = "${id}"]`)
      copies.forEach(copy => {
        copy.position('y', copy.position('y') + dy)
      })
    })

    currentY = currentY + (bbox.y2 - bbox.y1) + treeGap
  }

  // 显示所有树节点（包括原始节点和副本节点）
  for (let i = 0; i < trees.length; i++) {
    trees[i].forEach(id => {
      const node = cy.getElementById(id)
      if (node.length > 0) {
        node.style('display', 'element')
        node.style('opacity', 1)
      }
      // 显示对应的副本节点
      cy.nodes(`[originalId = "${id}"]`).forEach(copy => {
        copy.style('display', 'element')
        copy.style('opacity', 1)
      })
    })
  }

  // 固定 zoom
  const allConnected = treeNodes.union(cy.nodes('[isCopy = 1]'))
  const totalBbox = allConnected.boundingBox()
  console.log(`[runConceptLayout] 森林布局后 bbox: w=${totalBbox.w.toFixed(0)}, h=${totalBbox.h.toFixed(0)}`)
  const container = cy.container()
  const containerW = container.clientWidth
  const containerH = container.clientHeight
  const zoom = Math.min(containerW / totalBbox.w, containerH / totalBbox.h, 0.5)
  cy.zoom(Math.max(Math.min(zoom, 0.5), 0.15))
  cy.center(allConnected)

  // 孤立节点布局
  if (orphanNodes.length > 0) {
    let maxX = 0
    allConnected.forEach(n => {
      maxX = Math.max(maxX, n.position('x') + 100)
    })

    let orphanIdx = 0
    const orphanCols = 4
    const orphanGapX = 160
    const orphanGapY = 60
    const orphanStartX = maxX + 100
    const orphanStartY = 50

    orphanNodes.forEach(n => {
      const col = orphanIdx % orphanCols
      const row = Math.floor(orphanIdx / orphanCols)
      n.position({
        x: orphanStartX + col * orphanGapX,
        y: orphanStartY + row * orphanGapY
      })
      n.style('display', 'element')
      n.style('opacity', 0.5)
      orphanIdx++
    })
  }
}
function computeTreeLayout(nodes, childrenMap, inDegree) {
  const layerWidth = 380
  const minNodeGap = 20
  const treeGap = 60

  const positions = {}
  const nodeIds = new Set(nodes.map(n => n.id()))

  // ========== 步骤1：计算每个节点到叶子的最大深度 ==========
  const depthToLeaf = {}
  const depthMemo = {}
  function calcDepthToLeaf(nodeId) {
    if (depthMemo[nodeId] !== undefined) return depthMemo[nodeId]
    const childIds = (childrenMap[nodeId] || []).filter(cid => nodeIds.has(cid))
    if (childIds.length === 0) {
      depthMemo[nodeId] = 0
      return 0
    }
    let max = 0
    for (const cid of childIds) {
      max = Math.max(max, calcDepthToLeaf(cid) + 1)
    }
    depthMemo[nodeId] = max
    return max
  }
  for (const nid of nodeIds) {
    depthToLeaf[nid] = calcDepthToLeaf(nid)
  }

  // ========== 步骤2：构建完整的父节点映射（支持多父节点）==========
  const parentMap = {} // nodeId -> [parentIds]
  nodes.forEach(n => {
    const nid = n.id()
    const childIds = childrenMap[nid] || []
    for (const cid of childIds) {
      if (!parentMap[cid]) parentMap[cid] = []
      parentMap[cid].push(nid)
    }
  })

  // ========== 步骤3：找到根节点（入度为0）==========
  const rootIds = []
  nodes.forEach(n => {
    const nid = n.id()
    const nodeInDegree = inDegree[nid] || 0
    const hasOutEdge = childrenMap[nid] && childrenMap[nid].length > 0
    if (nodeInDegree === 0 && hasOutEdge) {
      rootIds.push(nid)
    }
  })

  // ========== 步骤4：根节点聚类（按共享子节点贪心排序）==========
  // 计算每个共享子节点对应的根集合
  const sharedChildRoots = {} // childId -> Set(rootIds)
  for (const nid of nodeIds) {
    const pids = parentMap[nid] || []
    if (pids.length > 1) {
      const roots = new Set()
      for (const pid of pids) {
        // 向上追溯到根
        let current = pid
        const seen = new Set()
        while (true) {
          if (seen.has(current)) break
          seen.add(current)
          const ppids = parentMap[current] || []
          if (ppids.length === 0) break
          current = ppids[0]
        }
        if (rootIds.includes(current)) {
          roots.add(current)
        }
      }
      if (roots.size > 1) {
        sharedChildRoots[nid] = roots
      }
    }
  }

  // 计算根节点之间的亲和力
  const affinity = {}
  for (const roots of Object.values(sharedChildRoots)) {
    const rootList = Array.from(roots)
    for (let i = 0; i < rootList.length; i++) {
      for (let j = i + 1; j < rootList.length; j++) {
        const r1 = rootList[i]
        const r2 = rootList[j]
        if (!affinity[r1]) affinity[r1] = {}
        if (!affinity[r2]) affinity[r2] = {}
        affinity[r1][r2] = (affinity[r1][r2] || 0) + 1
        affinity[r2][r1] = (affinity[r2][r1] || 0) + 1
      }
    }
  }

  // 贪心排序根节点
  function greedySortRoots(rootIds, affinity) {
    if (rootIds.length <= 1) return rootIds

    const remaining = new Set(rootIds)
    const sorted = []

    // 找到亲和力最高的根节点对作为起点
    let maxAffinity = -1
    let startRoot = rootIds[0]
    for (let i = 0; i < rootIds.length; i++) {
      for (let j = i + 1; j < rootIds.length; j++) {
        const aff = (affinity[rootIds[i]] && affinity[rootIds[i]][rootIds[j]]) || 0
        if (aff > maxAffinity) {
          maxAffinity = aff
          startRoot = rootIds[i]
        }
      }
    }

    sorted.push(startRoot)
    remaining.delete(startRoot)

    while (remaining.size > 0) {
      let bestRoot = null
      let bestAffinity = -1

      for (const candidate of remaining) {
        let totalAff = 0
        for (const sortedRoot of sorted) {
          totalAff += (affinity[candidate] && affinity[candidate][sortedRoot]) || 0
        }
        if (totalAff > bestAffinity) {
          bestAffinity = totalAff
          bestRoot = candidate
        }
      }

      if (bestRoot) {
        sorted.push(bestRoot)
        remaining.delete(bestRoot)
      } else {
        const next = remaining.values().next().value
        sorted.push(next)
        remaining.delete(next)
      }
    }

    return sorted
  }

  const sortedRootIds = greedySortRoots(rootIds, affinity)

  // ========== 步骤5：自底向上计算 y 位置 ==========
  // 叶子节点先分配，父节点取子节点的加权平均（共享子节点权重更高）
  const yPositions = {}
  const assigned = new Set()

  // 按 depthToLeaf 从大到小排序（叶子优先）
  const sortedByDepth = Array.from(nodeIds).sort((a, b) => depthToLeaf[b] - depthToLeaf[a])

  let currentY = 0
  for (const nid of sortedByDepth) {
    const childIds = (childrenMap[nid] || []).filter(cid => nodeIds.has(cid))

    if (childIds.length === 0) {
      // 叶子节点
      yPositions[nid] = currentY
      currentY += 55 + minNodeGap  // 更紧凑的间距
      assigned.add(nid)
    } else {
      // 父节点：取已分配子节点的加权平均
      // 共享子节点（多父节点）权重更高，使父节点向共享子节点靠拢
      const assignedChildren = childIds.filter(cid => assigned.has(cid))

      if (assignedChildren.length > 0) {
        let totalY = 0
        let totalWeight = 0

        for (const cid of assignedChildren) {
          const isShared = (parentMap[cid] || []).length > 1
          const weight = isShared ? 3 : 1  // 共享子节点权重 3x
          totalY += yPositions[cid] * weight
          totalWeight += weight
        }

        yPositions[nid] = totalY / totalWeight
      } else {
        // 子节点未分配（shouldn't happen）
        yPositions[nid] = currentY
        currentY += 70 + minNodeGap
      }
      assigned.add(nid)
    }
  }

  // ========== 步骤6：分配 x 位置（根节点在左边）==========
  const maxDepth = Math.max(...Object.values(depthToLeaf))
  for (const nid of nodeIds) {
    const x = (maxDepth - depthToLeaf[nid]) * layerWidth
    positions[nid] = { x, y: yPositions[nid] }
  }

  return { positions, maxDepth, layerWidth }
}

function isChunkNodeType(nodeType) {
  if (!nodeType) return true  // 无类型默认为 chunk
  return ['child', 'parent'].includes(nodeType)
}

function isConceptNodeType(nodeType) {
  if (!nodeType) return false
  return ['concept', 'requirement', 'sub_requirement', 'technology', 'sub_technology'].includes(nodeType)
}

function isConceptNode(node) {
  if (!node) return false
  const t = node.type || node.chunk_type || ''
  return isConceptNodeType(t)
}

async function loadConceptNodeLinks(nodeId) {
  /**
   * 加载概念节点的关联信息（入边/出边邻居）。
   */
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

function getNodeLinks(nodeId) {
  if (!window.cy) return []
  const links = []

  try {
    const node = cy.getElementById(nodeId)
    if (!node || node.length === 0) return links

    // 出边（当前节点是源节点）
    node.outgoers('edge').forEach(e => {
      if (e.isEdge()) {
        const target = e.target()
        links.push({
          id: e.id(),
          direction: 'out',
          type: e.data('type') || 'LINK',
          targetId: target.id(),
          targetName: target.data('label') || target.id(),
        })
      }
    })

    // 入边（当前节点是目标节点）
    node.incomers('edge').forEach(e => {
      if (e.isEdge()) {
        const source = e.source()
        links.push({
          id: e.id(),
          direction: 'in',
          type: e.data('type') || 'LINK',
          targetId: source.id(),
          targetName: source.data('label') || source.id(),
        })
      }
    })
  } catch (e) {
    console.error('[GraphView] getNodeLinks error:', e)
  }

  return links
}

function fitGraph() {
  // 只适应有连接的概念节点
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
  // 判断当前可见的视图类型，决定使用哪种布局
  const visibleConcepts = cy.nodes().filter(n => {
    const t = n.data('type')
    return t && !['child', 'parent', 'markdown'].includes(t) && n.style('display') !== 'none'
  })
  if (visibleConcepts.length > 0) {
    runConceptLayout()
  } else {
    runLayout()
  }
}

function showChunkView() {
  /**
   * 切换到文档视图：显示 chunk 节点，隐藏概念节点。
   */
  // 清除概念副本
  cy.nodes('[isCopy = 1]').remove()
  cy.edges('[isCopyEdge = 1]').remove()

  // 显示 chunk 节点和边，隐藏概念节点和语义边
  cy.nodes().forEach(n => {
    const t = n.data('type')
    if (t === 'child' || t === 'parent' || t === 'markdown') {
      n.style('display', 'element')
      n.style('opacity', 1)
    } else {
      n.style('display', 'none')
    }
  })
  cy.edges().forEach(e => {
    const t = e.data('type')
    if (t === 'BELONGS_TO' || t === 'ADJACENT_TO') {
      e.style('display', 'element')
    } else {
      e.style('display', 'none')
    }
  })

  runLayout()
}

function showConceptView() {
  /**
   * 切换到概念视图：运行概念节点 dagre 布局。
   */
  runConceptLayout()
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
  if (!searchQuery.value) return
  const query = searchQuery.value.toLowerCase()

  // 搜索匹配节点
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
      text: first.data('text') || '',
      description: first.data('description') || '',
    }
    focusNode()
    highlightNeighbors(first)
  }
}

// ========== Phase 2: 概念分解功能 ==========

/**
 * 标签显示映射
 */
function typeLabel(type) {
  const map = {
    'definition': '定义',
    'law': '规律',
    'application': '应用',
    'extension': '扩展',
  }
  return map[type] || type
}

function relationLabel(relation) {
  const map = {
    'DEFINES': '定义了',
    'HAS_LAW': '阐述了',
    'APPLIES_TO': '应用于',
    'EXTENDS': '扩展了',
  }
  return map[relation] || relation
}

/**
 * 加载指定 chunk 的已提取概念
 */
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

/**
 * 对当前选中的 chunk 执行语义提取
 */
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
      const err = await resp.text()
      alert(`提取失败: ${err}`)
    }
  } catch (e) {
    console.error('[GraphView] 提取概念失败:', e)
    alert('提取失败，请检查网络连接')
  } finally {
    isExtracting.value = false
  }
}

// ==========================================

// ========== Phase 2: 批量提取和去重 ==========

async function batchExtract() {
  isBatchExtracting.value = true
  batchResult.value = null
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/build/semantic`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paradigm: selectedParadigm.value }),
      }
    )
    if (resp.ok) {
      const data = await resp.json()
      batchResult.value = data
      alert(`批量提取完成！处理了 ${data.chunks_processed} 个 chunk，成功 ${data.chunks_extracted} 个，失败 ${data.chunks_failed} 个，平均质量 ${data.avg_quality_score}`)
    } else {
      const err = await resp.text()
      alert(`批量提取失败: ${err}`)
    }
  } catch (e) {
    console.error('[GraphView] 批量提取失败:', e)
    alert('批量提取失败，请检查后端连接')
  } finally {
    isBatchExtracting.value = false
  }
}

async function dedupeConcepts() {
  isDeduping.value = true
  dedupeResult.value = null
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/dedupe`,
      { method: 'POST' }
    )
    if (resp.ok) {
      const data = await resp.json()
      dedupeResult.value = data
      conceptTable.value = data.concepts || []
      alert(`去重完成！${data.canonical_concepts || 0} 个去重后概念`)
    } else {
      const err = await resp.text()
      alert(`去重失败: ${err}`)
    }
  } catch (e) {
    console.error('[GraphView] 去重失败:', e)
    alert('去重失败，请检查后端连接')
  } finally {
    isDeduping.value = false
  }
}

/**
 * 过滤概念列表（搜索功能）
 */
function filterConcepts() {
  const query = conceptSearchQuery.value.trim().toLowerCase()
  if (!query) {
    filteredConcepts.value = [...conceptTable.value]
    return
  }
  filteredConcepts.value = conceptTable.value.filter(c => {
    const name = (c.name || '').toLowerCase()
    const aliases = (c.aliases || []).join(' ').toLowerCase()
    const type = (c.concept_type || '').toLowerCase()
    return name.includes(query) || aliases.includes(query) || type.includes(query)
  })
}

/**
 * 显示概念详情弹窗
 */
function showConceptDetail(concept) {
  selectedConcept.value = concept
  showConceptModal.value = true
}

// ==========================================

async function buildGraph() {
  isBuilding.value = true
  try {
    const resp = await fetch(
      `${window.location.origin}/api/knowledge-graph/${currentSubject.value}/build`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paradigm: 'theory' }),
      }
    )
    if (resp.ok) {
      const data = await resp.json()
      alert(data.message || '图谱构建完成')
      // 重新加载
      cy.elements().remove()
      await loadAllNodes()
    }
  } catch (e) {
    console.error('构建图谱失败:', e)
  } finally {
    isBuilding.value = false
  }
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

.legend-shape.circle {
  border-radius: 50%;
}

.legend-shape.rect {
  border-radius: 2px;
}

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

/* 信息面板 */
.info-panel {
  width: 300px;
  border-left: 1px solid var(--border-color, #e0e0e0);
  background: var(--bg-card, #fff);
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
}

.info-panel:not(.open) {
  width: 200px;
}

.info-content {
  padding: 16px;
  overflow-y: auto;
  height: 100%;
}

.info-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.info-header h3 {
  margin: 0;
  font-size: var(--font-size-md);
  color: var(--text-primary, #2c3e50);
}

.info-section {
  margin-bottom: 14px;
}

.info-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.info-value {
  font-size: var(--font-size-sm);
  color: var(--text-primary, #2c3e50);
  word-break: break-all;
}

.info-value.mono {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
}

.info-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary, #555);
  max-height: 200px;
  overflow-y: auto;
  padding: 8px;
  background: var(--bg-hover, #f8f9fa);
  border-radius: 4px;
}

.type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--font-size-xs);
  font-weight: 600;
}

.type-badge.parent {
  background: #fdeaea;
  color: #e74c3c;
}

.type-badge.child {
  background: #e8f4fd;
  color: #3498db;
}

.info-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color, #e0e0e0);
}

.info-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 24px;
  text-align: center;
  color: var(--text-muted, #7f8c8d);
}

.empty-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.empty-text {
  font-size: var(--font-size-md);
  font-weight: 600;
  margin-bottom: 4px;
}

.empty-hint {
  font-size: var(--font-size-xs);
}

/* ========== 概念分解样式 ========== */
.concept-section {
  border-top: 1px dashed var(--border-color, #e0e0e0);
  padding-top: 12px;
}

.concept-label {
  display: flex;
  align-items: center;
  gap: 8px;
}

.concept-actions {
  margin-bottom: 10px;
}

.concept-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.concept-item {
  padding: 10px 12px;
  border-radius: 6px;
  border-left: 3px solid #3498db;
  background: var(--bg-hover, #f8f9fa);
  transition: all 0.2s ease;
}

.concept-item:hover {
  background: var(--bg-active, #ecf0f1);
  transform: translateX(2px);
}

.concept-item.relation-defines {
  border-left-color: #27ae60;
}

.concept-item.relation-has_law {
  border-left-color: #2980b9;
}

.concept-item.relation-applies_to {
  border-left-color: #e67e22;
}

.concept-item.relation-extends {
  border-left-color: #8e44ad;
}

.concept-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.concept-name {
  font-weight: 600;
  font-size: var(--font-size-sm);
  color: var(--text-primary, #2c3e50);
}

.concept-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  background: #f0f0f0;
  color: #666;
  flex-shrink: 0;
}

.concept-badge.type-definition {
  background: #e8f8f0;
  color: #27ae60;
}

.concept-badge.type-law {
  background: #e8f0f8;
  color: #2980b9;
}

.concept-badge.type-application {
  background: #fef5e8;
  color: #e67e22;
}

.concept-badge.type-extension {
  background: #f3e8f8;
  color: #8e44ad;
}

.concept-relation {
  margin-bottom: 4px;
}

.relation-tag {
  font-size: 11px;
  color: var(--text-muted, #7f8c8d);
  font-style: italic;
}

.concept-desc {
  font-size: 12px;
  color: var(--text-secondary, #555);
  line-height: 1.4;
  margin-top: 4px;
}

.concept-empty {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  padding: 8px 0;
  text-align: center;
  font-style: italic;
}

/* 关联概念列表 */
.concept-links {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.concept-link-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: var(--bg-elevated, #f8f9fa);
  border-radius: 4px;
  font-size: var(--font-size-xs);
}

.link-direction {
  font-weight: 700;
  color: var(--text-secondary, #666);
}

.link-type {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
}

.link-type.link-solution {
  background: #e67e22;
  color: #fff;
}

.link-type.link-depends_on {
  background: #9b59b6;
  color: #fff;
}

.link-target {
  color: var(--text-primary, #2c3e50);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 小尺寸 spinner（用于标签旁边） */
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
/* 按钮样式 */
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

.btn:hover {
  background: var(--bg-hover, #f0f0f0);
}

.btn-primary {
  background: var(--accent-primary, #3498db);
  color: #fff;
  border-color: var(--accent-primary, #3498db);
}

.btn-primary:hover {
  background: #2980b9;
}

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

/* ========== 全局概念表格样式 ========== */
.concept-table-wrapper {
  background: var(--bg-card, #fff);
  border-top: 1px solid var(--border-color, #e0e0e0);
  padding: 16px 24px;
  max-height: 320px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.table-header h3 {
  margin: 0;
  font-size: var(--font-size-md);
  color: var(--text-primary, #2c3e50);
}

.table-count {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
}

.table-scroll {
  overflow-y: auto;
  flex: 1;
}

.concept-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-xs);
}

.concept-table thead {
  position: sticky;
  top: 0;
  background: var(--bg-active, #ecf0f1);
}

.concept-table th {
  text-align: left;
  padding: 8px 10px;
  font-weight: 600;
  color: var(--text-muted, #7f8c8d);
  border-bottom: 2px solid var(--border-color, #e0e0e0);
  white-space: nowrap;
}

.concept-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
  vertical-align: top;
}

.concept-table tbody tr:hover {
  background: var(--bg-hover, #f8f9fa);
}

.concept-table .mono-cell {
  font-family: monospace;
  font-size: 10px;
  color: var(--text-muted, #7f8c8d);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.concept-table .name-cell {
  font-weight: 600;
  color: var(--text-primary, #2c3e50);
  max-width: 150px;
  word-break: break-all;
}

.concept-table .alias-cell {
  max-width: 200px;
}

.concept-table .alias-tags {
  font-size: 10px;
  color: var(--text-muted, #7f8c8d);
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.concept-table .type-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  display: inline-block;
}

.btn-secondary {
  background: var(--bg-active, #ecf0f1);
  color: var(--text-primary, #2c3e50);
  border: 1px solid var(--border-color, #e0e0e0);
}

.btn-secondary:hover {
  background: var(--bg-hover, #f8f9fa);
}

/* ========== 概念表格搜索工具栏 ========== */
.concept-toolbar {
  display: flex;
  gap: 12px;
  padding: 10px 24px;
  background: var(--bg-card, #fff);
  border-top: 1px solid var(--border-color, #e0e0e0);
  align-items: center;
  flex-wrap: wrap;
}

/* ========== 分页样式 ========== */
.pagination {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  justify-content: center;
  border-top: 1px solid var(--border-color, #e0e0e0);
  background: var(--bg-hover, #f8f9fa);
}

.page-info {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
}

.page-size-select {
  padding: 4px 8px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 4px;
  font-size: var(--font-size-xs);
  background: var(--bg-card, #fff);
  color: var(--text-primary, #2c3e50);
  cursor: pointer;
}

/* ========== 弹窗样式 ========== */
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
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
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

/* 表格行可点击 */
.concept-table tbody tr {
  cursor: pointer;
}


.btn-icon:hover {
  color: var(--text-primary, #2c3e50);
}

.spinner-inline {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ========== 图谱构建选项面板样式 ========== */
.build-options-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-page, #f5f6fa);
  z-index: 50;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 40px 20px;
  overflow-y: auto;
}

.build-options-panel {
  background: var(--bg-card, #fff);
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
  width: 100%;
  max-width: 640px;
  padding: 32px;
}

.build-options-header {
  text-align: center;
  margin-bottom: 28px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.build-options-header h2 {
  margin: 0 0 8px 0;
  font-size: var(--font-size-xl);
  color: var(--text-primary, #2c3e50);
}

.build-options-subtitle {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-muted, #7f8c8d);
}

.build-options-body {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.option-section {
  padding: 16px;
  background: var(--bg-hover, #f8f9fa);
  border-radius: 8px;
  border: 1px solid var(--border-color, #e8e8e8);
}

.option-section.collapsed .collapsed-content {
  display: none;
}

.option-section.collapsed .collapse-arrow {
  transform: rotate(0deg);
}

.option-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary, #2c3e50);
  margin-bottom: 8px;
}

.option-icon {
  font-size: 18px;
}

.option-required {
  font-size: 10px;
  padding: 2px 6px;
  background: #fdeaea;
  color: #e74c3c;
  border-radius: 4px;
  font-weight: 500;
}

.option-tag {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}

.option-tag.experimental {
  background: #fff3e0;
  color: #f57c00;
}

.option-desc {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  margin: 0 0 12px 0;
  line-height: 1.5;
}

/* 范式卡片 */
.paradigm-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.paradigm-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  background: var(--bg-card, #fff);
  border: 2px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.paradigm-card:hover {
  border-color: var(--accent-primary, #3498db);
  box-shadow: 0 2px 8px rgba(52, 152, 219, 0.1);
}

.paradigm-card.active {
  border-color: var(--accent-primary, #3498db);
  background: #f0f7ff;
}

.paradigm-radio {
  padding-top: 2px;
  flex-shrink: 0;
}

.radio-dot {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border-color, #ccc);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.radio-dot.checked {
  border-color: var(--accent-primary, #3498db);
  background: var(--accent-primary, #3498db);
}

.radio-dot.checked::after {
  content: '';
  width: 6px;
  height: 6px;
  background: #fff;
  border-radius: 50%;
}

.paradigm-info {
  flex: 1;
}

.paradigm-name {
  font-weight: 600;
  font-size: var(--font-size-sm);
  color: var(--text-primary, #2c3e50);
  margin-bottom: 4px;
}

.paradigm-desc {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  line-height: 1.4;
}

/* 粒度滑块 */
.granularity-slider {
  padding: 8px 0;
}

.slider-labels {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
}

.slider-labels span.active {
  color: var(--accent-primary, #3498db);
  font-weight: 600;
}

.slider-input {
  width: 100%;
  height: 6px;
  -webkit-appearance: none;
  appearance: none;
  background: var(--border-color, #e0e0e0);
  border-radius: 3px;
  outline: none;
}

.slider-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  background: var(--accent-primary, #3498db);
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}

.slider-input::-moz-range-thumb {
  width: 18px;
  height: 18px;
  background: var(--accent-primary, #3498db);
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}

/* 复选框 */
.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.checkbox-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
  font-size: var(--font-size-sm);
  color: var(--text-secondary, #555);
}

.checkbox-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  margin-top: 2px;
  accent-color: var(--accent-primary, #3498db);
  cursor: pointer;
}

.checkbox-text {
  line-height: 1.4;
}

/* 权重条 */
.collapse-arrow {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted, #7f8c8d);
  transition: transform 0.2s;
  transform: rotate(90deg);
}

.weight-bars {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 0;
}

.weight-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.weight-name {
  width: 70px;
  font-size: var(--font-size-xs);
  color: var(--text-secondary, #555);
  text-align: right;
}

.weight-bar {
  flex: 1;
  height: 8px;
  background: var(--border-color, #e0e0e0);
  border-radius: 4px;
  overflow: hidden;
}

.weight-fill {
  height: 100%;
  background: var(--accent-primary, #3498db);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.weight-value {
  width: 40px;
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  text-align: right;
}

/* 进度提示 */
.build-progress {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 16px;
  margin: 16px 0;
  background: #e8f4fd;
  border-radius: 8px;
  color: var(--accent-primary, #2980b9);
  font-size: var(--font-size-sm);
}

.build-progress .spinner-inline {
  border-color: rgba(41, 128, 185, 0.2);
  border-top-color: #2980b9;
}

/* 底部按钮 */
.build-options-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 20px;
  margin-top: 20px;
  border-top: 1px solid var(--border-color, #e0e0e0);
}

.btn-lg {
  padding: 10px 24px;
  font-size: var(--font-size-sm);
}

/* 范式选择下拉框 */
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
</style>
