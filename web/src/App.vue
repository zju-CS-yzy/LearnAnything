<template>
  <div id="app">
    <!-- 左侧边栏 -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <div class="logo">📚 LearnAnything</div>
        <button class="toggle-btn" @click="sidebarCollapsed = !sidebarCollapsed">
          {{ sidebarCollapsed ? '>' : '<' }}
        </button>
      </div>
      <div class="subject-list">
        <div
          v-for="subject in subjects"
          :key="subject.id"
          class="subject-item"
          :class="{ active: currentSubject === subject.id }"
          @click="selectSubject(subject.id)"
        >
          <span class="subject-icon">{{ subject.icon }}</span>
          <span v-if="!sidebarCollapsed" class="subject-name">{{ subject.name }}</span>
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="main-content">
      <GraphView
        :subject="currentSubject"
        @node-selected="onNodeSelected"
      />
    </main>

    <!-- 右侧详情面板 -->
    <div class="detail-panel" v-if="selectedNode" :class="{ show: selectedNode }">
      <button class="close-btn" @click="selectedNode = null">✕</button>
      <h3>{{ selectedNode.name }}</h3>
      <div class="node-meta">
        <span class="node-type" :class="selectedNode.type">{{ typeLabel(selectedNode.type) }}</span>
      </div>
      <div class="node-description" v-if="selectedNode.description">
        {{ selectedNode.description }}
      </div>
      <div class="node-source" v-if="selectedNode.source_chunks">
        <div class="section-title">来源</div>
        <div class="source-list">{{ selectedNode.source_chunks }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import GraphView from './components/GraphView.vue'

const sidebarCollapsed = ref(false)
const currentSubject = ref('generic')
const selectedNode = ref(null)
const subjects = ref([
  { id: 'generic', name: '通用', icon: '📖' },
  { id: 'ai_llm', name: 'AI大模型', icon: '🤖' },
])

onMounted(() => {
  // 加载学科列表
  loadSubjects()
})

async function loadSubjects() {
  try {
    const resp = await fetch(`${window.location.origin}/api/subjects`)
    if (resp.ok) {
      const data = await resp.json()
      if (data.subjects?.length > 0) {
        subjects.value = data.subjects.map(s => ({
          id: s.id,
          name: s.name,
          icon: s.icon || '📖'
        }))
      }
    }
  } catch (e) {
    console.error('加载学科失败:', e)
  }
}

function selectSubject(id) {
  currentSubject.value = id
}

function onNodeSelected(node) {
  selectedNode.value = node
}

function typeLabel(type) {
  const labels = {
    requirement: '需求',
    sub_requirement: '子需求',
    technology: '技术',
    sub_technology: '子技术',
    concept: '概念'
  }
  return labels[type] || type
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #1e1e2e;
  color: #cdd6f4;
  overflow: hidden;
}

#app {
  display: flex;
  width: 100vw;
  height: 100vh;
}

/* 侧边栏 */
.sidebar {
  width: 220px;
  background: #181825;
  border-right: 1px solid #313244;
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
  flex-shrink: 0;
}

.sidebar.collapsed {
  width: 60px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid #313244;
}

.logo {
  font-size: 16px;
  font-weight: bold;
  color: #cdd6f4;
  white-space: nowrap;
  overflow: hidden;
}

.sidebar.collapsed .logo {
  display: none;
}

.toggle-btn {
  background: none;
  border: none;
  color: #cdd6f4;
  cursor: pointer;
  font-size: 14px;
  padding: 4px;
}

.subject-list {
  padding: 8px;
  overflow-y: auto;
}

.subject-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
  gap: 12px;
}

.subject-item:hover {
  background: #313244;
}

.subject-item.active {
  background: #3b82f6;
}

.subject-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.subject-name {
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
}

/* 主内容区 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

/* 详情面板 */
.detail-panel {
  position: fixed;
  right: -350px;
  top: 0;
  width: 320px;
  height: 100vh;
  background: #181825;
  border-left: 1px solid #313244;
  padding: 20px;
  z-index: 100;
  transition: right 0.3s ease;
  overflow-y: auto;
}

.detail-panel.show {
  right: 0;
}

.close-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  background: none;
  border: none;
  color: #cdd6f4;
  cursor: pointer;
  font-size: 18px;
}

.detail-panel h3 {
  margin-bottom: 12px;
  font-size: 18px;
  color: #cdd6f4;
}

.node-meta {
  margin-bottom: 16px;
}

.node-type {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
}

.node-type.requirement { background: #3b82f6; }
.node-type.sub_requirement { background: #60a5fa; }
.node-type.technology { background: #10b981; }
.node-type.sub_technology { background: #6ee7b7; }
.node-type.concept { background: #8b5cf6; }

.node-description {
  font-size: 14px;
  line-height: 1.6;
  color: #cdd6f4;
  margin-bottom: 20px;
}

.section-title {
  font-size: 12px;
  font-weight: bold;
  color: #7f849c;
  margin-bottom: 8px;
  text-transform: uppercase;
}

.source-list {
  font-size: 12px;
  color: #a6adc8;
  line-height: 1.5;
}
</style>
