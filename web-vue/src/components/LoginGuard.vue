<template>
  <div class="login-guard-overlay">
    <div class="login-guard-container">
      <!-- Logo / 标题 -->
      <div class="login-guard-brand">
        <div class="brand-logo">📚</div>
        <h1 class="brand-title">LearnAnything</h1>
        <p class="brand-subtitle">AI 驱动的个性化知识学习系统</p>
      </div>

      <!-- 登录/注册表单 -->
      <div class="login-guard-form">
        <div class="form-tabs">
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

        <form @submit.prevent="submit">
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

      <!-- 分隔线 -->
      <div class="divider">
        <span>或</span>
      </div>

      <!-- 本地用户快捷进入 -->
      <button class="local-user-btn" @click="enterAsLocal" :disabled="loading">
        <span class="local-icon">🏠</span>
        <div class="local-text">
          <div class="local-title">本地用户进入</div>
          <div class="local-desc">无需密码，数据仅保存在本机</div>
        </div>
      </button>

      <!-- 底部信息 -->
      <div class="login-guard-footer">
        <p>首次使用？点击上方"注册"创建账户</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useUser } from '../composables/useUser.js'

const emit = defineEmits(['success'])

const { loginWithPassword, register } = useUser()

const mode = ref('login')
const loading = ref(false)
const error = ref('')

const form = reactive({
  username: '',
  password: '',
  display_name: '',
})

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
  } catch (e) {
    error.value = e.message || '操作失败，请重试'
  } finally {
    loading.value = false
  }
}

// LA-055: 以本地用户（default）身份进入
function enterAsLocal() {
  // default 用户不需要密码，直接设置用户信息
  const { login } = useUser()
  login('default', 'default', '本地用户')
  emit('success')
}
</script>

<style scoped>
.login-guard-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-main, #f5f5f7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 20px;
}

.login-guard-container {
  width: 400px;
  max-width: 100%;
}

/* 品牌区域 */
.login-guard-brand {
  text-align: center;
  margin-bottom: 32px;
}

.brand-logo {
  font-size: 56px;
  margin-bottom: 12px;
}

.brand-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary, #1d1d1f);
  margin: 0 0 8px 0;
  letter-spacing: -0.5px;
}

.brand-subtitle {
  font-size: 14px;
  color: var(--text-muted, #86868b);
  margin: 0;
}

/* 表单区域 */
.login-guard-form {
  background: var(--bg-card, #fff);
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
  border: 1px solid var(--border-color, #e8e8ed);
}

.form-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border-color, #e8e8ed);
}

.tab-btn {
  flex: 1;
  padding: 10px;
  border: none;
  background: none;
  font-size: 15px;
  font-weight: 500;
  color: var(--text-muted, #86868b);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.tab-btn.active {
  color: var(--accent-primary, #4a90d9);
  border-bottom-color: var(--accent-primary, #4a90d9);
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary, #666);
}

.form-group input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 10px;
  font-size: 15px;
  background: var(--bg-main, #fafafa);
  color: var(--text-primary, #333);
  box-sizing: border-box;
  transition: border-color 0.2s;
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
  padding: 8px;
  background: rgba(229, 57, 53, 0.08);
  border-radius: 8px;
}

.submit-btn {
  width: 100%;
  padding: 14px;
  border: none;
  border-radius: 10px;
  background: var(--accent-primary, #4a90d9);
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.submit-btn:hover:not(:disabled) {
  background: var(--accent-hover, #3a7bc8);
  transform: translateY(-1px);
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.spinner {
  width: 18px;
  height: 18px;
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

/* 分隔线 */
.divider {
  display: flex;
  align-items: center;
  margin: 20px 0;
  color: var(--text-muted, #86868b);
  font-size: 13px;
}

.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border-color, #e8e8ed);
}

.divider span {
  padding: 0 12px;
}

/* 本地用户按钮 */
.local-user-btn {
  width: 100%;
  padding: 16px;
  border: 1.5px dashed var(--border-color, #ccc);
  border-radius: 12px;
  background: var(--bg-card, #fff);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: all 0.2s;
}

.local-user-btn:hover:not(:disabled) {
  border-color: var(--accent-primary, #4a90d9);
  background: rgba(74, 144, 217, 0.05);
}

.local-user-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.local-icon {
  font-size: 28px;
}

.local-text {
  text-align: left;
}

.local-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.local-desc {
  font-size: 12px;
  color: var(--text-muted, #86868b);
  margin-top: 2px;
}

/* 底部信息 */
.login-guard-footer {
  text-align: center;
  margin-top: 20px;
}

.login-guard-footer p {
  font-size: 13px;
  color: var(--text-muted, #86868b);
}
</style>
