import { ref } from 'vue'

// API 基础地址 — 从当前页面 origin 自动推断
const API_BASE = window.location.origin

// LA-050-Phase5 + LA-052-A: 从 localStorage 读取当前用户ID
function getXUserId() {
  try {
    const saved = localStorage.getItem('la_current_user')
    if (saved) {
      const user = JSON.parse(saved)
      return user.user_id || 'default'
    }
  } catch (e) {
    console.error('[useApi] 读取用户ID失败:', e)
  }
  return 'default'
}

// LA-052: 从 localStorage 读取认证 token
function getAuthToken() {
  try {
    return localStorage.getItem('la_auth_token') || ''
  } catch (e) {
    return ''
  }
}

// LA-050-Phase5 + LA-052: 获取带 X-User-ID 和 Authorization 的请求头
function authHeaders(base = {}) {
  const headers = {
    'Content-Type': 'application/json',
    'X-User-ID': getXUserId(),
    ...base,
  }
  // LA-052: 如果已登录，附加 Authorization token
  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

// 通用 fetch 封装 — 自动附加 X-User-ID
async function fetchApi(path, options = {}) {
  const url = `${API_BASE}${path}`
  const resp = await fetch(url, {
    ...options,
    headers: authHeaders(options.headers),
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
export async function apiAsk(query, subject = 'generic', user_id = null, user_theta = null) {
  const effectiveUserId = user_id || getXUserId()
  console.log('[useApi] apiAsk user_id:', effectiveUserId, 'user_theta:', user_theta)
  return fetchApi('/api/ask', {
    method: 'POST',
    body: JSON.stringify({ query, subject, user_id: effectiveUserId, user_theta }),
  })
}

// 智能问答（流式 SSE）
// LA-050-HISTORY-FIX: 传入 session_id，后端会返回实际的 session_id
// LA-044: 传入 user_theta 实现个性化回答
export async function* apiAskStream(query, subject = 'generic', user_id = null, session_id = null, user_theta = null) {
  // LA-050-Phase5: 如果未传入 user_id，从 localStorage 读取
  const effectiveUserId = user_id || getXUserId()
  console.log('[useApi] apiAskStream user_id:', effectiveUserId, 'session_id:', session_id, 'user_theta:', user_theta)
  
  const resp = await fetch(`${API_BASE}/api/ask/stream`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ query, subject, user_id: effectiveUserId, session_id, user_theta }),
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

// 创建学科
export async function apiCreateSubject(id, name, description = '', keywords = []) {
  return fetchApi('/api/subjects', {
    method: 'POST',
    body: JSON.stringify({ id, name, description, keywords }),
  })
}

// 删除学科
export async function apiDeleteSubject(subjectId) {
  return fetchApi(`/api/subjects/${subjectId}`, { method: 'DELETE' })
}

// 自动检测学科
export async function apiDetectSubject(query) {
  const form = new URLSearchParams()
  form.append('query', query)
  const resp = await fetch(`${API_BASE}/api/subjects/detect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`HTTP ${resp.status}: ${text}`)
  }
  return resp.json()
}

// 获取学科统计
export async function apiSubjectStats(subject) {
  return fetchApi(`/api/knowledge-base/${subject}/stats`)
}

// ========== LA-040-P1-VIS: 评测结果可视化 API ==========

// 获取能力条形图数据
export async function apiVisualizationBars(user_id = 'anonymous', subject = 'generic', sort = 'mastery_asc', limit = 20, filter_status = 'all') {
  const params = new URLSearchParams()
  params.append('user_id', user_id)
  params.append('subject', subject)
  params.append('sort', sort)
  params.append('limit', String(limit))
  params.append('filter_status', filter_status)
  return fetchApi(`/api/visualization/bars?${params.toString()}`)
}

// ========== LA-040-P2: 学习进度 API ==========

// 获取进步曲线
export async function apiProgressChart(user_id = 'anonymous', subject = 'generic', days = 30) {
  const params = new URLSearchParams()
  params.append('user_id', user_id)
  params.append('subject', subject)
  params.append('days', String(days))
  return fetchApi(`/api/visualization/progress?${params.toString()}`)
}

// 获取错题本
export async function apiWrongAnswers(user_id = 'anonymous', subject = 'generic', concept = null, mastered = null, sort = 'last_wrong_desc', limit = 50, offset = 0) {
  const params = new URLSearchParams()
  params.append('user_id', user_id)
  params.append('subject', subject)
  if (concept) params.append('concept', concept)
  if (mastered !== null) params.append('mastered', String(mastered))
  params.append('sort', sort)
  params.append('limit', String(limit))
  params.append('offset', String(offset))
  return fetchApi(`/api/visualization/wrong-answers?${params.toString()}`)
}

// 更新错题状态
export async function apiUpdateWrongAnswer(wrong_id, updates) {
  return fetchApi(`/api/visualization/wrong-answers/${wrong_id}`, {
    method: 'POST',
    body: JSON.stringify(updates),
  })
}

// 获取评测历史
export async function apiEvalHistory(user_id = 'anonymous', subject = 'generic', limit = 50, offset = 0) {
  const params = new URLSearchParams()
  params.append('user_id', user_id)
  params.append('subject', subject)
  params.append('limit', String(limit))
  params.append('offset', String(offset))
  return fetchApi(`/api/evaluation/history?${params.toString()}`)
}

// 获取 Bloom 认知层次统计
export async function apiBloomStats(subject = 'generic') {
  return fetchApi(`/api/quiz-bank/bloom-stats?subject=${subject}`)
}

// LA-040-P3: 获取 Bloom 认知雷达图数据
export async function apiBloomRadar(userId = 'anonymous', subject = 'generic') {
  return fetchApi(`/api/visualization/bloom-radar?user_id=${userId}&subject=${subject}`)
}

// LA-040-P3: 获取学习建议
export async function apiRecommendations(userId = 'anonymous', subject = 'generic') {
  return fetchApi(`/api/visualization/recommendations?user_id=${userId}&subject=${subject}`)
}

// ========== LA-051: 权限管理 API ==========

// 获取学科权限列表
export async function apiListPermissions(subjectId) {
  return fetchApi(`/api/subjects/${subjectId}/permissions`)
}

// 授予权限
export async function apiGrantPermission(subjectId, userId, role) {
  return fetchApi(`/api/subjects/${subjectId}/permissions`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, role }),
  })
}

// 撤销权限
export async function apiRevokePermission(subjectId, userId) {
  return fetchApi(`/api/subjects/${subjectId}/permissions/${userId}`, {
    method: 'DELETE',
  })
}

// 提交变更（contributor）
export async function apiSubmitChange(subjectId, changeType, description) {
  return fetchApi(`/api/subjects/${subjectId}/changes`, {
    method: 'POST',
    body: JSON.stringify({ change_type: changeType, description }),
  })
}

// 查看待审批变更
export async function apiListPendingChanges(subjectId) {
  return fetchApi(`/api/subjects/${subjectId}/changes/pending`)
}

// 审批变更
export async function apiReviewChange(changeId, approve, note = '') {
  return fetchApi(`/api/subjects/changes/${changeId}/review`, {
    method: 'POST',
    body: JSON.stringify({ approve, note }),
  })
}

// ========== LLM-ROBUST: 诊断 API ==========

// 获取 LLM 诊断信息（配置快照 + Key 池状态）
export async function apiLLMDiagnostic() {
  return fetchApi('/api/llm/diagnostic')
}

// 测试 LLM 连接
export async function apiLLMTest(provider = null, message = 'Hello, this is a connection test.') {
  return fetchApi('/api/llm/test', {
    method: 'POST',
    body: JSON.stringify({ provider, message }),
  })
}
