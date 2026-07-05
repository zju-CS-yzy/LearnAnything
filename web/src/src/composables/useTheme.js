/**
 * 全局主题管理 Composable
 * 支持暗色/亮色主题切换 + 字体大小调节
 */
import { ref, watch } from 'vue'

const STORAGE_KEY = 'la_theme_settings'

// 默认设置
const defaults = {
  theme: 'dark',
  fontSize: 'medium', // small | medium | large
}

// 从 localStorage 读取
function loadSettings() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) return { ...defaults, ...JSON.parse(saved) }
  } catch {}
  return { ...defaults }
}

const settings = ref(loadSettings())

// 字体大小映射（CSS 变量值）
const fontSizeMap = {
  small: '14px',
  medium: '16px',
  large: '18px',
}

// 监听变化并持久化 + 应用到 DOM
watch(settings, (val) => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(val))
  applyToDOM(val)
}, { deep: true })

/**
 * 应用主题设置到 DOM
 */
function applyToDOM(val) {
  const html = document.documentElement

  // 主题
  html.setAttribute('data-theme', val.theme)

  // 字体大小
  html.style.setProperty('--font-size-base', fontSizeMap[val.fontSize] || fontSizeMap.medium)

  // 同步到 body（让 Cytoscape 等外部库也能感知）
  document.body.setAttribute('data-theme', val.theme)
}

// 初始化时应用
applyToDOM(settings.value)

export function useTheme() {
  function setTheme(theme) {
    settings.value.theme = theme
  }

  function setFontSize(size) {
    settings.value.fontSize = size
  }

  function toggleTheme() {
    settings.value.theme = settings.value.theme === 'dark' ? 'light' : 'dark'
  }

  return {
    theme: settings,
    setTheme,
    setFontSize,
    toggleTheme,
  }
}
