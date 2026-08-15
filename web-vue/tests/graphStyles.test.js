import assert from 'node:assert/strict'
import test from 'node:test'

import {
  CONCEPT_TYPE_COLORS,
  buildCyStyles,
  getConceptTypeBorderColor,
  getConceptTypeColor,
} from '../src/components/graph/GraphStyles.js'

test('theory concept types use distinct semantic colors', () => {
  const theoryTypes = ['definition', 'law', 'application', 'extension']
  const colors = theoryTypes.map(getConceptTypeColor)

  assert.equal(new Set(colors).size, theoryTypes.length)
  assert.ok(colors.every(color => /^#[0-9A-F]{6}$/i.test(color)))
  assert.ok(theoryTypes.every(type => getConceptTypeBorderColor(type) !== colors[theoryTypes.indexOf(type)]))
})

test('cytoscape styles include one background selector per theory type', () => {
  const styles = buildCyStyles()

  for (const type of ['definition', 'law', 'application', 'extension']) {
    const rule = styles.find(item => item.selector === `node[type="${type}"]`)
    assert.ok(rule, `missing style for ${type}`)
    assert.equal(rule.style['background-color'], CONCEPT_TYPE_COLORS[type])
  }
})
