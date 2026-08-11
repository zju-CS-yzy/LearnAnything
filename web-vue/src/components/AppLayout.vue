<template>
  <div class="app-layout" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <!-- 左侧窄边栏 -->
    <Sidebar
      :active-view="activeView"
      :collapsed="sidebarCollapsed"
      @switch-view="switchView"
      @toggle-sidebar="toggleSidebar"
      @open-settings="openSettings"
    />

    <!-- 中间主内容区 -->
    <main class="main-area">
      <component :is="currentViewComponent" />
    </main>

    <!-- 右侧常驻 ChatView -->
    <aside class="chat-panel" :class="{ 'chat-collapsed': chatCollapsed }" :style="chatPanelStyle">
      <div
        class="chat-resize-handle"
        :class="{ 'is-dragging': isDragging }"
        @mousedown="onResizeMouseDown"
        title="拖动调整宽度，点击折叠/展开"
      >
        <div class="resize-grip"></div>
      </div>
      <div class="chat-content">
        <ChatView />
      </div>
    </aside>
  </div>
</template>

<script setup>
/**
 * AppLayout.vue — Trae 式三栏布局
 *
 * 布局结构：
 *   Sidebar (窄边栏) | Main (主内容区) | ChatView (右侧常驻)
 *
 * 特性：
 *   - 主内容区支持视图切换（Graph/Quiz/Evaluate/KnowledgeBase/Import/Progress）
 *   - ChatView 右侧常驻，可折叠
 *   - 学科状态通过 provide 注入，供所有子组件使用
 */
import { ref, computed, provide } from 'vue'
import Sidebar from './Sidebar.vue'
import ChatView from './ChatView.vue'

// 主内容区视图组件
import QuizView from './QuizView.vue'
import EvaluateView from './EvaluateView.vue'
import ProgressView from './ProgressView.vue'
import ImportView from './ImportView.vue'
import KnowledgeBaseView from './KnowledgeBaseView.vue'
import GraphView from './graph/GraphView.vue'
import LLMMonitorView from './LLMMonitorView.vue'
import AdminUsersView from './AdminUsersView.vue'

const emit = defineEmits(['open-settings'])

// 视图组件映射（chat 视图不再占用主区域，右侧常驻 ChatView 负责）
const viewComponents = {
  quiz: QuizView,
  evaluate: EvaluateView,
  progress: ProgressView,
  import: ImportView,
  knowledge: KnowledgeBaseView,
  graph: GraphView,
  monitor: LLMMonitorView,
  'admin-users': AdminUsersView,
}

// 状态
const activeView = ref('graph')  // 默认显示知识图谱
const sidebarCollapsed = ref(false)
const chatCollapsed = ref(false)

// 可拖动宽度配置
const chatWidth = ref(380)
const MIN_CHAT_WIDTH = 280
const MAX_CHAT_WIDTH_RATIO = 0.45  // 最大占视口宽度的 45%
const DRAG_THRESHOLD = 5           // 小于此像素视为点击而非拖动
const isDragging = ref(false)

// ChatView 面板样式（动态宽度）
const chatPanelStyle = computed(() => {
  if (chatCollapsed.value) {
    return { width: '24px' }
  }
  return { width: chatWidth.value + 'px' }
})

// 当前主内容区组件
const currentViewComponent = computed(() => viewComponents[activeView.value] || GraphView)

// 方法
function switchView(view) {
  activeView.value = view
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

function toggleChat() {
  chatCollapsed.value = !chatCollapsed.value
}

// 拖动调整 ChatView 宽度
function onResizeMouseDown(e) {
  // 如果已折叠，点击展开
  if (chatCollapsed.value) {
    toggleChat()
    return
  }

  const startX = e.clientX
  const startWidth = chatWidth.value
  let moved = false
  const maxWidth = Math.floor(window.innerWidth * MAX_CHAT_WIDTH_RATIO)

  isDragging.value = true

  function onMouseMove(e) {
    const deltaX = startX - e.clientX  // 左移为正（变宽），右移为负（变窄）
    const newWidth = startWidth + deltaX
    chatWidth.value = Math.max(MIN_CHAT_WIDTH, Math.min(maxWidth, newWidth))
    moved = Math.abs(e.clientX - startX) > DRAG_THRESHOLD
  }

  function onMouseUp(e) {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
    isDragging.value = false

    // 未发生有效拖动，视为点击 → 折叠
    if (!moved) {
      toggleChat()
    }
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
}

function openSettings() {
  emit('open-settings')
}

// 提供学科状态给子组件（App.vue 会注入）
const subjectState = ref(null)
provide('layoutSubjectState', subjectState)

// 暴露方法给父组件 App.vue
defineExpose({
  switchView,
  toggleSidebar,
  toggleChat,
  setSubjectState: (s) => { subjectState.value = s },
})
</script>

<style scoped>
.app-layout {
  display: flex;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-main, #f5f5f5);
}

/* 中间主内容区 */
.main-area {
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  background: var(--bg-main, #f5f5f5);
  transition: flex 0.3s ease;
}

/* 右侧 ChatView 面板 */
.chat-panel {
  display: flex;
  height: 100%;
  background: var(--bg-card, #ffffff);
  border-left: 1px solid var(--border-color, #e0e0e0);
  transition: width 0.2s ease;
  flex-shrink: 0;
}

.chat-panel.chat-collapsed {
  width: 24px !important;
}

.chat-resize-handle {
  width: 8px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: col-resize;
  background: transparent;
  border-right: 1px solid var(--border-color, #e0e0e0);
  user-select: none;
  transition: background 0.2s;
  position: relative;
}

.chat-resize-handle:hover {
  background: var(--bg-hover, #f0f0f0);
}

.chat-resize-handle.is-dragging {
  background: var(--accent-primary, #3b82f6);
}

.resize-grip {
  width: 3px;
  height: 48px;
  border-radius: 2px;
  background: var(--border-color, #e0e0e0);
  transition: background 0.2s;
}

.chat-resize-handle:hover .resize-grip,
.chat-resize-handle.is-dragging .resize-grip {
  background: var(--accent-primary, #3b82f6);
}

.chat-content {
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow: hidden;
}

.chat-collapsed .chat-content {
  display: none;
}

/* 侧边栏折叠时的调整 */
.app-layout.sidebar-collapsed .main-area {
  /* Sidebar 折叠后主区域自动占满 */
}

/* 暗色主题适配 */
@media (prefers-color-scheme: dark) {
  .app-layout {
    background: var(--bg-main-dark, #1a1a2e);
  }
  .main-area {
    background: var(--bg-main-dark, #1a1a2e);
  }
  .chat-panel {
    background: var(--bg-card-dark, #16213e);
    border-left-color: var(--border-color-dark, #2a2a4a);
  }
  .chat-resize-handle {
    background: var(--bg-hover-dark, #1a1a3e);
    border-right-color: var(--border-color-dark, #2a2a4a);
  }
  .chat-resize-handle:hover {
    background: var(--bg-active-dark, #202050);
  }
}
</style>
