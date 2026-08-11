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

    <!-- LA-UI-001: Agent 标签栏 -->
    <div class="agent-tabs">
      <button
        v-for="tab in agentTabs"
        :key="tab.id"
        class="agent-tab"
        :class="{ active: activeAgent === tab.id, flashing: tab.flashing }"
        @click="switchAgent(tab.id)"
        :title="tab.description"
      >
        <span class="tab-icon">{{ tab.icon }}</span>
        <span class="tab-label">{{ tab.label }}</span>
      </button>
    </div>

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
              <!-- LA-LOADING: 等待时显示占位内容 -->
              <div v-if="msg.text" class="message-body markdown-body" v-html="renderMarkdown(msg.text)"></div>
              <div v-else-if="msg.role === 'ai' && isStreaming && msg === lastAiMessage" class="message-body loading-placeholder">
                <span class="loading-text">正在思考中</span>
                <span class="loading-dots">
                  <span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
                </span>
              </div>
              <!-- LA-UI-001 M1/M2: 卡片消息分发（按 msg.type） -->
              <QuestionCard
                v-if="msg.type === 'question_card' && msg.questions && msg.questions.length"
                :questions="msg.questions"
                :subject="currentSubject"
                :topic="msg.topic || currentTopic"
                :mode="msg.mode || 'quiz'"
                :eval-session-id="msg.evalSessionId || ''"
                :dialog-session-id="sessionId"
                @eval-result="handleEvalResult"
              />
              <ConceptCard
                v-else-if="msg.type === 'concept_card'"
                :title="msg.title || ''"
                :preview="msg.preview || ''"
                :concept-type="msg.conceptType || ''"
                :actions="msg.actions || []"
                @action="handleCardAction(msg, $event)"
              />
              <ResultCard
                v-else-if="msg.type === 'result_card' && msg.result"
                :result="msg.result"
                :topic="msg.topic || ''"
              />
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
      <!-- 打字机光标：只在有实际内容输出时显示，不在"正在思考中"时显示 -->
        <div v-if="isStreaming && lastAiMessage && lastAiMessage.text" class="message-row ai-row">
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
      <!-- LA-UI-001: @命令选择浮层 -->
      <div v-if="atDropdownVisible" class="at-dropdown" :style="atDropdownStyle">
        <div
          v-for="(agent, idx) in atAgentOptions"
          :key="agent.id"
          class="at-option"
          :class="{ selected: atSelectedIndex === idx }"
          @click="selectAtAgent(agent.id)"
          @mouseenter="atSelectedIndex = idx"
        >
          <span class="at-option-icon">{{ agent.icon }}</span>
          <span class="at-option-label">{{ agent.label }}</span>
          <span class="at-option-alias">@{{ agent.id }}</span>
        </div>
      </div>
      <!-- LA-UI-001 M2: Coach 测评模式选择浮层（@coach 后弹出） -->
      <div v-if="evalModeDropdownVisible" class="at-dropdown eval-mode-dropdown">
        <div class="eval-mode-title">选择测评模式</div>
        <div
          v-for="mode in evalModeOptions"
          :key="mode.id"
          class="at-option"
          :class="{ selected: evalMode === mode.id }"
          @click="selectEvalMode(mode.id)"
        >
          <span class="at-option-icon">{{ mode.icon }}</span>
          <span class="at-option-label">{{ mode.label }}</span>
          <span class="at-option-alias">{{ mode.desc }}</span>
        </div>
      </div>
      <!-- LA-UI-001: 输入框高亮显示层 -->
      <div class="input-highlight-wrapper">
        <div v-if="highlightedInput" class="input-highlight" v-html="highlightedInput"></div>
        <div class="input-wrapper">
          <textarea
            ref="inputRef"
            v-model="inputText"
            placeholder="输入你的问题，按 Enter 发送，Shift+Enter 换行... 输入 @ 选择 Agent"
            rows="1"
            @keydown="handleKeydown"
            @input="handleInput"
            @blur="hideAtDropdown"
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
      </div>
      <div class="input-hint">
        <span v-if="isStreaming" class="streaming-hint">正在生成回答...</span>
        <span v-else-if="activeAgent !== 'auto'" class="agent-hint">
          💡 当前默认 Agent: <strong>{{ getAgentLabel(activeAgent) }}</strong>
          <!-- LA-UI-001 M2: Coach 测评模式指示 chip（点击可重新选择） -->
          <span v-if="coachTargeted" class="eval-mode-chip" @click="toggleEvalModeDropdown">
            {{ currentEvalModeLabel }} ▾
          </span>
          <span class="hint-sep">|</span>
          当前学科: {{ currentSubjectName }}
        </span>
        <span v-else>
          <!-- LA-UI-001 M2: 输入框 @coach 时也显示测评模式 chip -->
          <span v-if="coachTargeted" class="eval-mode-chip" @click="toggleEvalModeDropdown">
            {{ currentEvalModeLabel }} ▾
          </span>
          当前学科: {{ currentSubjectName }} | 输入 @ 选择 Agent
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, inject, computed } from 'vue'
import { marked } from 'marked'
// LA-UI-001: 使用新的统一入口 API
import { apiChatSendStream, apiChatShare } from '../composables/useApi.js'
import { executeCommand } from '../utils/commandExecutor.js'
import { useUser } from '../composables/useUser.js'
import { withMediaAuth } from '../utils/media.js'
// LA-UI-001 M1: 卡片消息组件
import QuestionCard from './chat/QuestionCard.vue'
import ConceptCard from './chat/ConceptCard.vue'
import ResultCard from './chat/ResultCard.vue'

// LA-050-Phase5: 当前用户（用于对话用户隔离）
const { currentUser, getAuthHeaders } = useUser()
const currentUserId = computed(() => currentUser.value?.user_id || 'anonymous')

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

// LA-LOADING: 获取最后一条 AI 消息（用于显示"正在思考中"占位符）
const lastAiMessage = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].role === 'ai') {
      return messages.value[i]
    }
  }
  return null
})

// 会话 ID（用于历史记录）— LA-051-SESSION-FIX: 初始为空，让后端分配
const sessionId = ref('')
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

// ========== LA-UI-001: Agent 标签栏数据 ==========

// Agent 标签定义
const agentTabs = [
  { id: 'auto', label: '自动', icon: '✨', description: '自动识别意图', flashing: false },
  { id: 'tutor', label: 'Tutor', icon: '🎓', description: '讲解知识、回答问题', flashing: false },
  { id: 'quiz', label: 'Quiz', icon: '📝', description: '出题、解析题目', flashing: false },
  { id: 'coach', label: 'Coach', icon: '📊', description: '能力评测、画像分析', flashing: false },
]

// 当前默认 Agent（'auto' 表示由 IntentClassifier 自动识别）
const activeAgent = ref('auto')

// 获取 Agent 显示标签
function getAgentLabel(agentId) {
  const tab = agentTabs.find(t => t.id === agentId)
  return tab ? tab.label : agentId
}

// LA-UI-001 M1: 卡片动作按钮 → 自动发送对应 @ 命令（设计文档 §3.3）
function handleCardAction(msg, act) {
  const title = msg.title || msg.topic || ''
  const actionMap = {
    ask_tutor: `@tutor 请详细解释「${title}」`,
    ask_quiz: `@quiz 请围绕「${title}」出 3 道题`,
    ask_evaluate: `@coach 评测一下我对「${title}」的掌握`,
  }
  const text = actionMap[act?.action]
  if (text) {
    sendMessage(text)
  }
}

// LA-UI-001 M2: 群聊测评提交完成 → 追加 ResultCard 结果卡片消息
function handleEvalResult(result) {
  messages.value.push({
    id: Date.now() + Math.random(),
    role: 'ai',
    type: 'result_card',
    agent: 'CoachAgent',
    text: '',
    time: new Date().toLocaleTimeString(),
    result: result,
    topic: currentTopic.value || '',
    sources: [],
    media: [],
  })
  scrollToBottom()
  saveSession()
}

// LA-UI-001 M3: 概念卡默认动作（设计文档 §3.3）
function defaultConceptActions() {
  return [
    { label: '详细解释', action: 'ask_tutor' },
    { label: '相关题目', action: 'ask_quiz' },
    { label: '能力评测', action: 'ask_evaluate' },
  ]
}

// LA-UI-001 M3: 处理左→右分享（图谱节点等 → 群聊概念卡 + 持久化）
async function handleShareToChat(detail) {
  if (!detail.title) return
  messages.value.push({
    id: Date.now() + Math.random(),
    role: 'user',
    type: 'concept_card',
    text: '',
    title: detail.title,
    preview: detail.preview || '',
    conceptType: detail.conceptType || '',
    actions: detail.actions || defaultConceptActions(),
    time: new Date().toLocaleTimeString(),
  })
  scrollToBottom()
  saveSession()

  // 持久化到对话历史（失败不阻塞本地展示）
  try {
    const res = await apiChatShare({
      session_id: sessionId.value || null,
      subject: currentSubject.value,
      card_type: 'concept',
      title: detail.title,
      preview: detail.preview || '',
      data: detail.data || {},
      source_view: detail.sourceView || 'graph',
    })
    // 采纳后端分配的 session_id（与 chat 流行为一致）
    if (res.session_id && res.session_id !== sessionId.value) {
      const oldSessionId = sessionId.value
      sessionId.value = res.session_id
      if (!oldSessionId || oldSessionId.startsWith('session_')) {
        window.dispatchEvent(new CustomEvent('chat-session-created', {
          detail: { sessionId: res.session_id }
        }))
      }
      saveSession()
    }
  } catch (e) {
    console.warn('[ChatView] 分享持久化失败（仅本地展示）:', e)
  }
}

// 切换默认 Agent
function switchAgent(agentId) {
  activeAgent.value = agentId
  // 如果输入框为空，自动添加 @agent 前缀
  const text = inputText.value.trim()
  if (!text) {
    if (agentId !== 'auto') {
      inputText.value = `@${agentId} `
    } else {
      inputText.value = ''
    }
    nextTick(() => {
      inputRef.value?.focus()
      autoResize()
    })
  }
  // LA-UI-001 M2: 切换到 Coach 时弹出测评模式选择浮层
  evalModeDropdownVisible.value = (agentId === 'coach')
  console.log('[ChatView] LA-UI-001: 切换默认 Agent ->', agentId)
}

// ========== LA-UI-001: @命令解析数据 ==========

/**
 * 获取 textarea 中光标的像素坐标（相对于 textarea 自身）。
 * LA-UI-001-FIX: 使用 fixed 定位的镜像元素，确保坐标系和 textarea 完全对齐。
 */
function getCaretCoordinates(textarea, position) {
  const div = document.createElement('div')
  const style = getComputedStyle(textarea)

  // 复制 textarea 的关键样式
  const properties = [
    'fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'letterSpacing',
    'textTransform', 'wordSpacing', 'lineHeight', 'textIndent',
    'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
    'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
    'boxSizing', 'width', 'height',
  ]
  properties.forEach(p => {
    div.style[p] = style[p]
  })

  // LA-UI-001-FIX: 关键修复 — 将镜像 div 固定在 textarea 的精确视口位置
  // 这样 markerRect 和 textareaRect 使用同一坐标系，差值就是相对坐标
  const textareaRect = textarea.getBoundingClientRect()
  div.style.position = 'fixed'
  div.style.top = `${textareaRect.top}px`
  div.style.left = `${textareaRect.left}px`
  div.style.visibility = 'hidden'
  div.style.whiteSpace = 'pre-wrap'
  div.style.wordWrap = 'break-word'
  div.style.overflow = 'hidden'
  div.style.zIndex = '-1000'

  // 同步滚动偏移
  div.scrollTop = textarea.scrollTop
  div.scrollLeft = textarea.scrollLeft

  // 构建内容
  const text = textarea.value
  const beforeCaret = text.slice(0, position)
  const afterCaret = text.slice(position)

  const escapeHtml = (s) => s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
    .replace(/ /g, '&nbsp;')

  div.innerHTML = escapeHtml(beforeCaret) + '<span id="_caret_marker_">|</span>' + escapeHtml(afterCaret)

  document.body.appendChild(div)

  try {
    const marker = div.querySelector('#_caret_marker_')
    if (!marker) {
      throw new Error('Caret marker not found in mirror div')
    }

    const markerRect = marker.getBoundingClientRect()

    // 相对于 textarea 左上角的坐标（已自然包含 padding/border 影响）
    return {
      x: markerRect.left - textareaRect.left,
      y: markerRect.top - textareaRect.top,
    }
  } finally {
    document.body.removeChild(div)
  }
}

// @命令选择浮层
const atDropdownVisible = ref(false)
const atSelectedIndex = ref(0)
const atDropdownStyle = ref({})

// Agent 选项（排除 auto）
const atAgentOptions = computed(() => agentTabs.filter(t => t.id !== 'auto'))

// 输入框高亮显示（将 @agent 部分着色）
const highlightedInput = computed(() => {
  const text = inputText.value
  if (!text) return ''
  // 匹配 @tutor、@quiz、@coach（含可选 <测评模式> 标签）
  return text.replace(
    /@(tutor|quiz|coach)(<[^>]+>)?/g,
    '<span class="at-highlight">@$1$2</span>'
  )
})

// 处理输入（@命令检测）
function handleInput(e) {
  autoResize()
  detectAtCommand()
}

// 检测 @命令并弹出选择浮层
function detectAtCommand() {
  const text = inputText.value
  const cursorPos = inputRef.value?.selectionStart || text.length

  // LA-UI-001-DEBUG: 调试日志
  console.log('[ChatView] detectAtCommand:', { text: text.slice(0, 20), cursorPos })

  // 获取光标前的文本
  const beforeCursor = text.slice(0, cursorPos)

  // 匹配 @ 后紧跟的字符（或刚输入 @）
  const atMatch = beforeCursor.match(/@([a-zA-Z_]*)$/)

  // LA-UI-001-DEBUG: 调试日志
  console.log('[ChatView] atMatch:', atMatch)

  if (atMatch) {
    const query = atMatch[1].toLowerCase()
    // 过滤匹配的 Agent
    const matches = atAgentOptions.value.filter(a =>
      a.id.startsWith(query) || a.label.toLowerCase().startsWith(query)
    )

    // LA-UI-001-DEBUG: 调试日志
    console.log('[ChatView] matches:', matches.length, matches.map(m => m.id))

    if (matches.length > 0) {
      atDropdownVisible.value = true
      atSelectedIndex.value = 0

      // LA-UI-001-FIX: 先设置默认定位（输入框上方左对齐，确保弹窗一定可见）
      atDropdownStyle.value = {
        position: 'absolute',
        left: '12px',
        bottom: 'calc(100% + 8px)',
      }

      // 再尝试精确光标跟随定位（异步，不影响弹窗可见性）
      nextTick(() => {
        try {
          const textarea = inputRef.value
          if (!textarea) return

          const coords = getCaretCoordinates(textarea, cursorPos)
          const maxLeft = Math.max(12, Math.min(coords.x, textarea.clientWidth - 160))

          // 更新 left，使弹窗水平方向靠近光标（bottom 保持默认）
          atDropdownStyle.value = {
            position: 'absolute',
            left: `${maxLeft}px`,
            bottom: 'calc(100% + 8px)',
          }
          console.log('[ChatView] 弹窗定位:', atDropdownStyle.value)
        } catch (e) {
          console.warn('[ChatView] 光标跟随定位失败，使用默认位置:', e)
          // 保持默认定位，弹窗仍然可见
        }
      })
    } else {
      atDropdownVisible.value = false
    }
  } else {
    atDropdownVisible.value = false
  }
}

// 选择 @Agent
function selectAtAgent(agentId) {
  const text = inputText.value
  const cursorPos = inputRef.value?.selectionStart || text.length
  const beforeCursor = text.slice(0, cursorPos)

  // 替换 @xxx 为 @agentId
  const newBefore = beforeCursor.replace(/@[a-zA-Z_]*$/, `@${agentId} `)
  const afterCursor = text.slice(cursorPos)
  inputText.value = newBefore + afterCursor

  atDropdownVisible.value = false
  // LA-UI-001-FIX: @弹窗选择不修改 activeAgent，仅影响当前消息输入框
  // activeAgent 只由标签栏点击（switchAgent）控制

  // LA-UI-001 M2: @coach 后弹出测评模式选择浮层
  if (agentId === 'coach') {
    evalModeDropdownVisible.value = true
  }

  nextTick(() => {
    inputRef.value?.focus()
    autoResize()
  })
}

// ========== LA-UI-001 M2: Coach 测评模式选择 ==========

const evalModeOptions = [
  { id: 'generate', label: '出新题', icon: '✨', desc: 'LLM 实时生成新题目' },
  { id: 'bank', label: '题库抽题', icon: '📚', desc: '从已确认题库随机抽取' },
  { id: 'mixed', label: '混合模式', icon: '🔀', desc: '一半题库 + 一半新题' },
]
const evalMode = ref('generate')
const evalModeDropdownVisible = ref(false)

// 当前输入是否以 Coach 为目标（@coach 前缀或标签栏选中 Coach）
const coachTargeted = computed(() =>
  activeAgent.value === 'coach' || /^@coach\b/i.test(inputText.value)
)

const currentEvalModeLabel = computed(() => {
  const m = evalModeOptions.find(x => x.id === evalMode.value)
  return m ? `测评模式: ${m.label}` : '测评模式'
})

function selectEvalMode(modeId) {
  evalMode.value = modeId
  evalModeDropdownVisible.value = false
  // LA-UI-001 M2: 将测评模式写入输入框 @coach<模式> 前缀，作为可见的选择记录
  const modeLabel = evalModeOptions.find(x => x.id === modeId)?.label || ''
  if (modeLabel) {
    const prefixMatch = inputText.value.match(/^@coach(?:<[^>]*>)?\s*/i)
    if (prefixMatch) {
      inputText.value = `@coach<${modeLabel}> ` + inputText.value.slice(prefixMatch[0].length)
    } else if (activeAgent.value === 'coach') {
      // 标签栏选中的 Coach：输入框无 @coach 前缀时补上
      inputText.value = `@coach<${modeLabel}> ` + inputText.value
    }
    nextTick(autoResize)
  }
  nextTick(() => inputRef.value?.focus())
}

function toggleEvalModeDropdown() {
  evalModeDropdownVisible.value = !evalModeDropdownVisible.value
}

// 隐藏 @浮层
function hideAtDropdown() {
  // 延迟隐藏，避免点击选项时已经消失
  setTimeout(() => {
    atDropdownVisible.value = false
  }, 150)
}

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
  return `<img src="${withMediaAuth(src)}" alt="${text || ''}" title="${title || ''}" class="chat-inline-image" loading="lazy" onerror="this.style.display='none';this.parentNode.classList.add('img-error')" />`
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
// LA-MEDIA-UNIFY: 优先使用后端已解析的统一 URL
function openMediaModal(media) {
  let src
  if (media.url) {
    src = media.url.startsWith('http') ? media.url : media.url
  } else {
    src = `/api/media/${media.path}`
  }
  window.open(withMediaAuth(src), '_blank')
}

function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

function handleKeydown(e) {
  // LA-UI-001: @浮层显示时的键盘导航
  if (atDropdownVisible.value) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      atSelectedIndex.value = (atSelectedIndex.value + 1) % atAgentOptions.value.length
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      atSelectedIndex.value = (atSelectedIndex.value - 1 + atAgentOptions.value.length) % atAgentOptions.value.length
      return
    }
    if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault()
      const selected = atAgentOptions.value[atSelectedIndex.value]
      if (selected) {
        selectAtAgent(selected.id)
      }
      return
    }
    if (e.key === 'Escape') {
      atDropdownVisible.value = false
      return
    }
  }

  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// LA-044: 用户 theta 状态（从 UserStateStore 获取）
const userTheta = ref(null)

// LA-044: 从后端获取用户 theta
async function loadUserTheta() {
  try {
    const resp = await fetch(`${window.location.origin}/api/user-state`, {
      headers: getAuthHeaders(),
    })
    if (resp.ok) {
      const data = await resp.json()
      const theta = data?.state?.profile?.global_theta
      if (theta !== undefined && theta !== null) {
        userTheta.value = theta
        console.log('[ChatView] LA-044: 加载用户 theta:', theta)
      } else {
        console.log('[ChatView] LA-044: 用户 theta 未设置')
      }
    }
  } catch (e) {
    console.error('[ChatView] LA-044: 加载 theta 失败:', e)
  }
}

async function sendMessage(presetText = null) {
  const rawText = presetText || inputText.value
  const text = rawText.trim()
  if (!text || isStreaming.value) return

  // LA-044: 如果 theta 未加载，尝试加载
  if (userTheta.value === null) {
    await loadUserTheta()
  }

  // LA-UI-001: 从输入中提取 @命令，确定 agent_target
  let agentTarget = null
  let actualText = text
  // LA-UI-001 M2: 测评模式标签（@coach<混合模式> 中的显式记录）
  let evalModeFromTag = null

  // 检查输入中是否有显式的 @agent（支持可选 <测评模式> 标签）
  // LA-UI-001-FIX: @命令只影响当前消息，不修改 activeAgent（避免锁定）
  const atMatch = text.match(/^@(tutor|quiz|coach)(?:<([^>]+)>)?\s+(.+)$/i)
  if (atMatch) {
    agentTarget = atMatch[1].toLowerCase()
    actualText = atMatch[3]
    // 解析 <测评模式> 标签 → eval_mode id
    if (atMatch[2]) {
      const modeOpt = evalModeOptions.find(m => m.label === atMatch[2].trim())
      if (modeOpt) {
        evalModeFromTag = modeOpt.id
        evalMode.value = modeOpt.id  // 同步 chip 显示
      }
    }
    // NOTE: 不修改 activeAgent，@命令是临时覆盖，不是永久切换
  } else if (activeAgent.value !== 'auto') {
    // 用户通过标签栏显式选择了默认 Agent
    agentTarget = activeAgent.value
  }
  // 如果都没有，agentTarget = null → 后端 IntentClassifier 自动识别

  console.log('[ChatView] LA-UI-001: sendMessage agent_target=', agentTarget,
              'activeAgent=', activeAgent.value, 'text=', actualText.slice(0, 40))

  // 第一用户消息作为会话标题
  const isFirstMessage = messages.value.length === 0
  if (isFirstMessage) {
    sessionTitle.value = text.slice(0, 30)
    // LA-060-FIX: 新对话开始时立即通知 Sidebar 刷新历史列表
    window.dispatchEvent(new CustomEvent('chat-session-started', {
      detail: {
        tempId: `temp_${Date.now()}`,
        title: sessionTitle.value,
        subject: currentSubject.value,
        timestamp: Date.now(),
      }
    }))
  }

  const userMsg = {
    id: Date.now(),
    role: 'user',
    type: 'text',  // LA-UI-001 M1: 消息类型（text/question_card/concept_card/result_card）
    text: text,
    time: new Date().toLocaleTimeString(),
  }
  messages.value.push(userMsg)

  if (!presetText) {
    inputText.value = ''
    atDropdownVisible.value = false
    evalModeDropdownVisible.value = false
    nextTick(autoResize)
  }
  scrollToBottom()

  isStreaming.value = true
  const aiMsg = {
    id: Date.now() + 1,
    role: 'ai',
    type: 'text',  // LA-UI-001 M1: 消息类型，含 questions 时改为 question_card
    text: '',
    agent: '',
    time: new Date().toLocaleTimeString(),
    sources: [],
    media: [],
    questions: null,
    topic: '',
  }
  messages.value.push(aiMsg)

  try {
    // LA-UI-001: 使用新的统一入口 API
    const stream = apiChatSendStream(actualText, currentSubject.value, {
      user_id: currentUserId.value,
      session_id: sessionId.value,
      agent_target: agentTarget,
      user_theta: userTheta.value,
      // LA-UI-001 M2: Coach 测评模式（仅 Coach 目标时传递；<模式> 标签优先于 chip 状态）
      eval_mode: agentTarget === 'coach' ? (evalModeFromTag || evalMode.value) : null,
    })

    for await (const { event, data } of stream) {
      if (event === 'meta') {
        aiMsg.agent = data.agent || 'TutorAgent'

        // LA-050-HISTORY-FIX: 更新 session_id
        if (data.session_id && data.session_id !== sessionId.value) {
          const oldSessionId = sessionId.value
          sessionId.value = data.session_id
          if (!oldSessionId || oldSessionId.startsWith('session_')) {
            window.dispatchEvent(new CustomEvent('chat-session-created', {
              detail: { sessionId: data.session_id }
            }))
          }
        }

        // LA-047: 保存引用来源
        const sources = data.sources || data.metadata?.sources || []
        if (sources.length) {
          aiMsg.sources = sources
        }

        // LA-049: 保存媒体资源
        const media = data.media || data.metadata?.media || []
        if (media.length) {
          aiMsg.media = media
        }

        // LA-044: 保存当前话题
        if (data.current_topic) {
          currentTopic.value = data.current_topic
        }

        // LA-UI-001 M1/M2: 单Agent卡片 — meta 携带 questions 时切换卡片渲染；
        // card_mode='evaluate' 时为测评作答卡（M2），否则为测验题卡（M1）
        if (!data.multi_agent && data.questions && data.questions.length) {
          aiMsg.type = 'question_card'
          aiMsg.questions = data.questions
          aiMsg.topic = data.topic || ''
          if (data.card_mode === 'evaluate' && data.eval_session_id) {
            aiMsg.mode = 'evaluate'
            aiMsg.evalSessionId = data.eval_session_id
          }
        }

        // LA-UI-001: 多 Agent 消息渲染
        if (data.multi_agent && data.agent_tasks && data.agent_tasks.length > 1) {
          console.log('[ChatView] LA-UI-001: 多Agent回答，渲染', data.agent_tasks.length, '条消息')
          const tasks = data.agent_tasks
          // 第一个Agent的结果填充到已创建的 aiMsg
          if (tasks[0]) {
            aiMsg.agent = tasks[0].agent
            aiMsg.text = tasks[0].text || ''
            const meta0 = tasks[0].metadata || {}
            if (meta0.questions && meta0.questions.length) {
              aiMsg.type = 'question_card'
              aiMsg.questions = meta0.questions
              aiMsg.topic = meta0.topic || ''
              // LA-UI-001 M2: 多Agent中的 Coach 测评卡
              if (meta0.card_mode === 'evaluate' && meta0.eval_session_id) {
                aiMsg.mode = 'evaluate'
                aiMsg.evalSessionId = meta0.eval_session_id
              }
            }
            // 顶层 media/sources 属于最后一个Agent的结果，第一个Agent应使用自己的
            aiMsg.sources = meta0.sources || []
            aiMsg.media = meta0.media || []
          }
          // 其余Agent的结果作为新消息追加
          // 注意: role 必须是 'ai'(模板按 role === 'ai' 判定AI消息),且需要 id 作为 :key
          for (let i = 1; i < tasks.length; i++) {
            const task = tasks[i]
            const taskMeta = task.metadata || {}
            const hasQuestions = !!(taskMeta.questions && taskMeta.questions.length)
            // LA-UI-001 M2: 多Agent中的 Coach 测评卡
            const isEvalCard = hasQuestions && taskMeta.card_mode === 'evaluate' && !!taskMeta.eval_session_id
            messages.value.push({
              id: Date.now() + 1 + i,
              role: 'ai',
              type: hasQuestions ? 'question_card' : 'text',
              agent: task.agent,
              text: task.text || '',
              time: new Date().toLocaleTimeString(),
              questions: taskMeta.questions || null,
              topic: taskMeta.topic || '',
              mode: isEvalCard ? 'evaluate' : 'quiz',
              evalSessionId: isEvalCard ? taskMeta.eval_session_id : '',
              sources: taskMeta.sources || [],
              media: taskMeta.media || [],
            })
            console.log('[ChatView] LA-UI-001: 追加Agent消息', task.agent, (task.text || '').slice(0, 50))
          }
          scrollToBottom()
        }
      } else if (event === 'chunk') {
        aiMsg.text += data.text || ''
        scrollToBottom()
      } else if (event === 'command') {
        // LA-UI-001 M4: Agent 返回的视图命令 → CommandExecutor 驱动左侧视图
        executeCommand(data)
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
  // LA-051-SESSION-FIX: 如果 sessionId 为空，不保存到 localStorage
  if (!sessionId.value) {
    console.log('[ChatView] saveSession: sessionId 为空，跳过 localStorage 保存')
    return
  }
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
    const resp = await fetch(`${window.location.origin}/api/dialog/sessions/${id}/messages`, {
      headers: getAuthHeaders(),
    })
    if (resp.ok) {
      const data = await resp.json()
      const historyMessages = (data.messages || []).map(m => {
        // LA-UI-001 M3: 分享消息恢复为概念卡（动作按钮重建，不持久化 actions）
        if (m.card && m.card.card_type) {
          return {
            id: Date.now() + Math.random(),
            role: m.role === 'user' ? 'user' : 'ai',
            type: 'concept_card',
            text: '',
            title: m.card.title || '',
            preview: m.card.preview || '',
            conceptType: (m.card.data || {}).concept_type || '',
            actions: defaultConceptActions(),
            time: m.time ? new Date(m.time).toLocaleTimeString() : new Date().toLocaleTimeString(),
            sources: m.sources || [],
            media: m.media || [],
          }
        }
        // LA-UI-001 M2: 评测结果消息恢复为 ResultCard
        if (m.eval_result) {
          return {
            id: Date.now() + Math.random(),
            role: 'ai',
            type: 'result_card',
            agent: m.agent || 'CoachAgent',
            text: '',
            time: m.time ? new Date(m.time).toLocaleTimeString() : new Date().toLocaleTimeString(),
            result: m.eval_result,
            topic: m.topic || '',
            sources: m.sources || [],
            media: m.media || [],
          }
        }
        // LA-UI-001 M1: 含 questions 的历史消息恢复为题卡渲染；
        // DB content 保留完整题目文本（供 LLM 对话历史），展示层用引导语 + 卡片
        const questions = m.questions || null
        const hasCard = !!(questions && questions.length)
        const topic = m.topic || ''
        // LA-UI-001 M2: CoachAgent 的题卡恢复为测评卡（只读回顾——测评会话有 TTL，过期不可再提交）
        const isCoachCard = hasCard && (m.agent === 'CoachAgent' || m.intent === 'evaluate')
        return {
          id: Date.now() + Math.random(),
          role: m.role === 'user' ? 'user' : 'ai',
          type: hasCard ? 'question_card' : 'text',
          text: hasCard
            ? `以下是 ${questions.length} 道关于「${topic || '相关知识点'}」的题目：`
            : (m.content || ''),
          agent: m.role === 'agent' ? (m.agent || 'TutorAgent') : '',
          time: m.time ? new Date(m.time).toLocaleTimeString() : new Date().toLocaleTimeString(),
          questions: hasCard ? questions : null,
          topic: topic,
          mode: isCoachCard ? 'evaluate' : 'quiz',
          evalSessionId: '',  // 历史恢复的测评卡无有效会话，只读回顾
          sources: m.sources || [],
          media: m.media || [],
        }
      })
      
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
      headers: {
        ...getAuthHeaders(),  // LA-051-SESSION: 添加认证头
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        user_id: currentUserId.value,  // LA-050-Phase5: 使用当前用户ID
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
      // LA-044: 通知 Sidebar 刷新会话列表，并传递新会话 ID
      window.dispatchEvent(new CustomEvent('chat-session-created', {
        detail: { sessionId: data.session_id }
      }))
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
  // LA-UI-001 M3: 监听左→右分享事件（图谱节点等 → 群聊概念卡）
  window.addEventListener('share-to-chat', (e) => {
    handleShareToChat(e.detail || {})
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
  /* LA-053-FIX-2: 防止内容撑破气泡 */
  min-width: 0;
  max-width: 100%;
  overflow-x: hidden;
}

.message-body {
  /* LA-053-FIX-2: 确保 markdown 内容区域不会撑破父容器 */
  min-width: 0;
  overflow-x: hidden;
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
/* LA-053-FIX-2: 必须使用 :deep() 因为图片通过 v-html/marked 渲染，不在 Vue scoped 范围内 */
.markdown-body :deep(img) {
  max-width: 100%;
  height: auto;
  max-height: min(50vh, 400px);
  object-fit: contain;
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
  /* LA-UI-001-FIX: 弹窗 absolute 定位的参照容器 */
  position: relative;
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

/* LA-LOADING: 思考中占位符样式 */
.loading-placeholder {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--text-muted);
  font-size: var(--font-size-base);
  padding: 4px 0;
}

.loading-text {
  font-style: italic;
}

.loading-dots {
  display: inline-flex;
}

.loading-dots .dot {
  animation: loading-dot-bounce 1.4s infinite ease-in-out both;
  margin-left: 1px;
}

.loading-dots .dot:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots .dot:nth-child(2) {
  animation-delay: -0.16s;
}

.loading-dots .dot:nth-child(3) {
  animation-delay: 0s;
}

@keyframes loading-dot-bounce {
  0%, 80%, 100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

/* ========== LA-UI-001: Agent 标签栏样式 ========== */

.agent-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 16px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
  flex-shrink: 0;
  overflow-x: auto;
}

.agent-tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.agent-tab:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.agent-tab.active {
  background: var(--accent-primary);
  color: white;
  border-color: var(--accent-primary);
}

.agent-tab.flashing {
  animation: tab-flash 1s ease-in-out 3;
}

@keyframes tab-flash {
  0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0); }
  50% { box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.3); }
}

.tab-icon {
  font-size: 14px;
}

.tab-label {
  font-weight: 500;
}

/* ========== LA-UI-001: @命令解析样式 ========== */

.input-highlight-wrapper {
  position: relative;
  width: 100%;
}

.input-highlight {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 10px 12px;
  font-size: 14px;
  line-height: 1.5;
  color: transparent;
  pointer-events: none;
  white-space: pre-wrap;
  word-wrap: break-word;
  z-index: 1;
  min-height: 40px;
}

.at-highlight {
  color: transparent;
  background: rgba(59, 130, 246, 0.15);
  border-radius: 3px;
  padding: 0 2px;
}

.at-dropdown {
  position: absolute;
  /* LA-UI-001-FIX: left/bottom 由 JS 动态计算，跟随光标位置 */
  background: var(--bg-main);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  padding: 4px;
  min-width: 160px;
  z-index: 100;
}

/* LA-UI-001 M2: Coach 测评模式浮层与指示 chip */
.eval-mode-dropdown {
  left: 12px;
  bottom: calc(100% + 8px);
  min-width: 220px;
}

.eval-mode-title {
  font-size: 11px;
  color: var(--text-muted);
  padding: 6px 10px 4px;
}

.eval-mode-chip {
  display: inline-block;
  font-size: 11px;
  color: var(--accent-primary);
  background: var(--bg-active);
  border: 1px solid var(--accent-primary);
  border-radius: 10px;
  padding: 1px 10px;
  margin: 0 6px;
  cursor: pointer;
  user-select: none;
}
.eval-mode-chip:hover {
  background: var(--bg-hover);
}

.at-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.15s;
}

.at-option:hover,
.at-option.selected {
  background: var(--bg-hover);
}

.at-option-icon {
  font-size: 16px;
}

.at-option-label {
  flex: 1;
  font-weight: 500;
  color: var(--text-primary);
}

.at-option-alias {
  font-size: 12px;
  color: var(--text-muted);
  background: var(--bg-secondary);
  padding: 2px 6px;
  border-radius: 4px;
}

.agent-hint {
  color: var(--accent-primary);
}

.hint-sep {
  margin: 0 6px;
  color: var(--border-color);
}
</style>
