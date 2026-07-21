<template>
  <div class="chat-view">
    <!-- 顶部标题栏 -->
    <header class="chat-header">
      <div class="header-title">
        <span class="header-icon">💬</span>
        <span>智能问答</span>
      </div>
      <div class="header-tags">
        <span class="tag">{{ currentSubjectName }}</span>
        <!-- LA-044: 当前话题标签 -->
        <span v-if="currentTopic" class="tag tag-topic">📌 {{ currentTopic }}</span>
      </div>
    </header>

    <!-- 消息列表区域 -->
    <div class="messages-container" ref="messagesContainer">
      <!-- 空状态提示 -->
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-icon">🎓</div>
        <div class="empty-title">LearnAnything</div>
        <div class="empty-desc">基于知识库的智能问答系统</div>
        <div class="empty-hints">
          <div class="hint-item" v-for="hint in quickHints" :key="hint" @click="sendMessage(hint)">
            {{ hint }}
          </div>
        </div>
      </div>

      <!-- 消息列表 -->
      <div v-else class="messages-list">
        <div
          v-for="msg in messages"
          :key="msg.id"
          class="message-row"
          :class="{ 'user-row': msg.role === 'user', 'ai-row': msg.role === 'ai' }"
        >
          <div class="message-avatar">
            <span v-if="msg.role === 'user'">👤</span>
            <span v-else>🎓</span>
          </div>
          <div class="message-content">
            <div class="message-bubble">
              <div class="message-meta" v-if="msg.role === 'ai' && msg.agent">
                <span class="agent-tag">{{ msg.agent }}</span>
                <span class="time-tag">{{ msg.time }}</span>
              </div>
              <!-- 消息正文：Markdown 渲染（含内联图片/公式） -->
              <div class="message-body markdown-body" v-html="renderMarkdown(msg.text)"></div>
              <!-- LA-049: 关联媒体资源（LLM 未在正文中嵌入时，在此展示） -->
              <div class="message-media" v-if="msg.media && msg.media.length">
                <div class="media-title">📷 相关图片</div>
                <div class="media-grid">
                  <div class="media-item" v-for="(m, i) in msg.media" :key="i">
                    <img
                      :src="`/api/media/${m.path}`"
                      :alt="m.caption"
                      class="media-thumb"
                      @click="openMediaModal(m)"
                    />
                    <div class="media-caption">{{ m.caption }}</div>
                  </div>
                </div>
              </div>
              <!-- 引用来源（LA-047 扩展） -->
              <div class="message-sources" v-if="msg.sources && msg.sources.length">
                <div class="sources-title">📎 引用来源</div>
                <div class="source-item" v-for="(src, i) in msg.sources" :key="i">
                  <span class="source-index">{{ i + 1 }}</span>
                  <span class="source-text">
                    <!-- 来源文件名（优先） -->
                    <span v-if="src.source" class="source-file">{{ src.source }}</span>
                    <span v-else-if="src.chunk_id" class="source-file">{{ src.chunk_id.slice(0, 40) }}...</span>
                    <span v-else class="source-file">未知来源</span>
                    <!-- 章节路径 -->
                    <span v-if="src.heading_path" class="source-detail"> | {{ src.heading_path }}</span>
                    <span v-else-if="src.chunk_id" class="source-detail"> | {{ src.chunk_id.slice(0, 30) }}</span>
                    <!-- 页码 -->
                    <span v-if="src.page_number" class="source-detail"> | 第{{ src.page_number }}页</span>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-if="isStreaming" class="message-row ai-row">
          <div class="message-avatar"><span>🎓</span></div>
          <div class="message-content">
            <div class="message-bubble">
              <span class="cursor-blink"></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部输入区域 -->
    <div class="input-area">
      <div class="input-wrapper">
        <textarea
          ref="inputRef"
          v-model="inputText"
          placeholder="输入你的问题，按 Enter 发送，Shift+Enter 换行..."
          rows="1"
          @keydown="handleKeydown"
          @input="autoResize"
        ></textarea>
        <div class="input-actions">
          <button
            class="btn btn-primary send-btn"
            :disabled="!inputText.trim() || isStreaming"
            @click="sendMessage()"
          >
            <span v-if="isStreaming" class="spinner"></span>
            <span v-else>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </span>
          </button>
        </div>
      </div>
      <div class="input-hint">
        <span v-if="isStreaming" class="streaming-hint">正在生成回答...</span>
        <span v-else>当前学科: {{ currentSubjectName }} | Shift + Enter 换行</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, inject, computed } from 'vue'
import { marked } from 'marked'
import { apiAskStream } from '../composables/useApi.js'

// 全局学科状态
const subjectState = inject('subjectState')
const currentSubject = computed(() => subjectState.currentSubject.value)
const currentSubjectName = computed(() => {
  const sub = subjectState.subjects.value.find(s => s.id === currentSubject.value)
  return sub?.name || currentSubject.value
})

// 消息列表
const messages = ref([])
const inputText = ref('')
const isStreaming = ref(false)
const messagesContainer = ref(null)
const inputRef = ref(null)

// 会话 ID（用于历史记录）
const sessionId = ref(`session_${Date.now()}`)
const sessionTitle = ref('新会话')
// LA-044: 当前话题
const currentTopic = ref('')

// 快速提示
const quickHints = [
  '什么是 RAG 检索增强生成？',
  'Transformer 的注意力机制是什么？',
  '如何设计优秀的提示词？',
  'LangChain 的核心组件有哪些？',
]

// LA-IMG: 自定义 marked renderer，处理图片路径和大小
// FIX-LA048: marked v12+ 中 renderer 方法接收对象参数 {href, title, text}
// FIX-LA049: 兼容 marked v11/v12 的 image 方法签名差异
const mediaRenderer = new marked.Renderer()
mediaRenderer.image = (href, title, text) => {
  // 兼容 marked v11 和 v12：v12 传入 token 对象，v11 传入三个参数
  if (typeof href === 'object' && href !== null) {
    const token = href
    href = token.href
    title = token.title
    text = token.text
  }
  // 确保 href 有效
  if (!href) {
    console.error('[ChatView] mediaRenderer.image: href is undefined')
    return ''
  }
  // 确保路径使用 /api/media/ 前缀
  let src = href
  if (!src.startsWith('http') && !src.startsWith('/api/media/')) {
    src = `/api/media/${src}`
  }
  // FIX-LA049: 对路径进行 URL 编码（处理中文、空格等特殊字符）
  // 使用 encodeURI 而非 encodeURIComponent，保留路径中的 /
  if (!src.startsWith('http')) {
    const prefix = '/api/media/'
    if (src.startsWith(prefix)) {
      const pathPart = src.slice(prefix.length)
      // 只编码路径中的特殊字符，保留 /
      src = prefix + pathPart.split('/').map(encodeURIComponent).join('/')
    }
  }
  return `<img src="${src}" alt="${text || ''}" title="${title || ''}" class="chat-inline-image" loading="lazy" onerror="this.style.display='none';this.parentNode.classList.add('img-error')" />`
}

function renderMarkdown(text) {
  if (!text) return ''
  try {
    // FIX-LA048: 清理 LLM 可能产生的转义字符（如 \#  -> #）
    text = text.replace(/\\#/g, '#')
    // FIX-LA048: 清理 HTML 实体编码的 heading（如 &amp;#35; -> #）
    text = text.replace(/&#35;/g, '#')
    return marked.parse(text, { 
      breaks: true, 
      renderer: mediaRenderer,
      headerIds: false,  // 禁用 heading ID 生成，避免冲突
      mangle: false,
    })
  } catch {
    return text
  }
}

// LA-IMG: 编码媒体路径（处理 Windows 反斜杠和 URL 编码）
function encodeMediaPath(path) {
  if (!path) return ''
  // 将 Windows 反斜杠替换为正斜杠
  return path.replace(/\\/g, '/')
}

// LA-049: 打开媒体大图预览
function openMediaModal(media) {
  const src = `/api/media/${media.path}`
  window.open(src, '_blank')
}

function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

async function sendMessage(presetText = null) {
  const text = presetText || inputText.value.trim()
  if (!text || isStreaming.value) return

  // 第一用户消息作为会话标题
  if (messages.value.length === 0) {
    sessionTitle.value = text.slice(0, 30)
    // 通知 Sidebar 创建新会话
    window.dispatchEvent(new CustomEvent('chat-session-created', {
      detail: { id: sessionId.value, title: sessionTitle.value }
    }))
  }

  const userMsg = {
    id: Date.now(),
    role: 'user',
    text: text,
    time: new Date().toLocaleTimeString(),
  }
  messages.value.push(userMsg)

  if (!presetText) {
    inputText.value = ''
    nextTick(autoResize)
  }
  scrollToBottom()

  isStreaming.value = true
  const aiMsg = {
    id: Date.now() + 1,
    role: 'ai',
    text: '',
    agent: '',
    time: new Date().toLocaleTimeString(),
    sources: [],
    media: [],  // LA-049: 关联媒体资源
  }
  messages.value.push(aiMsg)

  try {
    const stream = apiAskStream(text, currentSubject.value)
    for await (const { event, data } of stream) {
      if (event === 'meta') {
        aiMsg.agent = data.agent || 'TutorAgent'
        // LA-047: 保存引用来源
        if (data.sources && data.sources.length) {
          aiMsg.sources = data.sources
        }
        // LA-049: 保存媒体资源
        if (data.media && data.media.length) {
          aiMsg.media = data.media
        }
        // LA-044: 保存当前话题
        if (data.current_topic) {
          currentTopic.value = data.current_topic
        }
      } else if (event === 'chunk') {
        aiMsg.text += data.text || ''
        scrollToBottom()
      } else if (event === 'error') {
        aiMsg.text += '\n\n[错误] ' + (data.error || '未知错误')
      }
    }
  } catch (e) {
    aiMsg.text = '请求失败: ' + e.message
  } finally {
    isStreaming.value = false
    scrollToBottom()
    saveSession()
  }
}

function scrollToBottom() {
  nextTick(() => {
    const el = messagesContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function saveSession() {
  try {
    const sessions = JSON.parse(localStorage.getItem('la_chat_sessions') || '[]')
    const existing = sessions.find(s => s.id === sessionId.value)
    if (existing) {
      existing.messages = messages.value
      existing.updatedAt = Date.now()
    } else {
      sessions.unshift({
        id: sessionId.value,
        title: sessionTitle.value,
        subject: currentSubject.value,
        messages: messages.value,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      })
    }
    localStorage.setItem('la_chat_sessions', JSON.stringify(sessions))
  } catch (e) {
    console.error('保存会话失败:', e)
  }
}

// 加载历史会话（LA-044: 从后端 API 获取）
async function loadSession(id) {
  try {
    console.log('[ChatView] 加载历史会话:', id)
    
    // 从后端 API 获取历史消息
    const resp = await fetch(`${window.location.origin}/api/dialog/sessions/${id}/messages`)
    if (resp.ok) {
      const data = await resp.json()
      const historyMessages = (data.messages || []).map(m => ({
        id: Date.now() + Math.random(),
        role: m.role === 'user' ? 'user' : 'ai',
        text: m.content || '',
        agent: m.role === 'agent' ? (m.agent || 'TutorAgent') : '',
        time: m.time ? new Date(m.time).toLocaleTimeString() : new Date().toLocaleTimeString(),
        sources: m.sources || [],
        media: m.media || [],
      }))
      
      sessionId.value = id
      sessionTitle.value = '历史会话'
      messages.value = historyMessages
      console.log('[ChatView] 历史会话加载完成:', historyMessages.length, '条消息')
    } else {
      console.error('[ChatView] 加载历史会话失败:', resp.status)
      // 回退到 localStorage
      fallbackLoadFromLocal(id)
    }
  } catch (e) {
    console.error('[ChatView] 加载历史会话失败:', e)
    fallbackLoadFromLocal(id)
  }
}

// 回退：从 localStorage 加载
function fallbackLoadFromLocal(id) {
  try {
    const sessions = JSON.parse(localStorage.getItem('la_chat_sessions') || '[]')
    const session = sessions.find(s => s.id === id)
    if (session) {
      sessionId.value = session.id
      sessionTitle.value = session.title
      messages.value = session.messages || []
    }
  } catch (e) {
    console.error('从 localStorage 加载会话失败:', e)
  }
}

// LA-044: 新建会话 — 调用后端创建新 session
async function createNewSession() {
  try {
    const resp = await fetch(`${window.location.origin}/api/dialog/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: 'anonymous',
        subject_id: currentSubject.value,
      }),
    })
    if (resp.ok) {
      const data = await resp.json()
      sessionId.value = data.session_id
      sessionTitle.value = '新会话'
      currentTopic.value = ''
      messages.value = []
      console.log('[ChatView] 新建会话:', data.session_id)
      // LA-044: 通知 Sidebar 刷新会话列表
      window.dispatchEvent(new CustomEvent('chat-session-created'))
    }
  } catch (e) {
    console.error('新建会话失败:', e)
    // 回退：本地生成新 sessionId
    sessionId.value = `session_${Date.now()}`
    sessionTitle.value = '新会话'
    currentTopic.value = ''
    messages.value = []
  }
}

// 暴露给父组件/全局事件
defineExpose({ createNewSession })

onMounted(() => {
  autoResize()
  window.addEventListener('load-chat-session', (e) => {
    loadSession(e.detail.sessionId)
  })
  // LA-044: 监听新建会话事件（来自 Sidebar）
  window.addEventListener('create-new-chat-session', () => {
    createNewSession()
  })
})
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: var(--header-height);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
  background: var(--bg-main);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary);
}

.header-icon { font-size: var(--font-size-lg); }

/* LA-044: 话题标签样式 */
.header-tags {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tag-topic {
  background: var(--bg-active) !important;
  color: var(--accent-primary) !important;
  border: 1px solid var(--accent-primary);
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  min-height: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  text-align: center;
  padding: 40px;
}

.empty-icon { font-size: 64px; margin-bottom: 16px; }
.empty-title { font-size: var(--font-size-2xl); font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.empty-desc { font-size: var(--font-size-sm); color: var(--text-muted); margin-bottom: 32px; }

.empty-hints {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 400px;
}

.hint-item {
  padding: 10px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  color: var(--text-secondary);
  font-size: var(--font-size-md);
  text-align: left;
}
.hint-item:hover {
  background: var(--bg-hover);
  border-color: var(--accent-primary);
  color: var(--text-primary);
}

.messages-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 0 24px;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
}

.message-row {
  display: flex;
  gap: 12px;
}

.user-row { flex-direction: row-reverse; }

.message-avatar {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xl);
  flex-shrink: 0;
  margin-top: 4px;
}

.message-content {
  max-width: calc(100% - 60px);
  min-width: 0;
}

.message-bubble {
  padding: 12px 16px;
  border-radius: var(--radius-md);
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  word-break: break-word;
}

/* FIX-LA048: Markdown heading 样式 */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5) {
  margin: 12px 0 8px 0;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
}
.markdown-body :deep(h1) { font-size: var(--font-size-xl); }
.markdown-body :deep(h2) { font-size: var(--font-size-lg); }
.markdown-body :deep(h3) { font-size: var(--font-size-md); border-bottom: 1px solid var(--border-color); padding-bottom: 4px; }
.markdown-body :deep(h4) { font-size: var(--font-size-md); color: var(--accent-primary); }
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 8px 0;
  padding-left: 20px;
}
.markdown-body :deep(li) {
  margin: 4px 0;
  line-height: 1.6;
}
.markdown-body :deep(code) {
  background: var(--bg-active);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
  font-size: var(--font-size-sm);
}
.markdown-body :deep(pre) {
  background: var(--bg-active);
  padding: 12px;
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin: 8px 0;
}
.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}
.markdown-body :deep(strong) {
  font-weight: 600;
  color: var(--text-primary);
}
.markdown-body :deep(p) {
  margin: 6px 0;
  line-height: 1.7;
}

.user-row .message-bubble {
  background: var(--bg-active);
  border-color: var(--border-light);
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: var(--font-size-xs);
}

.agent-tag { color: var(--accent-primary); font-weight: 500; }
.time-tag { color: var(--text-muted); }

.message-sources {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-color);
}

.sources-title { font-size: var(--font-size-xs); color: var(--text-muted); margin-bottom: 6px; }

.source-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 4px 0;
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
}

.source-index {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-active);
  border-radius: 50%;
  font-size: var(--font-size-xs);
  flex-shrink: 0;
  color: var(--accent-primary);
}

.source-text {
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.source-detail {
  color: var(--text-muted);
}

/* LA-IMG: 内联图片样式（markdown 中引用的图片） */
.chat-inline-image {
  max-width: 100%;
  max-height: 300px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  margin: 8px 0;
  display: block;
}

/* LA-049: 媒体资源展示区（LLM 未在正文中引用时，在此展示） */
.message-media {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-color);
}

.media-title {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  margin-bottom: 8px;
}

.media-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}

.media-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: pointer;
  transition: transform var(--transition-fast);
}

.media-item:hover {
  transform: scale(1.03);
}

.media-thumb {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.media-caption {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  margin-top: 4px;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.input-area {
  border-top: 1px solid var(--border-color);
  padding: 12px 24px 16px;
  flex-shrink: 0;
  background: var(--bg-main);
}

.input-wrapper {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  max-width: 900px;
  margin: 0 auto;
}

.input-wrapper textarea {
  flex: 1;
  min-height: 44px;
  max-height: 200px;
  padding: 10px 14px;
  border-radius: var(--radius-lg);
  resize: none;
  overflow-y: auto;
  line-height: 1.5;
}

.input-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.send-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.input-hint {
  text-align: center;
  margin-top: 6px;
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.streaming-hint {
  color: var(--accent-primary);
  animation: pulse 1.5s ease infinite;
}
</style>
