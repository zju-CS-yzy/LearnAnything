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

    <!-- 学科选择器 -->
    <div class="subject-section" v-show="!collapsed">
      <div class="section-title">当前学科</div>
      <div class="subject-selector">
        <select v-model="selectedSubject" @change="changeSubject" class="subject-select">
          <option v-for="sub in subjectState.subjects.value" :key="sub.id" :value="sub.id">
            {{ sub.name }} ({{ sub.document_count }})
          </option>
        </select>
        <button class="btn-icon" @click="showCreateSubject = true" title="新建学科">+</button>
        <button class="btn-icon btn-delete" @click="deleteSubject" title="删除当前学科">🗑️</button>
      </div>
      <!-- 新建学科弹窗 -->
      <div v-if="showCreateSubject" class="subject-create">
        <input v-model="newSubjectId" placeholder="标识(如ai_llm)" class="subject-input" />
        <input v-model="newSubjectName" placeholder="名称(如AI大模型)" class="subject-input" />
        <input v-model="newSubjectKeywords" placeholder="关键词(逗号分隔)" class="subject-input" />
        <div class="subject-create-actions">
          <button class="btn btn-sm btn-primary" @click="createSubject">创建</button>
          <button class="btn btn-sm btn-secondary" @click="showCreateSubject = false">取消</button>
        </div>
      </div>
    </div>

    <!-- 新建会话按钮 -->
    <button class="new-chat-btn" v-show="!collapsed" @click="newChatSession">
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
      <div class="history-list" v-if="chatSessions.length">
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
      <div v-else class="history-empty">暂无历史会话</div>
    </div>

    <!-- 底部信息 -->
    <div class="sidebar-footer" v-show="!collapsed">
      <!-- 主题与字体设置 -->
      <div class="settings-section">
        <div class="setting-row">
          <span class="setting-label">🌙</span>
          <button
            class="theme-toggle-btn"
            :class="{ 'is-light': themeState.theme.value.theme === 'light' }"
            @click="themeState.toggleTheme()"
            :title="themeState.theme.value.theme === 'dark' ? '切换到亮色主题' : '切换到暗色主题'"
          >
            <span class="toggle-track">
              <span class="toggle-thumb"></span>
            </span>
          </button>
          <span class="setting-label">☀️</span>
        </div>
        <div class="setting-row">
          <span class="setting-label">🔤</span>
          <div class="font-size-selector">
            <button
              v-for="size in fontSizeOptions"
              :key="size.value"
              class="font-size-btn"
              :class="{ active: themeState.theme.value.fontSize === size.value }"
              @click="themeState.setFontSize(size.value)"
              :title="size.label"
            >
              {{ size.icon }}
            </button>
          </div>
        </div>
      </div>

      <div class="footer-status">
        <span class="status-dot" :class="healthStatus"></span>
        <span class="footer-text">{{ statusText }}</span>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, inject, watch } from 'vue'
import { useHealthCheck, apiCreateSubject, apiListSubjects, apiDeleteSubject } from '../composables/useApi.js'

const props = defineProps({
  activeView: { type: String, default: 'chat' },
  collapsed: { type: Boolean, default: false },
})

defineEmits(['switch-view', 'toggle-sidebar'])

// 全局学科状态
const subjectState = inject('subjectState')
const selectedSubject = ref(subjectState.currentSubject.value)

// 全局主题状态
const themeState = inject('themeState')

// 字体大小选项
const fontSizeOptions = [
  { value: 'small', label: '小字号', icon: 'S' },
  { value: 'medium', label: '中字号', icon: 'M' },
  { value: 'large', label: '大字号', icon: 'L' },
]

watch(() => subjectState.currentSubject.value, (val) => {
  selectedSubject.value = val
})

function changeSubject() {
  subjectState.setSubject(selectedSubject.value)
}

// 新建学科
const showCreateSubject = ref(false)
const newSubjectId = ref('')
const newSubjectName = ref('')
const newSubjectKeywords = ref('')

async function createSubject() {
  if (!newSubjectId.value.trim() || !newSubjectName.value.trim()) return
  try {
    const keywords = newSubjectKeywords.value.split(',').map(k => k.trim()).filter(Boolean)
    const result = await apiCreateSubject(
      newSubjectId.value.trim(),
      newSubjectName.value.trim(),
      '',
      keywords,
    )
    subjectState.addSubject(result)
    subjectState.setSubject(result.id)
    showCreateSubject.value = false
    newSubjectId.value = ''
    newSubjectName.value = ''
    newSubjectKeywords.value = ''
  } catch (e) {
    alert('创建学科失败: ' + e.message)
  }
}

// 删除当前学科
async function deleteSubject() {
  const subjectId = selectedSubject.value
  if (!subjectId || subjectId === 'generic') {
    alert('不能删除默认学科')
    return
  }
  const sub = subjectState.subjects.value.find(s => s.id === subjectId)
  const subName = sub?.name || subjectId
  if (!confirm(`确定要删除学科「${subName}」吗？\n\n此操作将同时删除该学科的所有知识库数据、图谱和文档，不可恢复。`)) {
    return
  }
  try {
    await apiDeleteSubject(subjectId)
    subjectState.removeSubject(subjectId)
    alert(`学科「${subName}」已删除`)
  } catch (e) {
    alert('删除学科失败: ' + e.message)
  }
}

// 导航菜单项
const navItems = [
  { id: 'chat', icon: '💬', label: '智能对话' },
  { id: 'quiz', icon: '📝', label: '出题' },
  { id: 'evaluate', icon: '📊', label: '评测' },
  { id: 'import', icon: '📚', label: '导入' },
  { id: 'knowledge', icon: '🗂️', label: '知识库' },
  { id: 'graph', icon: '🕸️', label: '知识图谱' },
]

// 健康状态
const { status: healthStatus } = useHealthCheck()

const statusText = computed(() => {
  const map = { online: '后端已连接', offline: '后端未连接', connecting: '连接中...' }
  return map[healthStatus.value] || '未知'
})

// 历史会话（LA-044: 从后端 API 获取）
const chatSessions = ref([])
const currentSessionId = ref('')

async function loadSessions() {
  try {
    const resp = await fetch(`${window.location.origin}/api/dialog/sessions?user_id=anonymous`)
    if (resp.ok) {
      const data = await resp.json()
      // 映射后端字段到前端格式
      chatSessions.value = (data.sessions || []).map(s => ({
        id: s.id,
        title: s.current_topic || `${s.subject_id || '通用'} 会话`,
        subject: s.subject_id,
        turnCount: s.turn_count,
        updatedAt: s.updated_at,
      }))
    } else {
      chatSessions.value = []
    }
  } catch (e) {
    console.error('[Sidebar] 加载会话列表失败:', e)
    chatSessions.value = []
  }
}

function selectSession(id) {
  currentSessionId.value = id
  // 通知 ChatView 加载会话
  window.dispatchEvent(new CustomEvent('load-chat-session', { detail: { sessionId: id } }))
}

// LA-044: 新建会话 — 调用 ChatView 的 createNewSession
function newChatSession() {
  // 触发全局事件，ChatView 监听并创建新会话
  window.dispatchEvent(new CustomEvent('create-new-chat-session'))
  // 刷新会话列表
  setTimeout(loadSessions, 500)
}

loadSessions()

// 监听新会话创建（本地触发）
window.addEventListener('chat-session-created', (e) => {
  loadSessions()  // LA-044: 改为从后端刷新
})
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
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.logo-icon { font-size: var(--font-size-xl); }
.logo-icon-only { font-size: var(--font-size-2xl); margin: 0 auto; }

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

/* 学科选择器 */
.subject-section {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.subject-selector {
  display: flex;
  align-items: center;
  gap: 6px;
}

.subject-select {
  flex: 1;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
}

.subject-create {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.subject-input {
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: var(--font-size-xs);
}

.subject-create-actions {
  display: flex;
  gap: 6px;
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
  font-size: var(--font-size-md);
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
  font-size: var(--font-size-md);
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
  font-size: var(--font-size-md);
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
  font-size: var(--font-size-xs);
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
  font-size: var(--font-size-sm);
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

.history-icon { font-size: var(--font-size-md); flex-shrink: 0; }

.history-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-empty {
  padding: 12px 16px;
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  text-align: center;
}

/* 底部状态 */
.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}

/* 设置区域 */
.settings-section {
  padding: 8px 0;
  border-top: 1px solid var(--border-color);
  margin-bottom: 8px;
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 4px 0;
}

.setting-label {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  flex-shrink: 0;
}

/* 主题切换按钮 */
.theme-toggle-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
}

.toggle-track {
  display: block;
  width: 40px;
  height: 20px;
  background: var(--bg-active);
  border-radius: 10px;
  position: relative;
  border: 1px solid var(--border-color);
  transition: background var(--transition-fast);
}

.toggle-thumb {
  display: block;
  width: 16px;
  height: 16px;
  background: var(--text-primary);
  border-radius: 50%;
  position: absolute;
  top: 1px;
  left: 2px;
  transition: transform var(--transition-fast), background var(--transition-fast);
}

.theme-toggle-btn.is-light .toggle-track {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
}

.theme-toggle-btn.is-light .toggle-thumb {
  transform: translateX(20px);
  background: white;
}

/* 字体大小选择器 */
.font-size-selector {
  display: flex;
  gap: 4px;
}

.font-size-btn {
  width: 28px;
  height: 28px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
  background: var(--bg-active);
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
  justify-content: center;
}

.font-size-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.font-size-btn.active {
  background: var(--accent-primary);
  color: white;
  border-color: var(--accent-primary);
}

/* 折叠时底部 */
.sidebar.collapsed .sidebar-footer {
  padding: 8px;
}

.sidebar.collapsed .settings-section,
.sidebar.collapsed .footer-status {
  display: none;
}

.footer-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.footer-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 删除学科按钮 */
.btn-delete {
  font-size: var(--font-size-sm);
  transition: all var(--transition-fast);
}
.btn-delete:hover {
  background: #dc2626;
  color: white;
  border-color: #dc2626;
}
</style>
