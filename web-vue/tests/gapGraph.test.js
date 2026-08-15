import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildGapReplacementIndex,
  buildGapSearchQueries,
  buildVirtualGapElements,
  edgeMatchesGapIndex,
  edgeMatchesGap,
  filterGaps,
  gapChainPositions,
  supplementedNodeIds,
  stripEvidenceField,
  summarizeGaps,
  virtualGapNodeId,
} from '../src/components/graph/gapGraph.js'
import { isSemanticEdge } from '../src/components/graph/ParadigmConfig.js'

const baseGap = {
  gap_id: 'gap_abc', status: 'open', source_id: 'definition', target_id: 'extension',
  missing_types: ['law', 'application'], original_relation: 'EXTENDS', confidence: 0.9,
}

test('multi-level gap becomes a deterministic virtual chain', () => {
  const result = buildVirtualGapElements([baseGap], { law: '规律', application: '应用' })
  assert.equal(result.nodes.length, 2)
  assert.equal(result.edges.length, 3)
  assert.equal(result.nodes[0].data.id, virtualGapNodeId('gap_abc', 0))
  assert.deepEqual(
    result.edges.map(edge => [edge.data.source, edge.data.target]),
    [
      ['definition', 'virtual-gap:gap_abc:0'],
      ['virtual-gap:gap_abc:0', 'virtual-gap:gap_abc:1'],
      ['virtual-gap:gap_abc:1', 'extension'],
    ],
  )
})

test('root gaps omit the absent endpoint and ignored gaps are not rendered', () => {
  const root = { ...baseGap, gap_id: 'root', source_id: null, missing_types: ['definition'] }
  const ignored = { ...baseGap, gap_id: 'ignored', status: 'ignored' }
  const result = buildVirtualGapElements([root, ignored])
  assert.equal(result.nodes.length, 1)
  assert.equal(result.edges.length, 1)
  assert.equal(result.edges[0].data.source, 'virtual-gap:root:0')
})

test('a virtual gap is never rendered as a leaf when the target is absent', () => {
  const incomplete = { ...baseGap, gap_id: 'no-target', target_id: null }
  const result = buildVirtualGapElements([incomplete])
  assert.equal(result.nodes.length, 0)
  assert.equal(result.edges.length, 0)
  assert.equal(result.replacedPairs.length, 0)
})

test('type and confidence filters compose', () => {
  const gaps = [baseGap, { ...baseGap, gap_id: 'low', missing_types: ['law'], confidence: 0.2 }]
  assert.deepEqual(filterGaps(gaps, { missingType: 'application', minConfidence: 0.8 }), [baseGap])
})

test('only the original skip edge matches replacement metadata', () => {
  const pair = buildVirtualGapElements([baseGap]).replacedPairs[0]
  assert.equal(edgeMatchesGap({ source: 'definition', target: 'extension', type: 'EXTENDS' }, pair), true)
  assert.equal(edgeMatchesGap({ source: 'extension', target: 'definition', type: 'EXTENDS' }, pair), false)
})

test('virtual gap edges participate in concept layout without entering paradigm config', () => {
  assert.equal(isSemanticEdge('VIRTUAL_GAP_EDGE'), true)
  assert.equal(isSemanticEdge('NOT_CONFIGURED'), false)
})

test('supplemented node ids are normalized and deduplicated in API order', () => {
  assert.deepEqual(
    supplementedNodeIds({ supplemented_by: [' concept-a ', 'concept-b', 'concept-a', ''] }),
    ['concept-a', 'concept-b'],
  )
  assert.deepEqual(supplementedNodeIds(null), [])
})

test('structured Evidence suffix is not rendered as concept description', () => {
  assert.equal(
    stripEvidenceField('保证生成质量。 Evidence: [chunk-1] 原文引文'),
    '保证生成质量。',
  )
  assert.equal(stripEvidenceField('正常描述，不包含结构化字段。'), '正常描述，不包含结构化字段。')
})

test('academic search has deterministic queries when the LLM omits suggestions', () => {
  const queries = buildGapSearchQueries({
    sourceConcept: { name: '检索增强生成', aliases: ['RAG'] },
    targetConcept: { name: '生成器模块', aliases: ['Generator'] },
    missingTypes: ['requirement'],
    typeLabels: { requirement: '需求/目标' },
  })
  assert.ok(queries.length > 0)
  assert.match(queries[0], /RAG/)
  assert.match(queries[0], /Generator/)
})

test('gap chain positions interpolate between stable endpoint positions', () => {
  assert.deepEqual(
    gapChainPositions({ x: 0, y: 30 }, { x: 300, y: 90 }, 2),
    [{ x: 100, y: 50 }, { x: 200, y: 70 }],
  )
})

test('root gap chain positions extend from the available endpoint', () => {
  assert.deepEqual(
    gapChainPositions(null, { x: 300, y: 90 }, 2, 100),
    [{ x: 100, y: 90 }, { x: 200, y: 90 }],
  )
})

test('all open gaps can be materialized without a global overlay cap', () => {
  const gaps = Array.from({ length: 220 }, (_, index) => ({
    ...baseGap,
    gap_id: `gap-all-${index}`,
    source_id: `source-${index}`,
    target_id: `target-${index}`,
    missing_types: ['technology'],
  }))
  const result = buildVirtualGapElements(gaps)
  assert.equal(result.nodes.length, 220)
  assert.equal(result.edges.length, 440)
  assert.equal(result.replacedPairs.length, 220)
})

test('replacement index matches exact and wildcard skipped edges', () => {
  const index = buildGapReplacementIndex([
    { source: 'a', target: 'b', relation: 'IMPLEMENTS' },
    { source: 'c', target: 'd', relation: '' },
  ])
  assert.equal(edgeMatchesGapIndex({ source: 'a', target: 'b', type: 'IMPLEMENTS' }, index), true)
  assert.equal(edgeMatchesGapIndex({ source: 'a', target: 'b', type: 'DEPEND_ON' }, index), false)
  assert.equal(edgeMatchesGapIndex({ source: 'c', target: 'd', type: 'DEPEND_ON' }, index), true)
})

test('tree-local Gap summary counts statuses and open missing types', () => {
  assert.deepEqual(summarizeGaps([
    baseGap,
    { ...baseGap, gap_id: 'ignored', status: 'ignored', missing_types: ['law'] },
    { ...baseGap, gap_id: 'supplemented', status: 'supplemented' },
  ]), {
    by_status: { open: 1, ignored: 1, supplemented: 1, obsolete: 0 },
    open_by_missing_type: { law: 1, application: 1 },
  })
})
