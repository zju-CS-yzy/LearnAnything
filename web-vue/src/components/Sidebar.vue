<template>
  <aside class="sidebar" :class="{ collapsed }">
    <!-- 顶部 Logo 区域 -->
    <div class="sidebar-header">
      <div class="logo" v-show="!collapsed">
        <span class="logo-icon">🎓</span>
        <span class="logo-text">LearnAnything</span>
      </div>
      <span class="logo-icon-only" v-show="collapsed">🎓</span>
      <button class="toggle-btn btn-icon" @click="$emit('toggle-sidebar')" :title="collapsed ? '展开' : '折叠'">
        <svg v-if="!collapsed" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="15 18 9 12 15 6"></polyline>
        </svg>
        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
      </button>
    </div>

    <!-- 新建会话按钮 -->
    <button class="new-chat-btn" v-show="!collapsed" @click="$emit('switch-view', 'chat')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="5" x2="12" y2="19"></line>
        <line x1="5" y1="12" x2="19" y2="12"></line>
      </svg>
      <span>新建会话</span>
    </button>

    <!-- 导航菜单 -->
    <nav class="nav-menu">
      <div
        v-for="item in navItems"
        :key="item.id"
        class="nav-item"
        :class="{ active: activeView === item.id }"
        @click="$emit('switch-view', item.id)"
        :title="collapsed ? item.label : ''"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span class="nav-label" v-show="!collapsed">{{ item.label }}</span>
      </div>
    </nav>

    <!-- 历史会话（仅智能对话视图时显示） -->
    <div class="history-section" v-show="!collapsed && activeView === 'chat'">
      <div class="section-title">历史会话</div>
      <div class="history-list">
        <div
          v-for="session in chatSessions"
          :key="session.id"
          class="history-item"
          :class="{ active: currentSessionId === session.id }"
          @click="selectSession(session.id)"
        >
          <span class="history-icon">💬</span>
          <span class="history-text">{{ session.title }}</span>
        </div>
      </div>
    </div>

    <!-- 底部信息 -->
    <div class="sidebar-footer" v-show="!collapsed">
      <div class="footer-status">
        <span class="status-dot" :class="healthStatus"></span>
        <span class="footer-text">{{ statusText }}</span>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref } from 'vue'
import { useHealthCheck } from '../composables/useApi.js'

// Props
defineProps({
  activeView: { type: String, default: 'chat' },
  collapsed: { type: Boolean, default: false },
})

defineEmits(['switch-view', 'toggle-sidebar'])

// 导航菜单项
const navItems = [
  { id: 'chat', icon: '💬', label: '智能对话' },
  { id: 'quiz', icon: '📝', label: '出题' },
  { id: 'evaluate', icon: '📊', label: '评测' },
  { id: 'import', icon: '📚', label: '导入' },
  { id: 'knowledge', icon: '🗂️', label: '知识库' },
]

// 健康状态
const { status: healthStatus } = useHealthCheck()

const statusText = computed(() => {
  const map = { online: '后端已连接', offline: '后端未连接', connecting: '连接中...' }
  return map[healthStatus.value] || '未知'
})

// 会话历史（示例数据，实际应从 localStorage 或后端获取）
const chatSessions = ref([
  { id: '1', title: 'RAG 技术讨论' },
  { id: '2', title: 'Transformer 注意力机制' },
  { id: '3', title: '化学键基础知识' },
])
const currentSessionId = ref('1')

function selectSession(id) {
  currentSessionId.value = id
  // TODO: 加载会话历史消息
}

import { computed } from 'vue'
</script>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  height: 100%;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width var(--transition-normal);
  overflow: hidden;
}

.sidebar.collapsed {
  width: var(--sidebar-collapsed);
}

/* 顶部 Logo */
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
  height: var(--header-height);
  flex-shrink: 0;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.logo-icon {
  font-size: 20px;
}

.logo-icon-only {
  font-size: 24px;
  margin: 0 auto;
}

.toggle-btn {
  color: var(--text-secondary);
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: all var(--transition-fast);
}
.toggle-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

/* 新建会话按钮 */
.new-chat-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 12px 16px;
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}
.new-chat-btn:hover {
  background: var(--bg-hover);
  border-color: var(--accent-primary);
}

/* 导航菜单 */
.nav-menu {
  padding: 8px 12px;
  flex-shrink: 0;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  color: var(--text-secondary);
  font-size: 14px;
  margin-bottom: 2px;
  white-space: nowrap;
}
.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.nav-item.active {
  background: var(--bg-active);
  color: var(--accent-primary);
  font-weight: 500;
}

.nav-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
  flex-shrink: 0;
}

/* 历史会话 */
.history-section {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
  min-height: 0;
}

.section-title {
  padding: 8px 16px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.history-list {
  padding: 0 8px;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  color: var(--text-secondary);
  font-size: 13px;
  margin-bottom: 2px;
}
.history-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.history-item.active {
  background: var(--bg-active);
  color: var(--text-primary);
}

.history-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.history-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 底部状态 */
.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}

.footer-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.footer-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
