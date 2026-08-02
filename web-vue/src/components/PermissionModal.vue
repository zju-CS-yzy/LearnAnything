<template>
  <!-- LA-051: 权限管理弹窗 -->
  <div class="permission-overlay" v-if="visible" @click="close">
    <div class="permission-modal" @click.stop>
      <!-- 弹窗头部 -->
      <div class="permission-header">
        <div class="permission-title">
          <span class="title-icon">⚙️</span>
          <span>权限管理 — {{ subjectName }}</span>
        </div>
        <button class="close-btn" @click="close">&times;</button>
      </div>

      <!-- Tab 切换 -->
      <div class="permission-tabs">
        <button
          :class="['tab-btn', { active: activeTab === 'members' }]"
          @click="activeTab = 'members'"
        >
          成员管理
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'pending' }]"
          @click="activeTab = 'pending'"
        >
          审批队列
          <span v-if="pendingCount > 0" class="tab-badge">{{ pendingCount }}</span>
        </button>
      </div>

      <!-- ===== Tab 1: 成员管理 ===== -->
      <div v-if="activeTab === 'members'" class="tab-content">
        <!-- 邀请新成员（仅 owner 可见） -->
        <div v-if="canManage" class="invite-section">
          <div class="section-label">邀请新成员</div>
          <div class="invite-form">
            <input
              v-model="inviteForm.userId"
              type="text"
              placeholder="输入用户ID (如 user_xxxx)"
              class="invite-input"
              :readonly="false"
            />
            <select v-model="inviteForm.role" class="invite-select">
              <option value="maintainer">维护者</option>
              <option value="contributor">贡献者</option>
              <option value="reader">读者</option>
            </select>
            <button class="btn btn-primary btn-sm" @click="grantPermission" :disabled="inviting">
              <span v-if="inviting" class="spinner-sm"></span>
              <span v-else>邀请</span>
            </button>
          </div>
        </div>

        <!-- 成员列表 -->
        <div class="members-section">
          <div class="section-label">
            成员列表
            <span class="member-count">({{ members.length }}人)</span>
          </div>
          <div v-if="members.length === 0" class="empty-hint">
            暂无成员，请在上方邀请
          </div>
          <div v-else class="member-list">
            <div
              v-for="member in members"
              :key="member.user_id"
              class="member-item"
            >
              <span class="member-icon">👤</span>
              <span class="member-name">{{ member.user_id }}</span>
              <span :class="['role-tag', `role-${member.role}`]">
                {{ roleLabel(member.role) }}
              </span>
              <!-- 仅 owner 可撤销他人权限，且不能撤销自己 -->
              <button
                v-if="canManage && member.user_id !== currentUserId"
                class="btn-revoke"
                @click="revokePermission(member.user_id)"
                title="撤销权限"
              >
                撤销
              </button>
            </div>
          </div>
        </div>

        <!-- 当前用户角色提示 -->
        <div class="role-hint">
          您的角色：<strong>{{ roleLabel(myRole) }}</strong>
          <span v-if="myRole === 'owner'" class="hint-detail">（可管理成员、审批变更）</span>
          <span v-else-if="myRole === 'maintainer'" class="hint-detail">（可读写、审批变更）</span>
          <span v-else-if="myRole === 'contributor'" class="hint-detail">（可浏览、提交变更）</span>
          <span v-else class="hint-detail">（仅可浏览）</span>
        </div>
      </div>

      <!-- ===== Tab 2: 审批队列 ===== -->
      <div v-if="activeTab === 'pending'" class="tab-content">
        <!-- 待审批列表 -->
        <div class="pending-section">
          <div class="section-label">
            待审批变更
            <span v-if="pendingChanges.length > 0" class="pending-count">
              ({{ pendingChanges.length }})
            </span>
          </div>
          <div v-if="pendingChanges.length === 0" class="empty-hint">
            暂无待审批的变更
          </div>
          <div v-else class="pending-list">
            <div
              v-for="change in pendingChanges"
              :key="change.id"
              class="pending-item"
            >
              <div class="pending-header">
                <span class="pending-type">{{ changeTypeLabel(change.change_type) }}</span>
                <span class="pending-user">👤 {{ change.submitted_by }}</span>
                <span class="pending-time">{{ formatTime(change.created_at) }}</span>
              </div>
              <div class="pending-desc">{{ change.description || '无描述' }}</div>
              <!-- 仅 owner/maintainer 可审批 -->
              <div v-if="canReview" class="pending-actions">
                <input
                  v-model="change.reviewNote"
                  placeholder="审批备注（可选）"
                  class="review-note-input"
                />
                <button
                  class="btn btn-success btn-sm"
                  @click="reviewChange(change.id, true, change.reviewNote)"
                  :disabled="change.reviewing"
                >
                  <span v-if="change.reviewing" class="spinner-sm"></span>
                  <span v-else>✅ 批准</span>
                </button>
                <button
                  class="btn btn-danger btn-sm"
                  @click="reviewChange(change.id, false, change.reviewNote)"
                  :disabled="change.reviewing"
                >
                  ❌ 拒绝
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  apiListPermissions,
  apiGrantPermission,
  apiRevokePermission,
  apiListPendingChanges,
  apiReviewChange,
} from '../composables/useApi.js'
import { useUser } from '../composables/useUser.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  subjectId: { type: String, default: '' },
  subjectName: { type: String, default: '' },
  role: { type: String, default: '' }, // 当前用户在此学科的角色
})

const emit = defineEmits(['close', 'updated'])

const { currentUser } = useUser()
const currentUserId = computed(() => currentUser.value?.user_id || '')

// Tab 状态
const activeTab = ref('members')

// 成员管理
const members = ref([])
const inviting = ref(false)
const inviteForm = ref({ userId: '', role: 'contributor' })

// 审批队列
const pendingChanges = ref([])

// 计算属性
const canManage = computed(() => props.role === 'owner' || props.role === 'maintainer')
const canReview = computed(() => props.role === 'owner' || props.role === 'maintainer')
const pendingCount = computed(() => pendingChanges.value.length)
const myRole = computed(() => props.role)

// 角色标签映射
function roleLabel(role) {
  const map = {
    owner: '拥有者',
    maintainer: '维护者',
    contributor: '贡献者',
    reader: '读者',
  }
  return map[role] || role
}

function changeTypeLabel(type) {
  const map = {
    import: '📥 导入',
    update: '📝 更新',
    delete: '🗑️ 删除',
  }
  return map[type] || type
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

// 加载成员列表
async function loadMembers() {
  if (!props.subjectId) return
  try {
    const resp = await apiListPermissions(props.subjectId)
    members.value = resp.permissions || []
  } catch (e) {
    console.error('[PermissionModal] 加载成员失败:', e)
    members.value = []
  }
}

// 加载审批队列
async function loadPending() {
  if (!props.subjectId) return
  try {
    const resp = await apiListPendingChanges(props.subjectId)
    pendingChanges.value = (resp.pending || []).map(c => ({ ...c, reviewNote: '', reviewing: false }))
  } catch (e) {
    console.error('[PermissionModal] 加载审批队列失败:', e)
    pendingChanges.value = []
  }
}

// 授予权限
async function grantPermission() {
  if (!inviteForm.value.userId) {
    alert('请输入用户ID')
    return
  }
  inviting.value = true
  try {
    await apiGrantPermission(props.subjectId, inviteForm.value.userId, inviteForm.value.role)
    inviteForm.value.userId = ''
    await loadMembers()
    emit('updated')
  } catch (e) {
    alert('邀请失败: ' + e.message)
  } finally {
    inviting.value = false
  }
}

// 撤销权限
async function revokePermission(userId) {
  if (!confirm(`确定撤销 ${userId} 的权限吗？`)) return
  try {
    await apiRevokePermission(props.subjectId, userId)
    await loadMembers()
    emit('updated')
  } catch (e) {
    alert('撤销失败: ' + e.message)
  }
}

// 审批变更
async function reviewChange(changeId, approve, note) {
  const change = pendingChanges.value.find(c => c.id === changeId)
  if (change) change.reviewing = true
  try {
    await apiReviewChange(changeId, approve, note)
    await loadPending()
    emit('updated')
  } catch (e) {
    alert('审批失败: ' + e.message)
  } finally {
    if (change) change.reviewing = false
  }
}

function close() {
  emit('close')
}

// 监听 visible 变化，打开时加载数据
watch(() => props.visible, (val) => {
  if (val) {
    activeTab.value = 'members'
    loadMembers()
    loadPending()
  }
})
</script>

<style scoped>
/* 遮罩层 */
.permission-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* 弹窗 */
.permission-modal {
  background: #fff;
  border-radius: 12px;
  width: 480px;
  max-width: 90vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  animation: slideUp 0.25s ease;
}

@keyframes slideUp {
  from { transform: translateY(30px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

/* 头部 */
.permission-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
}

.permission-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 8px;
}

.title-icon {
  font-size: 18px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #9ca3af;
  cursor: pointer;
  line-height: 1;
}

.close-btn:hover {
  color: #374151;
}

/* Tab */
.permission-tabs {
  display: flex;
  border-bottom: 1px solid #e5e7eb;
  padding: 0 20px;
}

.tab-btn {
  padding: 12px 16px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  font-size: 14px;
  color: #6b7280;
  transition: all 0.2s;
  position: relative;
}

.tab-btn:hover {
  color: #374151;
}

.tab-btn.active {
  color: #3b82f6;
  border-bottom-color: #3b82f6;
}

.tab-badge {
  display: inline-block;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 10px;
  margin-left: 4px;
}

/* 内容区 */
.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.section-label {
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* 邀请表单 */
.invite-section {
  margin-bottom: 20px;
}

.invite-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.invite-input {
  width: 100%;
  padding: 10px 12px;
  border: 2px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  background: #fff;
  box-sizing: border-box;
}

.invite-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
}

.invite-select {
  padding: 10px 12px;
  border: 2px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  background: #fff;
  cursor: pointer;
}

/* 成员列表 */
.member-count {
  color: #9ca3af;
  font-weight: normal;
  margin-left: 4px;
}

.member-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.member-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #f9fafb;
  border-radius: 6px;
}

.member-icon {
  font-size: 14px;
}

.member-name {
  flex: 1;
  font-size: 14px;
  color: #1f2937;
}

.role-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.role-owner {
  background: #fef3c7;
  color: #92400e;
}

.role-maintainer {
  background: #dbeafe;
  color: #1e40af;
}

.role-contributor {
  background: #d1fae5;
  color: #065f46;
}

.role-reader {
  background: #f3f4f6;
  color: #4b5563;
}

.btn-revoke {
  background: none;
  border: none;
  color: #ef4444;
  font-size: 12px;
  cursor: pointer;
  padding: 2px 6px;
}

.btn-revoke:hover {
  text-decoration: underline;
}

/* 角色提示 */
.role-hint {
  margin-top: 16px;
  padding: 10px;
  background: #eff6ff;
  border-radius: 6px;
  font-size: 13px;
  color: #1e40af;
}

.hint-detail {
  color: #6b7280;
  margin-left: 4px;
}

/* 待审批列表 */
.pending-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pending-item {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafafa;
}

.pending-header {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
}

.pending-type {
  font-weight: 500;
  color: #374151;
}

.pending-user {
  color: #6b7280;
}

.pending-time {
  color: #9ca3af;
  margin-left: auto;
}

.pending-desc {
  font-size: 13px;
  color: #4b5563;
  margin-bottom: 10px;
  word-break: break-all;
}

.pending-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.review-note-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
}

/* 通用按钮 */
.btn {
  padding: 8px 16px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.15s;
}

.btn-sm {
  padding: 5px 12px;
  font-size: 13px;
}

.btn-primary {
  background: #3b82f6;
  color: #fff;
}

.btn-primary:hover {
  background: #2563eb;
}

.btn-success {
  background: #10b981;
  color: #fff;
}

.btn-success:hover {
  background: #059669;
}

.btn-danger {
  background: #ef4444;
  color: #fff;
}

.btn-danger:hover {
  background: #dc2626;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 空状态 */
.empty-hint {
  text-align: center;
  padding: 30px;
  color: #9ca3af;
  font-size: 13px;
}

/* 加载动画 */
.spinner-sm {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
