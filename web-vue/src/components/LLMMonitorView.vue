<template>
  <div class="llm-monitor-view">
    <!-- 顶部标题 -->
    <header class="monitor-header">
      <h1>📊 LLM 监控面板</h1>
      <div class="monitor-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab-btn"
          :class="{ active: currentTab === tab.id }"
          @click="currentTab = tab.id"
        >
          {{ tab.icon }} {{ tab.label }}
        </button>
      </div>
    </header>

    <!-- 用量统计 Tab -->
    <div v-if="currentTab === 'usage'" class="monitor-content">
      <!-- 概览卡片 -->
      <div class="stats-cards">
        <div class="stat-card">
          <div class="stat-label">本月请求数</div>
          <div class="stat-value">{{ usageStats.total_requests || 0 }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">本月 Token 数</div>
          <div class="stat-value">{{ formatNumber(usageStats.total_tokens || 0) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">本月预估费用</div>
          <div class="stat-value">¥{{ (usageStats.total_cost || 0).toFixed(4) }}</div>
        </div>
        <div class="stat-card" :class="budgetStatusClass">
          <div class="stat-label">预算使用率</div>
          <div class="stat-value">{{ ((usageStats.budget_used_ratio || 0) * 100).toFixed(1) }}%</div>
          <div v-if="usageStats.warning_triggered" class="stat-warning">⚠️ 已触发告警</div>
        </div>
      </div>

      <!-- 每日趋势图 -->
      <div class="chart-section">
        <h3>📈 最近 {{ dailyDays }} 天用量趋势</h3>
        <div class="days-selector">
          <button
            v-for="d in [7, 14, 30]"
            :key="d"
            class="days-btn"
            :class="{ active: dailyDays === d }"
            @click="changeDailyDays(d)"
          >
            {{ d }}天
          </button>
        </div>
        <div class="daily-chart">
          <div
            v-for="item in dailyStats"
            :key="item.date"
            class="daily-bar"
            :style="{ height: getBarHeight(item.tokens, maxDailyTokens) + '%' }"
            :title="`${item.date}: ${formatNumber(item.tokens)} tokens, ¥${item.cost.toFixed(4)}`"
          >
            <div class="bar-fill" :class="{ warning: item.cost > dailyCostThreshold }"></div>
            <div class="bar-label">{{ formatShortDate(item.date) }}</div>
          </div>
        </div>
      </div>

      <!-- 模型分组 -->
      <div class="model-section">
        <h3>🤖 模型用量分布（最近30天）</h3>
        <div class="model-list">
          <div v-for="model in modelStats" :key="model.model" class="model-item">
            <div class="model-name">{{ model.model }}</div>
            <div class="model-bar-container">
              <div
                class="model-bar"
                :style="{ width: getModelBarWidth(model.tokens) + '%' }"
              ></div>
            </div>
            <div class="model-detail">
              <span>{{ model.requests }} 次</span>
              <span>{{ formatNumber(model.tokens) }} tokens</span>
              <span>¥{{ model.cost.toFixed(4) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 预算设置 -->
      <div class="budget-section">
        <h3>💰 预算设置</h3>
        <div class="budget-form">
          <label>
            月度预算上限（USD）
            <input
              v-model.number="budgetForm.monthly_budget"
              type="number"
              min="0"
              step="0.1"
              placeholder="例如: 10"
            />
          </label>
          <label>
            告警阈值（0-1）
            <input
              v-model.number="budgetForm.warning_threshold"
              type="number"
              min="0"
              max="1"
              step="0.1"
              placeholder="例如: 0.8"
            />
          </label>
          <button class="btn btn-primary" @click="saveBudget" :disabled="savingBudget">
            {{ savingBudget ? '保存中...' : '保存预算' }}
          </button>
        </div>
        <div v-if="budgetMessage" class="budget-message" :class="budgetMessage.type">
          {{ budgetMessage.text }}
        </div>
      </div>
    </div>

    <!-- 慢请求监控 Tab -->
    <div v-if="currentTab === 'slow'" class="monitor-content">
      <!-- 概览 -->
      <div class="stats-cards">
        <div class="stat-card">
          <div class="stat-label">总请求数</div>
          <div class="stat-value">{{ slowStats.total || 0 }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">慢请求数</div>
          <div class="stat-value" :class="{ warning: (slowStats.slow_ratio || 0) > 0.1 }">
            {{ slowStats.slow_count || 0 }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">慢请求比例</div>
          <div class="stat-value" :class="{ warning: (slowStats.slow_ratio || 0) > 0.1 }">
            {{ ((slowStats.slow_ratio || 0) * 100).toFixed(1) }}%
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">平均延迟</div>
          <div class="stat-value">{{ (slowStats.avg_latency_ms || 0).toFixed(0) }}ms</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">最大延迟</div>
          <div class="stat-value">{{ (slowStats.max_latency_ms || 0).toFixed(0) }}ms</div>
        </div>
      </div>

      <!-- 模型延迟对比 -->
      <div class="model-section">
        <h3>⏱️ 模型延迟对比</h3>
        <div class="model-list">
          <div v-for="model in slowModelStats" :key="model.model" class="model-item">
            <div class="model-name">{{ model.model }}</div>
            <div class="model-bar-container">
              <div
                class="model-bar latency-bar"
                :class="{ slow: model.avg_latency_ms > 5000 }"
                :style="{ width: getLatencyBarWidth(model.avg_latency_ms) + '%' }"
              ></div>
            </div>
            <div class="model-detail">
              <span>{{ model.count }} 次</span>
              <span>平均 {{ model.avg_latency_ms.toFixed(0) }}ms</span>
              <span v-if="model.slow_count > 0" class="slow-count">{{ model.slow_count }} 次慢请求</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 慢请求列表 -->
      <div class="slow-list-section">
        <h3>🐢 慢请求记录（最近 {{ slowLimit }} 条）</h3>
        <div class="slow-list">
          <div v-if="slowRequests.length === 0" class="empty-state">暂无慢请求记录</div>
          <div
            v-for="req in slowRequests"
            :key="req.id || req.timestamp"
            class="slow-item"
          >
            <div class="slow-header">
              <span class="slow-model">{{ req.model }}</span>
              <span class="slow-time">{{ formatDateTime(req.timestamp) }}</span>
              <span class="slow-latency">{{ req.latency_ms }}ms</span>
            </div>
            <div v-if="req.error" class="slow-error">{{ req.error }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  apiGetTokenUsageStats,
  apiGetTokenUsageDaily,
  apiGetTokenUsageModels,
  apiGetTokenBudget,
  apiSetTokenBudget,
  apiGetSlowRequests,
  apiGetSlowRequestStats,
  apiGetSlowRequestModels,
} from '../composables/useApi.js'

// Tab 配置
const tabs = [
  { id: 'usage', label: '用量统计', icon: '💰' },
  { id: 'slow', label: '慢请求监控', icon: '⏱️' },
]
const currentTab = ref('usage')

// ====== 用量统计数据 ======
const usageStats = ref({})
const dailyStats = ref([])
const dailyDays = ref(7)
const modelStats = ref([])
const budgetForm = ref({ monthly_budget: 10, warning_threshold: 0.8 })
const savingBudget = ref(false)
const budgetMessage = ref(null)

// ====== 慢请求数据 ======
const slowRequests = ref([])
const slowLimit = ref(20)
const slowStats = ref({})
const slowModelStats = ref([])

// 计算属性
const maxDailyTokens = computed(() => {
  const max = Math.max(...dailyStats.value.map(d => d.tokens || 0), 1)
  return max * 1.2 // 留出顶部空间
})

const dailyCostThreshold = computed(() => {
  const budget = budgetForm.value.monthly_budget || 10
  return budget / 30 // 日均预算
})

const budgetStatusClass = computed(() => {
  const ratio = usageStats.value.budget_used_ratio || 0
  if (ratio > 1) return 'danger'
  if (ratio > 0.8) return 'warning'
  return ''
})

// 方法
function formatNumber(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

function formatShortDate(dateStr) {
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function formatDateTime(ts) {
  const d = new Date(ts)
  return d.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function getBarHeight(tokens, max) {
  if (!max) return 0
  return Math.max((tokens / max) * 100, 3)
}

function getModelBarWidth(tokens) {
  const max = Math.max(...modelStats.value.map(m => m.tokens || 0), 1)
  return Math.max((tokens / max) * 100, 1)
}

function getLatencyBarWidth(ms) {
  const max = Math.max(...slowModelStats.value.map(m => m.avg_latency_ms || 0), 1)
  return Math.max((ms / max) * 100, 1)
}

async function changeDailyDays(days) {
  dailyDays.value = days
  await loadDailyStats()
}

async function loadUsageStats() {
  try {
    usageStats.value = await apiGetTokenUsageStats()
  } catch (e) {
    console.error('[LLMMonitor] 加载用量统计失败:', e)
  }
}

async function loadDailyStats() {
  try {
    dailyStats.value = await apiGetTokenUsageDaily(dailyDays.value)
  } catch (e) {
    console.error('[LLMMonitor] 加载每日统计失败:', e)
  }
}

async function loadModelStats() {
  try {
    modelStats.value = await apiGetTokenUsageModels(30)
  } catch (e) {
    console.error('[LLMMonitor] 加载模型统计失败:', e)
  }
}

async function loadBudget() {
  try {
    const budget = await apiGetTokenBudget()
    if (budget.monthly_budget !== undefined) {
      budgetForm.value.monthly_budget = budget.monthly_budget
      budgetForm.value.warning_threshold = budget.warning_threshold
    }
  } catch (e) {
    console.error('[LLMMonitor] 加载预算失败:', e)
  }
}

async function saveBudget() {
  savingBudget.value = true
  budgetMessage.value = null
  try {
    await apiSetTokenBudget(budgetForm.value.monthly_budget, budgetForm.value.warning_threshold)
    budgetMessage.value = { type: 'success', text: '预算设置已保存' }
    await loadUsageStats() // 刷新统计
  } catch (e) {
    budgetMessage.value = { type: 'error', text: '保存失败: ' + e.message }
  } finally {
    savingBudget.value = false
    setTimeout(() => { budgetMessage.value = null }, 3000)
  }
}

async function loadSlowRequests() {
  try {
    slowRequests.value = await apiGetSlowRequests(slowLimit.value)
  } catch (e) {
    console.error('[LLMMonitor] 加载慢请求失败:', e)
  }
}

async function loadSlowStats() {
  try {
    slowStats.value = await apiGetSlowRequestStats()
  } catch (e) {
    console.error('[LLMMonitor] 加载慢请求统计失败:', e)
  }
}

async function loadSlowModelStats() {
  try {
    slowModelStats.value = await apiGetSlowRequestModels()
  } catch (e) {
    console.error('[LLMMonitor] 加载模型延迟统计失败:', e)
  }
}

// 加载所有数据
async function loadAll() {
  await Promise.all([
    loadUsageStats(),
    loadDailyStats(),
    loadModelStats(),
    loadBudget(),
    loadSlowRequests(),
    loadSlowStats(),
    loadSlowModelStats(),
  ])
}

onMounted(() => {
  loadAll()
})
</script>

<style scoped>
.llm-monitor-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--bg-main, #f5f5f5);
}

.monitor-header {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
  background: var(--bg-card, #fff);
  flex-shrink: 0;
}

.monitor-header h1 {
  margin: 0 0 12px 0;
  font-size: var(--font-size-xl, 20px);
  color: var(--text-primary, #333);
}

.monitor-tabs {
  display: flex;
  gap: 8px;
}

.tab-btn {
  padding: 8px 16px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: var(--radius-sm, 6px);
  background: var(--bg-main, #f5f5f5);
  color: var(--text-secondary, #666);
  font-size: var(--font-size-md, 14px);
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: var(--bg-hover, #f0f0f0);
}

.tab-btn.active {
  background: var(--accent-primary, #3b82f6);
  color: white;
  border-color: var(--accent-primary, #3b82f6);
}

.monitor-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}

/* 统计卡片 */
.stats-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}

.stat-card {
  padding: 16px;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: var(--radius-md, 8px);
  text-align: center;
}

.stat-card.warning {
  border-color: #f59e0b;
  background: #fffbeb;
}

.stat-card.danger {
  border-color: #ef4444;
  background: #fef2f2;
}

.stat-label {
  font-size: var(--font-size-xs, 12px);
  color: var(--text-muted, #999);
  margin-bottom: 8px;
}

.stat-value {
  font-size: var(--font-size-2xl, 24px);
  font-weight: 600;
  color: var(--text-primary, #333);
}

.stat-value.warning {
  color: #f59e0b;
}

.stat-warning {
  font-size: var(--font-size-xs, 12px);
  color: #ef4444;
  margin-top: 4px;
}

/* 图表区域 */
.chart-section,
.model-section,
.budget-section,
.slow-list-section {
  margin-bottom: 24px;
  padding: 16px;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: var(--radius-md, 8px);
}

.chart-section h3,
.model-section h3,
.budget-section h3,
.slow-list-section h3 {
  margin: 0 0 12px 0;
  font-size: var(--font-size-md, 14px);
  color: var(--text-primary, #333);
}

/* 每日趋势图 */
.days-selector {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
}

.days-btn {
  padding: 4px 10px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: var(--radius-sm, 4px);
  background: var(--bg-main, #f5f5f5);
  font-size: var(--font-size-xs, 12px);
  cursor: pointer;
}

.days-btn.active {
  background: var(--accent-primary, #3b82f6);
  color: white;
  border-color: var(--accent-primary, #3b82f6);
}

.daily-chart {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 150px;
  padding-bottom: 24px;
  position: relative;
}

.daily-bar {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  min-width: 20px;
  height: 100%;
  position: relative;
}

.bar-fill {
  width: 100%;
  background: var(--accent-primary, #3b82f6);
  border-radius: 3px 3px 0 0;
  min-height: 3px;
  transition: height 0.3s;
}

.bar-fill.warning {
  background: #f59e0b;
}

.bar-label {
  position: absolute;
  bottom: -20px;
  font-size: 10px;
  color: var(--text-muted, #999);
  white-space: nowrap;
  transform: rotate(-45deg);
  transform-origin: top left;
}

/* 模型列表 */
.model-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.model-item {
  display: grid;
  grid-template-columns: 200px 1fr auto;
  align-items: center;
  gap: 12px;
}

.model-name {
  font-size: var(--font-size-sm, 13px);
  font-weight: 500;
  color: var(--text-primary, #333);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.model-bar-container {
  height: 8px;
  background: var(--bg-active, #e0e0e0);
  border-radius: 4px;
  overflow: hidden;
}

.model-bar {
  height: 100%;
  background: var(--accent-primary, #3b82f6);
  border-radius: 4px;
  transition: width 0.3s;
}

.model-bar.latency-bar {
  background: #10b981;
}

.model-bar.latency-bar.slow {
  background: #ef4444;
}

.model-detail {
  display: flex;
  gap: 12px;
  font-size: var(--font-size-xs, 12px);
  color: var(--text-muted, #999);
  white-space: nowrap;
}

.slow-count {
  color: #ef4444;
}

/* 预算设置 */
.budget-form {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.budget-form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: var(--font-size-sm, 13px);
  color: var(--text-secondary, #666);
}

.budget-form input {
  padding: 6px 10px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: var(--radius-sm, 4px);
  font-size: var(--font-size-md, 14px);
  width: 120px;
}

.budget-message {
  margin-top: 8px;
  font-size: var(--font-size-sm, 13px);
}

.budget-message.success {
  color: #10b981;
}

.budget-message.error {
  color: #ef4444;
}

/* 慢请求列表 */
.slow-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.empty-state {
  text-align: center;
  padding: 24px;
  color: var(--text-muted, #999);
  font-size: var(--font-size-sm, 13px);
}

.slow-item {
  padding: 10px 12px;
  background: var(--bg-main, #f5f5f5);
  border-radius: var(--radius-sm, 6px);
  border-left: 3px solid #ef4444;
}

.slow-header {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: var(--font-size-sm, 13px);
}

.slow-model {
  font-weight: 500;
  color: var(--text-primary, #333);
}

.slow-time {
  color: var(--text-muted, #999);
}

.slow-latency {
  color: #ef4444;
  font-weight: 500;
  margin-left: auto;
}

.slow-error {
  margin-top: 4px;
  font-size: var(--font-size-xs, 12px);
  color: #ef4444;
}

/* 按钮 */
.btn {
  padding: 8px 16px;
  border-radius: var(--radius-sm, 6px);
  font-size: var(--font-size-md, 14px);
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.btn-primary {
  background: var(--accent-primary, #3b82f6);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
