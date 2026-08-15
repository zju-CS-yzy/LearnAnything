<template>
  <component
    :is="inline ? 'span' : 'div'"
    class="rich-text"
    :class="{ 'rich-text-inline': inline }"
    v-html="html"
  />
</template>

<script setup>
import { computed } from 'vue'
import { renderRichText } from '../../utils/richText.js'

const props = defineProps({
  content: { type: [String, Number], default: '' },
  inline: { type: Boolean, default: false },
  markdown: { type: Boolean, default: true },
})

const html = computed(() => renderRichText(String(props.content ?? ''), {
  markdown: props.markdown,
  inline: props.inline,
}))
</script>
