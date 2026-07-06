/**
 * GraphLayout.js — 图谱布局算法
 * 包含文档树自定义布局 + 概念层 dagre 布局
 */

// ========== 辅助函数 ==========

/**
 * 从 chunk text 生成简洁的节点标题
 */
export function generateNodeLabel(text, headingPath, fallback) {
  if (!text) return fallback || '未知节点'

  // 尝试提取 Markdown 标题
  const headerMatch = text.match(/^#+\s+(.+?)(?:\n|$)/m)
  if (headerMatch) {
    return headerMatch[1].trim().slice(0, 30)
  }

  // 尝试提取 heading_path 中的最后一级
  if (headingPath) {
    const parts = headingPath.split('>').map(p => p.trim()).filter(Boolean)
    if (parts.length > 0) {
      return parts[parts.length - 1].slice(0, 30)
    }
  }

  // 清理 text
  let clean = text
    .replace(/[#*`\[\]\(\)]/g, '')
    .replace(/\s+/g, ' ')
    .trim()

  if (clean.length > 30) {
    clean = clean.slice(0, 30) + '...'
  }

  return clean || fallback || '未知节点'
}

/**
 * UML 类图风格卡片标签构建
 */
export function buildUMLCardLabel(name, type, description) {
  const typeLabel = getTypeLabel(type)
  const title = name.substring(0, 12)
  const desc = description || ''
  const descLines = []
  for (let i = 0; i < desc.length; i += 15) {
    descLines.push(desc.substring(i, i + 15))
  }
  const descText = descLines.join('\n')
  const cardLabel = `${title}\n━━━━━━\n${typeLabel}\n━━━━━━\n${descText}`

  // 计算高度
  const fixedLines = 5
  const descLineCount = Math.max(descLines.length, 1)
  const totalLines = fixedLines + descLineCount - 1
  const lineHeight = 16
  const padding = 36
  const cardHeight = Math.max(80, totalLines * lineHeight + padding)

  return { cardLabel, cardHeight }
}

/**
 * 类型标签映射
 */
export function getTypeLabel(type) {
  const map = {
    'requirement': '【需求】',
    'sub_requirement': '【子需求】',
    'technology': '【技术】',
    'sub_technology': '【子技术】',
    'concept': '【概念】',
  }
  return map[type] || '【概念】'
}

// ========== 文档树自定义布局 ==========

/**
 * 自定义树形布局算法
 * 原则：
 * 1. 单向的树，根节点在最左侧
 * 2. 同层节点在横向位置上并列
 * 3. 叶节点在最右侧，上下相邻叶节点间隔相同
 * 4. 有子节点的节点，纵向位置位于其所有下层节点的中部
 * 5. 不同树共享子节点时，复制子节点到各自的树中
 */
export function runTreeLayout(cy) {
  const chunkNodes = cy.nodes().filter(n => {
    const t = n.data('type')
    return t === 'child' || t === 'markdown'
  })
  const chunkEdges = cy.edges().filter(e => {
    const t = e.data('type')
    return t === 'BELONGS_TO' || t === 'ADJACENT_TO'
  })

  if (chunkNodes.length === 0) return

  // 1. 构建子节点映射和父节点映射
  const childrenMap = {}
  const parentMap = {}
  chunkEdges.forEach(e => {
    const s = e.source().id()
    const t = e.target().id()
    childrenMap[s] = childrenMap[s] || []
    childrenMap[s].push(t)
    parentMap[t] = parentMap[t] || []
    parentMap[t].push(s)
  })

  // 2. 找到所有根节点（入度为0）
  const rootIds = []
  chunkNodes.forEach(n => {
    const nid = n.id()
    if (!parentMap[nid] || parentMap[nid].length === 0) {
      rootIds.push(nid)
    }
  })

  // 3. 复制共享子节点（入度 > 1 的节点）
  cy.nodes('[isCopy = 1]').remove()
  cy.edges('[isCopyEdge = 1]').remove()

  const copyNodes = []
  const copyEdges = []
  const originalToCopies = {}

  rootIds.forEach((rootId, treeIdx) => {
    const visitedInTree = new Set()
    const stack = [{ originalId: rootId, parentTreeNodeId: null }]

    while (stack.length > 0) {
      const { originalId, parentTreeNodeId } = stack.pop()

      let treeNodeId
      if (visitedInTree.has(originalId)) {
        if (!originalToCopies[originalId]) {
          originalToCopies[originalId] = {}
        }
        if (!originalToCopies[originalId][treeIdx]) {
          const copyId = `${originalId}_tree${treeIdx}`
          originalToCopies[originalId][treeIdx] = copyId

          const origNode = cy.getElementById(originalId)
          copyNodes.push({
            data: {
              id: copyId,
              label: origNode.data('label'),
              type: origNode.data('type'),
              source: origNode.data('source'),
              page_number: origNode.data('page_number'),
              text: origNode.data('text'),
              heading_path: origNode.data('heading_path'),
              originalId: originalId,
              isCopy: 1,
            }
          })
        }
        treeNodeId = originalToCopies[originalId][treeIdx]
      } else {
        treeNodeId = originalId
        visitedInTree.add(originalId)
      }

      if (parentTreeNodeId) {
        copyEdges.push({
          data: {
            id: `${parentTreeNodeId}_to_${treeNodeId}`,
            source: parentTreeNodeId,
            target: treeNodeId,
            type: 'BELONGS_TO',
            isCopyEdge: visitedInTree.has(originalId) && originalId !== treeNodeId ? 1 : 0,
          }
        })
      }

      const childIds = childrenMap[originalId] || []
      for (let i = childIds.length - 1; i >= 0; i--) {
        stack.push({ originalId: childIds[i], parentTreeNodeId: treeNodeId })
      }
    }
  })

  if (copyNodes.length > 0) cy.add(copyNodes)
  if (copyEdges.length > 0) cy.add(copyEdges)

  // 存储副本映射用于高亮
  cy.scratch('originalToCopies', originalToCopies)

  // 4. 计算布局位置
  const treeChildren = {}
  chunkEdges.forEach(e => {
    const s = e.source().id()
    const t = e.target().id()
    treeChildren[s] = treeChildren[s] || []
    treeChildren[s].push(t)
  })
  copyEdges.forEach(e => {
    const s = e.data.source
    const t = e.data.target
    treeChildren[s] = treeChildren[s] || []
    treeChildren[s].push(t)
  })

  const layerWidth = 250
  const nodeGap = 60
  const treeGap = 120

  const subtreeHeight = {}
  function calcHeight(nodeId) {
    if (subtreeHeight[nodeId] !== undefined) return subtreeHeight[nodeId]
    const children = treeChildren[nodeId] || []
    if (children.length === 0) {
      subtreeHeight[nodeId] = 1
      return 1
    }
    const count = children.reduce((sum, cid) => sum + calcHeight(cid), 0)
    subtreeHeight[nodeId] = count
    return count
  }

  const positions = {}
  function assignPos(nodeId, depth, startY) {
    const x = depth * layerWidth
    const children = treeChildren[nodeId] || []

    if (children.length === 0) {
      positions[nodeId] = { x, y: startY }
      return startY + nodeGap
    }

    let currentY = startY
    const childCenters = []

    children.forEach(childId => {
      const childEndY = assignPos(childId, depth + 1, currentY)
      childCenters.push((currentY + childEndY - nodeGap) / 2)
      currentY = childEndY
    })

    const firstY = childCenters[0]
    const lastY = childCenters[childCenters.length - 1]
    positions[nodeId] = { x, y: (firstY + lastY) / 2 }

    return currentY
  }

  let currentY = 0
  rootIds.forEach((rootId, treeIdx) => {
    let treeRootId = rootId
    if (originalToCopies[rootId] && originalToCopies[rootId][treeIdx]) {
      treeRootId = originalToCopies[rootId][treeIdx]
    }

    const treeHeight = calcHeight(treeRootId) * nodeGap
    assignPos(treeRootId, 0, currentY)
    currentY += treeHeight + treeGap
  })

  // 5. 应用位置
  Object.entries(positions).forEach(([nodeId, pos]) => {
    const node = cy.getElementById(nodeId)
    if (node.length > 0) {
      node.position(pos)
    }
  })

  // 6. 适应视图
  const allNodes = cy.nodes().filter(n => {
    const t = n.data('type')
    return t === 'child' || t === 'markdown' || n.data('isCopy') === 1
  })

  if (allNodes.length > 0) {
    const bbox = allNodes.boundingBox()
    const container = cy.container()
    const containerW = container.clientWidth
    const containerH = container.clientHeight

    const zoomByWidth = (containerW * 0.9) / bbox.w
    const zoomByHeight = (containerH * 0.8) / bbox.h
    const zoom = Math.min(zoomByWidth, zoomByHeight, 1.0)

    cy.zoom(Math.max(zoom, 0.1))
    cy.pan({ x: 30, y: 30 })
  }
}

// ========== 概念层 dagre 布局 ==========

/**
 * 概念节点布局（dagre LR + 副本处理）
 */
export function runConceptLayout(cy) {
  // 清除之前可能创建的副本
  cy.nodes().filter(n => n.data('isCopy') === '1').remove()
  cy.edges().filter(e => e.data('isCopyEdge') === '1').remove()

  const allConceptNodes = cy.nodes().filter(n => {
    const t = n.data('type')
    return t && t !== 'child' && t !== 'parent' && t !== 'markdown'
  })

  const semanticEdges = cy.edges().filter(e => {
    const t = e.data('type')
    return t === 'SOLUTION' || t === 'DEPENDS_ON'
  })

  const edgeList = []
  semanticEdges.forEach(e => {
    edgeList.push({
      source: e.source().id(),
      target: e.target().id(),
      type: e.data('type'),
      edgeRef: e
    })
  })

  const connectedNodeIds = new Set()
  edgeList.forEach(e => {
    connectedNodeIds.add(e.source)
    connectedNodeIds.add(e.target)
  })

  const treeNodes = allConceptNodes.filter(n => connectedNodeIds.has(n.id()))
  const orphanNodes = allConceptNodes.filter(n => !connectedNodeIds.has(n.id()))

  // 隐藏 chunk 节点和 chunk 边
  cy.nodes().forEach(n => {
    const t = n.data('type')
    if (t === 'child' || t === 'parent' || t === 'markdown') {
      n.style('display', 'none')
    }
  })
  cy.edges().forEach(e => {
    const t = e.data('type')
    if (t !== 'SOLUTION' && t !== 'DEPENDS_ON') {
      e.style('display', 'none')
    }
  })

  // ===== 步骤1: 分树 =====
  const nodeInDegree = {}
  edgeList.forEach(e => {
    nodeInDegree[e.target] = (nodeInDegree[e.target] || 0) + 1
  })

  const rootIds = new Set()
  treeNodes.forEach(n => {
    const nid = n.id()
    if (!nodeInDegree[nid] || nodeInDegree[nid] === 0) {
      rootIds.add(nid)
    }
  })

  const trees = []
  const assigned = new Set()

  rootIds.forEach(rootId => {
    const treeNodeIds = new Set()
    const queue = [rootId]

    while (queue.length > 0) {
      const nid = queue.shift()
      if (treeNodeIds.has(nid)) continue
      treeNodeIds.add(nid)

      edgeList.forEach(e => {
        if (e.source === nid && !treeNodeIds.has(e.target)) {
          queue.push(e.target)
        }
        if (e.target === nid && !treeNodeIds.has(e.source)) {
          queue.push(e.source)
        }
      })
    }

    trees.push(treeNodeIds)
    treeNodeIds.forEach(id => assigned.add(id))
  })

  const unassignedIds = new Set()
  treeNodes.forEach(n => {
    if (!assigned.has(n.id())) {
      unassignedIds.add(n.id())
    }
  })
  if (unassignedIds.size > 0) {
    trees.push(unassignedIds)
  }

  // ===== 步骤2: 对每棵树独立处理 =====
  const treeBboxes = []
  const treeGap = 30

  for (let i = 0; i < trees.length; i++) {
    const treeNodeIds = trees[i]
    if (treeNodeIds.size === 0) continue

    const treeCyNodes = []
    treeNodeIds.forEach(id => {
      const el = cy.getElementById(id)
      if (el.length > 0) treeCyNodes.push(el)
    })

    const treeEdgeList = []
    edgeList.forEach(e => {
      if (treeNodeIds.has(e.source) && treeNodeIds.has(e.target)) {
        treeEdgeList.push(e)
      }
    })

    const treeCopyNodes = []
    const treeCopyEdges = []

    const treeInDegree = {}
    treeEdgeList.forEach(e => {
      treeInDegree[e.target] = (treeInDegree[e.target] || 0) + 1
    })

    treeNodeIds.forEach(nid => {
      const edges = treeEdgeList.filter(e => e.target === nid)
      if (edges.length <= 1) return

      for (let j = 1; j < edges.length; j++) {
        const copyId = `${nid}_copy${j}_tree${i}`
        const originalNode = cy.getElementById(nid)

        treeCopyNodes.push({
          data: {
            id: copyId,
            label: originalNode.data('label'),
            cardLabel: originalNode.data('cardLabel'),
            cardHeight: originalNode.data('cardHeight'),
            type: originalNode.data('type'),
            description: originalNode.data('description'),
            parent_hint: originalNode.data('parent_hint'),
            source_chunks: originalNode.data('source_chunks'),
            originalId: nid,
            isCopy: '1',
          }
        })

        edges[j].edgeRef.style('display', 'none')
        treeCopyEdges.push({
          data: {
            id: `${edges[j].source}_${edges[j].type}_${copyId}`,
            source: edges[j].source,
            target: copyId,
            type: edges[j].type,
            label: edges[j].type === 'SOLUTION' ? '解决' : '依赖',
            isCopyEdge: '1',
          }
        })
      }
    })

    if (treeCopyNodes.length > 0) cy.add(treeCopyNodes)
    if (treeCopyEdges.length > 0) cy.add(treeCopyEdges)

    let treeCollection = cy.collection()
    treeCyNodes.forEach(n => { treeCollection = treeCollection.union(n) })
    treeCopyNodes.forEach(n => {
      const el = cy.getElementById(n.data.id)
      if (el.length > 0) treeCollection = treeCollection.union(el)
    })
    treeEdgeList.forEach(e => {
      if (e.edgeRef.style('display') !== 'none') {
        treeCollection = treeCollection.union(e.edgeRef)
      }
    })
    treeCopyEdges.forEach(e => {
      const el = cy.getElementById(e.data.id)
      if (el.length > 0) treeCollection = treeCollection.union(el)
    })

    treeCollection.layout({
      name: 'dagre',
      rankDir: 'LR',
      rankSep: 120,
      nodeSep: 50,
      edgeSep: 15,
      padding: 15,
      fit: false,
      animate: false,
    }).run()

    treeBboxes.push(treeCollection.boundingBox())
  }

  // ===== 步骤3: 按从上到下排列各棵树 =====
  let currentY = 0
  for (let i = 0; i < trees.length; i++) {
    const bbox = treeBboxes[i]
    const treeNodeIds = trees[i]
    if (treeNodeIds.size === 0) continue

    const dy = currentY - bbox.y1

    treeNodeIds.forEach(id => {
      const node = cy.getElementById(id)
      if (node.length > 0) {
        node.position('y', node.position('y') + dy)
      }
      const copies = cy.nodes(`[originalId = "${id}"]`)
      copies.forEach(copy => {
        copy.position('y', copy.position('y') + dy)
      })
    })

    currentY = currentY + (bbox.y2 - bbox.y1) + treeGap
  }

  // 显示所有树节点
  for (let i = 0; i < trees.length; i++) {
    trees[i].forEach(id => {
      const node = cy.getElementById(id)
      if (node.length > 0) {
        node.style('display', 'element')
        node.style('opacity', 1)
      }
      cy.nodes(`[originalId = "${id}"]`).forEach(copy => {
        copy.style('display', 'element')
        copy.style('opacity', 1)
      })
    })
  }

  // 固定 zoom
  const allConnected = treeNodes.union(cy.nodes('[isCopy = 1]'))
  const totalBbox = allConnected.boundingBox()
  const container = cy.container()
  const containerW = container.clientWidth
  const containerH = container.clientHeight
  // 优先 fit 宽度，垂直方向允许滚动
  const zoomByWidth = (containerW * 0.85) / totalBbox.w
  const zoom = Math.min(zoomByWidth, 0.5)
  cy.zoom(Math.max(zoom, 0.15))
  // 水平居中，垂直对齐顶部留出边距
  cy.pan({
    x: (containerW - totalBbox.w * cy.zoom()) / 2,
    y: 30
  })

  // 隐藏不在任何树中的孤立节点
  if (orphanNodes.length > 0) {
    orphanNodes.forEach(n => {
      n.style('display', 'none')
    })
  }
}
