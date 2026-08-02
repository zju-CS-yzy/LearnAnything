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
            {{ sub.visibility === 'private' ? '🔒' : sub.visibility === 'group' ? '👥' : '🌐' }}
          </option>
        </select>
        <button class="btn-icon" @click="showCreateSubject = true" title="新建学科">+</button>
        <button class="btn-icon btn-perm" v-if="canManageCurrentSubject" @click="openPermissionModal" title="权限管理">⚙️</button>
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
      <!-- LA-DEPLOY-FEAT: 设置入口，随时可重新配置 API Key -->
      <div class="nav-divider"></div>
      <div
        class="nav-item settings-item"
        @click="$emit('open-settings')"
        :title="collapsed ? settingsItem.label : ''"
      >
        <span class="nav-icon">{{ settingsItem.icon }}</span>
        <span class="nav-label" v-show="!collapsed">{{ settingsItem.label }}</span>
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
          <div class="history-content">
            <span class="history-text">{{ session.title }}</span>
            <span v-if="session.subject" class="history-subject">{{ session.subject }}</span>
          </div>
          <div class="history-actions">
            <span v-if="session.turnCount" class="history-turns">{{ session.turnCount }}轮</span>
            <button
              class="delete-btn"
              title="删除会话"
              @click.stop="deleteSession(session.id)"
            >
              🗑️
            </button>
          </div>
        </div>
      </div>
      <div v-else class="history-empty">暂无历史会话</div>
    </div>

    <!-- 底部信息 -->
    <div class="sidebar-footer" v-show="!collapsed">
      <!-- 用户切换器（LA-050-Phase5） -->
      <div class="user-section" v-if="!collapsed">
        <div class="user-current" @click="toggleUserPanel">
          <span class="user-avatar">{{ currentUserDisplay[0] || '?' }}</span>
          <div class="user-info">
            <span class="user-name">{{ currentUserDisplay }}</span>
            <span class="user-id">{{ currentUserId }}</span>
          </div>
          <span class="user-toggle">▼</span>
        </div>
        <!-- 用户面板 -->
        <div v-if="showUserPanel" class="user-panel">
          <div class="user-panel-header">切换用户</div>
          <div
            v-for="u in userList"
            :key="u.user_id"
            class="user-panel-item"
            :class="{ active: u.user_id === currentUserId }"
            @click="switchToUser(u.user_id)"
          >
            <span class="user-panel-avatar">{{ (u.display_name || u.username || '?')[0] }}</span>
            <span class="user-panel-name">{{ u.display_name || u.username }}</span>
            <span class="user-panel-id">{{ u.user_id }}</span>
          </div>
          <div class="user-panel-divider"></div>
          <!-- LA-052: 已登录用户显示登出按钮，未登录显示登录/注册 -->
          <button v-if="isLoggedIn" class="user-panel-btn" @click="doLogout">
            🚪 登出
          </button>
          <button v-else class="user-panel-btn" @click="showLoginDialog = true">
            🔐 登录 / 注册
          </button>
        </div>
      </div>

      <!-- LA-052: 登录/注册弹窗 -->
      <LoginModal
        :visible="showLoginDialog"
        @close="showLoginDialog = false"
        @success="window.location.reload()"
      />

      <!-- LA-051: 权限管理弹窗 -->
      <PermissionModal
        :visible="showPermissionModal"
        :subject-id="selectedSubject"
        :subject-name="currentSubjectName"
        :role="currentSubjectRole"
        @close="showPermissionModal = false"
        @updated="onPermissionUpdated"
      />

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
import { useUser } from '../composables/useUser.js'
import LoginModal from './LoginModal.vue'
import PermissionModal from './PermissionModal.vue'

const props = defineProps({
  activeView: { type: String, default: 'chat' },
  collapsed: { type: Boolean, default: false },
})

defineEmits(['switch-view', 'toggle-sidebar', 'open-settings'])

// ====== LA-050-Phase5 + LA-052: 用户管理 ======
const { currentUser, xUserId, isLoggedIn, loginWithPassword, register, logout, switchUser, userList, getAuthHeaders } = useUser()

const showUserPanel = ref(false)
const showLoginDialog = ref(false)
const showPermissionModal = ref(false)  // LA-051: 权限管理弹窗
const loginForm = ref({ userId: '', username: '' })

const currentUserId = computed(() => currentUser.value?.user_id || 'default')
const currentUserDisplay = computed(() => currentUser.value?.display_name || currentUser.value?.username || '本地用户')

// LA-051: 当前学科信息
const currentSubject = computed(() =>
  subjectState.subjects.value.find(s => s.id === selectedSubject.value)
)
const currentSubjectName = computed(() => currentSubject.value?.name || selectedSubject.value)
const currentSubjectRole = computed(() => currentSubject.value?.role || '')
const canManageCurrentSubject = computed(() => {
  const role = currentSubjectRole.value
  return role === 'owner' || role === 'maintainer'
})

function openPermissionModal() {
  showPermissionModal.value = true
}

function onPermissionUpdated() {
  // 权限变更后刷新学科列表
  loadSubjects()
}

async function loadSubjects() {
  try {
    const resp = await apiListSubjects()
    subjectState.setSubjects(resp.subjects || [])
  } catch (e) {
    console.error('[Sidebar] 加载学科列表失败:', e)
  }
}

function toggleUserPanel() {
  showUserPanel.value = !showUserPanel.value
}

// LA-052-A: 切换用户逻辑
// - default 用户直接切换（本地主人，无需密码）
// - 其他用户需要密码登录
async function switchToUser(userId) {
  if (userId === 'default') {
    // default 用户直接切换
    switchUser(userId)
    showUserPanel.value = false
    window.location.reload()
    return
  }

  // 其他用户：检查是否已有 token
  const list = userList.value
  const target = list.find(u => u.user_id === userId)
  if (!target) {
    console.warn('[Sidebar] 用户不在列表中:', userId)
    return
  }

  // 如果有 token 且是当前用户，直接切换
  // 否则需要重新登录
  showUserPanel.value = false
  showLoginDialog.value = true
}

async function doLogout() {
  await logout()
  showUserPanel.value = false
  window.location.reload()
}

function doLogin() {
  const userId = loginForm.value.userId.trim()
  const username = loginForm.value.username.trim() || userId
  if (!userId) {
    alert('请输入用户ID')
    return
  }
  login(userId, username)
  showLoginDialog.value = false
  loginForm.value = { userId: '', username: '' }
  window.location.reload()
}

// ====== 原有代码 ======
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
  { id: 'progress', icon: '📈', label: '学习进度' },
  { id: 'import', icon: '📚', label: '导入' },
  { id: 'knowledge', icon: '🗂️', label: '知识库' },
  { id: 'graph', icon: '🕸️', label: '知识图谱' },
]

const settingsItem = { id: 'settings', icon: '⚙️', label: '设置' }

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
    // LA-050-Phase5: 使用当前用户的 X-User-ID
    const resp = await fetch(`${window.location.origin}/api/dialog/sessions?user_id=${currentUserId.value}`, {
      headers: getAuthHeaders(),
    })
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
  // LA-051-SESSION-FIX: 移除 setTimeout(loadSessions, 500)
  // 原因：500ms 的延迟无法保证后端已完成会话创建，造成竞态条件
  // 刷新应完全由 chat-session-created 事件驱动（ChatView 创建成功后触发）
  window.dispatchEvent(new CustomEvent('create-new-chat-session'))
}

// LA-044: 删除会话
async function deleteSession(id) {
  if (!confirm('确定要删除该会话吗？此操作不可恢复。')) {
    return
  }
  try {
    const resp = await fetch(`${window.location.origin}/api/dialog/sessions/${id}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    })
    if (resp.ok) {
      console.log('[Sidebar] 会话已删除:', id)
      // 从列表中移除
      chatSessions.value = chatSessions.value.filter(s => s.id !== id)
      // 如果删除的是当前会话，清空当前会话ID
      if (currentSessionId.value === id) {
        currentSessionId.value = ''
      }
    } else {
      console.error('[Sidebar] 删除会话失败:', resp.status)
    }
  } catch (e) {
    console.error('[Sidebar] 删除会话失败:', e)
  }
}

loadSessions()

// 监听新会话创建（本地触发）
// LA-051-SESSION-FIX: 刷新后自动选中新会话
window.addEventListener('chat-session-created', async (e) => {
  await loadSessions()  // LA-044: 从后端刷新
  // 如果事件中传递了新会话 ID，自动选中它
  const newSessionId = e.detail?.sessionId
  if (newSessionId && chatSessions.value.some(s => s.id === newSessionId)) {
    currentSessionId.value = newSessionId
  }
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

/* 设置入口 */
.nav-divider {
  height: 1px;
  background: var(--border-color);
  margin: 8px 0;
}

.settings-item {
  color: var(--text-muted);
}
.settings-item:hover {
  color: var(--text-primary);
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

.history-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.history-subject {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-turns {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  flex-shrink: 0;
}

.history-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.delete-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: var(--font-size-sm);
  padding: 2px 4px;
  border-radius: 4px;
  opacity: 0;
  transition: opacity var(--transition-fast), background var(--transition-fast);
}

.history-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  background: var(--bg-active);
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

/* LA-051: 权限管理按钮 */
.btn-perm {
  font-size: var(--font-size-sm);
  transition: all var(--transition-fast);
}
.btn-perm:hover {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

/* ====== LA-050-Phase5: 用户切换器样式 ====== */
.user-section {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 8px;
}

.user-current {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.user-current:hover {
  background: var(--bg-hover);
}

.user-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--accent-primary);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-sm);
  font-weight: 600;
  flex-shrink: 0;
}

.user-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.user-name {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-id {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.user-toggle {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  transition: transform var(--transition-fast);
}

/* 用户面板 */
.user-panel {
  margin-top: 4px;
  padding: 4px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.user-panel-header {
  padding: 4px 8px;
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
}

.user-panel-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.user-panel-item:hover {
  background: var(--bg-hover);
}
.user-panel-item.active {
  background: var(--bg-active);
}

.user-panel-avatar {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--accent-primary);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xs);
  font-weight: 600;
  flex-shrink: 0;
}

.user-panel-name {
  flex: 1;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-panel-id {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  flex-shrink: 0;
}

.user-panel-divider {
  height: 1px;
  background: var(--border-color);
  margin: 4px 0;
}

.user-panel-btn {
  width: 100%;
  padding: 6px 8px;
  border: none;
  background: none;
  color: var(--accent-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  border-radius: var(--radius-sm);
  text-align: left;
  transition: background var(--transition-fast);
}
.user-panel-btn:hover {
  background: var(--bg-hover);
}

/* 登录弹窗 */
.login-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.login-dialog {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 24px;
  width: 320px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}

.login-dialog h3 {
  margin: 0 0 16px 0;
  font-size: var(--font-size-lg);
  color: var(--text-primary);
}

.login-input {
  width: 100%;
  padding: 10px 12px;
  margin-bottom: 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: var(--font-size-md);
  box-sizing: border-box;
}
.login-input:focus {
  outline: none;
  border-color: var(--accent-primary);
}

.login-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.login-btn {
  flex: 1;
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-active);
  color: var(--text-primary);
  font-size: var(--font-size-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.login-btn:hover {
  background: var(--bg-hover);
}
.login-btn.primary {
  background: var(--accent-primary);
  color: white;
  border-color: var(--accent-primary);
}
.login-btn.primary:hover {
  opacity: 0.9;
}

.login-hint {
  margin: 12px 0 0 0;
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}
</style>
