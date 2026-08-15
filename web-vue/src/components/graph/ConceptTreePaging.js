const PAGE_HIDDEN_CLASS = 'tree-page-hidden'

export function clearConceptTreePage(cy) {
  if (!cy) return
  cy.elements(`.${PAGE_HIDDEN_CLASS}`)
    .style('display', 'element')
    .removeClass(PAGE_HIDDEN_CLASS)
}

export function applyConceptTreePage(cy, tree) {
  if (!cy) return cy?.collection() || null
  clearConceptTreePage(cy)
  if (!tree) return cy.collection()

  const nodeIds = new Set(tree.nodeIds || [])
  const edgeIds = new Set(tree.edgeIds || [])
  cy.nodes().filter(node =>
    node.style('display') !== 'none' && !nodeIds.has(node.id()),
  ).addClass(PAGE_HIDDEN_CLASS).style('display', 'none')
  cy.edges().filter(edge =>
    edge.style('display') !== 'none' && !edgeIds.has(edge.id()),
  ).addClass(PAGE_HIDDEN_CLASS).style('display', 'none')

  return cy.nodes().filter(node => nodeIds.has(node.id()))
}

export function findConceptTreePage(pages, cy, nodeId) {
  if (!nodeId) return -1
  const trees = pages || []
  const exact = trees.findIndex(tree => (tree.nodeIds || []).includes(nodeId))
  if (exact >= 0 || !cy) return exact
  return trees.findIndex(tree => (tree.nodeIds || []).some(id => {
    const node = cy.getElementById(id)
    return node.length && (node.data('originalId') || id) === nodeId
  }))
}

export function filterGapsForConceptTree(gaps, tree, cy) {
  if (!tree || !cy) return []
  const nodeIds = new Set(tree.nodeIds || [])
  const redundantGapIds = new Set(tree.redundantGapIds || [])
  const canonicalIds = new Set()
  const openGapIds = new Set()
  nodeIds.forEach(id => {
    const node = cy.getElementById(id)
    if (node.length) {
      if (node.data('gapId')) openGapIds.add(node.data('gapId'))
      canonicalIds.add(node.data('originalId') || id)
    }
  })

  return (gaps || []).filter(gap => {
    if (redundantGapIds.has(gap.gap_id)) return false
    if (openGapIds.has(gap.gap_id)) return true

    if ((gap.supplemented_by || []).some(id => canonicalIds.has(id))) return true

    const matchingEdge = (tree.edgeIds || []).some(edgeId => {
      const edge = cy.getElementById(edgeId)
      if (!edge.length) return false
      const source = edge.source()
      const target = edge.target()
      const sourceId = source.data('originalId') || source.id()
      const targetId = target.data('originalId') || target.id()
      return sourceId === gap.source_id && targetId === gap.target_id &&
        (!gap.original_relation || edge.data('type') === gap.original_relation)
    })
    if (matchingEdge) return true

    if (!gap.source_id) return Boolean(gap.target_id && canonicalIds.has(gap.target_id))
    return canonicalIds.has(gap.source_id) &&
      (!gap.target_id || canonicalIds.has(gap.target_id))
  })
}
