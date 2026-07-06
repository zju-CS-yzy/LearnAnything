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
 * 概念节点布局（分连通分量 → 每分量 dagre LR → 二维网格排列）
 * 
 * 策略：
 * 1. 正确识别连通分量（无向图 BFS，避免单节点假树）
 * 2. 每个连通分量独立跑 dagre LR（树内从左向右生长）
 * 3. 多棵树按网格排列（从上到下、从左到右，每棵树独立区域）
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
  // 先隐藏所有概念节点
  allConceptNodes.forEach(n => n.style('display', 'none'))

  // ===== 步骤1: 正确识别连通分量（无向图 BFS） =====
  const components = []
  const visited = new Set()

  connectedNodeIds.forEach(startId => {
    if (visited.has(startId)) return

    const comp = new Set()
    const stack = [startId]

    while (stack.length > 0) {
      const nid = stack.pop()
      if (comp.has(nid)) continue
      comp.add(nid)
      visited.add(nid)

      edgeList.forEach(e => {
        if (e.source === nid && !comp.has(e.target)) {
          stack.push(e.target)
        }
        if (e.target === nid && !comp.has(e.source)) {
          stack.push(e.source)
        }
      })
    }

    if (comp.size > 0) {
      components.push(comp)
    }
  })

  console.log(`[runConceptLayout] Components: ${components.length}, nodes: ${connectedNodes.length}, edges: ${edgeList.length}`)

  // ===== 步骤2: 对每个连通分量独立处理（dagre LR + 副本） =====
  const compBboxes = []
  const compInfos = []

  components.forEach((compNodes, compIdx) => {
    if (compNodes.size === 0) return

    // 收集该分量的节点和边
    const compCyNodes = []
    compNodes.forEach(id => {
      const el = cy.getElementById(id)
      if (el.length > 0) compCyNodes.push(el)
    })

    const compEdgeList = edgeList.filter(e =>
      compNodes.has(e.source) && compNodes.has(e.target)
    )

    // 处理多入边节点（创建副本）
    const compInDegree = {}
    compEdgeList.forEach(e => {
      compInDegree[e.target] = (compInDegree[e.target] || 0) + 1
    })

    const copyNodes = []
    const copyEdges = []

    compNodes.forEach(nid => {
      const deg = compInDegree[nid] || 0
      if (deg <= 1) return

      const incoming = compEdgeList
        .filter(e => e.target === nid)
        .sort((a, b) => a.source.localeCompare(b.source))

      for (let j = 1; j < incoming.length; j++) {
        const copyId = `${nid}_copy${j}_c${compIdx}`
        const originalNode = cy.getElementById(nid)

        copyNodes.push({
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

    // 构建布局集合
    let layoutCollection = cy.collection()
    compCyNodes.forEach(n => { layoutCollection = layoutCollection.union(n) })
    copyNodes.forEach(n => {
      const el = cy.getElementById(n.data.id)
      if (el.length > 0) layoutCollection = layoutCollection.union(el)
    })
    compEdgeList.forEach(e => {
      if (e.edgeRef.style('display') !== 'none') {
        layoutCollection = layoutCollection.union(e.edgeRef)
      }
    })
    copyEdges.forEach(e => {
      const el = cy.getElementById(e.data.id)
      if (el.length > 0) layoutCollection = layoutCollection.union(el)
    })

    // 对该分量跑 dagre LR
    layoutCollection.layout({
      name: 'dagre',
      rankDir: 'LR',
      rankSep: 100,
      nodeSep: 45,
      edgeSep: 12,
      padding: 12,
      fit: false,
      animate: false,
    }).run()

    const bbox = layoutCollection.boundingBox()
    compBboxes.push(bbox)
    compInfos.push({
      nodeCount: compNodes.size,
      copyCount: copyNodes.length,
      w: bbox.x2 - bbox.x1,
      h: bbox.y2 - bbox.y1,
    })
  })

  // ===== 步骤3: 纵向堆叠排列各分量 =====
  // 按节点数从大到小排序（大的在上面）
  const order = compInfos.map((info, i) => ({ i, ...info }))
    .sort((a, b) => b.nodeCount - a.nodeCount)

  const treeGap = 80
  let currentY = 30
  let maxW = 0

  order.forEach(({ i: compIdx, w, h }) => {
    const bbox = compBboxes[compIdx]
    const compNodes = components[compIdx]

    // x 轴对齐到 30（所有树左边缘对齐）
    // y 轴从 currentY 开始
    const targetX = 30
    const targetY = currentY

    const dx = targetX - bbox.x1
    const dy = targetY - bbox.y1

    // 移动该分量所有节点和副本
    compNodes.forEach(id => {
      const node = cy.getElementById(id)
      if (node.length > 0) {
        node.position('x', node.position('x') + dx)
        node.position('y', node.position('y') + dy)
      }
      cy.nodes(`[originalId = "${id}"]`).forEach(copy => {
        copy.position('x', copy.position('x') + dx)
        copy.position('y', copy.position('y') + dy)
      })
    })

    // 更新下一个树的起始 Y
    currentY = currentY + h + treeGap
    maxW = Math.max(maxW, w)

    console.log(`[runConceptLayout] Comp ${compIdx}: ${compNodes.size} nodes, y=${Math.round(targetY)}, h=${Math.round(h)}, nextY=${Math.round(currentY)}`)
  })

  console.log(`[runConceptLayout] Total height: ${Math.round(currentY)}, maxW: ${Math.round(maxW)}, trees: ${order.length}`)

  // ===== 步骤4: 显示节点并计算全局 zoom =====
  connectedNodes.forEach(n => {
    n.style('display', 'element')
    n.style('opacity', 1)
  })
  cy.nodes('[isCopy = 1]').forEach(n => {
    n.style('display', 'element')
    n.style('opacity', 0.85)
  })

  // 全局 bbox
  let minX = Infinity, maxX = -Infinity
  let minY = Infinity, maxY = -Infinity
  connectedNodes.forEach(n => {
    const x = n.position('x')
    const y = n.position('y')
    minX = Math.min(minX, x); maxX = Math.max(maxX, x)
    minY = Math.min(minY, y); maxY = Math.max(maxY, y)
  })
  cy.nodes('[isCopy = 1]').forEach(n => {
    const x = n.position('x')
    const y = n.position('y')
    minX = Math.min(minX, x); maxX = Math.max(maxX, x)
    minY = Math.min(minY, y); maxY = Math.max(maxY, y)
  })
  const totalW = maxX - minX + 200  // 加 padding
  const totalH = maxY - minY + 100

  console.log(`[runConceptLayout] Global: ${Math.round(totalW)} x ${Math.round(totalH)}`)

  const containerW = container.clientWidth
  const containerH = container.clientHeight

  // 纵向堆叠：宽度是瓶颈，优先 fit 宽度；高度方向可滚动
  const zoomByWidth = (containerW * 0.85) / totalW
  const zoom = Math.min(zoomByWidth, 0.5)
  cy.zoom(Math.max(zoom, 0.1))
  cy.pan({ x: 30, y: 30 })
  cy.zoom(Math.max(zoom, 0.1))
  cy.pan({ x: 30, y: 30 })

  // 隐藏孤立节点
  orphanNodes.forEach(n => n.style('display', 'none'))
}
