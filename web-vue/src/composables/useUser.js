import { ref, computed, readonly } from 'vue'

// 存储键名
const USER_KEY = 'la_current_user'
const USERS_KEY = 'la_users'
const TOKEN_KEY = 'la_auth_token'  // LA-052: token 存储

// LA-051-P1-FIX: 用户切换事件 — 用于跨模块通知（如 App.vue 重新加载学科列表）
const USER_CHANGE_EVENT = 'la-user-changed'

// 默认本地用户（LA-052-A: 替代 anonymous，无需密码）
const DEFAULT = { user_id: 'default', username: 'default', display_name: '本地用户', system_role: 'user' }

/**
 * 用户管理 Composable
 *
 * LA-050-Phase5: 前端用户隔离核心
 * LA-052: 增加密码认证（token 管理）
 */

const _currentUser = ref({ ...DEFAULT })
const _authToken = ref('')
const _userList = ref([{ ...DEFAULT }])
const _sessionLogin = ref(false)

function loadUser() {
  try {
    const saved = localStorage.getItem(USER_KEY)
    if (saved) {
      _currentUser.value = JSON.parse(saved)
      console.log('[useUser] 已加载用户:', _currentUser.value.username)
    } else {
      _currentUser.value = { ...DEFAULT }
      console.log('[useUser] 使用默认本地用户')
    }
  } catch (e) {
    console.error('[useUser] 加载用户失败:', e)
    _currentUser.value = { ...DEFAULT }
  }
}

function loadToken() {
  try {
    _authToken.value = localStorage.getItem(TOKEN_KEY) || ''
  } catch (e) {
    _authToken.value = ''
  }
}

function saveUser(user) {
  const prevId = _currentUser.value?.user_id
  _currentUser.value = user
  try {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
    console.log('[useUser] 已保存用户:', user.username)
  } catch (e) {
    console.error('[useUser] 保存用户失败:', e)
  }
  // LA-051-P1-FIX: 用户切换时触发全局事件，通知 App.vue 重新加载学科列表
  if (prevId && prevId !== user.user_id) {
    window.dispatchEvent(new CustomEvent(USER_CHANGE_EVENT, { detail: { user_id: user.user_id, prev_id: prevId } }))
  }
}

function saveToken(token) {
  _authToken.value = token
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token)
    } else {
      localStorage.removeItem(TOKEN_KEY)
    }
  } catch (e) {
    console.error('[useUser] 保存 token 失败:', e)
  }
}

// 模块级别共享状态（所有 useUser() 调用共享）
// _currentUser 和 _authToken 已在文件顶部定义

function addToUserList(user) {
  try {
    const list = [..._userList.value]
    const idx = list.findIndex(u => u && u.user_id === user.user_id)
    if (idx >= 0) {
      list[idx] = user
    } else {
      list.push(user)
    }
    _userList.value = list
    localStorage.setItem(USERS_KEY, JSON.stringify(list))
    console.log('[useUser] 用户已添加到列表:', user.username, '列表长度:', list.length)
  } catch (e) {
    console.error('[useUser] 保存用户列表失败:', e)
  }
}

function refreshUserList() {
  try {
    const saved = localStorage.getItem(USERS_KEY)
    let list = saved ? JSON.parse(saved) : []
    list = list.filter(u => u && u.user_id && u.user_id !== 'anonymous')
    if (!list.find(u => u.user_id === 'default')) {
      list.unshift({ ...DEFAULT })
    }
    _userList.value = list
    localStorage.setItem(USERS_KEY, JSON.stringify(list))
  } catch (e) {
    _userList.value = [{ ...DEFAULT }]
  }
}

// 初始化加载
loadUser()
loadToken()
refreshUserList()

// ==================== 公开 API ====================

export function useUser() {
  const currentUser = readonly(_currentUser)
  const authToken = readonly(_authToken)

  // LA-055-FIX: isLoggedIn — 仅当前会话主动登录过且不是 default 用户
  const isLoggedIn = computed(() => {
    return _sessionLogin.value && _authToken.value && _currentUser.value && _currentUser.value.user_id !== 'default'
  })

  // LA-055-FIX: isAuthenticated — 当前会话已通过 LoginGuard（包括 default 用户）
  const isAuthenticated = computed(() => {
    return _sessionLogin.value && !!_currentUser.value
  })

  // 本地用户快捷进入（default 用户）
  const isLocalUser = computed(() => {
    return _currentUser.value?.user_id === 'default'
  })

  const isSystemAdmin = computed(() => {
    return !!_authToken.value && _currentUser.value?.system_role === 'admin'
  })

  const xUserId = computed(() => _currentUser.value?.user_id || 'default')

  // LA-052: 密码登录
  async function loginWithPassword(username, password) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    const data = await res.json()
    if (!data.success) {
      throw new Error(data.detail || data.message || '登录失败')
    }
    saveToken(data.token)
    const user = {
      user_id: data.user_id,
      username: data.username,
      display_name: data.display_name || data.username,
      system_role: data.system_role || 'user',
      login_at: new Date().toISOString(),
    }
    saveUser(user)
    addToUserList(user)
    // LA-055-FIX: 标记当前会话已登录
    _sessionLogin.value = true
    return data
  }

  // LA-052: 注册
  async function register(username, password, displayName) {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username,
        password,
        display_name: displayName || username,
      }),
    })
    const data = await res.json()
    if (!data.success) {
      throw new Error(data.detail || data.message || '注册失败')
    }
    saveToken(data.token)
    const user = {
      user_id: data.user_id,
      username: data.username,
      display_name: data.display_name || data.username,
      system_role: data.system_role || 'user',
      login_at: new Date().toISOString(),
    }
    saveUser(user)
    addToUserList(user)
    // LA-055-FIX: 标记当前会话已登录
    _sessionLogin.value = true
    return data
  }

  // LA-052: 登出
  async function logout() {
    if (_authToken.value) {
      try {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${_authToken.value}` },
        })
      } catch (e) {
        console.warn('[useUser] 登出 API 调用失败:', e)
      }
    }
    saveToken('')
    saveUser({ ...DEFAULT })
    _sessionLogin.value = false
  }

  // 旧登录方式（兼容）
  // LA-055-FIX: 设置用户后标记当前会话已登录
  function login(user_id, username, display_name) {
    const user = {
      user_id,
      username,
      display_name: display_name || username,
      system_role: 'user',
      login_at: new Date().toISOString(),
    }
    saveUser(user)
    addToUserList(user)
    _sessionLogin.value = true
  }

  // 切换用户（不重新登录，从已保存列表中选择）
  function switchUser(user_id) {
    const list = userList.value
    const found = list.find(u => u.user_id === user_id)
    if (found) {
      saveUser(found)
      // LA-052-A: 切换到 default 用户时清除 token
      if (found.user_id === 'default') {
        saveToken('')
      }
      return true
    }
    console.warn('[useUser] 用户不在列表中:', user_id)
    return false
  }

  // 用户列表 — 使用模块级别的 _userList
  const userList = computed(() => _userList.value)

  // LA-052: 获取请求 Headers（含 token + X-User-ID）
  function getAuthHeaders() {
    const headers = {
      'X-User-ID': xUserId.value,
    }
    if (_authToken.value) {
      headers['Authorization'] = `Bearer ${_authToken.value}`
    }
    return headers
  }

  return {
    currentUser,
    isLoggedIn,
    isAuthenticated,  // LA-055-FIX: 当前会话认证状态
    isSystemAdmin,
    authToken,
    xUserId,
    loginWithPassword,
    register,
    logout,
    login,       // 旧方式兼容
    switchUser,
    userList,
    getAuthHeaders,
  }
}
