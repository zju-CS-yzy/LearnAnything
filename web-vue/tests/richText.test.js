import assert from 'node:assert/strict'
import test from 'node:test'

import { extractMathSegments, renderRichText } from '../src/utils/richText.js'

test('renders inline and display LaTeX without losing Markdown', () => {
  const html = renderRichText('由 **质能关系** $E=mc^2$ 可得：\n\n$$p^2c^2 + m^2c^4$$')

  assert.match(html, /<strong>质能关系<\/strong>/)
  assert.match(html, /class="katex"/)
  assert.match(html, /math-inline/)
  assert.match(html, /math-display/)
  assert.doesNotMatch(html, /LAZXMATH/)
})

test('supports bracket and parenthesis delimiters used by document extractors', () => {
  const { formulas } = extractMathSegments('行内 \\(x^2\\)，块级 \\[y=mx+b\\]')

  assert.deepEqual(formulas.map(item => [item.latex, item.display]), [
    ['x^2', false],
    ['y=mx+b', true],
  ])
})

test('does not mistake a plain numeric price for a formula', () => {
  const html = renderRichText('价格是 $5$，不是公式。')

  assert.doesNotMatch(html, /class="katex"/)
  assert.match(html, /\$5\$/)
})

test('escapes raw HTML while preserving safe formula output', () => {
  const html = renderRichText('<script>alert(1)</script> $\\frac{1}{2}$')

  assert.doesNotMatch(html, /<script>/)
  assert.match(html, /&lt;script&gt;/)
  assert.match(html, /class="katex"/)
})

test('plain question text mode still renders LaTeX', () => {
  const html = renderRichText('求 $\\gamma=1/\\sqrt{1-v^2/c^2}$', { markdown: false })

  assert.match(html, /class="katex"/)
  assert.doesNotMatch(html, /<p>/)
})

test('inline mode renders emphasis and formulas without block wrappers', () => {
  const html = renderRichText('参考 **公式** $E=mc^2$', { inline: true })

  assert.match(html, /<strong>公式<\/strong>/)
  assert.match(html, /class="katex"/)
  assert.doesNotMatch(html, /<p>/)
})
