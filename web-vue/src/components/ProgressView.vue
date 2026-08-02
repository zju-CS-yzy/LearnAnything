<template>
  <div class="progress-view">
    <header class="view-header">
      <div class="header-title">
        <span class="header-icon">📈</span>
        <span>学习进度</span>
      </div>
    </header>

    <div class="view-content">
      <!-- 标签页切换 -->
      <div class="tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab-btn"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          <span class="tab-icon">{{ tab.icon }}</span>
          <span class="tab-label">{{ tab.label }}</span>
        </button>
      </div>

      <!-- 进步曲线 -->
      <div v-if="activeTab === 'progress'" class="tab-panel">
        <div v-if="progressLoading" class="loading">加载中...</div>
        <div v-else-if="progressError" class="error">{{ progressError }}</div>
        <div v-else-if="progressData.data_points.length === 0" class="empty">
          <div class="empty-icon">📊</div>
          <div class="empty-text">暂无评测数据</div>
          <div class="empty-hint">完成一次评测后即可查看进步曲线</div>
        </div>
        <div v-else class="panel-content">
          <div class="stats-bar">
            <div class="stat-item">
              <div class="stat-value">{{ progressData.total_evaluations }}</div>
              <div class="stat-label">评测次数</div>
            </div>
            <div class="stat-item">
              <div class="stat-value" :class="trendClass">{{ trendText }}</div>
              <div class="stat-label">整体趋势</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">{{ latestAccuracy }}%</div>
              <div class="stat-label">最近正确率</div>
            </div>
          </div>

          <!-- ECharts 折线图 -->
          <div class="line-chart-container card">
            <div ref="progressChartRef" class="line-chart"></div>
          </div>

          <!-- 数据点表格（保留作为详细视图） -->
          <div class="progress-table card">
            <div class="table-header">
              <span>日期</span>
              <span>正确率</span>
              <span>得分</span>
              <span>能力值(θ)</span>
            </div>
            <div
              v-for="(dp, i) in progressData.data_points"
              :key="i"
              class="table-row"
              :class="{ highlight: i === progressData.data_points.length - 1 }"
            >
              <span>{{ dp.date }}</span>
              <span>
                <span class="accuracy-bar">
                  <span class="accuracy-fill" :style="{ width: (dp.accuracy * 100) + '%' }"></span>
                </span>
                {{ (dp.accuracy * 100).toFixed(1) }}%
              </span>
              <span>{{ dp.correct_count }}/{{ dp.total_questions }}</span>
              <span>{{ dp.theta.toFixed(3) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 错题本 -->
      <div v-if="activeTab === 'mistakes'" class="tab-panel">
        <div v-if="mistakesLoading" class="loading">加载中...</div>
        <div v-else-if="mistakesError" class="error">{{ mistakesError }}</div>
        <div v-else-if="mistakesData.items.length === 0" class="empty">
          <div class="empty-icon">✅</div>
          <div class="empty-text">暂无错题记录</div>
          <div class="empty-hint">答错的题目会自动收录到这里</div>
        </div>
        <div v-else class="panel-content">
          <div class="stats-bar">
            <div class="stat-item">
              <div class="stat-value">{{ mistakesData.total }}</div>
              <div class="stat-label">错题总数</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">{{ mistakesData.mastered_count }}</div>
              <div class="stat-label">已掌握</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">{{ mistakesData.reviewing_count }}</div>
              <div class="stat-label">复习中</div>
            </div>
          </div>

          <div class="mistakes-list">
            <div
              v-for="item in mistakesData.items"
              :key="item.wrong_id"
              class="mistake-card card"
              :class="{ mastered: item.is_mastered }"
            >
              <div class="mistake-header">
                <span class="mistake-type tag">{{ item.question_type }}</span>
                <span v-if="item.bloom_level" class="bloom-tag tag">{{ bloomLabel(item.bloom_level) }}</span>
                <span class="wrong-count">❌ {{ item.wrong_count }} 次</span>
              </div>
              <div class="mistake-question">{{ item.question_text }}</div>
              <div class="mistake-answers">
                <span class="user-wrong">你的答案：{{ item.user_answer || '(未作答)' }}</span>
                <span class="correct-answer">正确答案：{{ item.correct_answer }}</span>
              </div>
              <div v-if="item.explanation" class="mistake-explanation">{{ item.explanation }}</div>
              <div class="mistake-actions">
                <button
                  class="btn btn-sm"
                  :class="item.is_mastered ? 'btn-secondary' : 'btn-primary'"
                  @click="toggleMastered(item)"
                >
                  {{ item.is_mastered ? '标记为未掌握' : '标记已掌握' }}
                </button>
                <button class="btn btn-sm btn-secondary" @click="practiceConcept(item.concept_name)">
                  针对性练习
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 评测历史 -->
      <div v-if="activeTab === 'history'" class="tab-panel">
        <div v-if="historyLoading" class="loading">加载中...</div>
        <div v-else-if="historyError" class="error">{{ historyError }}</div>
        <div v-else-if="historyData.items.length === 0" class="empty">
          <div class="empty-icon">📋</div>
          <div class="empty-text">暂无评测历史</div>
          <div class="empty-hint">前往"评测"页面开始你的第一次评测</div>
        </div>
        <div v-else class="panel-content">
          <div class="stats-bar">
            <div class="stat-item">
              <div class="stat-value">{{ historyData.total }}</div>
              <div class="stat-label">总评测数</div>
            </div>
          </div>

          <div class="history-list">
            <div
              v-for="item in historyData.items"
              :key="item.history_id"
              class="history-card card"
            >
              <div class="history-header">
                <span class="history-topic">{{ item.topic || '未命名评测' }}</span>
                <span class="history-date">{{ formatDate(item.evaluated_at) }}</span>
              </div>
              <div class="history-stats">
                <div class="history-score" :class="scoreClass(item.accuracy)">
                  {{ (item.accuracy * 100).toFixed(1) }}%
                </div>
                <div class="history-detail">
                  {{ item.correct_count }}/{{ item.total_questions }} 正确
                  · 得分 {{ item.total_score }}/{{ item.max_score }}
                  · θ={{ item.theta.toFixed(2) }}
                </div>
              </div>
              <div v-if="item.weak_areas.length" class="history-weak">
                <span class="weak-label">薄弱环节：</span>
                <span v-for="area in item.weak_areas" :key="area" class="area-tag">{{ area }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Bloom 认知雷达图 -->
      <div v-if="activeTab === 'bloom'" class="tab-panel">
        <div v-if="bloomLoading" class="loading">加载中...</div>
        <div v-else-if="bloomError" class="error">{{ bloomError }}</div>
        <div v-else class="panel-content">
          <div class="bloom-intro">
            <div class="bloom-title">🧠 Bloom 认知能力雷达</div>
            <div class="bloom-desc">
              基于布鲁姆教育目标分类法，展示你在六个认知层次上的掌握度
            </div>
          </div>

          <!-- 雷达图容器 -->
          <div class="radar-container card">
            <div ref="radarChartRef" class="radar-chart"></div>
          </div>

          <!-- 维度详情 -->
          <div class="bloom-dimensions">
            <div
              v-for="dim in bloomRadarData.dimensions"
              :key="dim.level"
              class="dimension-card card"
              :class="{ 'dim-weak': dim.mastery !== null && dim.mastery < 0.5 }"
            >
              <div class="dim-header">
                <span class="dim-name">{{ dim.name }}</span>
                <span class="dim-level">{{ dim.level }}</span>
              </div>
              <div class="dim-mastery">
                <span class="dim-mastery-value" :style="{ color: dimColor(dim.mastery) }">
                  {{ dim.mastery !== null ? (dim.mastery * 100).toFixed(0) + '%' : '—' }}
                </span>
                <span class="dim-mastery-bar">
                  <span
                    class="dim-mastery-fill"
                    :style="{ width: (dim.mastery || 0) * 100 + '%', background: dimColor(dim.mastery) }"
                  ></span>
                </span>
              </div>
              <div class="dim-detail">
                <span v-if="dim.wrong_count > 0" class="dim-wrong">❌ 错题 {{ dim.wrong_count }} 次</span>
                <span v-else class="dim-good">✅ 无错题</span>
                <span class="dim-bank">题库 {{ dim.bank_count }} 题</span>
              </div>
            </div>
          </div>

          <!-- 统计摘要 -->
          <div class="bloom-summary card" v-if="bloomRadarData.summary">
            <div class="summary-title">📊 能力摘要</div>
            <div class="summary-grid">
              <div class="summary-item">
                <div class="summary-value">{{ (bloomRadarData.overall_accuracy * 100).toFixed(0) }}%</div>
                <div class="summary-label">整体正确率</div>
              </div>
              <div class="summary-item">
                <div class="summary-value">{{ bloomRadarData.summary.dimensions_evaluated || 0 }}</div>
                <div class="summary-label">已评估维度</div>
              </div>
              <div class="summary-item">
                <div class="summary-value" :style="{ color: dimColor(bloomRadarData.summary.strongest_mastery) }">
                  {{ bloomRadarData.summary.strongest_dimension || '—' }}
                </div>
                <div class="summary-label">最强维度</div>
              </div>
              <div class="summary-item">
                <div class="summary-value" :style="{ color: dimColor(bloomRadarData.summary.weakest_mastery) }">
                  {{ bloomRadarData.summary.weakest_dimension || '—' }}
                </div>
                <div class="summary-label">薄弱维度</div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <!-- 学习建议面板 -->
      <div v-if="activeTab === 'recommend'" class="tab-panel">
        <div v-if="recommendLoading" class="loading">加载中...</div>
        <div v-else-if="recommendError" class="error">{{ recommendError }}</div>
        <div v-else-if="recommendData.items.length === 0" class="empty">
          <div class="empty-icon">🎉</div>
          <div class="empty-text">暂无薄弱点</div>
          <div class="empty-hint">你的知识掌握很均衡，继续保持！</div>
        </div>
        <div v-else class="panel-content">
          <div class="recommend-intro">
            <div class="recommend-title">🎯 推荐学习路径</div>
            <div class="recommend-desc">
              基于你的错题记录，建议按以下顺序针对性学习
            </div>
          </div>

          <div class="recommend-list">
            <div
              v-for="(item, idx) in recommendData.items"
              :key="idx"
              class="recommend-card card"
              :class="{ 'rec-priority': item.mastery_level < 0.4 }"
            >
              <div class="rec-header">
                <span class="rec-rank">{{ idx + 1 }}</span>
                <span class="rec-concept">{{ item.concept_name }}</span>
                <span class="rec-mastery" :style="{ color: dimColor(item.mastery_level) }">
                  {{ (item.mastery_level * 100).toFixed(0) }}%
                </span>
              </div>
              <div class="rec-reason">{{ item.reason }}</div>
              <div class="rec-detail">
                <span class="rec-wrong">❌ 累计错题 {{ item.wrong_count }} 次</span>
                <span v-if="item.last_tested" class="rec-date">
                  最近错于 {{ formatDate(item.last_tested) }}
                </span>
              </div>
              <div class="rec-actions">
                <button
                  v-for="act in item.actions"
                  :key="act.action"
                  class="btn btn-sm"
                  :class="act.action === 'tutor' ? 'btn-primary' : 'btn-secondary'"
                  @click="executeAction(act)"
                >
                  {{ act.label }}
                </button>
              </div>
            </div>
          </div>

          <div class="recommend-summary card">
            <div class="summary-title">📊 建议摘要</div>
            <div class="summary-grid">
              <div class="summary-item">
                <div class="summary-value">{{ recommendData.total_weak }}</div>
                <div class="summary-label">薄弱概念</div>
              </div>
              <div class="summary-item">
                <div class="summary-value">
                  {{ recommendData.items.filter(i => i.mastery_level < 0.4).length }}
                </div>
                <div class="summary-label">急需补强</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, watch, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import {
  apiProgressChart,
  apiWrongAnswers,
  apiEvalHistory,
  apiBloomStats,
  apiBloomRadar,
  apiRecommendations,
  apiUpdateWrongAnswer,
} from '../composables/useApi.js'

// 全局学科状态
const subjectState = inject('subjectState')
const currentSubject = computed(() => subjectState.currentSubject.value)

const tabs = [
  { id: 'progress', icon: '📈', label: '进步曲线' },
  { id: 'mistakes', icon: '📕', label: '错题本' },
  { id: 'history', icon: '📋', label: '评测历史' },
  { id: 'bloom', icon: '🧠', label: 'Bloom 层次' },
  { id: 'recommend', icon: '🎯', label: '学习建议' },
]

const activeTab = ref('progress')

// ── 进步曲线 ──
const progressLoading = ref(false)
const progressError = ref('')
const progressData = ref({ data_points: [], trend: 'stable', total_evaluations: 0 })
const progressChartRef = ref(null)
let progressChart = null

const latestAccuracy = computed(() => {
  const pts = progressData.value.data_points
  if (pts.length === 0) return 0
  return (pts[pts.length - 1].accuracy * 100).toFixed(1)
})

const trendText = computed(() => {
  const map = { improving: '📈 上升', stable: '➡️ 持平', declining: '📉 下降' }
  return map[progressData.value.trend] || '未知'
})

const trendClass = computed(() => {
  const map = { improving: 'trend-up', stable: 'trend-stable', declining: 'trend-down' }
  return map[progressData.value.trend] || ''
})

function initProgressChart() {
  if (!progressChartRef.value) return
  if (progressChart) {
    progressChart.dispose()
  }
  progressChart = echarts.init(progressChartRef.value)
}

function updateProgressChart() {
  if (!progressChart || !progressData.value.data_points.length) return

  const pts = progressData.value.data_points
  const dates = pts.map(p => p.date)
  const thetas = pts.map(p => p.theta)
  const accuracies = pts.map(p => (p.accuracy * 100).toFixed(1))

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: ['能力值(θ)', '正确率(%)'],
      bottom: 0,
    },
    grid: {
      left: '8%',
      right: '8%',
      bottom: '15%',
      top: '10%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: 11 },
    },
    yAxis: [
      {
        type: 'value',
        name: 'θ',
        min: -2,
        max: 2,
        position: 'left',
        axisLine: { show: true, lineStyle: { color: '#3498db' } },
        axisLabel: { color: '#3498db' },
        splitLine: { lineStyle: { color: 'rgba(0,0,0,0.05)' } },
      },
      {
        type: 'value',
        name: '正确率',
        min: 0,
        max: 100,
        position: 'right',
        axisLine: { show: true, lineStyle: { color: '#2ecc71' } },
        axisLabel: { formatter: '{value}%', color: '#2ecc71' },
        splitLine: { show: false },
      }
    ],
    series: [
      {
        name: '能力值(θ)',
        type: 'line',
        data: thetas,
        smooth: true,
        symbol: 'circle',
        symbolSize: 8,
        lineStyle: { color: '#3498db', width: 2.5 },
        itemStyle: { color: '#3498db' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(52,152,219,0.25)' },
              { offset: 1, color: 'rgba(52,152,219,0.02)' }
            ]
          }
        },
      },
      {
        name: '正确率(%)',
        type: 'line',
        yAxisIndex: 1,
        data: accuracies,
        smooth: true,
        symbol: 'diamond',
        symbolSize: 8,
        lineStyle: { color: '#2ecc71', width: 2.5 },
        itemStyle: { color: '#2ecc71' },
      }
    ]
  }

  progressChart.setOption(option)
}

async function loadProgress() {
  progressLoading.value = true
  progressError.value = ''
  try {
    const result = await apiProgressChart('anonymous', currentSubject.value, 30)
    progressData.value = result
    await nextTick()
    initProgressChart()
    updateProgressChart()
  } catch (e) {
    progressError.value = '加载失败: ' + e.message
  } finally {
    progressLoading.value = false
  }
}

// ── 错题本 ──
const mistakesLoading = ref(false)
const mistakesError = ref('')
const mistakesData = ref({ total: 0, mastered_count: 0, reviewing_count: 0, items: [] })

async function loadMistakes() {
  mistakesLoading.value = true
  mistakesError.value = ''
  try {
    const result = await apiWrongAnswers('anonymous', currentSubject.value)
    mistakesData.value = result
  } catch (e) {
    mistakesError.value = '加载失败: ' + e.message
  } finally {
    mistakesLoading.value = false
  }
}

async function toggleMastered(item) {
  try {
    await apiUpdateWrongAnswer(item.wrong_id, { is_mastered: !item.is_mastered })
    item.is_mastered = !item.is_mastered
  } catch (e) {
    alert('更新失败: ' + e.message)
  }
}

function practiceConcept(conceptName) {
  window.dispatchEvent(new CustomEvent('la-switch-tab', {
    detail: { tab: 'quiz', topic: conceptName }
  }))
}

// ── 评测历史 ──
const historyLoading = ref(false)
const historyError = ref('')
const historyData = ref({ total: 0, items: [] })

async function loadHistory() {
  historyLoading.value = true
  historyError.value = ''
  try {
    const result = await apiEvalHistory('anonymous', currentSubject.value)
    historyData.value = result
  } catch (e) {
    historyError.value = '加载失败: ' + e.message
  } finally {
    historyLoading.value = false
  }
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function scoreClass(acc) {
  if (acc >= 0.8) return 'score-high'
  if (acc >= 0.6) return 'score-mid'
  return 'score-low'
}

// ── Bloom 认知雷达图 ──
const bloomLoading = ref(false)
const bloomError = ref('')
const bloomData = ref({ total: 0, labeled: 0, coverage: '0%', levels: {} })
const bloomRadarData = ref({
  dimensions: [],
  total_evaluated: 0,
  total_correct: 0,
  overall_accuracy: 0,
  summary: {},
})
const radarChartRef = ref(null)
let radarChart = null

const bloomNames = {
  remember: '记忆',
  understand: '理解',
  apply: '应用',
  analyze: '分析',
  evaluate: '评估',
  create: '创造',
}

const bloomColors = {
  remember: '#95a5a6',
  understand: '#3498db',
  apply: '#2ecc71',
  analyze: '#f39c12',
  evaluate: '#e67e22',
  create: '#e74c3c',
}

function bloomName(level) {
  return bloomNames[level] || level
}

function bloomColor(level) {
  return bloomColors[level] || '#999'
}

function bloomLabel(level) {
  return bloomNames[level] || level
}

function bloomPercent(level) {
  const stat = bloomData.value.levels[level]
  if (!stat || !bloomData.value.total) return 0
  return (stat.count / bloomData.value.total * 100)
}

function dimColor(mastery) {
  if (mastery === null || mastery === undefined) return '#999'
  if (mastery >= 0.7) return '#2ecc71'
  if (mastery >= 0.5) return '#f39c12'
  return '#e74c3c'
}

function initRadarChart() {
  if (!radarChartRef.value) return
  if (radarChart) {
    radarChart.dispose()
  }
  radarChart = echarts.init(radarChartRef.value)
}

function updateRadarChart() {
  if (!radarChart || !bloomRadarData.value.dimensions.length) return

  const dims = bloomRadarData.value.dimensions
  const indicator = dims.map(d => ({
    name: d.name,
    max: 1,
    color: bloomColors[d.level] || '#666',
  }))

  const values = dims.map(d => d.mastery !== null ? d.mastery : 0)
  const hasData = dims.some(d => d.mastery !== null)

  const option = {
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        const lines = params.value.map((v, i) => {
          const d = dims[i]
          return `${d.name}: ${d.mastery !== null ? (v * 100).toFixed(0) + '%' : '未评估'}`
        })
        return lines.join('<br/>')
      }
    },
    radar: {
      indicator: indicator,
      center: ['50%', '50%'],
      radius: '65%',
      axisName: {
        fontSize: 13,
        fontWeight: 500,
      },
      splitArea: {
        areaStyle: {
          color: ['rgba(250,250,250,0.3)', 'rgba(200,200,200,0.1)'],
        }
      },
      axisLine: {
        lineStyle: { color: 'rgba(0,0,0,0.1)' }
      },
      splitLine: {
        lineStyle: { color: 'rgba(0,0,0,0.1)' }
      }
    },
    series: [{
      type: 'radar',
      data: [{
        value: values,
        name: '当前掌握度',
        areaStyle: {
          color: hasData ? 'rgba(52, 152, 219, 0.2)' : 'transparent',
        },
        lineStyle: {
          color: '#3498db',
          width: 2,
        },
        itemStyle: {
          color: '#3498db',
        },
        symbol: 'circle',
        symbolSize: 6,
      }]
    }]
  }

  radarChart.setOption(option)
}

async function loadBloom() {
  bloomLoading.value = true
  bloomError.value = ''
  try {
    // 同时加载题库统计和雷达图数据
    const [stats, radar] = await Promise.all([
      apiBloomStats(currentSubject.value),
      apiBloomRadar('anonymous', currentSubject.value),
    ])
    bloomData.value = stats
    bloomRadarData.value = radar
    // 等待 DOM 更新后初始化/更新雷达图
    await nextTick()
    initRadarChart()
    updateRadarChart()
  } catch (e) {
    bloomError.value = '加载失败: ' + e.message
  } finally {
    bloomLoading.value = false
  }
}

// ── 学习建议 ──
const recommendLoading = ref(false)
const recommendError = ref('')
const recommendData = ref({ total_weak: 0, items: [] })

async function loadRecommendations() {
  recommendLoading.value = true
  recommendError.value = ''
  try {
    const result = await apiRecommendations('anonymous', currentSubject.value)
    recommendData.value = result
  } catch (e) {
    recommendError.value = '加载失败: ' + e.message
  } finally {
    recommendLoading.value = false
  }
}

function executeAction(act) {
  if (act.action === 'tutor') {
    window.dispatchEvent(new CustomEvent('la-switch-tab', {
      detail: { tab: 'chat', topic: act.topic }
    }))
  } else if (act.action === 'quiz') {
    window.dispatchEvent(new CustomEvent('la-switch-tab', {
      detail: { tab: 'quiz', topic: act.topic }
    }))
  }
}

// ── 学科自动切换 ──
const hasTriedSwitch = ref(false)

async function tryLoadWithSmartSwitch(loadFn, tabName) {
  /*
   * 智能加载：如果当前学科无数据，自动切换到用户有数据的学科
   */
  await loadFn()
  
  // 检查是否有数据
  let hasData = false
  if (tabName === 'progress') {
    hasData = progressData.value.data_points.length > 0
  } else if (tabName === 'mistakes') {
    hasData = wrongAnswers.value.items.length > 0
  } else if (tabName === 'history') {
    hasData = evalHistory.value.items.length > 0
  }
  
  // 无数据且未尝试过切换，且有其他学科可选
  if (!hasData && !hasTriedSwitch.value) {
    const otherSubjects = subjectState.subjects.value.filter(s => s.id !== currentSubject.value)
    if (otherSubjects.length > 0) {
      console.log(`[ProgressView] 当前学科 ${currentSubject.value} 无数据，尝试切换到 ${otherSubjects[0].id}`)
      hasTriedSwitch.value = true
      subjectState.setSubject(otherSubjects[0].id)
      // subjectState 变化会触发 watch，自动重新加载
      return
    }
  }
}

// ── 标签页切换加载 ──
watch(activeTab, (tab) => {
  if (tab === 'progress') tryLoadWithSmartSwitch(loadProgress, 'progress')
  if (tab === 'mistakes') tryLoadWithSmartSwitch(loadMistakes, 'mistakes')
  if (tab === 'history') tryLoadWithSmartSwitch(loadHistory, 'history')
  if (tab === 'bloom') loadBloom()
  if (tab === 'recommend') loadRecommendations()
})

watch(currentSubject, () => {
  hasTriedSwitch.value = false  // 学科手动切换后重置
  if (activeTab.value === 'progress') loadProgress()
  if (activeTab.value === 'mistakes') loadMistakes()
  if (activeTab.value === 'history') loadHistory()
  if (activeTab.value === 'bloom') loadBloom()
  if (activeTab.value === 'recommend') loadRecommendations()
})

onMounted(() => {
  tryLoadWithSmartSwitch(loadProgress, 'progress')
})
</script>

<style scoped>
.progress-view {
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
  padding: 20px 24px;
  min-height: 0;
}

/* 标签页 */
.tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 1px;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border: none;
  background: none;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all var(--transition-fast);
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
}

.tab-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.tab-btn.active {
  color: var(--accent-primary);
  border-bottom-color: var(--accent-primary);
  background: var(--bg-active);
  font-weight: 500;
}

.tab-icon { font-size: var(--font-size-md); }

/* 面板内容 */
.tab-panel {
  max-width: 900px;
}

.panel-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 统计栏 */
.stats-bar {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.stat-item {
  flex: 1;
  min-width: 120px;
  padding: 16px;
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  text-align: center;
}

.stat-value {
  font-size: var(--font-size-xl);
  font-weight: 700;
  color: var(--accent-primary);
}

.stat-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  margin-top: 4px;
}

.trend-up { color: var(--success); }
.trend-stable { color: var(--text-muted); }
.trend-down { color: var(--error); }

/* 进步曲线折线图 */
.line-chart-container {
  padding: 16px;
}

.line-chart {
  width: 100%;
  height: 320px;
}

/* 进步表格 */
.progress-table {
  overflow: hidden;
}

.table-header,
.table-row {
  display: grid;
  grid-template-columns: 120px 1fr 100px 100px;
  gap: 12px;
  padding: 10px 16px;
  align-items: center;
}

.table-header {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border-color);
}

.table-row {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-light);
}

.table-row:last-child { border-bottom: none; }
.table-row.highlight { background: var(--bg-active); }

.accuracy-bar {
  display: inline-block;
  width: 60px;
  height: 6px;
  background: var(--bg-input);
  border-radius: 3px;
  margin-right: 8px;
  vertical-align: middle;
}

.accuracy-fill {
  height: 100%;
  background: var(--accent-gradient);
  border-radius: 3px;
  transition: width 0.3s ease;
}

/* 错题卡片 */
.mistakes-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mistake-card {
  padding: 16px;
  border-left: 3px solid var(--error);
  transition: all var(--transition-fast);
}

.mistake-card.mastered {
  border-left-color: var(--success);
  opacity: 0.7;
}

.mistake-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.mistake-type { font-size: var(--font-size-xs); }

.bloom-tag {
  font-size: var(--font-size-xs);
  background: var(--bg-active);
  color: var(--accent-primary);
}

.wrong-count {
  margin-left: auto;
  font-size: var(--font-size-xs);
  color: var(--error);
}

.mistake-question {
  font-size: var(--font-size-md);
  color: var(--text-primary);
  line-height: 1.6;
  margin-bottom: 10px;
}

.mistake-answers {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: var(--font-size-sm);
  margin-bottom: 10px;
}

.user-wrong { color: var(--error); }
.correct-answer { color: var(--success); }

.mistake-explanation {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  padding: 10px;
  background: var(--bg-input);
  border-radius: var(--radius-sm);
  margin-bottom: 10px;
}

.mistake-actions {
  display: flex;
  gap: 8px;
}

/* 历史卡片 */
.history-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.history-card {
  padding: 16px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.history-topic {
  font-weight: 600;
  color: var(--text-primary);
}

.history-date {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.history-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 10px;
}

.history-score {
  font-size: var(--font-size-lg);
  font-weight: 700;
}

.score-high { color: var(--success); }
.score-mid { color: var(--warning); }
.score-low { color: var(--error); }

.history-detail {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
}

.history-weak {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.weak-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

/* Bloom 雷达图 */
.radar-container {
  padding: 16px;
  margin-bottom: 16px;
}

.radar-chart {
  width: 100%;
  height: 360px;
}

.bloom-dimensions {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.dimension-card {
  padding: 14px 16px;
  transition: all var(--transition-fast);
}

.dimension-card.dim-weak {
  border-left: 3px solid #e74c3c;
}

.dim-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.dim-name {
  font-weight: 600;
  color: var(--text-primary);
}

.dim-level {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  text-transform: uppercase;
}

.dim-mastery {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.dim-mastery-value {
  font-size: var(--font-size-lg);
  font-weight: 700;
  min-width: 48px;
  text-align: right;
}

.dim-mastery-bar {
  flex: 1;
  height: 8px;
  background: var(--bg-input);
  border-radius: 4px;
  overflow: hidden;
}

.dim-mastery-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.dim-detail {
  display: flex;
  gap: 12px;
  font-size: var(--font-size-xs);
}

.dim-wrong {
  color: var(--error);
}

.dim-good {
  color: var(--success);
}

.dim-bank {
  color: var(--text-muted);
  margin-left: auto;
}

.bloom-summary {
  padding: 16px;
}

.summary-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.summary-grid {
  display: flex;
  gap: 24px;
}

.summary-item {
  text-align: center;
}

.summary-value {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--accent-primary);
}

.summary-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

/* 学习建议 */
.recommend-intro {
  margin-bottom: 16px;
}

.recommend-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary);
}

.recommend-desc {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  margin-top: 4px;
}

.recommend-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.recommend-card {
  padding: 16px;
  transition: all var(--transition-fast);
}

.recommend-card.rec-priority {
  border-left: 3px solid #e74c3c;
}

.rec-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.rec-rank {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--accent-primary);
  color: white;
  font-size: var(--font-size-xs);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.rec-concept {
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.rec-mastery {
  font-size: var(--font-size-lg);
  font-weight: 700;
  min-width: 48px;
  text-align: right;
}

.rec-reason {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-bottom: 8px;
  line-height: 1.5;
}

.rec-detail {
  display: flex;
  gap: 16px;
  font-size: var(--font-size-xs);
  margin-bottom: 10px;
}

.rec-wrong {
  color: var(--error);
}

.rec-date {
  color: var(--text-muted);
  margin-left: auto;
}

.rec-actions {
  display: flex;
  gap: 8px;
}

.recommend-summary {
  padding: 16px;
}

.summary-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.summary-grid {
  display: flex;
  gap: 24px;
}

.summary-item {
  text-align: center;
}

.summary-value {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--accent-primary);
}

.summary-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

/* 通用 */
.card {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--font-size-xs);
  background: var(--bg-active);
  color: var(--text-secondary);
}

.area-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--font-size-xs);
  background: var(--bg-active);
  color: var(--error);
  border: 1px solid var(--border-light);
}

.loading,
.empty,
.error {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-muted);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.empty-text {
  font-size: var(--font-size-md);
  color: var(--text-primary);
  margin-bottom: 6px;
}

.empty-hint {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
}

.error {
  color: var(--error);
}

.btn-sm {
  padding: 6px 12px;
  font-size: var(--font-size-xs);
}
</style>
