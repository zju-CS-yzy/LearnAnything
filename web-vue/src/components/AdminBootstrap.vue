<template>
  <div v-if="modelValue" class="bootstrap-overlay" @click.self="close">
    <section class="bootstrap-modal" role="dialog" aria-modal="true" aria-labelledby="bootstrap-title">
      <button class="close-btn" type="button" aria-label="关闭" @click="close">&times;</button>
      <div class="bootstrap-icon">🛡️</div>
      <h2 id="bootstrap-title">初始化本机管理员</h2>
      <p class="intro">
        这台设备尚未设置系统管理员。管理员可以配置模型 API、查看系统监控并管理其他管理员。
      </p>
      <div class="account-card">
        <span>当前账户</span>
        <strong>{{ currentUser.display_name || currentUser.username }}</strong>
        <small>{{ currentUser.username }}</small>
      </div>
      <form @submit.prevent="claim">
        <label for="bootstrap-password">重新输入当前账户密码</label>
        <input
          id="bootstrap-password"
          v-model="password"
          type="password"
          minlength="6"
          maxlength="256"
          autocomplete="current-password"
          required
          :disabled="loading"
          placeholder="用于确认是账户本人操作"
        />
        <p v-if="error" class="error-message">{{ error }}</p>
        <button class="claim-btn" type="submit" :disabled="loading || password.length < 6">
          {{ loading ? '正在初始化…' : '将当前账户设为管理员' }}
        </button>
      </form>
      <p class="security-note">仅本机可执行，并且只能在系统没有管理员时成功一次。</p>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useUser } from '../composables/useUser.js'

defineProps({
  modelValue: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'claimed'])
const { currentUser, getAuthHeaders, refreshCurrentUser } = useUser()
const password = ref('')
const loading = ref(false)
const error = ref('')

function close() {
  if (!loading.value) emit('update:modelValue', false)
}

async function claim() {
  error.value = ''
  loading.value = true
  try {
    const response = await fetch('/api/admin/bootstrap/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ password: password.value }),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || '管理员初始化失败')
    await refreshCurrentUser()
    password.value = ''
    emit('update:modelValue', false)
    emit('claimed')
  } catch (exception) {
    error.value = exception.message || '管理员初始化失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.bootstrap-overlay {
  position: fixed;
  inset: 0;
  z-index: 2100;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.62);
  backdrop-filter: blur(4px);
}

.bootstrap-modal {
  position: relative;
  width: min(440px, 92vw);
  padding: 32px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 18px;
  background: var(--bg-card, #fff);
  color: var(--text-primary, #111827);
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.28);
}

.close-btn {
  position: absolute;
  top: 14px;
  right: 16px;
  border: 0;
  background: transparent;
  color: var(--text-muted, #6b7280);
  font-size: 25px;
  cursor: pointer;
}

.bootstrap-icon { font-size: 38px; }
h2 { margin: 10px 0 8px; font-size: 23px; }
.intro { margin: 0 0 20px; color: var(--text-secondary, #4b5563); line-height: 1.65; }

.account-card {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 3px 12px;
  margin-bottom: 20px;
  padding: 13px 15px;
  border-radius: 10px;
  background: var(--bg-main, #f3f4f6);
}
.account-card span { grid-row: span 2; align-self: center; color: var(--text-muted, #6b7280); }
.account-card strong, .account-card small { text-align: right; }
.account-card small { color: var(--text-muted, #6b7280); }

label { display: block; margin-bottom: 7px; font-size: 14px; font-weight: 600; }
input {
  box-sizing: border-box;
  width: 100%;
  padding: 11px 13px;
  border: 1px solid var(--border-color, #d1d5db);
  border-radius: 9px;
  background: var(--bg-main, #fff);
  color: var(--text-primary, #111827);
}
input:focus { outline: 2px solid rgba(59, 130, 246, 0.22); border-color: #3b82f6; }
.error-message { margin: 10px 0 0; color: #dc2626; font-size: 13px; }
.claim-btn {
  width: 100%;
  margin-top: 16px;
  padding: 11px 16px;
  border: 0;
  border-radius: 9px;
  background: #2563eb;
  color: #fff;
  font-weight: 700;
  cursor: pointer;
}
.claim-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.security-note { margin: 15px 0 0; color: var(--text-muted, #6b7280); font-size: 12px; text-align: center; }
</style>
