<template>
  <div v-if="profile" class="concept-evidence">
    <div class="fact-row">
      <span v-for="(count, type) in profile.types || {}" :key="type" class="type-chip">
        {{ type }} · {{ count }}
      </span>
      <span class="occurrences">出现 {{ profile.occurrences || 0 }} 次</span>
    </div>

    <div v-if="(profile.aliases || []).length" class="evidence-group">
      <span class="group-label">别名</span>
      <span>{{ profile.aliases.join('、') }}</span>
    </div>

    <div v-if="(profile.descriptions || []).length" class="evidence-group">
      <span class="group-label">描述</span>
      <RichText
        v-for="description in profile.descriptions"
        :key="description"
        class="description"
        :content="description"
      />
    </div>

    <details v-if="(profile.source_chunks || []).length">
      <summary>来源片段 {{ profile.source_chunks.length }}</summary>
      <ul>
        <li v-for="chunk in profile.source_chunks" :key="chunk">{{ chunk }}</li>
      </ul>
    </details>
  </div>
</template>

<script setup>
import RichText from '../../common/RichText.vue'

defineProps({
  profile: { type: Object, default: null },
})
</script>

<style scoped>
.concept-evidence { display: grid; gap: 12px; color: #555249; font-size: 13px; }
.fact-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.type-chip { padding: 4px 7px; border-radius: 6px; background: #ece9e1; color: #3e3b35; }
.occurrences { color: #77736a; }
.evidence-group { display: grid; gap: 5px; }
.group-label { color: #77736a; font-size: 11px; font-weight: 650; letter-spacing: .04em; text-transform: uppercase; }
.description { line-height: 1.55; }
details { border-top: 1px solid #ebe7de; padding-top: 9px; }
summary { cursor: pointer; color: #5b63b9; }
ul { margin: 8px 0 0; padding-left: 18px; }
li { margin-bottom: 4px; overflow-wrap: anywhere; color: #716d64; }
</style>
