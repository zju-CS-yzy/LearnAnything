<template>
  <div class="app-root">
    <!-- LA-055: 登录路由守卫 -->
    <LoginGuard v-if="showLoginGuard" @success="onLoginSuccess" />

    <!-- LA-DEPLOY: 首次启动配置向导 -->
    <SetupWizard v-model="showSetupWizard" @configured="onSetupConfigured" />

    <!-- Trae 式三栏布局 -->
    <AppLayout
      ref="layoutRef"
      @open-settings="openSettings"
    />
  </div>
</template>

<script setup>
/**
 * App.vue — 应用根组件
 *
 * 职责：
 *   1. 全局初始化（登录检查、首次启动向导、学科加载）
 *   2. 提供全局状态（学科、主题、用户）
 *   3. 事件协调（用户切换、设置打开等）
 *
 * 布局已迁移到 AppLayout.vue（Trae 式三栏：Sidebar + Main + ChatView）
 */
import { ref, provide, onMounted, onUnmounted } from 'vue'
import AppLayout from './components/AppLayout.vue'
import SetupWizard from './components/SetupWizard.vue'
import LoginGuard from './components/LoginGuard.vue'

import { useSubject } from './composables/useSubject.js'
import { useTheme } from './composables/useTheme.js'
import { apiListSubjects } from './composables/useApi.js'
import { useUser } from './composables/useUser.js'

// ========== 全局状态 ==========

// 学科状态
const subjectState = useSubject()
provide('subjectState', subjectState)

// 主题状态
const themeState = useTheme()
provide('themeState', themeState)

// 用户状态
const { isAuthenticated, currentUser } = useUser()

// ========== 布局引用 ==========

const layoutRef = ref(null)

// 将学科状态传递给布局组件
onMounted(() => {
  if (layoutRef.value) {
    layoutRef.value.setSubjectState(subjectState)
  }
})

// ========== 登录守卫 ==========

const showLoginGuard = ref(false)

function onLoginSuccess() {
  showLoginGuard.value = false
}

// ========== 配置向导 ==========

const showSetupWizard = ref(false)

function onSetupConfigured() {
  console.log('[App] API 密钥配置完成')
  window.location.reload()
}

function openSettings() {
  console.log('[App] 用户打开设置向导')
  showSetupWizard.value = true
}

// ========== 学科列表加载 ==========

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

// ========== 用户切换事件 ==========

function handleUserChange(event) {
  console.log('[App] 用户切换事件:', event.detail)
  loadSubjects()
}

// ========== 生命周期 ==========

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
  window.removeEventListener('la-user-changed', handleUserChange)
})
</script>

<style scoped>
.app-root {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
}
</style>
