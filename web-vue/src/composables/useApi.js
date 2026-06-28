import { ref } from 'vue'

// API 基础地址 — 从当前页面 origin 自动推断
const API_BASE = window.location.origin

// 通用 fetch 封装
async function fetchApi(path, options = {}) {
  const url = `${API_BASE}${path}`
  const resp = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`HTTP ${resp.status}: ${text}`)
  }
  return resp.json()
}

// 健康检查
export function useHealthCheck() {
  const status = ref('connecting') // connecting | online | offline

  async function check() {
    try {
      const resp = await fetch(`${API_BASE}/api/health`, { method: 'GET' })
      status.value = resp.ok ? 'online' : 'offline'
    } catch (e) {
      status.value = 'offline'
    }
  }

  // 页面加载时立即检查，之后每 10 秒轮询
  check()
  setInterval(check, 10000)

  return { status, check }
}

// 智能问答（非流式）
export async function apiAsk(query, subject = 'generic') {
  return fetchApi('/api/ask', {
    method: 'POST',
    body: JSON.stringify({ query, subject }),
  })
}

// 智能问答（流式 SSE）
export async function* apiAskStream(query, subject = 'generic') {
  const resp = await fetch(`${API_BASE}/api/ask/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, subject }),
  })

  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`HTTP ${resp.status}: ${text}`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.trim()) continue
      yield parseSSE(line)
    }
  }
}

// 解析 SSE 行
function parseSSE(raw) {
  const lines = raw.split('\n')
  let eventName = 'message'
  let data = ''

  for (const line of lines) {
    if (line.startsWith('event: ')) {
      eventName = line.slice(7).trim()
    } else if (line.startsWith('data: ')) {
      data = line.slice(6).trim()
    }
  }

  try {
    return { event: eventName, data: JSON.parse(data) }
  } catch {
    return { event: eventName, data }
  }
}

// 出题
export async function apiQuiz(topic, subject = 'generic', count = 5) {
  return fetchApi('/api/quiz', {
    method: 'POST',
    body: JSON.stringify({ topic, subject, count }),
  })
}

// 评测 — 开始（支持 mode: generate/bank/mixed）
export async function apiEvalStart(topic, subject = 'generic', count = 5, mode = 'generate') {
  return fetchApi('/api/evaluate/start', {
    method: 'POST',
    body: JSON.stringify({ topic, subject, count, mode }),
  })
}

// 评测 — 提交
export async function apiEvalSubmit(sessionId, answers) {
  return fetchApi('/api/evaluate/submit', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, answers }),
  })
}

// ========== 题库管理 API ==========

// 保存题目到题库
export async function apiQuizBankSave(questions, subject = 'generic', topic = '', isApproved = false) {
  return fetchApi('/api/quiz-bank/save', {
    method: 'POST',
    body: JSON.stringify({ questions, subject, topic, is_approved: isApproved }),
  })
}

// 查询题库列表
export async function apiQuizBankList(subject = 'generic', topic = null, isApproved = null, limit = 100) {
  const params = new URLSearchParams()
  params.append('subject', subject)
  if (topic) params.append('topic', topic)
  if (isApproved !== null) params.append('is_approved', isApproved)
  params.append('limit', limit)
  return fetchApi(`/api/quiz-bank/list?${params.toString()}`)
}

// 确认保留题目
export async function apiQuizBankApprove(qid) {
  return fetchApi(`/api/quiz-bank/approve/${qid}`, { method: 'POST' })
}

// 删除题目
export async function apiQuizBankDelete(qid) {
  return fetchApi(`/api/quiz-bank/${qid}`, { method: 'DELETE' })
}

// 题库统计
export async function apiQuizBankStats(subject = 'generic') {
  return fetchApi(`/api/quiz-bank/stats?subject=${subject}`)
}

// 导入文本
export async function apiImportText(text, subject = 'generic', sourceName = 'frontend') {
  return fetchApi('/api/import/text', {
    method: 'POST',
    body: JSON.stringify({ subject, text, source_name: sourceName }),
  })
}

// 获取学科列表
export async function apiListSubjects() {
  return fetchApi('/api/subjects')
}

// 获取学科统计
export async function apiSubjectStats(subject) {
  return fetchApi(`/api/knowledge-base/${subject}/stats`)
}
