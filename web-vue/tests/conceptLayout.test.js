import test from 'node:test'
import assert from 'node:assert/strict'

import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'

import { runConceptLayout } from '../src/components/graph/GraphLayout.js'
import { buildVirtualGapElements, virtualGapNodeId } from '../src/components/graph/gapGraph.js'
import {
  applyConceptTreePage,
  clearConceptTreePage,
  filterGapsForConceptTree,
  findConceptTreePage,
} from '../src/components/graph/ConceptTreePaging.js'

cytoscape.use(dagre)

function graph(elements) {
  return cytoscape({
    headless: true,
    styleEnabled: true,
    elements,
    style: [
      { selector: 'node', style: { width: 160, height: 80 } },
      { selector: 'edge', style: { display: 'element' } },
    ],
  })
}

test('virtual Gap nodes participate in the original root tree layout', (t) => {
  const gap = {
    gap_id: 'layout-gap', status: 'open', source_id: 'root', target_id: 'target',
    missing_types: ['technology'], confidence: 1,
  }
  const virtual = buildVirtualGapElements([gap])
  const cy = graph([
    { data: { id: 'root', type: 'requirement', label: 'root' } },
    { data: { id: 'target', type: 'technology', label: 'target' } },
    ...virtual.nodes,
    ...virtual.edges,
  ])
  t.after(() => cy.destroy())

  const result = runConceptLayout(cy)

  const rootX = cy.getElementById('root').position('x')
  const gapX = cy.getElementById(virtualGapNodeId('layout-gap', 0)).position('x')
  const targetX = cy.getElementById('target').position('x')
  assert.ok(rootX < gapX, `expected root (${rootX}) before Gap (${gapX})`)
  assert.ok(gapX < targetX, `expected Gap (${gapX}) before target (${targetX})`)
  assert.equal(result.trees.length, 1)
  assert.deepEqual(result.trees[0].nodeIds, ['root', virtualGapNodeId('layout-gap', 0), 'target'])
  assert.deepEqual(
    filterGapsForConceptTree([
      gap,
      { ...gap, gap_id: 'different-tree', source_id: 'elsewhere' },
    ], result.trees[0], cy),
    [gap],
  )
})

test('a supplemented real node remains inside the original tree when both replacement edges load', (t) => {
  const cy = graph([
    { data: { id: 'root', type: 'requirement', label: 'root' } },
    { data: { id: 'source', type: 'technology', label: 'source' } },
    { data: { id: 'supplemented', type: 'requirement', label: 'supplemented' } },
    { data: { id: 'target', type: 'technology', label: 'target' } },
    { data: { id: 'root-source', source: 'root', target: 'source', type: 'IMPLEMENTS' } },
    { data: { id: 'source-gap', source: 'source', target: 'supplemented', type: 'DEPEND_ON' } },
    { data: { id: 'gap-target', source: 'supplemented', target: 'target', type: 'IMPLEMENTS' } },
  ])
  t.after(() => cy.destroy())

  const result = runConceptLayout(cy)

  assert.equal(result.trees.length, 1)
  assert.deepEqual(result.trees[0].nodeIds, ['root', 'source', 'supplemented', 'target'])
  assert.equal(findConceptTreePage(result.trees, cy, 'supplemented'), 0)
  assert.ok(cy.getElementById('source').position('x') < cy.getElementById('supplemented').position('x'))
  assert.ok(cy.getElementById('supplemented').position('x') < cy.getElementById('target').position('x'))
})

test('a reused supplemented concept carries its reviewed outgoing path on the branch copy', (t) => {
  const completedGap = {
    gap_id: 'reused-gap', status: 'supplemented', source_id: 'root-b', target_id: 'target',
    missing_types: ['law'], supplemented_by: ['shared-law'],
    replacement_relations: ['HAS_LAW', 'APPLIES_TO'],
  }
  const cy = graph([
    { data: { id: 'root-a', type: 'definition', label: 'A' } },
    { data: { id: 'root-b', type: 'definition', label: 'B' } },
    { data: { id: 'shared-law', type: 'law', label: 'Lorentz transformation' } },
    { data: { id: 'target', type: 'application', label: 'gravity' } },
    { data: { id: 'a-law', source: 'root-a', target: 'shared-law', type: 'HAS_LAW' } },
    { data: { id: 'b-law', source: 'root-b', target: 'shared-law', type: 'HAS_LAW' } },
    { data: { id: 'law-target', source: 'shared-law', target: 'target', type: 'APPLIES_TO' } },
  ])
  t.after(() => cy.destroy())

  const result = runConceptLayout(cy, { supplementedGaps: [completedGap] })
  const rootAPage = result.trees.find(tree => tree.rootOriginalId === 'root-a')
  const rootBPage = result.trees.find(tree => tree.rootOriginalId === 'root-b')
  assert.ok(rootAPage)
  assert.ok(rootBPage)
  const reusedOccurrence = rootBPage.nodeIds
    .map(id => cy.getElementById(id))
    .find(node => (node.data('supplementedGapIds') || []).includes('reused-gap'))
  assert.ok(reusedOccurrence)
  assert.equal(reusedOccurrence.data('originalId'), 'shared-law')
  const pathEdge = cy.edges().filter(edge =>
    edge.data('gapId') === 'reused-gap' && edge.source().id() === reusedOccurrence.id()
  )
  assert.equal(pathEdge.length, 1)
  assert.equal(pathEdge.target().data('originalId') || pathEdge.target().id(), 'target')
  assert.equal(pathEdge.target().data('isSupplementedGapCopy'), '1')
  assert.ok(rootBPage.nodeIds.includes(pathEdge.target().id()))
  assert.ok(!rootBPage.nodeIds.includes('target'))
  assert.ok(rootAPage.nodeIds.includes('target'))

  // A rendered occurrence may belong to only one paged tree. Sharing it
  // causes each tree placement pass to translate the same node again.
  const membership = new Map()
  result.trees.forEach(tree => tree.nodeIds.forEach(id => {
    membership.set(id, (membership.get(id) || 0) + 1)
  }))
  assert.ok([...membership.values()].every(count => count === 1))
})

test('post validation excludes a same-tree copy reached through an equivalent Gap path', (t) => {
  const gap = {
    gap_id: 'redundant-gap', status: 'open', source_id: 'root', target_id: 'shared',
    missing_types: ['requirement'], confidence: 1,
  }
  const virtual = buildVirtualGapElements([gap])
  const cy = graph([
    { data: { id: 'root', type: 'requirement', label: 'root' } },
    { data: { id: 'parent', type: 'technology', label: 'parent' } },
    { data: { id: 'shared', type: 'technology', label: '向量搜索' } },
    { data: { id: 'root-parent', source: 'root', target: 'parent', type: 'IMPLEMENTS' } },
    { data: { id: 'parent-shared', source: 'parent', target: 'shared', type: 'DEPEND_ON' } },
    ...virtual.nodes,
    ...virtual.edges,
  ])
  t.after(() => cy.destroy())

  const first = runConceptLayout(cy)
  assert.equal(first.trees.length, 1)
  assert.deepEqual(first.trees[0].nodeIds, ['root', 'parent', 'shared'])
  assert.equal(first.trees[0].redundantCopyIds.length, 1)
  assert.deepEqual(first.trees[0].redundantGapIds, ['redundant-gap'])
  assert.ok(!first.trees[0].nodeIds.includes(virtualGapNodeId('redundant-gap', 0)))
  assert.ok(first.trees[0].redundantNodeIds.every(id =>
    cy.getElementById(id).style('display') === 'none'
  ))
  assert.deepEqual(filterGapsForConceptTree([gap], first.trees[0], cy), [])

  const second = runConceptLayout(cy)
  assert.deepEqual(second.trees, first.trees)
})

test('post validation keeps a same-tree copy when its upstream path contains a distinct real node', (t) => {
  const cy = graph([
    { data: { id: 'root', type: 'requirement', label: 'root' } },
    { data: { id: 'parent-a', type: 'technology', label: 'A' } },
    { data: { id: 'parent-b', type: 'technology', label: 'B' } },
    { data: { id: 'shared', type: 'technology', label: '向量搜索' } },
    { data: { id: 'root-a', source: 'root', target: 'parent-a', type: 'IMPLEMENTS' } },
    { data: { id: 'root-b', source: 'root', target: 'parent-b', type: 'IMPLEMENTS' } },
    { data: { id: 'a-shared', source: 'parent-a', target: 'shared', type: 'DEPEND_ON' } },
    { data: { id: 'b-shared', source: 'parent-b', target: 'shared', type: 'DEPEND_ON' } },
  ])
  t.after(() => cy.destroy())

  const result = runConceptLayout(cy)
  assert.equal(result.trees.length, 1)
  assert.equal(result.trees[0].redundantCopyIds.length, 0)
  assert.equal(result.trees[0].nodeIds.filter(id =>
    (cy.getElementById(id).data('originalId') || id) === 'shared'
  ).length, 2)
})

test('post validation keeps copies that isolate different root trees', (t) => {
  const gap = {
    gap_id: 'cross-tree-gap', status: 'open', source_id: 'root-b', target_id: 'shared',
    missing_types: ['requirement'], confidence: 1,
  }
  const virtual = buildVirtualGapElements([gap])
  const cy = graph([
    { data: { id: 'root-a', type: 'requirement', label: 'A' } },
    { data: { id: 'root-b', type: 'requirement', label: 'B' } },
    { data: { id: 'parent', type: 'technology', label: 'parent' } },
    { data: { id: 'shared', type: 'technology', label: 'shared' } },
    { data: { id: 'a-parent', source: 'root-a', target: 'parent', type: 'IMPLEMENTS' } },
    { data: { id: 'parent-shared', source: 'parent', target: 'shared', type: 'DEPEND_ON' } },
    ...virtual.nodes,
    ...virtual.edges,
  ])
  t.after(() => cy.destroy())

  const result = runConceptLayout(cy)
  assert.equal(result.trees.length, 2)
  assert.ok(result.trees.every(tree => tree.redundantCopyIds.length === 0))
  assert.ok(result.trees.some(tree => tree.nodeIds.some(id =>
    cy.getElementById(id).data('originalId') === 'shared'
  )))
})

test('post validation keeps a candidate Gap path that owns another child branch', (t) => {
  const gap = {
    gap_id: 'branched-gap', status: 'open', source_id: 'root', target_id: 'shared',
    missing_types: ['requirement'], confidence: 1,
  }
  const virtual = buildVirtualGapElements([gap])
  const gapNodeId = virtualGapNodeId('branched-gap', 0)
  const cy = graph([
    { data: { id: 'root', type: 'requirement', label: 'root' } },
    { data: { id: 'parent', type: 'technology', label: 'parent' } },
    { data: { id: 'shared', type: 'technology', label: 'shared' } },
    { data: { id: 'other', type: 'technology', label: 'other' } },
    { data: { id: 'root-parent', source: 'root', target: 'parent', type: 'IMPLEMENTS' } },
    { data: { id: 'parent-shared', source: 'parent', target: 'shared', type: 'DEPEND_ON' } },
    ...virtual.nodes,
    ...virtual.edges,
    { data: { id: 'gap-other', source: gapNodeId, target: 'other', type: 'IMPLEMENTS' } },
  ])
  t.after(() => cy.destroy())

  const result = runConceptLayout(cy)
  assert.equal(result.trees.length, 1)
  assert.equal(result.trees[0].redundantCopyIds.length, 0)
  assert.ok(result.trees[0].nodeIds.includes(gapNodeId))
  assert.ok(result.trees[0].nodeIds.includes('other'))
})

test('re-running concept layout restores copy-owned edges before recreating copies', (t) => {
  const cy = graph([
    { data: { id: 'root-a', type: 'requirement', label: 'A' } },
    { data: { id: 'root-b', type: 'requirement', label: 'B' } },
    { data: { id: 'shared', type: 'technology', label: 'shared' } },
    { data: { id: 'leaf', type: 'technology', label: 'leaf' } },
    { data: { id: 'a-shared', source: 'root-a', target: 'shared', type: 'VIRTUAL_GAP_EDGE' } },
    { data: { id: 'b-shared', source: 'root-b', target: 'shared', type: 'VIRTUAL_GAP_EDGE' } },
    { data: { id: 'shared-leaf', source: 'shared', target: 'leaf', type: 'VIRTUAL_GAP_EDGE' } },
  ])
  t.after(() => cy.destroy())

  const firstLayout = runConceptLayout(cy)
  const firstCopies = cy.nodes().filter(node => node.data('isCopy') === '1').length
  const firstHidden = cy.edges('.layout-copy-hidden-edge').length

  const secondLayout = runConceptLayout(cy)
  assert.equal(cy.nodes().filter(node => node.data('isCopy') === '1').length, firstCopies)
  assert.equal(cy.edges('.layout-copy-hidden-edge').length, firstHidden)
  assert.equal(firstCopies, 1)
  assert.equal(firstHidden, 1)
  assert.equal(firstLayout.trees.length, 2)
  assert.equal(secondLayout.trees.length, 2)
  assert.deepEqual(
    secondLayout.trees.map(tree => tree.rootId).sort(),
    ['root-a', 'root-b'],
  )
  const rootBPage = findConceptTreePage(secondLayout.trees, cy, 'root-b')
  const ignoredGap = {
    gap_id: 'ignored-copy-edge', status: 'ignored', source_id: 'root-b',
    target_id: 'shared', original_relation: 'VIRTUAL_GAP_EDGE', missing_types: ['technology'],
  }
  assert.deepEqual(
    filterGapsForConceptTree([ignoredGap], secondLayout.trees[rootBPage], cy),
    [ignoredGap],
  )
  const visiblePageNodes = applyConceptTreePage(cy, secondLayout.trees[rootBPage])
  assert.deepEqual(
    visiblePageNodes.map(node => node.id()).sort(),
    secondLayout.trees[rootBPage].nodeIds.slice().sort(),
  )
  assert.ok(cy.edges('.layout-copy-hidden-edge').every(edge => edge.style('display') === 'none'))
  assert.ok(cy.edges().filter(edge => edge.style('display') !== 'none').every(edge =>
    secondLayout.trees[rootBPage].edgeIds.includes(edge.id()),
  ))

  clearConceptTreePage(cy)
  assert.ok(cy.edges('.layout-copy-hidden-edge').every(edge => edge.style('display') === 'none'))
})
