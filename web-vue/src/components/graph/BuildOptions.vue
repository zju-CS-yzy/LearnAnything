<template>
  <div v-if="visible" class="build-options-overlay">
    <div class="build-options-panel">
      <div class="build-options-header">
        <h2>🏗️ 图谱生成配置</h2>
        <p class="build-options-subtitle">选择参数后一键生成完整的知识图谱</p>
      </div>

      <div class="build-options-body">
        <!-- 范式选择 -->
        <div class="option-section">
          <div class="option-label">
            <span class="option-icon">🧩</span>
            <span>分解范式</span>
            <span class="option-required">必选</span>
          </div>
          <p class="option-desc">选择适合你知识库内容类型的分解策略</p>
          <div class="paradigm-cards">
            <div
              v-for="p in paradigms"
              :key="p.id"
              class="paradigm-card"
              :class="{ active: options.paradigm === p.id }"
              @click="options.paradigm = p.id"
            >
              <div class="paradigm-radio">
                <div class="radio-dot" :class="{ checked: options.paradigm === p.id }"></div>
              </div>
              <div class="paradigm-info">
                <div class="paradigm-name">{{ p.name }}</div>
                <div class="paradigm-desc">{{ p.description }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 分解粒度 -->
        <div class="option-section">
          <div class="option-label">
            <span class="option-icon">🔬</span>
            <span>分解粒度</span>
            <span class="option-tag experimental">实验性</span>
          </div>
          <p class="option-desc">控制概念提取的精细程度（当前版本仅做记录）</p>
          <div class="granularity-slider">
            <div class="slider-labels">
              <span :class="{ active: options.granularity === 'coarse' }">粗</span>
              <span :class="{ active: options.granularity === 'medium' }">中</span>
              <span :class="{ active: options.granularity === 'fine' }">细</span>
            </div>
            <input
              type="range"
              min="0"
              max="2"
              step="1"
              :value="['coarse','medium','fine'].indexOf(options.granularity)"
              @input="options.granularity = ['coarse','medium','fine'][$event.target.value]"
              class="slider-input"
            />
          </div>
        </div>

        <!-- 附加选项 -->
        <div class="option-section">
          <div class="option-label">
            <span class="option-icon">⚙️</span>
            <span>附加选项</span>
          </div>
          <div class="checkbox-group">
            <label class="checkbox-item">
              <input type="checkbox" v-model="options.withSemantic" />
              <span class="checkbox-text">构建语义层（自动提取概念并建立语义关系）</span>
            </label>
            <label class="checkbox-item">
              <input type="checkbox" v-model="options.withDedupe" />
              <span class="checkbox-text">执行概念去重（合并相似概念，生成规范概念表）</span>
            </label>
            <label class="checkbox-item">
              <input type="checkbox" v-model="options.forceRebuild" />
              <span class="checkbox-text">强制重建（删除已有图谱数据后重新生成）</span>
            </label>
          </div>
        </div>
      </div>

      <!-- 进度提示 -->
      <div v-if="isBuilding" class="build-progress">
        <span class="spinner-inline"></span>
        <span>{{ progress || '正在生成图谱...' }}</span>
      </div>

      <!-- 操作按钮 -->
      <div class="build-options-footer">
        <button class="btn btn-lg" @click="$emit('close')" :disabled="isBuilding">取消</button>
        <button class="btn btn-lg btn-primary" @click="$emit('confirm', { ...options })" :disabled="isBuilding">
          <span v-if="isBuilding" class="spinner-inline"></span>
          <span v-else>🚀 开始生成</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * BuildOptions — 图谱构建配置覆盖层
 * 范式选择、粒度控制、附加选项
 */

import { reactive } from 'vue'

defineProps({
  visible: { type: Boolean, default: false },
  isBuilding: { type: Boolean, default: false },
  progress: { type: String, default: '' },
  paradigms: {
    type: Array,
    default: () => [
      { id: 'theory', name: '理论归纳', description: '适合理论学科（物理、数学等）：定义→规律→应用→扩展' },
      { id: 'engineering', name: '工程分解', description: '适合技术类知识：需求→技术→子需求→子技术' },
      { id: 'hierarchical', name: '层级归纳', description: '适合通用知识：事实→概念→方法→评价' },
    ]
  }
})

defineEmits(['close', 'confirm'])

const options = reactive({
  paradigm: 'theory',
  granularity: 'medium',
  withSemantic: true,
  withDedupe: true,
  forceRebuild: false,
})
</script>

<style scoped>
.build-options-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-page, #f5f6fa);
  z-index: 50;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 40px 20px;
  overflow-y: auto;
}

.build-options-panel {
  background: var(--bg-card, #fff);
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
  width: 100%;
  max-width: 640px;
  padding: 32px;
}

.build-options-header {
  text-align: center;
  margin-bottom: 28px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
}

.build-options-header h2 {
  margin: 0 0 8px 0;
  font-size: var(--font-size-xl);
  color: var(--text-primary, #2c3e50);
}

.build-options-subtitle {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-muted, #7f8c8d);
}

.build-options-body {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.option-section {
  padding: 16px;
  background: var(--bg-hover, #f8f9fa);
  border-radius: 8px;
  border: 1px solid var(--border-color, #e8e8e8);
}

.option-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary, #2c3e50);
  margin-bottom: 8px;
}

.option-icon { font-size: 18px; }

.option-required {
  font-size: 10px;
  padding: 2px 6px;
  background: #fdeaea;
  color: #e74c3c;
  border-radius: 4px;
  font-weight: 500;
}

.option-tag {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}

.option-tag.experimental {
  background: #fff3e0;
  color: #f57c00;
}

.option-desc {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  margin: 0 0 12px 0;
  line-height: 1.5;
}

/* 范式卡片 */
.paradigm-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.paradigm-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  background: var(--bg-card, #fff);
  border: 2px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.paradigm-card:hover {
  border-color: var(--accent-primary, #3498db);
  box-shadow: 0 2px 8px rgba(52, 152, 219, 0.1);
}

.paradigm-card.active {
  border-color: var(--accent-primary, #3498db);
  background: #f0f7ff;
}

.paradigm-radio {
  padding-top: 2px;
  flex-shrink: 0;
}

.radio-dot {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border-color, #ccc);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.radio-dot.checked {
  border-color: var(--accent-primary, #3498db);
  background: var(--accent-primary, #3498db);
}

.radio-dot.checked::after {
  content: '';
  width: 6px;
  height: 6px;
  background: #fff;
  border-radius: 50%;
}

.paradigm-info { flex: 1; }

.paradigm-name {
  font-weight: 600;
  font-size: var(--font-size-sm);
  color: var(--text-primary, #2c3e50);
  margin-bottom: 4px;
}

.paradigm-desc {
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
  line-height: 1.4;
}

/* 粒度滑块 */
.granularity-slider { padding: 8px 0; }

.slider-labels {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: var(--font-size-xs);
  color: var(--text-muted, #7f8c8d);
}

.slider-labels span.active {
  color: var(--accent-primary, #3498db);
  font-weight: 600;
}

.slider-input {
  width: 100%;
  height: 6px;
  -webkit-appearance: none;
  appearance: none;
  background: var(--border-color, #e0e0e0);
  border-radius: 3px;
  outline: none;
}

.slider-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  background: var(--accent-primary, #3498db);
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}

.slider-input::-moz-range-thumb {
  width: 18px;
  height: 18px;
  background: var(--accent-primary, #3498db);
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}

/* 复选框 */
.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.checkbox-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
  font-size: var(--font-size-sm);
  color: var(--text-secondary, #555);
}

.checkbox-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  margin-top: 2px;
  accent-color: var(--accent-primary, #3498db);
  cursor: pointer;
}

.checkbox-text { line-height: 1.4; }

/* 进度提示 */
.build-progress {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 16px;
  margin: 16px 0;
  background: #e8f4fd;
  border-radius: 8px;
  color: var(--accent-primary, #2980b9);
  font-size: var(--font-size-sm);
}

.build-progress .spinner-inline {
  border-color: rgba(41, 128, 185, 0.2);
  border-top-color: #2980b9;
}

/* 底部按钮 */
.build-options-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 20px;
  margin-top: 20px;
  border-top: 1px solid var(--border-color, #e0e0e0);
}

.btn {
  padding: 6px 12px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 4px;
  background: var(--bg-card, #fff);
  color: var(--text-primary, #2c3e50);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all 0.2s;
}

.btn:hover { background: var(--bg-hover, #f0f0f0); }

.btn-primary {
  background: var(--accent-primary, #3498db);
  color: #fff;
  border-color: var(--accent-primary, #3498db);
}

.btn-primary:hover { background: #2980b9; }

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-lg {
  padding: 10px 24px;
  font-size: var(--font-size-sm);
}

.spinner-inline {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
