<template>
  <div class="login-overlay" v-if="visible" @click="close">
    <div class="login-modal" @click.stop>
      <div class="login-header">
        <div class="login-tabs">
          <button
            :class="['tab-btn', { active: mode === 'login' }]"
            @click="mode = 'login'; error = ''"
          >
            登录
          </button>
          <button
            :class="['tab-btn', { active: mode === 'register' }]"
            @click="mode = 'register'; error = ''"
          >
            注册
          </button>
        </div>
        <button class="close-btn" @click="close">&times;</button>
      </div>

      <form class="login-form" @submit.prevent="submit">
        <div class="form-group">
          <label>用户名</label>
          <input
            v-model="form.username"
            type="text"
            required
            minlength="2"
            maxlength="50"
            placeholder="请输入用户名"
            :disabled="loading"
          />
        </div>

        <div class="form-group">
          <label>密码</label>
          <input
            v-model="form.password"
            type="password"
            required
            minlength="6"
            placeholder="至少 6 位"
            :disabled="loading"
          />
        </div>

        <div class="form-group" v-if="mode === 'register'">
          <label>显示昵称（可选）</label>
          <input
            v-model="form.display_name"
            type="text"
            placeholder="默认与用户名相同"
            :disabled="loading"
          />
        </div>

        <div class="error-msg" v-if="error">{{ error }}</div>

        <button type="submit" class="submit-btn" :disabled="loading">
          <span v-if="loading" class="spinner"></span>
          <span v-else>{{ mode === 'login' ? '登录' : '注册' }}</span>
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useUser } from '../composables/useUser.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'success'])

const { loginWithPassword, register } = useUser()

const mode = ref('login')
const loading = ref(false)
const error = ref('')

const form = reactive({
  username: '',
  password: '',
  display_name: '',
})

function close() {
  error.value = ''
  emit('close')
}

async function submit() {
  error.value = ''
  loading.value = true

  try {
    if (mode.value === 'login') {
      await loginWithPassword(form.username, form.password)
    } else {
      await register(form.username, form.password, form.display_name)
    }
    emit('success')
    close()
  } catch (e) {
    error.value = e.message || '操作失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.login-modal {
  background: var(--bg-card, #fff);
  border-radius: 12px;
  width: 360px;
  max-width: 90vw;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.login-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 0;
}

.login-tabs {
  display: flex;
  gap: 16px;
}

.tab-btn {
  padding: 8px 4px;
  border: none;
  background: none;
  font-size: 16px;
  font-weight: 500;
  color: var(--text-muted, #999);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.tab-btn.active {
  color: var(--accent-primary, #4a90d9);
  border-bottom-color: var(--accent-primary, #4a90d9);
}

.close-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: var(--bg-hover, #f0f0f0);
  border-radius: 50%;
  font-size: 18px;
  color: var(--text-muted, #999);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  background: var(--border-color, #ddd);
}

.login-form {
  padding: 20px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  color: var(--text-secondary, #666);
}

.form-group input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg-main, #fafafa);
  color: var(--text-primary, #333);
  box-sizing: border-box;
}

.form-group input:focus {
  outline: none;
  border-color: var(--accent-primary, #4a90d9);
}

.form-group input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-msg {
  color: #e53935;
  font-size: 13px;
  margin-bottom: 12px;
  text-align: center;
}

.submit-btn {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 8px;
  background: var(--accent-primary, #4a90d9);
  color: #fff;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.submit-btn:hover:not(:disabled) {
  background: var(--accent-hover, #3a7bc8);
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
