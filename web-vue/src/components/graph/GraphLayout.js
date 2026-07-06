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
 * 概念节点布局（全局 dagre TB + 副本处理）
 * 策略：所有连通节点一起跑 dagre，dagre 自动处理 rank 分配
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

  // 收集边
  const edgeList = []
  semanticEdges.forEach(e => {
    edgeList.push({
      source: e.source().id(),
      target: e.target().id(),
      type: e.data('type'),
      edgeRef: e
    })
  })

  // 找出有连接的节点
  const connectedNodeIds = new Set()
  edgeList.forEach(e => {
    connectedNodeIds.add(e.source)
    connectedNodeIds.add(e.target)
  })

  const connectedNodes = allConceptNodes.filter(n => connectedNodeIds.has(n.id()))
  const orphanNodes = allConceptNodes.filter(n => !connectedNodeIds.has(n.id()))

  console.log(`[runConceptLayout] Connected: ${connectedNodes.length} nodes, ${edgeList.length} edges, Orphan: ${orphanNodes.length}`)

  // 隐藏 chunk 节点和无关边
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

  // 先隐藏所有概念节点，只显示有连接的
  allConceptNodes.forEach(n => n.style('display', 'none'))

  // ===== 步骤1: 处理多入边节点（创建副本） =====
  const nodeInDegree = {}
  edgeList.forEach(e => {
    nodeInDegree[e.target] = (nodeInDegree[e.target] || 0) + 1
  })

  const copyNodes = []
  const copyEdges = []

  connectedNodes.forEach(n => {
    const nid = n.id()
    const deg = nodeInDegree[nid] || 0
    if (deg <= 1) return

    // 找出指向该节点的所有边（按源节点排序确保稳定）
    const incoming = edgeList.filter(e => e.target === nid).sort((a, b) => a.source.localeCompare(b.source))

    for (let j = 1; j < incoming.length; j++) {
      const copyId = `${nid}_copy${j}`

      copyNodes.push({
        data: {
          id: copyId,
          label: n.data('label'),
          cardLabel: n.data('cardLabel'),
          cardHeight: n.data('cardHeight'),
          type: n.data('type'),
          description: n.data('description'),
          parent_hint: n.data('parent_hint'),
          source_chunks: n.data('source_chunks'),
          originalId: nid,
          isCopy: '1',
        }
      })

      // 隐藏原边，添加副本边
      incoming[j].edgeRef.style('display', 'none')
      copyEdges.push({
        data: {
          id: `${incoming[j].source}_${incoming[j].type}_${copyId}`,
          source: incoming[j].source,
          target: copyId,
          type: incoming[j].type,
          label: incoming[j].type === 'SOLUTION' ? '解决' : '依赖',
          isCopyEdge: '1',
        }
      })
    }
  })

  if (copyNodes.length > 0) cy.add(copyNodes)
  if (copyEdges.length > 0) cy.add(copyEdges)

  // ===== 步骤2: 收集所有要布局的节点和边 =====
  let layoutCollection = cy.collection()

  connectedNodes.forEach(n => { layoutCollection = layoutCollection.union(n) })
  copyNodes.forEach(n => {
    const el = cy.getElementById(n.data.id)
    if (el.length > 0) layoutCollection = layoutCollection.union(el)
  })

  // 只收集仍然可见的边
  edgeList.forEach(e => {
    if (e.edgeRef.style('display') !== 'none') {
      layoutCollection = layoutCollection.union(e.edgeRef)
    }
  })
  copyEdges.forEach(e => {
    const el = cy.getElementById(e.data.id)
    if (el.length > 0) layoutCollection = layoutCollection.union(el)
  })

  console.log(`[runConceptLayout] Layout collection: ${layoutCollection.nodes().length} nodes, ${layoutCollection.edges().length} edges`)

  // ===== 步骤3: 全局 dagre 布局（TB 方向） =====
  layoutCollection.layout({
    name: 'dagre',
    rankDir: 'TB',
    rankSep: 80,
    nodeSep: 40,
    edgeSep: 15,
    padding: 20,
    fit: false,
    animate: false,
  }).run()

  // ===== 步骤4: 显示节点并设置视图 =====
  connectedNodes.forEach(n => {
    n.style('display', 'element')
    n.style('opacity', 1)
  })
  cy.nodes('[isCopy = 1]').forEach(n => {
    n.style('display', 'element')
    n.style('opacity', 0.85)
  })

  // 计算 bbox 并设置 zoom
  const bbox = layoutCollection.boundingBox()
  const container = cy.container()
  const containerW = container.clientWidth
  const containerH = container.clientHeight

  console.log(`[runConceptLayout] BBox: ${Math.round(bbox.w)} x ${Math.round(bbox.h)}`)

  const zoomByWidth = (containerW * 0.9) / bbox.w
  const zoomByHeight = (containerH * 0.9) / bbox.h
  const zoom = Math.min(zoomByWidth, zoomByHeight, 0.5)
  cy.zoom(Math.max(zoom, 0.1))
  cy.pan({ x: 30, y: 30 })

  // 隐藏孤立节点
  orphanNodes.forEach(n => {
    n.style('display', 'none')
  })
}
