<template>
  <div class="chat-view">
    <!-- 顶部标题栏 -->
    <header class="chat-header">
      <div class="header-title">
        <span class="header-icon">💬</span>
        <span>智能问答</span>
      </div>
      <div class="header-subject">
        <span class="tag">{{ currentSubject }}</span>
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
              <div class="message-body markdown-body" v-html="renderMarkdown(msg.text)"></div>
              <!-- 引用来源 -->
              <div class="message-sources" v-if="msg.sources && msg.sources.length">
                <div class="sources-title">📎 引用来源</div>
                <div class="source-item" v-for="(src, i) in msg.sources" :key="i">
                  <span class="source-index">{{ i + 1 }}</span>
                  <span class="source-text">{{ src.text }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <!-- 流式输出中的光标 -->
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
        <span v-else>Shift + Enter 换行</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { marked } from 'marked'
import { apiAsk, apiAskStream } from '../composables/useApi.js'

// 消息列表
const messages = ref([])
const inputText = ref('')
const isStreaming = ref(false)
const messagesContainer = ref(null)
const inputRef = ref(null)
const currentSubject = ref('generic')

// 快速提示
const quickHints = [
  '什么是 RAG 检索增强生成？',
  'Transformer 的注意力机制是什么？',
  '如何设计优秀的提示词？',
  'LangChain 的核心组件有哪些？',
]

// Markdown 渲染
function renderMarkdown(text) {
  if (!text) return ''
  try {
    return marked.parse(text, { breaks: true })
  } catch {
    return text
  }
}

// 自动调整 textarea 高度
function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

// 键盘事件处理
function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// 发送消息
async function sendMessage(presetText = null) {
  const text = presetText || inputText.value.trim()
  if (!text || isStreaming.value) return

  // 添加用户消息
  const userMsg = {
    id: Date.now(),
    role: 'user',
    text: text,
    time: new Date().toLocaleTimeString(),
  }
  messages.value.push(userMsg)

  // 清空输入框
  if (!presetText) {
    inputText.value = ''
    nextTick(autoResize)
  }

  // 滚动到底部
  scrollToBottom()

  // 开始流式输出
  isStreaming.value = true
  const aiMsg = {
    id: Date.now() + 1,
    role: 'ai',
    text: '',
    agent: '',
    time: new Date().toLocaleTimeString(),
    sources: [],
  }
  messages.value.push(aiMsg)

  try {
    const stream = apiAskStream(text, currentSubject.value)
    for await (const { event, data } of stream) {
      if (event === 'meta') {
        aiMsg.agent = data.agent || 'TutorAgent'
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
  }
}

// 滚动到底部
function scrollToBottom() {
  nextTick(() => {
    const el = messagesContainer.value
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  })
}

onMounted(() => {
  autoResize()
})
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* 顶部标题栏 */
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
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-icon {
  font-size: 18px;
}

/* 消息区域 */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  min-height: 0;
}

/* 空状态 */
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

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.empty-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.empty-desc {
  font-size: 14px;
  color: var(--text-muted);
  margin-bottom: 32px;
}

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
  font-size: 14px;
  text-align: left;
}

.hint-item:hover {
  background: var(--bg-hover);
  border-color: var(--accent-primary);
  color: var(--text-primary);
}

/* 消息列表 */
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

.user-row {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
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

.user-row .message-bubble {
  background: var(--bg-active);
  border-color: var(--border-light);
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
}

.agent-tag {
  color: var(--accent-primary);
  font-weight: 500;
}

.time-tag {
  color: var(--text-muted);
}

/* 引用来源 */
.message-sources {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-color);
}

.sources-title {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.source-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 4px 0;
  font-size: 12px;
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
  font-size: 11px;
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

/* 输入区域 */
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
  font-size: 12px;
  color: var(--text-muted);
}

.streaming-hint {
  color: var(--accent-primary);
  animation: pulse 1.5s ease infinite;
}
</style>
