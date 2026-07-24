<template>
  <div class="evaluation-report">
    <!-- 头部 -->
    <header class="report-header">
      <h2 class="report-title">
        <span class="title-icon">📊</span>
        评测报告
      </h2>
      <button class="close-btn" @click="$emit('close')">×</button>
    </header>

    <!-- 标签页 -->
    <div class="report-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 内容区 -->
    <div class="report-content">
      <!-- 视图1: 概览 -->
      <div v-if="activeTab === 'overview'" class="tab-panel">
        <!-- 统计卡片 -->
        <div class="stat-cards">
          <div class="stat-card">
            <div class="stat-value" :class="scoreClass">{{ accuracy }}%</div>
            <div class="stat-label">正确率</div>
            <div class="stat-sub">{{ correctCount }}/{{ totalQuestions }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" :class="thetaClass">{{ thetaText }}</div>
            <div class="stat-label">能力值</div>
            <div class="stat-sub">θ = {{ theta.toFixed(2) }}</div>
          </div>
          <div class="stat-card" v-if="thetaChange !== null">
            <div class="stat-value" :class="changeClass">
              {{ thetaChange > 0 ? '↑' : thetaChange < 0 ? '↓' : '→' }}
              {{ Math.abs(thetaChange).toFixed(2) }}
            </div>
            <div class="stat-label">较上次</div>
            <div class="stat-sub">{{ thetaChange > 0 ? '进步' : thetaChange < 0 ? '退步' : '持平' }}</div>
          </div>
        </div>

        <!-- 一句话总结 -->
        <div class="summary-text" v-if="summaryText">
          <span class="summary-icon">💬</span>
          {{ summaryText }}
        </div>

        <!-- 薄弱知识点 -->
        <div class="weak-section" v-if="weakConcepts.length">
          <div class="section-title">⚠️ 薄弱知识点（{{ weakConcepts.length }}个）</div>
          <div class="weak-list">
            <div
              v-for="item in weakConcepts"
              :key="item.concept_id"
              class="weak-item"
            >
              <div class="weak-info">
                <span class="weak-name">{{ item.concept_name }}</span>
                <span class="weak-score">{{ (item.mastery_level * 100).toFixed(0) }}%</span>
              </div>
              <div class="weak-bar">
                <div class="weak-fill" :style="{ width: (item.mastery_level * 100) + '%' }"></div>
              </div>
              <div class="weak-actions">
                <button class="action-btn" @click="$emit('review', item.concept_name)">去复习</button>
                <button class="action-btn" @click="$emit('practice', item.concept_name)">去练习</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 视图2: 能力条形图 -->
      <div v-if="activeTab === 'bars'" class="tab-panel">
        <div class="bars-controls">
          <select v-model="barsSort" @change="loadBars" class="control-select">
            <option value="mastery_asc">掌握度升序</option>
            <option value="mastery_desc">掌握度降序</option>
            <option value="name">按名称</option>
          </select>
          <select v-model="barsFilter" @change="loadBars" class="control-select">
            <option value="all">全部</option>
            <option value="weak">仅薄弱</option>
            <option value="medium">仅中等</option>
            <option value="strong">仅强项</option>
          </select>
        </div>

        <!-- ECharts 容器 -->
        <div ref="chartRef" class="chart-container"></div>

        <!-- 统计摘要 -->
        <div class="bars-summary" v-if="barsData.summary">
          <div class="summary-item">
            <span class="summary-label">已评估概念</span>
            <span class="summary-value">{{ barsData.summary.strong_count + barsData.summary.medium_count + barsData.summary.weak_count }} 个</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">平均掌握度</span>
            <span class="summary-value">{{ (barsData.summary.avg_mastery * 100).toFixed(1) }}%</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">强项</span>
            <span class="summary-value strong">{{ barsData.summary.strong_count }} 个</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">薄弱</span>
            <span class="summary-value weak">{{ barsData.summary.weak_count }} 个</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { apiVisualizationBars } from '../composables/useApi.js'

// ========== Props / Emits ==========
const props = defineProps({
  subject: { type: String, default: 'generic' },
  // 从评测结果传入的数据
  evalReport: { type: Object, default: null },
})

const emit = defineEmits(['close', 'review', 'practice'])

// ========== 标签页 ==========
const tabs = [
  { key: 'overview', label: '概览' },
  { key: 'bars', label: '能力条形图' },
]
const activeTab = ref('overview')

// ========== 概览面板数据 ==========
const accuracy = computed(() => {
  if (!props.evalReport) return 0
  const total = props.evalReport.total_score || 0
  const max = props.evalReport.max_score || 1
  return Math.round((total / max) * 100)
})

const totalQuestions = computed(() => {
  if (!props.evalReport || !props.evalReport.details) return 0
  return props.evalReport.details.length
})

const correctCount = computed(() => {
  if (!props.evalReport || !props.evalReport.details) return 0
  return props.evalReport.details.filter(d => d.is_correct).length
})

const theta = computed(() => {
  if (!props.evalReport || !props.evalReport.irt) return 0.5
  // IRT theta 范围通常是 -3~3，映射到 0~1
  const raw = props.evalReport.irt.theta || 0
  return Math.max(0, Math.min(1, (raw + 3) / 6))
})

const thetaText = computed(() => {
  const t = theta.value
  if (t >= 0.8) return '高级'
  if (t >= 0.6) return '中上'
  if (t >= 0.4) return '中级'
  if (t >= 0.2) return '初级'
  return '入门'
})

const thetaChange = computed(() => {
  // 简化：从 report 中读取（后续可从历史记录计算）
  return null // Phase 1 暂不实现
})

const scoreClass = computed(() => {
  const a = accuracy.value
  if (a >= 80) return 'strong'
  if (a >= 60) return 'medium'
  return 'weak'
})

const thetaClass = computed(() => {
  const t = theta.value
  if (t >= 0.7) return 'strong'
  if (t >= 0.4) return 'medium'
  return 'weak'
})

const changeClass = computed(() => {
  const c = thetaChange.value
  if (c === null) return ''
  if (c > 0) return 'strong'
  if (c < 0) return 'weak'
  return 'medium'
})

const summaryText = computed(() => {
  if (!props.evalReport) return ''
  const details = props.evalReport.details || []
  const wrong = details.filter(d => !d.is_correct)
  if (wrong.length === 0) return '太棒了！全部答对，继续保持！'
  if (accuracy.value >= 80) return `表现不错！仅错 ${wrong.length} 题，注意回顾错题即可。`
  if (accuracy.value >= 60) return `基础尚可，但在 ${wrong.length} 个知识点上需要加强。`
  return `需要努力！建议重点复习薄弱知识点，重新巩固基础。`
})

// 薄弱概念（从 barsData 或 evalReport 推导）
const weakConcepts = ref([])

// ========== 条形图面板数据 ==========
const chartRef = ref(null)
let chartInstance = null
const barsSort = ref('mastery_asc')
const barsFilter = ref('all')
const barsData = ref({ items: [], summary: null })
const isLoadingBars = ref(false)

// ========== 加载条形图数据 ==========
async function loadBars() {
  isLoadingBars.value = true
  try {
    // LA-040-P1-VIS Phase 1: 优先从 API 获取历史数据
    const result = await apiVisualizationBars(
      'anonymous',
      props.subject,
      barsSort.value,
      20,
      barsFilter.value
    )
    
    // 如果 API 返回数据，直接使用
    if (result.items && result.items.length > 0) {
      barsData.value = result
      weakConcepts.value = result.items.filter(it => it.status === 'weak').slice(0, 5)
      console.log('[EvaluationReport] 从 API 加载条形图数据:', result.items.length, '条')
    } else {
      // API 无数据：从本次评测结果 evalReport 构建临时条形图数据
      console.log('[EvaluationReport] API 无历史数据，从本次评测结果构建')
      buildBarsFromEvalReport()
    }
    
    await nextTick()
    renderChart()
  } catch (e) {
    console.error('[EvaluationReport] 加载条形图数据失败:', e)
    // API 调用失败也尝试从 evalReport 构建
    buildBarsFromEvalReport()
    await nextTick()
    renderChart()
  } finally {
    isLoadingBars.value = false
  }
}

// LA-040-P1-VIS Phase 1: 从本次评测结果构建临时条形图数据
function buildBarsFromEvalReport() {
  if (!props.evalReport) {
    barsData.value = { items: [], summary: { strong_count: 0, medium_count: 0, weak_count: 0, avg_mastery: 0 } }
    return
  }
  
  const report = props.evalReport
  const items = []
  
  // 1. 从 weak_areas 构建薄弱项（掌握度 20-40%）
  if (report.weak_areas) {
    report.weak_areas.forEach((area, idx) => {
      items.push({
        concept_id: `weak_${idx}`,
        concept_name: area,
        mastery_level: 0.30 + (idx * 0.05), // 薄弱项掌握度 30-45%
        test_count: report.total_questions || 1,
        correct_count: 0,
        last_tested: new Date().toISOString(),
        status: 'weak',
        last_mastery: null,
        change: null
      })
    })
  }
  
  // 2. 从 strong_areas 构建强项（掌握度 70-90%）
  if (report.strong_areas) {
    report.strong_areas.forEach((area, idx) => {
      items.push({
        concept_id: `strong_${idx}`,
        concept_name: area,
        mastery_level: 0.75 + (idx * 0.05), // 强项掌握度 75-90%
        test_count: report.total_questions || 1,
        correct_count: Math.ceil((report.total_questions || 1) * 0.8),
        last_tested: new Date().toISOString(),
        status: 'strong',
        last_mastery: null,
        change: null
      })
    })
  }
  
  // 3. 如果没有 weak/strong_areas，从答题详情按概念统计
  if (items.length === 0 && report.details) {
    const conceptStats = {}
    report.details.forEach(d => {
      const concept = d.concept || d.topic || '未分类'
      if (!conceptStats[concept]) {
        conceptStats[concept] = { total: 0, correct: 0 }
      }
      conceptStats[concept].total += 1
      if (d.is_correct) conceptStats[concept].correct += 1
    })
    
    Object.entries(conceptStats).forEach(([concept, stats]) => {
      const mastery = stats.correct / stats.total
      items.push({
        concept_id: concept,
        concept_name: concept,
        mastery_level: mastery,
        test_count: stats.total,
        correct_count: stats.correct,
        last_tested: new Date().toISOString(),
        status: mastery >= 0.7 ? 'strong' : mastery >= 0.4 ? 'medium' : 'weak',
        last_mastery: null,
        change: null
      })
    })
  }
  
  // 4. 如果仍然没有数据，显示总体能力
  if (items.length === 0) {
    const accuracy = report.percentage || 50
    const mastery = accuracy / 100
    items.push({
      concept_id: 'overall',
      concept_name: '综合能力',
      mastery_level: mastery,
      test_count: report.total_questions || 1,
      correct_count: report.correct_count || 0,
      last_tested: new Date().toISOString(),
      status: mastery >= 0.7 ? 'strong' : mastery >= 0.4 ? 'medium' : 'weak',
      last_mastery: null,
      change: null
    })
  }
  
  // 排序
  if (barsSort.value === 'mastery_asc') {
    items.sort((a, b) => a.mastery_level - b.mastery_level)
  } else if (barsSort.value === 'mastery_desc') {
    items.sort((a, b) => b.mastery_level - a.mastery_level)
  } else {
    items.sort((a, b) => a.concept_name.localeCompare(b.concept_name))
  }
  
  // 筛选
  let filtered = items
  if (barsFilter.value !== 'all') {
    filtered = items.filter(it => it.status === barsFilter.value)
  }
  
  const strong_count = items.filter(it => it.status === 'strong').length
  const medium_count = items.filter(it => it.status === 'medium').length
  const weak_count = items.filter(it => it.status === 'weak').length
  const avg_mastery = items.reduce((sum, it) => sum + it.mastery_level, 0) / items.length
  
  barsData.value = {
    total_concepts: items.length,
    displayed: filtered.length,
    items: filtered,
    summary: {
      strong_count,
      medium_count,
      weak_count,
      avg_mastery: Math.round(avg_mastery * 100) / 100,
      last_evaluated: new Date().toISOString()
    }
  }
  
  weakConcepts.value = items.filter(it => it.status === 'weak').slice(0, 5)
  console.log('[EvaluationReport] 从评测结果构建条形图:', items.length, '条')
}

// ========== ECharts 渲染 ==========
function renderChart() {
  if (!chartRef.value) return

  // 动态导入 echarts（避免 SSR 问题）
  import('echarts').then(echarts => {
    if (chartInstance) {
      chartInstance.dispose()
    }

    chartInstance = echarts.init(chartRef.value)

    const items = barsData.value.items || []
    const names = items.map(it => it.concept_name)
    const values = items.map(it => (it.mastery_level * 100).toFixed(0))
    const colors = items.map(it => {
      if (it.status === 'strong') return '#27ae60'
      if (it.status === 'medium') return '#f39c12'
      return '#e74c3c'
    })

    const option = {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const p = params[0]
          const item = items[p.dataIndex]
          return `<strong>${p.name}</strong><br/>
                  掌握度: ${p.value}%<br/>
                  测试次数: ${item.test_count}<br/>
                  答对: ${item.correct_count}/${item.test_count}`
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'value',
        max: 100,
        axisLabel: { formatter: '{value}%', color: '#8b8b8b' },
        splitLine: { lineStyle: { color: '#2a2a4a' } }
      },
      yAxis: {
        type: 'category',
        data: names,
        axisLabel: { color: '#e0e0e0', fontSize: 12 },
        axisLine: { lineStyle: { color: '#2a2a4a' } }
      },
      series: [{
        type: 'bar',
        data: values.map((v, i) => ({
          value: v,
          itemStyle: { color: colors[i], borderRadius: [0, 4, 4, 0] }
        })),
        barWidth: '60%',
        label: {
          show: true,
          position: 'right',
          formatter: '{c}%',
          color: '#e0e0e0',
          fontSize: 11
        }
      }]
    }

    chartInstance.setOption(option)
  })
}

function handleResize() {
  if (chartInstance) {
    chartInstance.resize()
  }
}

// ========== 生命周期 ==========
watch(() => activeTab.value, (tab) => {
  if (tab === 'bars') {
    loadBars()
  }
})

onMounted(() => {
  window.addEventListener('resize', handleResize)
  // 默认加载概览的薄弱概念
  loadBars()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
})
</script>

<style scoped>
.evaluation-report {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-main);
}

.report-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 48px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.report-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.title-icon {
  font-size: 20px;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 24px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: var(--transition-fast);
}

.close-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* 标签页 */
.report-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 20px 0;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.tab-btn {
  padding: 8px 16px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  transition: var(--transition-fast);
  border-bottom: 2px solid transparent;
}

.tab-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.tab-btn.active {
  color: var(--accent-primary);
  border-bottom-color: var(--accent-primary);
  background: var(--bg-active);
}

/* 内容区 */
.report-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.tab-panel {
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 统计卡片 */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 16px;
  text-align: center;
}

.stat-value {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  margin-bottom: 4px;
}

.stat-value.strong { color: var(--success); }
.stat-value.medium { color: var(--warning); }
.stat-value.weak { color: var(--error); }

.stat-label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-bottom: 2px;
}

.stat-sub {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

/* 总结文本 */
.summary-text {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 12px 16px;
  margin-bottom: 20px;
  font-size: var(--font-size-md);
  color: var(--text-primary);
  line-height: 1.6;
}

.summary-icon {
  margin-right: 6px;
}

/* 薄弱知识点 */
.weak-section {
  margin-top: 8px;
}

.section-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.weak-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.weak-item {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 12px 16px;
}

.weak-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.weak-name {
  font-weight: 500;
  color: var(--text-primary);
}

.weak-score {
  font-size: var(--font-size-sm);
  color: var(--error);
  font-weight: 600;
}

.weak-bar {
  height: 6px;
  background: var(--bg-input);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 10px;
}

.weak-fill {
  height: 100%;
  background: var(--error);
  border-radius: 3px;
  transition: width 0.5s ease;
}

.weak-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 4px 12px;
  border: 1px solid var(--border-light);
  background: var(--bg-input);
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: var(--transition-fast);
}

.action-btn:hover {
  background: var(--accent-primary);
  color: white;
  border-color: var(--accent-primary);
}

/* 条形图控制 */
.bars-controls {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.control-select {
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  background: var(--bg-input);
  color: var(--text-primary);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

/* 图表容器 */
.chart-container {
  width: 100%;
  height: 400px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
}

/* 条形图摘要 */
.bars-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
}

.summary-item {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.summary-value {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.summary-value.strong { color: var(--success); }
.summary-value.weak { color: var(--error); }
</style>
