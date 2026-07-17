<template>
  <Teleport to="body">
    <Transition name="tooltip-fade">
      <div
        v-if="visible && node"
        class="graph-node-tooltip"
        :style="tooltipStyle"
        @mouseenter="onTooltipEnter"
        @mouseleave="onTooltipLeave"
      >
        <!-- 头部：名称 + 类型 -->
        <div class="tooltip-header">
          <h4 class="tooltip-title">{{ node.label || node.name || '未命名' }}</h4>
          <span class="tooltip-type-badge" :class="'type-' + (node.type || 'concept')">
            {{ typeLabel(node.type) }}
          </span>
        </div>

        <!-- 描述 -->
        <div v-if="node.description" class="tooltip-section">
          <div class="tooltip-label">描述</div>
          <div class="tooltip-description">{{ node.description }}</div>
        </div>

        <!-- 来源 Chunk -->
        <div v-if="node.source_chunks && node.source_chunks.length > 0" class="tooltip-section">
          <div class="tooltip-label">
            来源片段 ({{ node.source_chunks.length }} 个)
          </div>
          <div class="tooltip-source-list">
            <span
              v-for="chunk in node.source_chunks.slice(0, 5)"
              :key="chunk"
              class="tooltip-source-tag"
            >{{ chunk.slice(0, 16) }}{{ chunk.length > 16 ? '...' : '' }}</span>
            <span v-if="node.source_chunks.length > 5" class="tooltip-more">
              +{{ node.source_chunks.length - 5 }} 个
            </span>
          </div>
        </div>

        <!-- 关联媒体 -->
        <div v-if="node.media_refs && node.media_refs.length > 0" class="tooltip-section">
          <div class="tooltip-label">
            关联媒体 ({{ node.media_refs.length }} 个)
          </div>
          <div
            class="tooltip-media-list"
            :class="{ 'single-image': node.media_refs.length === 1 }"
          >
            <div
              v-for="(ref, idx) in node.media_refs.slice(0, 6)"
              :key="idx"
              class="tooltip-media-item"
              :class="{ 'single': node.media_refs.length === 1 }"
            >
              <!-- 图片缩略图 -->
              <div
                v-if="isImageType(ref)"
                class="tooltip-media-thumb"
                :class="{ 'single': node.media_refs.length === 1 }"
              >
                <img
                  v-if="ref.thumbnail_path || ref.path"
                  :src="getMediaUrl(ref.thumbnail_path || ref.path)"
                  :alt="ref.caption || '图片'"
                  loading="lazy"
                  @error="onImageError"
                />
                <div v-else class="tooltip-media-placeholder">
                  {{ getMediaTypeLabel(ref) }}
                </div>
              </div>
              <!-- 公式：LaTeX 渲染 -->
              <div v-else-if="isFormulaType(ref)" class="tooltip-media-formula" v-html="renderFormula(ref)">
              </div>
              <!-- 表格占位 -->
              <div v-else class="tooltip-media-text">
                <span class="tooltip-media-icon">{{ getMediaIcon(ref) }}</span>
                <span class="tooltip-media-caption">{{ ref.caption || getMediaTypeLabel(ref) }}</span>
              </div>
            </div>
            <div v-if="node.media_refs.length > 6" class="tooltip-more">
              +{{ node.media_refs.length - 6 }} 个媒体
            </div>
          </div>
        </div>

        <!-- 底部提示 -->
        <div class="tooltip-footer">
          点击节点查看详情
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'
import { renderLatex } from '../../utils/latex.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  node: { type: Object, default: null },
  position: { type: Object, default: () => ({ x: 0, y: 0 }) },
})

const emit = defineEmits(['update:visible'])

// 防止 tooltip 内部鼠标进入时意外关闭
let tooltipHover = false

function onTooltipEnter() {
  tooltipHover = true
}

function onTooltipLeave() {
  tooltipHover = false
  emit('update:visible', false)
}

// 计算 tooltip 位置：节点右侧偏移，带边界检测
const tooltipStyle = computed(() => {
  const offsetX = 20
  const offsetY = -10
  const tooltipWidth = 400   /* LA-035-P28: 与 max-width 一致 */
  const tooltipHeight = 350  /* LA-035-P28: 预估高度 */

  let left = props.position.x + offsetX
  let top = props.position.y + offsetY

  // LA-035-P28: 右边界检测
  const viewportWidth = window.innerWidth
  if (left + tooltipWidth > viewportWidth - 20) {
    left = props.position.x - tooltipWidth - offsetX
  }
  // LA-035-P28: 下边界检测
  const viewportHeight = window.innerHeight
  if (top + tooltipHeight > viewportHeight - 20) {
    top = viewportHeight - tooltipHeight - 20
  }
  // LA-035-P28: 上边界检测
  if (top < 10) {
    top = 10
  }
  // LA-035-P28: 左边界检测
  if (left < 10) {
    left = 10
  }

  return {
    left: `${left}px`,
    top: `${top}px`,
  }
})

function typeLabel(type) {
  const map = {
    'definition': '定义', 'law': '规律', 'application': '应用', 'extension': '扩展',
    'requirement': '需求', 'sub_requirement': '子需求',
    'technology': '技术', 'sub_technology': '子技术', 'concept': '概念',
  }
  return map[type] || type || '概念'
}

function isImageType(ref) {
  const t = (ref.type || ref.media_type || '').toLowerCase()
  return t.includes('image') || t.includes('图片') || t.includes('fig') ||
    (!t.includes('table') && !t.includes('formula') && !t.includes('公式'))
}

function getMediaTypeLabel(ref) {
  const t = (ref.type || ref.media_type || '').toLowerCase()
  if (t.includes('table') || t.includes('表格')) return '表格'
  if (t.includes('formula') || t.includes('公式') || t.includes('math')) return '公式'
  return '图片'
}

function getMediaIcon(ref) {
  const t = (ref.type || ref.media_type || '').toLowerCase()
  if (t.includes('table') || t.includes('表格')) return '📊'
  if (t.includes('formula') || t.includes('公式') || t.includes('math')) return '🧮'
  return '🖼️'
}

// 判断是否为公式类型
function isFormulaType(ref) {
  const t = (ref.type || ref.media_type || '').toLowerCase()
  return t.includes('formula') || t.includes('公式') || t.includes('math')
}

// 渲染公式：使用 katex 渲染为 HTML
function renderFormula(ref) {
  const latex = ref.latex || ref.description || ''
  const display = ref.display === 'block'
  if (!latex.trim()) return '<span class="tooltip-media-icon">🧮</span> 公式'
  return renderLatex(latex, display)
}

function getMediaUrl(path) {
  if (!path) return ''
  if (path.startsWith('http')) return path
  // LA-035: Windows 路径反斜杠替换为正斜杠，确保 URL 正确
  const normalizedPath = path.replace(/\\/g, '/')
  // 本地路径：通过后端静态文件服务
  return `${window.location.origin}/api/media/${encodeURIComponent(normalizedPath)}`
}

function onImageError(e) {
  e.target.style.display = 'none'
  const placeholder = e.target.parentElement.querySelector('.tooltip-media-placeholder')
  if (placeholder) placeholder.style.display = 'flex'
}
</script>

<style scoped>
/* KaTeX 公式样式（全局引入 CSS 后配合 scoped 生效） */
@import 'katex/dist/katex.min.css';

.graph-node-tooltip {
  position: fixed;
  z-index: 9999;
  min-width: 240px;
  max-width: 400px;  /* LA-035-P28: 增大到 400px 给图片更多空间 */
  max-height: 80vh;  /* LA-035-P28: 限制最大高度，避免超出屏幕 */
  overflow-y: auto;  /* LA-035-P28: 内容过多时滚动 */
  background: var(--bg-card, #ffffff);
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  padding: 16px;
  font-size: 13px;
  color: var(--text-primary, #2c3e50);
  pointer-events: auto;
}

/* 暗色主题适配 */
@media (prefers-color-scheme: dark) {
  .graph-node-tooltip {
    background: #1e1e2e;
    border-color: #3d3d5c;
    color: #e0e0e0;
  }
}

.tooltip-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-color, #eee);
}

.tooltip-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
  word-break: break-word;
  flex: 1;
}

.tooltip-type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.type-concept, .type-definition, .type-law, .type-application, .type-extension {
  background: rgba(46, 204, 113, 0.15);
  color: #27ae60;
}

.type-requirement, .type-sub_requirement {
  background: rgba(231, 76, 60, 0.15);
  color: #c0392b;
}

.type-technology, .type-sub_technology {
  background: rgba(52, 152, 219, 0.15);
  color: #2980b9;
}

.tooltip-section {
  margin-bottom: 12px;
}

.tooltip-label {
  font-size: 11px;
  color: var(--text-muted, #7f8c8d);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.tooltip-description {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary, #555);
  word-break: break-word;
}

.tooltip-source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.tooltip-source-tag {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  background: var(--bg-hover, #f0f0f0);
  color: var(--text-secondary, #666);
}

.tooltip-media-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);  /* LA-035-P28: 2 列网格 */
  gap: 8px;
}

/* LA-035-P28: 单张图片时单列显示 */
.tooltip-media-list.single-image {
  grid-template-columns: 1fr;
}

.tooltip-media-item {
  min-width: 0;  /* 防止 grid item 溢出 */
}

.tooltip-media-item.single {
  grid-column: 1 / -1;
}

.tooltip-media-thumb {
  width: 100%;
  aspect-ratio: 16 / 10;  /* LA-035-P28: 统一容器比例 */
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-hover, #f5f5f5);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* LA-035-P28: 单张图片时更大的显示区域 */
.tooltip-media-thumb.single {
  aspect-ratio: 16 / 9;
  max-height: 220px;
}

.tooltip-media-thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;  /* LA-035-P28: 保持比例，不裁剪 */
  background: var(--bg-hover, #f5f5f5);
}

.tooltip-media-placeholder {
  display: none;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--text-muted, #999);
}

.tooltip-media-text {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: var(--bg-hover, #f5f5f5);
  border-radius: 4px;
  font-size: 12px;
}

.tooltip-media-icon {
  font-size: 14px;
}

.tooltip-media-caption {
  color: var(--text-secondary, #666);
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 公式渲染容器 */
.tooltip-media-formula {
  padding: 8px 12px;
  background: var(--bg-hover, #f5f5f5);
  border-radius: 6px;
  font-size: 14px;
  line-height: 1.6;
  max-width: 280px;
  overflow-x: auto;
}

/* 暗色主题下公式文字反色 */
@media (prefers-color-scheme: dark) {
  .tooltip-media-formula :deep(.katex .mathnormal) {
    color: #e0e0e0;
  }
}

.tooltip-more {
  font-size: 11px;
  color: var(--text-muted, #999);
  padding: 4px 0;
}

.tooltip-footer {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-color, #eee);
  font-size: 11px;
  color: var(--text-muted, #999);
  text-align: center;
}

/* 过渡动画 */
.tooltip-fade-enter-active,
.tooltip-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.tooltip-fade-enter-from,
.tooltip-fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
