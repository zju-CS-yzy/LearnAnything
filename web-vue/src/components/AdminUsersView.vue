<template>
  <div class="admin-users-view">
    <header>
      <div>
        <p class="eyebrow">SYSTEM ADMINISTRATION</p>
        <h1>用户与管理员</h1>
        <p>管理员可以配置系统级 API、查看监控并授权其他管理员。</p>
      </div>
      <button class="refresh-btn" type="button" :disabled="loading" @click="loadUsers">刷新</button>
    </header>

    <div class="summary-card">
      <strong>{{ adminCount }}</strong>
      <span>名系统管理员</span>
      <small>系统始终至少保留一名管理员</small>
    </div>

    <p v-if="error" class="page-error">{{ error }}</p>
    <div class="user-list" :class="{ loading }">
      <article v-for="user in users" :key="user.user_id" class="user-card">
        <div class="avatar">{{ (user.display_name || user.username)[0] }}</div>
        <div class="identity">
          <strong>{{ user.display_name || user.username }}</strong>
          <span>@{{ user.username }}</span>
          <small>{{ user.user_id }}</small>
        </div>
        <span class="role-badge" :class="user.system_role">
          {{ user.system_role === 'admin' ? '系统管理员' : '普通用户' }}
        </span>
        <button
          v-if="user.system_role !== 'admin'"
          class="role-btn promote"
          type="button"
          @click="beginRoleChange(user, 'admin')"
        >
          设为管理员
        </button>
        <button
          v-else
          class="role-btn demote"
          type="button"
          :disabled="adminCount <= 1"
          :title="adminCount <= 1 ? '不能撤销最后一个管理员' : '撤销管理员权限'"
          @click="beginRoleChange(user, 'user')"
        >
          撤销管理员
        </button>
      </article>
      <p v-if="!loading && !users.length" class="empty-state">暂无可管理的密码账户</p>
    </div>

    <div v-if="pendingChange" class="confirm-overlay" @click.self="cancelRoleChange">
      <form class="confirm-modal" @submit.prevent="applyRoleChange">
        <h2>{{ pendingChange.role === 'admin' ? '授予管理员权限' : '撤销管理员权限' }}</h2>
        <p>
          目标账户：<strong>{{ pendingChange.user.display_name || pendingChange.user.username }}</strong>
        </p>
        <label for="admin-password">输入你的管理员密码确认操作</label>
        <input
          id="admin-password"
          v-model="adminPassword"
          type="password"
          minlength="6"
          maxlength="256"
          autocomplete="current-password"
          required
          autofocus
          :disabled="saving"
        />
        <p v-if="modalError" class="modal-error">{{ modalError }}</p>
        <div class="modal-actions">
          <button type="button" class="cancel-btn" :disabled="saving" @click="cancelRoleChange">取消</button>
          <button type="submit" class="confirm-btn" :disabled="saving || adminPassword.length < 6">
            {{ saving ? '正在保存…' : '确认' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useUser } from '../composables/useUser.js'

const { currentUser, getAuthHeaders, refreshCurrentUser } = useUser()
const users = ref([])
const adminCount = ref(0)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const modalError = ref('')
const pendingChange = ref(null)
const adminPassword = ref('')

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch('/api/admin/users', { headers: getAuthHeaders() })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || '加载用户失败')
    users.value = data.users || []
    adminCount.value = data.admin_count || 0
  } catch (exception) {
    error.value = exception.message || '加载用户失败'
  } finally {
    loading.value = false
  }
}

function beginRoleChange(user, role) {
  pendingChange.value = { user, role }
  adminPassword.value = ''
  modalError.value = ''
}

function cancelRoleChange() {
  if (saving.value) return
  pendingChange.value = null
  adminPassword.value = ''
  modalError.value = ''
}

async function applyRoleChange() {
  if (!pendingChange.value) return
  saving.value = true
  modalError.value = ''
  const { user, role } = pendingChange.value
  try {
    const response = await fetch(`/api/admin/users/${encodeURIComponent(user.user_id)}/role`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ role, current_password: adminPassword.value }),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || '角色更新失败')
    const changedCurrentUser = user.user_id === currentUser.value.user_id
    pendingChange.value = null
    adminPassword.value = ''
    modalError.value = ''
    if (changedCurrentUser) {
      await refreshCurrentUser()
      window.location.reload()
      return
    }
    await loadUsers()
  } catch (exception) {
    modalError.value = exception.message || '角色更新失败'
  } finally {
    saving.value = false
  }
}

onMounted(loadUsers)
</script>

<style scoped>
.admin-users-view { height: 100%; overflow: auto; padding: 30px; box-sizing: border-box; color: var(--text-primary, #111827); }
header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; }
.eyebrow { margin: 0 0 7px; color: #2563eb; font-size: 11px; font-weight: 800; letter-spacing: 0.14em; }
h1 { margin: 0; font-size: 28px; }
header p:not(.eyebrow) { margin: 8px 0 0; color: var(--text-secondary, #6b7280); }
.refresh-btn, .role-btn, .cancel-btn, .confirm-btn { border-radius: 8px; padding: 9px 13px; cursor: pointer; font-weight: 600; }
.refresh-btn { border: 1px solid var(--border-color, #d1d5db); background: var(--bg-card, #fff); color: inherit; }
.summary-card { display: grid; grid-template-columns: auto 1fr; column-gap: 9px; align-items: baseline; margin: 25px 0 18px; padding: 18px 20px; border: 1px solid var(--border-color, #e5e7eb); border-radius: 12px; background: var(--bg-card, #fff); }
.summary-card strong { grid-row: span 2; color: #2563eb; font-size: 32px; }
.summary-card span { font-weight: 700; }
.summary-card small { color: var(--text-muted, #6b7280); }
.user-list { display: grid; gap: 10px; opacity: 1; transition: opacity .2s; }
.user-list.loading { opacity: .55; }
.user-card { display: grid; grid-template-columns: 42px minmax(170px, 1fr) auto 120px; gap: 14px; align-items: center; padding: 15px 17px; border: 1px solid var(--border-color, #e5e7eb); border-radius: 12px; background: var(--bg-card, #fff); }
.avatar { display: grid; place-items: center; width: 42px; height: 42px; border-radius: 50%; background: #dbeafe; color: #1d4ed8; font-weight: 800; }
.identity { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.identity span, .identity small { color: var(--text-muted, #6b7280); overflow: hidden; text-overflow: ellipsis; }
.identity small { font-size: 11px; }
.role-badge { padding: 4px 9px; border-radius: 999px; font-size: 12px; font-weight: 700; }
.role-badge.admin { background: #fef3c7; color: #92400e; }
.role-badge.user { background: #f3f4f6; color: #4b5563; }
.role-btn { border: 1px solid transparent; }
.role-btn.promote { background: #2563eb; color: #fff; }
.role-btn.demote { background: transparent; border-color: #fca5a5; color: #b91c1c; }
.role-btn:disabled { opacity: .45; cursor: not-allowed; }
.page-error, .modal-error { color: #dc2626; }
.empty-state { padding: 30px; text-align: center; color: var(--text-muted, #6b7280); }
.confirm-overlay { position: fixed; inset: 0; z-index: 2200; display: grid; place-items: center; padding: 20px; background: rgba(15, 23, 42, .58); }
.confirm-modal { width: min(410px, 92vw); padding: 25px; border-radius: 14px; background: var(--bg-card, #fff); box-shadow: 0 22px 60px rgba(15,23,42,.28); }
.confirm-modal h2 { margin: 0 0 10px; }
.confirm-modal label { display: block; margin: 18px 0 7px; font-size: 14px; font-weight: 600; }
.confirm-modal input { box-sizing: border-box; width: 100%; padding: 10px 12px; border: 1px solid var(--border-color, #d1d5db); border-radius: 8px; background: var(--bg-main, #fff); color: inherit; }
.modal-actions { display: flex; justify-content: flex-end; gap: 9px; margin-top: 18px; }
.cancel-btn { border: 1px solid var(--border-color, #d1d5db); background: transparent; color: inherit; }
.confirm-btn { border: 0; background: #2563eb; color: #fff; }
@media (max-width: 760px) { .user-card { grid-template-columns: 42px 1fr auto; } .role-btn { grid-column: 2 / -1; } }
</style>
