import { marked } from 'marked'
import { renderLatex } from './latex.js'
import { withMediaAuth } from './media.js'

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function looksLikeMath(value) {
  const formula = String(value || '').trim()
  if (!formula || /^\d+(?:[.,]\d+)?$/.test(formula)) return false
  if (/\\[a-zA-Z]+|[_^{}=+\-*/<>]|[α-ωΑ-Ω∑∫√∞≈≤≥]/.test(formula)) return true
  return /^[a-zA-Z](?:\s*[a-zA-Z0-9])?$/.test(formula)
}

export function extractMathSegments(source) {
  const formulas = []
  const pattern = /(?<!\\)\$\$([\s\S]+?)(?<!\\)\$\$|\\\[([\s\S]+?)\\\]|\\\(([^\n]+?)\\\)|(?<!\\)\$([^\n$]+?)(?<!\\)\$/g
  const text = String(source ?? '').replace(pattern, (match, blockDollar, blockBracket, inlineParen, inlineDollar) => {
    const latex = blockDollar ?? blockBracket ?? inlineParen ?? inlineDollar ?? ''
    const display = blockDollar !== undefined || blockBracket !== undefined
    if (!display && !looksLikeMath(latex)) return match
    const index = formulas.push({ latex, display, raw: match }) - 1
    return `LAZXMATH${index}TOKEN`
  })
  return { text, formulas }
}

function safeMediaUrl(href) {
  let src = String(href || '').trim()
  if (!src) return ''
  if (/^javascript:/i.test(src)) return ''
  if (!/^(?:https?:|data:image\/|\/)/i.test(src)) src = `/api/media/${src}`
  if (src.startsWith('/api/media/')) {
    const pathPart = src.slice('/api/media/'.length)
    src = '/api/media/' + pathPart.split('/').map(segment => {
      try {
        return encodeURIComponent(decodeURIComponent(segment))
      } catch {
        return encodeURIComponent(segment)
      }
    }).join('/')
  }
  return withMediaAuth(src)
}

function createRenderer() {
  const renderer = new marked.Renderer()
  renderer.html = token => escapeHtml(typeof token === 'object' ? token.text : token)
  renderer.image = (href, title, text) => {
    if (typeof href === 'object' && href !== null) {
      const token = href
      href = token.href
      title = token.title
      text = token.text
    }
    const src = safeMediaUrl(href)
    if (!src) return ''
    return `<img src="${escapeHtml(src)}" alt="${escapeHtml(text)}" title="${escapeHtml(title)}" class="chat-inline-image" loading="lazy" />`
  }
  renderer.link = (href, title, text) => {
    if (typeof href === 'object' && href !== null) {
      const token = href
      href = token.href
      title = token.title
      text = token.text
    }
    const url = String(href || '')
    if (!/^(?:https?:|\/)/i.test(url)) return escapeHtml(text || url)
    return `<a href="${escapeHtml(url)}" title="${escapeHtml(title)}" target="_blank" rel="noopener noreferrer">${text || escapeHtml(url)}</a>`
  }
  return renderer
}

export function renderRichText(content, { markdown = true, inline = false } = {}) {
  if (content === null || content === undefined || content === '') return ''
  const { text, formulas } = extractMathSegments(content)
  let html
  try {
    const normalizedText = text.replace(/\\#/g, '#').replace(/&#35;/g, '#')
    html = markdown
      ? (inline ? marked.parseInline : marked.parse)(normalizedText, {
          breaks: true,
          renderer: createRenderer(),
          headerIds: false,
          mangle: false,
        })
      : escapeHtml(text).replace(/\n/g, '<br>')
  } catch {
    html = escapeHtml(text).replace(/\n/g, '<br>')
  }
  formulas.forEach((formula, index) => {
    const token = `LAZXMATH${index}TOKEN`
    const rendered = renderLatex(formula.latex, formula.display)
    const replacement = rendered
      ? `<span class="math-segment ${formula.display ? 'math-display' : 'math-inline'}">${rendered}</span>`
      : `<code class="math-fallback">${escapeHtml(formula.raw)}</code>`
    html = html.split(token).join(replacement)
  })
  return html
}
