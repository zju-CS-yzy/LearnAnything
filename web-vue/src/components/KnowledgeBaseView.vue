<template>
  <div class="kb-view">
    <header class="view-header">
      <div class="header-title">
        <span class="header-icon">🗂️</span>
        <span>知识库</span>
      </div>
    </header>

    <div class="view-content">
      <div class="empty-state card">
        <div class="empty-icon">📚</div>
        <div class="empty-title">知识库可视化</div>
        <div class="empty-desc">
          此功能正在开发中，计划实现：<br/>
          • 根据 chunk 之间的逻辑关联生成思维导图<br/>
          • 支持手动编辑节点关联和节点内容<br/>
          • 热重载：编辑后实时保存到向量库<br/>
          • 多维视角切换（按章节、按语义关联、按时间线）
        </div>
        <div class="empty-hint">
          当前可通过「导入」功能添加材料，「智能对话」功能进行问答测试
        </div>
      </div>

      <!-- 学科列表（占位） -->
      <div class="subjects-section card">
        <div class="section-title">已配置学科</div>
        <div class="subjects-list">
          <div class="subject-item">
            <span class="subject-icon">🧪</span>
            <div class="subject-info">
              <div class="subject-name">generic</div>
              <div class="subject-desc">通用知识库</div>
            </div>
            <span class="subject-status tag">活跃</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// 知识库视图 — 预留功能
// 阶段3 将在此实现思维导图可视化
</script>

<style scoped>
.kb-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.view-header {
  display: flex;
  align-items: center;
  padding: 0 24px;
  height: var(--header-height);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.view-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  min-height: 0;
}

.empty-state {
  max-width: 700px;
  margin: 0 auto 24px;
  text-align: center;
  padding: 40px 24px;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.empty-desc {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.8;
  margin-bottom: 16px;
}

.empty-hint {
  font-size: 13px;
  color: var(--text-muted);
  padding: 10px 16px;
  background: var(--bg-input);
  border-radius: var(--radius-sm);
  display: inline-block;
}

/* 学科列表 */
.subjects-section {
  max-width: 700px;
  margin: 0 auto;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text-primary);
}

.subjects-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.subject-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-input);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
}

.subject-icon {
  font-size: 24px;
}

.subject-info {
  flex: 1;
  min-width: 0;
}

.subject-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.subject-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.subject-status {
  font-size: 11px;
}
</style>
