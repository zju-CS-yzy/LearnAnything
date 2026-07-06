<template>
  <div class="app-container" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <!-- 左侧侧边栏 -->
    <Sidebar
      :active-view="activeView"
      :collapsed="sidebarCollapsed"
      @switch-view="switchView"
      @toggle-sidebar="toggleSidebar"
    />

    <!-- 右侧主内容区 -->
    <main class="main-content">
      <component :is="currentViewComponent" />
    </main>
  </div>
</template>

<script setup>
import { ref, computed, provide, onMounted } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatView from './components/ChatView.vue'
import QuizView from './components/QuizView.vue'
import EvaluateView from './components/EvaluateView.vue'
import ImportView from './components/ImportView.vue'
import KnowledgeBaseView from './components/KnowledgeBaseView.vue'
import GraphView from './components/graph/GraphView.vue'
import { useSubject } from './composables/useSubject.js'
import { useTheme } from './composables/useTheme.js'
import { apiListSubjects } from './composables/useApi.js'

// 视图组件映射
const viewComponents = {
  chat: ChatView,
  quiz: QuizView,
  evaluate: EvaluateView,
  import: ImportView,
  knowledge: KnowledgeBaseView,
  graph: GraphView,
}

const activeView = ref('chat')
const sidebarCollapsed = ref(false)
const currentViewComponent = computed(() => viewComponents[activeView.value] || ChatView)

function switchView(view) {
  activeView.value = view
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

// 全局学科状态
const subjectState = useSubject()
provide('subjectState', subjectState)

// 全局主题状态
const themeState = useTheme()
provide('themeState', themeState)

// 加载学科列表
onMounted(async () => {
  try {
    const result = await apiListSubjects()
    subjectState.setSubjects(result.subjects || [])
  } catch (e) {
    console.error('加载学科列表失败:', e)
  }
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
