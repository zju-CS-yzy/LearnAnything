<template>
  <div class="formula-media" :class="{ compact }">
    <span v-if="label" class="formula-media-label">{{ label }}</span>
    <div class="formula-media-content" v-html="html" />
    <code v-if="!html" class="formula-media-fallback">{{ latex || '公式内容不可用' }}</code>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { renderLatex } from '../../utils/latex.js'

const props = defineProps({
  latex: { type: String, default: '' },
  display: { type: Boolean, default: true },
  label: { type: String, default: '公式' },
  compact: { type: Boolean, default: false },
})

const html = computed(() => renderLatex(props.latex, props.display))
</script>
