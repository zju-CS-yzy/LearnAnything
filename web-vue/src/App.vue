<template>
  <div class="app-container" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <!-- LA-055: 登录路由守卫 -->
    <LoginGuard v-if="showLoginGuard" @success="onLoginSuccess" />

    <!-- LA-DEPLOY: 首次启动配置向导 -->
    <SetupWizard v-model="showSetupWizard" @configured="onSetupConfigured" />

    <!-- 左侧侧边栏 -->
    <Sidebar
      :active-view="activeView"
      :collapsed="sidebarCollapsed"
      @switch-view="switchView"
      @toggle-sidebar="toggleSidebar"
      @open-settings="openSettings"
    />

    <!-- 右侧主内容区 -->
    <main class="main-content">
      <component :is="currentViewComponent" />
    </main>
  </div>
</template>

<script setup>
import { ref, computed, provide, onMounted, onUnmounted } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatView from './components/ChatView.vue'
import QuizView from './components/QuizView.vue'
import EvaluateView from './components/EvaluateView.vue'
import ProgressView from './components/ProgressView.vue'
import ImportView from './components/ImportView.vue'
import KnowledgeBaseView from './components/KnowledgeBaseView.vue'
import GraphView from './components/graph/GraphView.vue'
import SetupWizard from './components/SetupWizard.vue'
import LoginGuard from './components/LoginGuard.vue'
import { useSubject } from './composables/useSubject.js'
import { useTheme } from './composables/useTheme.js'
import { apiListSubjects } from './composables/useApi.js'
import { useUser } from './composables/useUser.js'

// 视图组件映射
const viewComponents = {
  chat: ChatView,
  quiz: QuizView,
  evaluate: EvaluateView,
  progress: ProgressView,
  import: ImportView,
  knowledge: KnowledgeBaseView,
  graph: GraphView,
}

const activeView = ref('chat')
const sidebarCollapsed = ref(false)
const currentViewComponent = computed(() => viewComponents[activeView.value] || ChatView)

// LA-055: 登录路由守卫
const { isAuthenticated, currentUser } = useUser()
const showLoginGuard = ref(false)

// LA-DEPLOY: 首次启动配置向导状态
const showSetupWizard = ref(false)

function switchView(view) {
  activeView.value = view
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

// LA-055: 登录成功回调
function onLoginSuccess() {
  showLoginGuard.value = false
}

// LA-DEPLOY: 配置完成回调
function onSetupConfigured() {
  console.log('[App] API 密钥配置完成')
  // 刷新页面以加载新配置
  window.location.reload()
}

// LA-DEPLOY-FEAT: 打开设置向导（支持重新配置）
function openSettings() {
  console.log('[App] 用户打开设置向导')
  showSetupWizard.value = true
}

// 全局学科状态
const subjectState = useSubject()
provide('subjectState', subjectState)

// 全局主题状态
const themeState = useTheme()
provide('themeState', themeState)

// LA-051-P1-FIX: 封装学科列表加载，支持事件触发重新加载
async function loadSubjects() {
  try {
    console.log('[App] 加载学科列表, 用户:', currentUser.value?.user_id)
    const result = await apiListSubjects()
    subjectState.setSubjects(result.subjects || [])
    console.log('[App] 学科列表加载完成, 数量:', result.subjects?.length || 0)
  } catch (e) {
    console.error('[App] 加载学科列表失败:', e)
  }
}

// LA-051-P1-FIX: 监听用户切换事件，重新加载学科列表
function handleUserChange(event) {
  console.log('[App] 用户切换事件:', event.detail)
  loadSubjects()
}

// 加载学科列表 + 检测首次启动 + 登录守卫
onMounted(async () => {
  // LA-055: 检查会话认证状态
  if (!isAuthenticated.value) {
    console.log('[App] LA-055: 未认证，显示登录守卫')
    showLoginGuard.value = true
  }

  // LA-DEPLOY: 检查是否为首次启动
  try {
    const resp = await fetch('/api/setup/status')
    const status = await resp.json()
    if (status.is_first_run) {
      console.log('[App] 首次启动，显示配置向导')
      showSetupWizard.value = true
    }
  } catch (e) {
    console.error('检查首次启动状态失败:', e)
  }

  // 加载学科列表
  await loadSubjects()

  // LA-051-P1-FIX: 注册用户切换事件监听
  window.addEventListener('la-user-changed', handleUserChange)
})

onUnmounted(() => {
  // LA-051-P1-FIX: 清理事件监听
  window.removeEventListener('la-user-changed', handleUserChange)
})
</script>

<style scoped>
.app-container {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  transition: background-color var(--transition-normal);
}

.main-content {
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  background: var(--bg-main);
  transition: background-color var(--transition-normal);
}
</style>
