<template>
  <!-- LA-UI-001 M2: 评测结果卡片（群聊测评完成后回显，字段对齐 /api/evaluate/submit 响应） -->
  <div class="result-card">
    <div class="rc-header">
      <span class="rc-icon">📊</span>
      <span class="rc-title">评测结果</span>
      <span v-if="result.level" class="rc-level">「{{ result.level }}」</span>
      <span v-if="topic" class="rc-topic">{{ topic }}</span>
    </div>

    <div class="rc-body">
      <div class="rc-score-ring">
        <div class="rc-percentage">{{ percentage }}<span class="rc-pct-sign">%</span></div>
        <div class="rc-score">{{ result.total_score ?? 0 }} / {{ result.max_score ?? 0 }} 分</div>
      </div>
      <div class="rc-stats">
        <div class="rc-stat">
          <span class="rc-stat-label">正确</span>
          <span class="rc-stat-value rc-ok">{{ result.correct_count ?? 0 }}</span>
        </div>
        <div class="rc-stat">
          <span class="rc-stat-label">错误</span>
          <span class="rc-stat-value rc-bad">{{ wrongCount }}</span>
        </div>
        <div class="rc-stat">
          <span class="rc-stat-label">总题数</span>
          <span class="rc-stat-value">{{ result.total_questions ?? 0 }}</span>
        </div>
      </div>
    </div>

    <div v-if="result.summary" class="rc-summary">{{ result.summary }}</div>

    <div v-if="weakPoints.length" class="rc-weak">
      <span class="rc-weak-label">薄弱点：</span>
      <span v-for="(w, i) in weakPoints" :key="i" class="rc-weak-tag">{{ w }}</span>
    </div>

    <div class="rc-footer">已记录到学习进度 · 测评历史</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // /api/evaluate/submit 响应或其持久化子集：
  // { total_score, max_score, percentage, correct_count, total_questions,
  //   level, summary, weak_areas, strong_areas, details? }
  result: { type: Object, required: true },
  topic: { type: String, default: '' },
})

const percentage = computed(() => Math.round(props.result.percentage ?? 0))
const wrongCount = computed(() =>
  (props.result.total_questions ?? 0) - (props.result.correct_count ?? 0)
)
const weakPoints = computed(() => props.result.weak_areas || props.result.weak_points || [])
</script>

<style scoped>
.result-card {
  margin-top: 10px;
  background: var(--bg-input);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.rc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--bg-hover);
  border-bottom: 1px solid var(--border-color);
}

.rc-icon { font-size: 15px; }
.rc-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.rc-level { font-size: 12px; color: var(--accent-primary); }
.rc-topic { font-size: 12px; color: var(--text-secondary); }

.rc-body {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 14px;
}

.rc-score-ring { text-align: center; }
.rc-percentage {
  font-size: 26px;
  font-weight: 700;
  color: var(--accent-primary);
}
.rc-pct-sign { font-size: 14px; }
.rc-score { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }

.rc-stats { display: flex; gap: 18px; }
.rc-stat { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.rc-stat-label { font-size: 11px; color: var(--text-muted); }
.rc-stat-value { font-size: 16px; font-weight: 600; color: var(--text-primary); }
.rc-ok { color: #7ec699; }
.rc-bad { color: #e06c75; }

.rc-summary {
  padding: 0 14px 10px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.rc-weak {
  padding: 8px 14px;
  border-top: 1px solid var(--border-color);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.rc-weak-label { color: var(--text-secondary); }
.rc-weak-tag {
  color: #e0a35c;
  background: var(--bg-active);
  border-radius: 4px;
  padding: 1px 8px;
}

.rc-footer {
  padding: 6px 14px;
  border-top: 1px solid var(--border-color);
  font-size: 11px;
  color: var(--text-muted);
}
</style>
