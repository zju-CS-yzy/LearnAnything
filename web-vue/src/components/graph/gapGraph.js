/** Pure helpers for synthesising frontend-only VirtualGap graph elements. */

export function virtualGapNodeId(gapId, index) {
  return `virtual-gap:${gapId}:${index}`
}

export function virtualGapEdgeId(gapId, index) {
  return `virtual-gap-edge:${gapId}:${index}`
}

export function filterGaps(gaps, { missingType = '', minConfidence = 0 } = {}) {
  const threshold = Number(minConfidence) || 0
  return (gaps || []).filter(gap => {
    const types = gap.missing_types || []
    return (!missingType || types.includes(missingType)) && Number(gap.confidence || 0) >= threshold
  })
}

export function supplementedNodeIds(gap) {
  return [...new Set(
    (gap?.supplemented_by || [])
      .map(id => String(id || '').trim())
      .filter(Boolean),
  )]
}

export function stripEvidenceField(value) {
  const text = String(value || '').trim()
  return text.split(/\s+(?:evidence|证据)\s*[:：]/i, 1)[0].trim()
}

export function buildGapSearchQueries({
  recommended = [],
  sourceConcept = null,
  targetConcept = null,
  missingTypes = [],
  typeLabels = {},
} = {}) {
  const normalizedRecommended = (recommended || [])
    .map(item => String(item || '').trim())
    .filter(Boolean)
  if (normalizedRecommended.length) {
    return [...new Set(normalizedRecommended)].slice(0, 5)
  }
  const sourceAliases = Array.isArray(sourceConcept?.aliases) ? sourceConcept.aliases : []
  const targetAliases = Array.isArray(targetConcept?.aliases) ? targetConcept.aliases : []
  const sourceTerms = [...sourceAliases.slice(0, 2), sourceConcept?.name].filter(Boolean)
  const targetTerms = [...targetAliases.slice(0, 2), targetConcept?.name].filter(Boolean)
  const missingTerms = (missingTypes || []).map(type => typeLabels?.[type] || type).filter(Boolean)
  const candidates = [
    [...sourceTerms.slice(0, 2), ...missingTerms, ...targetTerms.slice(0, 2)].join(' '),
    [...sourceTerms.slice(0, 1), ...targetTerms.slice(0, 1)].join(' '),
    [...sourceTerms.slice(-1), ...missingTerms].join(' '),
  ].map(item => item.trim()).filter(Boolean)
  return [...new Set(candidates)].slice(0, 5)
}

export function summarizeGaps(gaps) {
  const byStatus = { open: 0, ignored: 0, supplemented: 0, obsolete: 0 }
  const openByMissingType = {}
  for (const gap of gaps || []) {
    const status = gap.status || 'open'
    byStatus[status] = (byStatus[status] || 0) + 1
    if (status === 'open') {
      for (const type of gap.missing_types || []) {
        openByMissingType[type] = (openByMissingType[type] || 0) + 1
      }
    }
  }
  return { by_status: byStatus, open_by_missing_type: openByMissingType }
}

export function buildGapReplacementIndex(pairs) {
  const exact = new Set()
  const wildcard = new Set()
  for (const pair of pairs || []) {
    const endpoints = `${pair.source}\u0000${pair.target}`
    if (pair.relation) exact.add(`${endpoints}\u0000${pair.relation}`)
    else wildcard.add(endpoints)
  }
  return { exact, wildcard }
}

export function edgeMatchesGapIndex(edgeData, index) {
  if (!edgeData || !index) return false
  const endpoints = `${edgeData.source}\u0000${edgeData.target}`
  return index.wildcard.has(endpoints) ||
    index.exact.has(`${endpoints}\u0000${edgeData.type || ''}`)
}

export function gapChainPositions(sourcePosition, targetPosition, count, spacing = 140) {
  const size = Math.max(0, Number(count) || 0)
  if (!size) return []

  const source = finitePosition(sourcePosition)
  const target = finitePosition(targetPosition)
  if (source && target) {
    return Array.from({ length: size }, (_, index) => {
      const ratio = (index + 1) / (size + 1)
      return {
        x: source.x + (target.x - source.x) * ratio,
        y: source.y + (target.y - source.y) * ratio,
      }
    })
  }
  if (source) {
    return Array.from({ length: size }, (_, index) => ({
      x: source.x + spacing * (index + 1),
      y: source.y,
    }))
  }
  if (target) {
    return Array.from({ length: size }, (_, index) => ({
      x: target.x - spacing * (size - index),
      y: target.y,
    }))
  }
  return Array.from({ length: size }, (_, index) => ({
    x: spacing * index,
    y: 0,
  }))
}

function finitePosition(position) {
  if (!position || !Number.isFinite(position.x) || !Number.isFinite(position.y)) return null
  return { x: Number(position.x), y: Number(position.y) }
}

export function buildVirtualGapElements(gaps, typeLabels = {}) {
  const nodes = []
  const edges = []
  const replacedPairs = []

  for (const gap of gaps || []) {
    if (gap.status !== 'open' || !(gap.missing_types || []).length) continue
    // A virtual Gap may be a root (missing source), but it must never become a
    // leaf. Records without a target remain available in the review panel and
    // are deliberately excluded from the graph overlay.
    if (!gap.target_id) continue
    const missingTypes = gap.missing_types
    const virtualIds = missingTypes.map((missingType, index) => {
      const id = virtualGapNodeId(gap.gap_id, index)
      nodes.push({
        group: 'nodes',
        data: {
          id,
          label: `+ ${typeLabels[missingType] || missingType}`,
          type: 'virtual_gap',
          gapType: missingType,
          gapIndex: index,
          gapCount: missingTypes.length,
          gapId: gap.gap_id,
          gap,
          isGapElement: true,
          isVirtualGap: true,
          confidence: Number(gap.confidence || 0),
        },
      })
      return id
    })

    const path = [gap.source_id, ...virtualIds, gap.target_id].filter(Boolean)
    for (let index = 0; index < path.length - 1; index += 1) {
      edges.push({
        group: 'edges',
        data: {
          id: virtualGapEdgeId(gap.gap_id, index),
          source: path[index],
          target: path[index + 1],
          type: 'VIRTUAL_GAP_EDGE',
          gapId: gap.gap_id,
          isGapElement: true,
          confidence: Number(gap.confidence || 0),
        },
      })
    }
    if (gap.source_id && gap.target_id) {
      replacedPairs.push({
        source: gap.source_id,
        target: gap.target_id,
        relation: gap.original_relation || '',
      })
    }
  }
  return { nodes, edges, replacedPairs }
}

export function edgeMatchesGap(edgeData, pair) {
  if (!edgeData || !pair) return false
  return edgeData.source === pair.source && edgeData.target === pair.target &&
    (!pair.relation || edgeData.type === pair.relation)
}
