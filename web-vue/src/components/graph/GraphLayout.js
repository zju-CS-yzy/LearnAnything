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
 * 
 * 修复 LA-033: 限制描述行数，调整 lineHeight 以匹配实际渲染
 * 避免 description 过长导致 cardHeight 不足，文本溢出截断
 */
export function buildUMLCardLabel(name, type, description) {
  const typeLabel = getTypeLabel(type)
  const title = name ? name.substring(0, 12) : '未命名'
  
  // 限制描述长度：最多 3 行，每行 15 字符 = 45 字符
  const maxDescChars = 45
  const descRaw = description || ''
  const descTrimmed = descRaw.length > maxDescChars ? descRaw.substring(0, maxDescChars) + '...' : descRaw
  
  const descLines = []
  for (let i = 0; i < descTrimmed.length; i += 15) {
    descLines.push(descTrimmed.substring(i, i + 15))
  }
  const descText = descLines.join('\n')
  const cardLabel = `${title}\n━━━━━━\n${typeLabel}\n━━━━━━\n${descText}`

  // 计算高度：lineHeight 18px 更贴近 12px 字体的实际渲染高度
  const fixedLines = 5
  const descLineCount = Math.max(descLines.length, 1)
  const totalLines = fixedLines + descLineCount - 1
  const lineHeight = 18
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
    return t === 'child' || t === 'markdown' || t === 'image'
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
  function calcHeight(nodeId, visiting = new Set()) {
    // 循环引用保护：如果正在访问此节点，返回1避免无限递归
    if (visiting.has(nodeId)) {
      console.warn(`[runTreeLayout] Circular reference detected at ${nodeId}`)
      return 1
    }
    if (subtreeHeight[nodeId] !== undefined) return subtreeHeight[nodeId]
    const children = treeChildren[nodeId] || []
    if (children.length === 0) {
      subtreeHeight[nodeId] = 1
      return 1
    }
    visiting.add(nodeId)
    const count = children.reduce((sum, cid) => sum + calcHeight(cid, visiting), 0)
    visiting.delete(nodeId)
    subtreeHeight[nodeId] = count
    return count
  }

  const positions = {}
  function assignPos(nodeId, depth, startY, visiting = new Set()) {
    // 循环引用保护
    if (visiting.has(nodeId)) {
      positions[nodeId] = { x: depth * layerWidth, y: startY }
      return startY + nodeGap
    }
    visiting.add(nodeId)

    const x = depth * layerWidth
    const children = treeChildren[nodeId] || []

    if (children.length === 0) {
      positions[nodeId] = { x, y: startY }
      visiting.delete(nodeId)
      return startY + nodeGap
    }

    let currentY = startY
    const childCenters = []

    children.forEach(childId => {
      const childEndY = assignPos(childId, depth + 1, currentY, visiting)
      childCenters.push((currentY + childEndY - nodeGap) / 2)
      currentY = childEndY
    })

    const firstY = childCenters[0]
    const lastY = childCenters[childCenters.length - 1]
    positions[nodeId] = { x, y: (firstY + lastY) / 2 }

    visiting.delete(nodeId)
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

  // 5.5 为图片节点安排位置（放在所有文本树的右侧）
  const imageNodes = cy.nodes().filter(n => n.data('type') === 'image')
  if (imageNodes.length > 0) {
    // 计算文本树的最右边界
    let maxTreeX = 0
    Object.values(positions).forEach(pos => {
      maxTreeX = Math.max(maxTreeX, pos.x)
    })
    const imageStartX = maxTreeX + 250  // 在文本树右侧留 250px 间距
    const imageGap = 80

    imageNodes.forEach((imgNode, idx) => {
      imgNode.position({
        x: imageStartX,
        y: 50 + idx * imageGap,
      })
    })
  }

  // 6. 适应视图
  const allNodes = cy.nodes().filter(n => {
    const t = n.data('type')
    return t === 'child' || t === 'markdown' || t === 'image' || n.data('isCopy') === 1
  })

  if (allNodes.length > 0) {
    const bbox = allNodes.boundingBox()
    const container = cy.container()
    const containerW = container.clientWidth || 800
    const containerH = container.clientHeight || 600

    // 防止 bbox 为 0 导致 zoom 为 Infinity
    const bboxW = Math.max(bbox.w, 1)
    const bboxH = Math.max(bbox.h, 1)

    const zoomByWidth = (containerW * 0.9) / bboxW
    const zoomByHeight = (containerH * 0.8) / bboxH
    const zoom = Math.min(zoomByWidth, zoomByHeight, 1.0)

    const finalZoom = Math.max(zoom, 0.1)
    if (isFinite(finalZoom)) {
      cy.zoom(finalZoom)
      cy.pan({ x: 30, y: 30 })
    } else {
      console.warn('[runTreeLayout] Invalid zoom calculated, using default', { zoom, bboxW, bboxH, containerW, containerH })
      cy.zoom(0.5)
      cy.pan({ x: 30, y: 30 })
    }
  } else {
    console.warn('[runTreeLayout] No nodes to layout')
  }

  // 动态调整边曲率：根据源节点和目标节点的相对 y 位置
  adjustEdgeCurvature(cy)
}

/**
 * 根据源节点和目标节点的相对 y 位置动态调整边曲率方向
 * - 目标更高（target.y < source.y）：向上凸（distance < 0）
 * - 目标更低（target.y > source.y）：向下凸（distance > 0）
 * - 大致相平：直线（distance = 0）
 */
function adjustEdgeCurvature(cy) {
  const THRESHOLD = 5  // y 差值阈值，小于此值视为相平
  const DISTANCE = 40  // 曲率幅度

  cy.edges().forEach(edge => {
    const source = edge.source()
    const target = edge.target()
    if (!source || !target || source.length === 0 || target.length === 0) return

    const dy = target.position('y') - source.position('y')

    let distance
    if (Math.abs(dy) < THRESHOLD) {
      distance = 0  // 相平 → 直线
    } else if (dy < 0) {
      distance = -DISTANCE  // 目标更高 → 向上凸
    } else {
      distance = DISTANCE  // 目标更低 → 向下凸
    }

    edge.style('control-point-distances', distance)
    edge.style('control-point-weights', 0.5)
  })
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

  // LA-035: 分离图片节点和概念节点
  const imageNodes = cy.nodes().filter(n => n.data('type') === 'image')
  const allConceptNodes = cy.nodes().filter(n => {
    const t = n.data('type')
    return t && t !== 'child' && t !== 'parent' && t !== 'markdown' && t !== 'image'
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

  console.log(`[runConceptLayout] ${components.length} comps, ${connectedNodes.length} nodes, ${edgeList.length} edges`)

  // ===== 步骤2: 副本处理 + 按根拆分为独立子树 =====
  // 先处理多入边节点（创建副本），然后按根拆分子树

  // 2a. 为每个分量创建副本（处理多入度节点）
  components.forEach((compNodes, compIdx) => {
    const compEdgeList = edgeList.filter(e =>
      compNodes.has(e.source) && compNodes.has(e.target)
    )

    const compInDegree = {}
    compEdgeList.forEach(e => {
      compInDegree[e.target] = (compInDegree[e.target] || 0) + 1
    })

    compNodes.forEach(nid => {
      const deg = compInDegree[nid] || 0
      if (deg <= 1) return

      const incoming = compEdgeList
        .filter(e => e.target === nid)
        .sort((a, b) => a.source.localeCompare(b.source))

      for (let j = 1; j < incoming.length; j++) {
        const copyId = `${nid}_copy${j}_c${compIdx}`
        const originalNode = cy.getElementById(nid)

        cy.add({
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
        cy.add({
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
  })

  // 2b. 基于 cy 中实际可见的边，识别所有根和子树
  const visibleEdges = cy.edges().filter(e => {
    const t = e.data('type')
    return (t === 'SOLUTION' || t === 'DEPENDS_ON') && e.style('display') !== 'none'
  })

  // 计算入度（基于可见边）
  const finalInDegree = {}
  visibleEdges.forEach(e => {
    const tid = e.target().id()
    finalInDegree[tid] = (finalInDegree[tid] || 0) + 1
  })

  // 找到所有根（入度为0的概念节点或副本）
  const allConceptIds = new Set()
  connectedNodes.forEach(n => allConceptIds.add(n.id()))
  cy.nodes('[isCopy = 1]').forEach(n => allConceptIds.add(n.id()))

  const roots = []
  allConceptIds.forEach(id => {
    if (!finalInDegree[id] || finalInDegree[id] === 0) {
      roots.push(id)
    }
  })

  // 处理纯环（没有根）：任选一个节点作为伪根
  if (roots.length === 0 && allConceptIds.size > 0) {
    roots.push(allConceptIds.values().next().value)
  }

  console.log(`[runConceptLayout] Total roots (trees): ${roots.length}, total concept nodes: ${allConceptIds.size}`)

  // 2c. 从每个根出发，收集可达子树
  const allTrees = []

  roots.forEach(rootId => {
    const treeNodes = new Set()
    const queue = [rootId]

    while (queue.length > 0) {
      const nid = queue.shift()
      if (treeNodes.has(nid)) continue
      treeNodes.add(nid)

      visibleEdges.forEach(e => {
        if (e.source().id() === nid && !treeNodes.has(e.target().id())) {
          queue.push(e.target().id())
        }
      })
    }

    if (treeNodes.size > 0) {
      allTrees.push({ rootId, nodes: treeNodes })
    }
  })

  console.log(`[runConceptLayout] Trees after split: ${allTrees.length}`)

  // 2d. 每棵树独立跑 dagre LR
  const treeBboxes = []

  allTrees.forEach((tree, idx) => {
    // 构建布局集合（该树的节点 + 内部边）
    let layoutCollection = cy.collection()

    tree.nodes.forEach(id => {
      const el = cy.getElementById(id)
      if (el.length > 0) layoutCollection = layoutCollection.union(el)
    })

    visibleEdges.forEach(e => {
      const src = e.source().id()
      const tgt = e.target().id()
      if (tree.nodes.has(src) && tree.nodes.has(tgt)) {
        layoutCollection = layoutCollection.union(e)
      }
    })

    if (layoutCollection.nodes().length === 0) {
      treeBboxes.push({ x1: 0, y1: 0, x2: 0, y2: 0, w: 0, h: 0 })
      return
    }

    // 重置位置并跑 dagre
    layoutCollection.nodes().forEach(n => n.position({ x: 0, y: 0 }))
    layoutCollection.layout({
      name: 'dagre',
      rankDir: 'LR',
      rankSep: 80,
      nodeSep: 40,
      edgeSep: 10,
      padding: 10,
      fit: false,
      animate: false,
    }).run()

    // 计算 bbox（节点实际尺寸）
    let minX = Infinity, maxX = -Infinity
    let minY = Infinity, maxY = -Infinity
    layoutCollection.nodes().forEach(n => {
      const x = n.position('x')
      const y = n.position('y')
      const w = n.width() || 160
      const h = n.height() || n.data('cardHeight') || 80
      minX = Math.min(minX, x - w / 2)
      maxX = Math.max(maxX, x + w / 2)
      minY = Math.min(minY, y - h / 2)
      maxY = Math.max(maxY, y + h / 2)
    })

    const bbox = { x1: minX, y1: minY, x2: maxX, y2: maxY, w: maxX - minX, h: maxY - minY }
    treeBboxes.push(bbox)

    console.log(`[runConceptLayout] Tree ${idx}: ${tree.nodes.size} nodes, h=${Math.round(bbox.h)}`)
  })

  // ===== 步骤3: 纵向堆叠所有树 =====
  const order = allTrees.map((tree, i) => ({ i, count: tree.nodes.size }))
    .sort((a, b) => b.count - a.count)

  const treeGap = 100
  let currentY = 30

  order.forEach(({ i: treeIdx }) => {
    const tree = allTrees[treeIdx]
    const bbox = treeBboxes[treeIdx]

    if (bbox.h === 0) return

    const targetX = 30
    const targetY = currentY

    const dx = targetX - bbox.x1
    const dy = targetY - bbox.y1

    // 移动该树所有节点
    tree.nodes.forEach(id => {
      const node = cy.getElementById(id)
      if (node.length > 0) {
        node.position('x', node.position('x') + dx)
        node.position('y', node.position('y') + dy)
      }
    })

    currentY = currentY + bbox.h + treeGap
  })

  // ===== 步骤4: 显示节点并计算全局 zoom =====
  connectedNodes.forEach(n => {
    n.style('display', 'element')
    n.style('opacity', 1)
  })
  cy.nodes('[isCopy = 1]').forEach(n => {
    n.style('display', 'element')
    n.style('opacity', 0.85)
  })

  // 全局 bbox（使用节点实际尺寸）
  let minX = Infinity, maxX = -Infinity
  let minY = Infinity, maxY = -Infinity
  connectedNodes.forEach(n => {
    const x = n.position('x')
    const y = n.position('y')
    const w = n.width() || 160
    const h = n.height() || n.data('cardHeight') || 80
    minX = Math.min(minX, x - w / 2)
    maxX = Math.max(maxX, x + w / 2)
    minY = Math.min(minY, y - h / 2)
    maxY = Math.max(maxY, y + h / 2)
  })
  cy.nodes('[isCopy = 1]').forEach(n => {
    const x = n.position('x')
    const y = n.position('y')
    const w = n.width() || 160
    const h = n.height() || n.data('cardHeight') || 80
    minX = Math.min(minX, x - w / 2)
    maxX = Math.max(maxX, x + w / 2)
    minY = Math.min(minY, y - h / 2)
    maxY = Math.max(maxY, y + h / 2)
  })
  const totalW = maxX - minX + 100
  const totalH = maxY - minY + 100

  console.log(`[runConceptLayout] Global: ${Math.round(totalW)} x ${Math.round(totalH)}`)

  const container = cy.container()
  const containerW = container.clientWidth

  // 纵向堆叠：宽度是瓶颈，优先 fit 宽度；高度方向可滚动
  const zoomByWidth = (containerW * 0.85) / totalW
  const zoom = Math.min(zoomByWidth, 0.5)
  cy.zoom(Math.max(zoom, 0.1))
  cy.pan({ x: 30, y: 30 })

  // 处理孤立节点：如果有语义边，只显示有连接的；如果没有语义边，将孤立节点排列成网格
  if (edgeList.length > 0) {
    // 有语义边：隐藏真正孤立的概念节点（保持现有行为）
    orphanNodes.forEach(n => n.style('display', 'none'))
  } else {
    // 无语义边：将孤立概念节点排列成网格显示
    console.log(`[runConceptLayout] No semantic edges, arranging ${orphanNodes.length} orphan nodes in grid`)
    const cols = Math.max(1, Math.floor(containerW / 200))
    const gapX = 180
    const gapY = 120
    orphanNodes.forEach((n, i) => {
      const col = i % cols
      const row = Math.floor(i / cols)
      n.position({ x: 100 + col * gapX, y: 100 + row * gapY })
      n.style('display', 'element')
      n.style('opacity', 1)
    })
  }

  // LA-035: 图片节点布局 — 放在概念树下方
  if (imageNodes.length > 0) {
    console.log(`[runConceptLayout] Arranging ${imageNodes.length} image nodes below concept trees`)
    // 计算概念树的最下边界
    let maxConceptY = 0
    connectedNodes.forEach(n => {
      maxConceptY = Math.max(maxConceptY, n.position('y') + (n.height() || 80) / 2)
    })
    cy.nodes('[isCopy = 1]').forEach(n => {
      maxConceptY = Math.max(maxConceptY, n.position('y') + (n.height() || 80) / 2)
    })
    // orphanNodes 如果在无语义边时已布局，也要考虑
    orphanNodes.forEach(n => {
      if (n.style('display') !== 'none') {
        maxConceptY = Math.max(maxConceptY, n.position('y') + (n.height() || 80) / 2)
      }
    })

    const imageStartY = maxConceptY + 80
    const imageGap = 60
    imageNodes.forEach((imgNode, idx) => {
      imgNode.position({ x: 50 + idx * imageGap, y: imageStartY })
      imgNode.style('display', 'element')
      imgNode.style('opacity', 1)
    })
  }

  // 动态调整边曲率
  adjustEdgeCurvature(cy)
}
