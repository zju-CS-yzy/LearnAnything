/**
 * LaTeX 渲染工具函数
 * 封装 katex 渲染逻辑，提供统一的公式渲染接口
 */
import katex from 'katex'

export function normalizeLatex(value) {
  let latex = String(value || '').trim()
  if (!latex) return ''
  latex = latex.replace(/\/\//g, '\\')
  if (latex.startsWith('$$') && latex.endsWith('$$')) latex = latex.slice(2, -2).trim()
  else if (latex.startsWith('\\[') && latex.endsWith('\\]')) latex = latex.slice(2, -2).trim()
  else if (latex.startsWith('\\(') && latex.endsWith('\\)')) latex = latex.slice(2, -2).trim()
  else if (latex.startsWith('$') && latex.endsWith('$')) latex = latex.slice(1, -1).trim()
  return latex
}

/**
 * 渲染 LaTeX 公式为 HTML 字符串
 * @param {string} latex - LaTeX 公式文本
 * @param {boolean} displayMode - true 为块级展示（独立行），false 为行内展示
 * @returns {string} 渲染后的 HTML 字符串，失败时返回空字符串
 */
export function renderLatex(latex, displayMode = false) {
  latex = normalizeLatex(latex)
  if (!latex) return ''
  try {
    return katex.renderToString(latex, {
      displayMode,
      throwOnError: false,
      output: 'html',
      strict: 'warn',
      trust: false,
    })
  } catch (e) {
    console.warn('LaTeX 渲染失败:', e.message)
    return ''
  }
}
