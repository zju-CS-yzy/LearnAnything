<template>
  <!-- LA-DEPLOY-FEAT: 按功能模块的 API 配置向导 -->
  <div class="setup-wizard" v-if="showWizard">
    <div class="setup-container">
      <!-- 右上角关闭按钮 — 支持随时退出 -->
      <button class="close-btn" @click="closeWizard" title="关闭">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>

      <div class="setup-header">
        <h1>🚀 欢迎使用 LearnAnything</h1>
        <p class="subtitle">配置 API 密钥以启用各项功能</p>
      </div>

      <div class="setup-content">
        <!-- 功能标签页 -->
        <div class="feature-tabs">
          <button
            v-for="feat in features"
            :key="feat.id"
            class="tab-btn"
            :class="{ active: currentFeature === feat.id, required: feat.required }"
            @click="currentFeature = feat.id"
          >
            <span class="tab-icon">{{ feat.icon }}</span>
            <span class="tab-name">{{ feat.name }}</span>
            <span v-if="feat.required" class="required-badge">必需</span>
            <span v-if="getFeatureStatus(feat.id) === 'ok'" class="status-ok">✓</span>
          </button>
        </div>

        <!-- 当前功能配置面板 -->
        <div class="feature-panel">
          <div class="panel-header">
            <h2>{{ currentFeatureInfo.name }}</h2>
            <p class="feature-desc">{{ currentFeatureInfo.description }}</p>
          </div>

          <!-- 提供商选择 -->
          <div class="form-group">
            <label>
              选择服务商
              <span v-if="!config[currentFeature].provider" class="required-inline">* 必选</span>
            </label>
            <div class="provider-grid">
              <div
                v-for="p in availableProviders"
                :key="p.id"
                class="provider-card"
                :class="{ selected: config[currentFeature].provider === p.id }"
                @click="selectProvider(p.id)"
              >
                <span class="provider-icon">{{ p.icon }}</span>
                <span class="provider-name">{{ p.name }}</span>
              </div>
            </div>
            <span class="error-msg" v-if="!config[currentFeature].provider">
              ⚠️ 请先点击上方卡片选择服务商
            </span>
          </div>

          <!-- API Key -->
          <div class="form-group">
            <label>
              API Key
              <a
                v-if="selectedProviderInfo.url"
                :href="selectedProviderInfo.url"
                target="_blank"
                class="get-key-link"
              >
                🔗 获取 API Key
              </a>
            </label>
            <input
              v-model="config[currentFeature].api_key"
              type="password"
              :placeholder="apiKeyPlaceholder"
              :class="{ error: errors[currentFeature] }"
            />
            <span class="hint">{{ selectedProviderInfo.api_key_format }}</span>
            <span class="error-msg" v-if="errors[currentFeature]">{{ errors[currentFeature] }}</span>
          </div>

          <!-- Base URL（自定义时显示） -->
          <div class="form-group" v-if="config[currentFeature].provider === 'custom'">
            <label>Base URL</label>
            <input
              v-model="config[currentFeature].base_url"
              type="text"
              placeholder="https://your-api-endpoint.com/v1"
            />
          </div>

          <!-- 模型选择 -->
          <div class="form-group">
            <label>模型</label>
            <select v-model="config[currentFeature].model">
              <option value="">-- 选择模型 --</option>
              <option
                v-for="(label, mid) in selectedProviderInfo.models"
                :key="mid"
                :value="mid"
              >
                {{ label }}
              </option>
            </select>
            <span class="hint" v-if="!config[currentFeature].provider">
              ⚠️ 请先选择上方服务商
            </span>
            <span class="hint" v-else-if="!config[currentFeature].model">
              留空将使用默认模型（{{ featureDefaultModel }}）
            </span>
          </div>

          <!-- 测试按钮 -->
          <div class="test-section">
            <button
              class="test-btn"
              :class="testResults[currentFeature].status"
              @click="testCurrentFeature"
              :disabled="testing"
            >
              <span v-if="testing">测试中...</span>
              <span v-else-if="testResults[currentFeature].status === 'success'">✓ 连接正常</span>
              <span v-else-if="testResults[currentFeature].status === 'error'">✗ 测试失败 - 重试</span>
              <span v-else>🔍 测试连接</span>
            </button>
            <span class="test-message" v-if="testResults[currentFeature].message">
              {{ testResults[currentFeature].message }}
            </span>
          </div>
        </div>

        <!-- 推荐配置提示 -->
        <div class="recommendation" v-if="!hasAnyConfig">
          <h3>💡 推荐配置方案</h3>
          <div class="rec-option" @click="applyRecommendation('zhipu_deepseek')">
            <strong>方案 A（推荐）</strong>
            <p>智谱AI (VLM + Embedding) + DeepSeek (LLM)</p>
            <span class="rec-tag">性价比高</span>
          </div>
          <div class="rec-option" @click="applyRecommendation('openai')">
            <strong>方案 B</strong>
            <p>OpenAI 全功能（GPT-4o + Embedding）</p>
            <span class="rec-tag">一站式</span>
          </div>
          <div class="rec-option" @click="applyRecommendation('siliconflow')">
            <strong>方案 C</strong>
            <p>硅基流动（国内一站式平台）</p>
            <span class="rec-tag">国内便捷</span>
          </div>
        </div>
      </div>

      <!-- 底部按钮 -->
      <div class="setup-footer">
        <div class="feature-summary">
          <span
            v-for="feat in features"
            :key="feat.id"
            class="summary-dot"
            :class="getFeatureStatus(feat.id)"
            :title="feat.name"
          >
            {{ feat.icon }}
          </span>
        </div>
        <div class="footer-actions">
          <button class="btn-secondary" @click="closeWizard">
            取消
          </button>
          <button
            class="btn-primary"
            @click="saveAndFinish"
            :disabled="saving || !canFinish"
          >
            {{ saving ? '保存中...' : '完成配置' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'

// LA-DEPLOY-FEAT: 按功能模块的 API 配置向导

const props = defineProps({
  modelValue: { type: Boolean, default: false }
})

const emit = defineEmits(['update:modelValue', 'configured'])

const showWizard = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

// 功能定义
const features = [
  {
    id: 'llm',
    name: '语言处理',
    icon: '💬',
    description: '智能对话、语义提取、评测评分。需要支持 chat completions 的 API。',
    required: true,
  },
  {
    id: 'llm_fallback',
    name: '备用语言处理',
    icon: '🛡️',
    description: '当主语言处理服务故障或限流时自动切换的备用 API。建议选用不同服务商。',
    required: false,
  },
  {
    id: 'vlm',
    name: '视觉处理',
    icon: '👁️',
    description: '图片描述、表格提取、公式识别。需要支持多模态（图片输入）的 API。',
    required: false,
  },
  {
    id: 'embedding',
    name: '文本向量化',
    icon: '📊',
    description: '文本向量化，用于语义搜索和知识检索。需要支持 embeddings 的 API。',
    required: true,
  },
  {
    id: 'mineru',
    name: 'PDF 解析',
    icon: '📄',
    description: 'PDF 结构化解析（标题层级、图片、公式提取）。需要 MinerU CLI 和 Token。',
    required: false,
  },
]

const currentFeature = ref('llm')
const currentFeatureInfo = computed(() => features.find(f => f.id === currentFeature.value))

// 配置数据
const config = reactive({
  llm: { provider: '', api_key: '', base_url: '', model: '', enabled: true, custom_model: '' },
  llm_fallback: { provider: '', api_key: '', base_url: '', model: '', enabled: true, custom_model: '' },
  vlm: { provider: '', api_key: '', base_url: '', model: '', enabled: true, custom_model: '' },
  embedding: { provider: '', api_key: '', base_url: '', model: '', enabled: true, custom_model: '' },
  mineru: { provider: 'mineru', api_key: '', base_url: '', model: '', enabled: true, custom_model: '' },
})

// 提供商列表
const providers = ref([])

// 错误信息
const errors = reactive({ llm: '', llm_fallback: '', vlm: '', embedding: '', mineru: '' })

// 测试结果
const testResults = reactive({
  llm: { status: 'pending', message: '' },
  llm_fallback: { status: 'pending', message: '' },
  vlm: { status: 'pending', message: '' },
  embedding: { status: 'pending', message: '' },
  mineru: { status: 'pending', message: '' },
})

const testing = ref(false)
const saving = ref(false)
const hasAnyConfig = ref(false)

// 计算属性
const availableProviders = computed(() => {
  // 根据当前功能筛选支持的提供商
  // LLM-ROBUST: llm_fallback 使用与 llm 相同的提供商列表
  const feat = currentFeature.value === 'llm_fallback' ? 'llm' : currentFeature.value
  return providers.value.filter(p => p.features.includes(feat) || feat === 'mineru')
})

const selectedProviderInfo = computed(() => {
  const pid = config[currentFeature.value].provider
  return providers.value.find(p => p.id === pid) || {}
})

const featureDefaultModel = computed(() => {
  // 返回当前功能+当前提供商的默认模型
  const feat = currentFeature.value
  const pid = config[feat].provider
  const defaults = {
    llm: { deepseek: 'deepseek-v4-pro', kimi: 'kimi-k2.5', openai: 'gpt-4o', siliconflow: 'deepseek-ai/DeepSeek-V3' },
    llm_fallback: { deepseek: 'deepseek-v4-pro', kimi: 'kimi-k2.5', openai: 'gpt-4o', siliconflow: 'deepseek-ai/DeepSeek-V3' },
    vlm: { zhipu: 'glm-4.5v', openai: 'gpt-4o', siliconflow: 'Qwen/Qwen2.5-VL-72B-Instruct' },
    embedding: { zhipu: 'embedding-3', openai: 'text-embedding-3-large', siliconflow: 'BAAI/bge-large-zh-v1.5' },
  }
  return defaults[feat]?.[pid] || ''
})

const apiKeyPlaceholder = computed(() => {
  const info = selectedProviderInfo.value
  return info.api_key_format ? `格式: ${info.api_key_format}` : '请输入 API Key'
})

const canFinish = computed(() => {
  // LLM 和 Embedding 必须配置
  return config.llm.api_key.trim() && config.embedding.api_key.trim()
})

// 方法
function selectProvider(pid) {
  const feat = currentFeature.value
  config[feat].provider = pid

  // LA-ROBUST: 自动设置默认模型
  const defaults = {
    llm: { deepseek: 'deepseek-v4-pro', kimi: 'kimi-k2.5', openai: 'gpt-4o', siliconflow: 'deepseek-ai/DeepSeek-V3' },
    vlm: { zhipu: 'glm-4.5v', openai: 'gpt-4o', siliconflow: 'Qwen/Qwen2.5-VL-72B-Instruct' },
    embedding: { zhipu: 'embedding-3', openai: 'text-embedding-3-large', siliconflow: 'BAAI/bge-large-zh-v1.5' },
  }
  config[feat].model = defaults[feat]?.[pid] || ''

  // LA-ROBUST: 自动设置 base_url（如果为空，或当前 base_url 是某个已知 provider 的默认值）
  const p = providers.value.find(p => p.id === pid)
  if (!p) return

  const newDefaultUrl = p.default_base_url || ''
  const currentUrl = config[feat].base_url || ''

  // 已知 provider 的默认 base_url 集合
  const knownDefaultUrls = providers.value
    .map(p => p.default_base_url)
    .filter(Boolean)

  // 如果当前 base_url 为空，或者是某个已知 provider 的默认 URL，则更新
  if (!currentUrl || knownDefaultUrls.includes(currentUrl)) {
    config[feat].base_url = newDefaultUrl
  }
  // 否则保留用户自定义的 base_url
}

function getFeatureStatus(featId) {
  if (testResults[featId].status === 'success') return 'ok'
  if (config[featId].api_key.trim()) return 'configured'
  return 'empty'
}

async function testCurrentFeature() {
  const feat = currentFeature.value
  const cfg = config[feat]

  // LA-DEPLOY-FIX: 先检查是否选择了提供商
  if (!cfg.provider) {
    testResults[feat] = { status: 'error', message: '⚠️ 请先选择上方服务商' }
    return
  }

  if (!cfg.api_key.trim()) {
    errors[feat] = '请先输入 API Key'
    testResults[feat] = { status: 'error', message: '请先输入 API Key' }
    return
  }
  errors[feat] = ''

  // 如果没有选择模型，使用默认模型
  const testCfg = { ...cfg }
  if (!testCfg.model) {
    testCfg.model = featureDefaultModel.value
  }

  testing.value = true
  testResults[feat] = { status: 'pending', message: '测试中...' }

  try {
    const resp = await fetch(`/api/setup/test/${feat}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(testCfg)
    })
    const result = await resp.json()

    if (result.success) {
      testResults[feat] = { status: 'success', message: `${result.message} (${result.latency_ms}ms)` }
    } else {
      testResults[feat] = { status: 'error', message: result.message }
    }
  } catch (e) {
    testResults[feat] = { status: 'error', message: `请求失败: ${e.message}` }
  } finally {
    testing.value = false
  }
}

function applyRecommendation(scheme) {
  if (scheme === 'zhipu_deepseek') {
    // 智谱AI 负责 vlm + embedding，DeepSeek 负责 llm，Kimi 作为备用 llm
    config.llm = { provider: 'deepseek', api_key: '', base_url: '', model: 'deepseek-chat', enabled: true, custom_model: '' }
    config.llm_fallback = { provider: 'kimi', api_key: '', base_url: '', model: 'kimi-k2.5', enabled: true, custom_model: '' }
    config.vlm = { provider: 'zhipu', api_key: '', base_url: '', model: 'glm-4.5v', enabled: true, custom_model: '' }
    config.embedding = { provider: 'zhipu', api_key: '', base_url: '', model: 'embedding-3', enabled: true, custom_model: '' }
    config.mineru = { provider: 'mineru', api_key: '', base_url: '', model: '', enabled: true, custom_model: '' }
  } else if (scheme === 'openai') {
    config.llm = { provider: 'openai', api_key: '', base_url: '', model: 'gpt-4o', enabled: true, custom_model: '' }
    config.llm_fallback = { provider: 'openai', api_key: '', base_url: '', model: 'gpt-4o-mini', enabled: true, custom_model: '' }
    config.vlm = { provider: 'openai', api_key: '', base_url: '', model: 'gpt-4o', enabled: true, custom_model: '' }
    config.embedding = { provider: 'openai', api_key: '', base_url: '', model: 'text-embedding-3-large', enabled: true, custom_model: '' }
    config.mineru = { provider: 'mineru', api_key: '', base_url: '', model: '', enabled: true, custom_model: '' }
  } else if (scheme === 'siliconflow') {
    config.llm = { provider: 'siliconflow', api_key: '', base_url: '', model: 'deepseek-ai/DeepSeek-V3', enabled: true, custom_model: '' }
    config.llm_fallback = { provider: 'siliconflow', api_key: '', base_url: '', model: 'Qwen/Qwen2.5-72B-Instruct', enabled: true, custom_model: '' }
    config.vlm = { provider: 'siliconflow', api_key: '', base_url: '', model: 'Qwen/Qwen2.5-VL-72B-Instruct', enabled: true, custom_model: '' }
    config.embedding = { provider: 'siliconflow', api_key: '', base_url: '', model: 'BAAI/bge-large-zh-v1.5', enabled: true, custom_model: '' }
    config.mineru = { provider: 'mineru', api_key: '', base_url: '', model: '', enabled: true, custom_model: '' }
  }
}

function closeWizard() {
  // LA-DEPLOY-FEAT: 支持取消/关闭向导，不保存任何更改
  showWizard.value = false
}

async function saveAndFinish() {
  saving.value = true
  try {
    const resp = await fetch('/api/setup/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    })
    const result = await resp.json()

    if (result.status === 'success') {
      emit('configured')
      showWizard.value = false
    } else {
      alert('保存失败: ' + result.message)
    }
  } catch (e) {
    alert('保存失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

// 加载提供商列表 + 已有配置（首次启动时调用）
onMounted(async () => {
  await loadProviders()
})

// LA-DEPLOY-FEAT-04: 每次打开向导时重新加载配置（解决 v-if 内层控制导致 onMounted 只执行一次的问题）
watch(showWizard, async (val) => {
  if (val) {
    await loadExistingConfig()
  }
})

async function loadProviders() {
  try {
    const resp = await fetch('/api/setup/providers')
    providers.value = await resp.json()

    // LA-DEPLOY-FIX: 当前功能默认选中第一个可用提供商
    const feat = currentFeature.value
    if (!config[feat].provider) {
      // LLM-ROBUST: llm_fallback 使用与 llm 相同的提供商列表
      const filterFeat = feat === 'llm_fallback' ? 'llm' : feat
      const available = providers.value.filter(p => p.features.includes(filterFeat) || filterFeat === 'mineru')
      if (available.length > 0) {
        selectProvider(available[0].id)
      }
    }
  } catch (e) {
    console.error('加载提供商列表失败:', e)
  }
}

async function loadExistingConfig() {
  try {
    // 检查是否有已有配置
    const statusResp = await fetch('/api/setup/status')
    const status = await statusResp.json()
    hasAnyConfig.value = Object.values(status.features_configured).some(v => v)

    // LA-DEPLOY-FEAT: 如果有已有配置，加载到表单中（支持重新配置）
    if (hasAnyConfig.value) {
      try {
        // 调用 config-raw 获取完整配置（含 API Key），用于预填充表单
        const cfgResp = await fetch('/api/setup/config-raw')
        const cfg = await cfgResp.json()
        for (const feat of features) {
          const fid = feat.id
          if (cfg[fid]) {
            config[fid].provider = cfg[fid].provider || ''
            config[fid].api_key = cfg[fid].api_key || ''  // 完整 key，密码框显示为星号
            config[fid].base_url = cfg[fid].base_url || ''
            config[fid].model = cfg[fid].model || ''
            config[fid].enabled = cfg[fid].enabled !== false
            config[fid].custom_model = cfg[fid].custom_model || ''
          }
        }
      } catch (e) {
        console.error('加载已有配置失败:', e)
      }
    }
  } catch (e) {
    console.error('检查配置状态失败:', e)
  }
}

// LA-DEPLOY-FIX: 切换功能Tab时，如果该功能没有provider，自动选中第一个
watch(currentFeature, (newFeat) => {
  if (!config[newFeat].provider) {
    // LLM-ROBUST: llm_fallback 使用与 llm 相同的提供商列表
    const feat = newFeat === 'llm_fallback' ? 'llm' : newFeat
    const available = providers.value.filter(p => p.features.includes(feat) || feat === 'mineru')
    if (available.length > 0) {
      selectProvider(available[0].id)
    }
  }
})
</script>

<style scoped>
.setup-wizard {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  overflow-y: auto;
}

.setup-container {
  position: relative;
  background: #fff;
  border-radius: 16px;
  width: 90%;
  max-width: 700px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
}

.setup-header {
  padding: 24px 32px 16px;
  text-align: center;
  border-bottom: 1px solid #eee;
}

.setup-header h1 {
  margin: 0 0 8px;
  font-size: 22px;
  color: #1a1a2e;
}

.subtitle {
  color: #666;
  margin: 0;
}

.setup-content {
  padding: 20px 32px;
  flex: 1;
  overflow-y: auto;
}

/* 功能标签页 */
.feature-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  background: white;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
  position: relative;
}

.tab-btn:hover {
  border-color: #3498db;
}

.tab-btn.active {
  border-color: #3498db;
  background: #ebf5fb;
}

.tab-btn.required {
  border-color: #e74c3c;
}

.tab-btn.required.active {
  border-color: #e74c3c;
  background: #fdeaea;
}

.required-badge {
  background: #e74c3c;
  color: white;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
}

.status-ok {
  color: #27ae60;
  font-weight: bold;
}

/* 面板 */
.feature-panel {
  background: #f8f9fa;
  border-radius: 12px;
  padding: 24px;
}

.panel-header {
  margin-bottom: 20px;
}

.panel-header h2 {
  margin: 0 0 6px;
  font-size: 18px;
}

.feature-desc {
  color: #666;
  font-size: 13px;
  margin: 0;
}

/* 表单 */
.form-group {
  margin-bottom: 18px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  font-size: 14px;
  color: #333;
}

.get-key-link {
  float: right;
  font-size: 12px;
  color: #3498db;
}

.form-group input,
.form-group select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: #3498db;
}

.form-group input.error {
  border-color: #e74c3c;
}

.hint {
  display: block;
  font-size: 12px;
  color: #888;
  margin-top: 4px;
}

.error-msg {
  display: block;
  color: #e74c3c;
  font-size: 12px;
  margin-top: 4px;
}

.required-inline {
  color: #e74c3c;
  font-size: 12px;
  margin-left: 4px;
}

/* 提供商选择 */
.provider-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}

.provider-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.provider-card:hover {
  border-color: #3498db;
}

.provider-card.selected {
  border-color: #3498db;
  background: #ebf5fb;
}

.provider-icon {
  font-size: 24px;
}

.provider-name {
  font-size: 12px;
  text-align: center;
}

/* 测试区域 */
.test-section {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #e0e0e0;
}

.test-btn {
  padding: 8px 20px;
  border: 1px solid #3498db;
  background: white;
  color: #3498db;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.test-btn:hover:not(:disabled) {
  background: #3498db;
  color: white;
}

.test-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.test-btn.success {
  border-color: #27ae60;
  color: #27ae60;
}

.test-btn.success:hover {
  background: #27ae60;
  color: white;
}

.test-btn.error {
  border-color: #e74c3c;
  color: #e74c3c;
}

.test-btn.error:hover {
  background: #e74c3c;
  color: white;
}

.test-message {
  font-size: 13px;
  color: #666;
}

/* 推荐配置 */
.recommendation {
  margin-top: 24px;
  padding: 16px;
  background: #fff3e0;
  border-radius: 8px;
}

.recommendation h3 {
  margin: 0 0 12px;
  font-size: 14px;
}

.rec-option {
  padding: 10px 12px;
  background: white;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  border: 1px solid #ffe0b2;
  transition: all 0.2s;
}

.rec-option:hover {
  border-color: #ff9800;
  box-shadow: 0 2px 8px rgba(255, 152, 0, 0.2);
}

.rec-option strong {
  display: block;
  font-size: 13px;
  margin-bottom: 2px;
}

.rec-option p {
  margin: 0;
  font-size: 12px;
  color: #666;
}

.rec-tag {
  display: inline-block;
  font-size: 11px;
  background: #ff9800;
  color: white;
  padding: 1px 6px;
  border-radius: 4px;
  margin-top: 4px;
}

/* 底部 */
.setup-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 32px 24px;
  border-top: 1px solid #eee;
}

.feature-summary {
  display: flex;
  gap: 8px;
}

.summary-dot {
  font-size: 16px;
  opacity: 0.3;
}

.summary-dot.configured {
  opacity: 0.7;
}

.summary-dot.ok {
  opacity: 1;
}

/* 右上角关闭按钮 */
.close-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 8px;
  color: #666;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #f0f0f0;
  color: #333;
}

/* 底部操作按钮 */
.footer-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.btn-secondary {
  padding: 10px 24px;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: white;
  color: #666;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover {
  border-color: #999;
  color: #333;
}

.btn-primary {
  padding: 10px 28px;
  border: none;
  border-radius: 8px;
  background: #3498db;
  color: white;
  font-size: 14px;
  cursor: pointer;
}

.btn-primary:hover:not(:disabled) {
  background: #2980b9;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
