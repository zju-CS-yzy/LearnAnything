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
import { ref, computed } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatView from './components/ChatView.vue'
import QuizView from './components/QuizView.vue'
import EvaluateView from './components/EvaluateView.vue'
import ImportView from './components/ImportView.vue'
import KnowledgeBaseView from './components/KnowledgeBaseView.vue'

// 视图组件映射（直接使用组件，不需要 shallowRef）
const viewComponents = {
  chat: ChatView,
  quiz: QuizView,
  evaluate: EvaluateView,
  import: ImportView,
  knowledge: KnowledgeBaseView,
}

// 当前激活的视图
const activeView = ref('chat')

// 计算当前视图组件
const currentViewComponent = computed(() => viewComponents[activeView.value] || ChatView)

// 侧边栏折叠状态
const sidebarCollapsed = ref(false)

// 切换视图
function switchView(view) {
  activeView.value = view
}

// 折叠/展开侧边栏
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}
</script>

<style scoped>
.app-container {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.main-content {
  flex: 1;
  min-width: 0; /* 防止 flex 子元素溢出 */
  height: 100%;
  overflow: hidden;
  background: var(--bg-main);
}

/* 侧边栏折叠时 */
.app-container.sidebar-collapsed {
  --sidebar-width: var(--sidebar-collapsed);
}
</style>
