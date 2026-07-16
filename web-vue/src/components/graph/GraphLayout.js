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
 * UML 类图风格卡片标签构建（LA-035-P10 增强版）
 * 
 * 新增：mediaRefs 参数，在卡片底部生成内容类型标签行
 * 标签行用 ASCII 边框模拟便签效果：
 *   ┌──────────────┐
 *   │ 图片×2 表格×1 │  ← 底部标签行
 *   └──────────────┘
 * 
 * 修复 LA-033: 限制描述行数，调整 lineHeight 以匹配实际渲染
 * 避免 description 过长导致 cardHeight 不足，文本溢出截断
 */
export function buildUMLCardLabel(name, type, description, mediaRefs) {
  const typeLabel = getTypeLabel(type)
  const title = name || '未命名'
  
  // 描述完整显示，最多 10 行防止极端情况，每行 18 字符
  const maxDescLines = 10
  const charsPerLine = 18
  const descRaw = description || ''
  const descLines = []
  for (let i = 0; i < descRaw.length && descLines.length < maxDescLines; i += charsPerLine) {
    descLines.push(descRaw.substring(i, i + charsPerLine))
  }
  const descText = descLines.join('\n')

  // 计算媒体标签行
  let tagLine = ''
  let tagLineCount = 0
  if (mediaRefs && mediaRefs.length > 0) {
    const counts = { image: 0, table: 0, formula: 0 }
    mediaRefs.forEach(ref => {
      const t = (ref.type || ref.media_type || '').toLowerCase()
      if (t.includes('image') || t.includes('图片') || t.includes('fig')) counts.image++
      else if (t.includes('table') || t.includes('表格') || t.includes('tab')) counts.table++
      else if (t.includes('formula') || t.includes('公式') || t.includes('math') || t.includes('equation')) counts.formula++
      else counts.image++
    })
    const parts = []
    if (counts.image > 0) parts.push(`图片×${counts.image}`)
    if (counts.table > 0) parts.push(`表格×${counts.table}`)
    if (counts.formula > 0) parts.push(`公式×${counts.formula}`)
    if (parts.length > 0) {
      tagLine = parts.join(' ')
      tagLineCount = 3
    }
  }

  let cardLabel = `${title}\n━━━━━━\n${typeLabel}\n━━━━━━\n${descText}`
  if (tagLine) {
    const padLen = Math.max(tagLine.length + 2, 8)
    const top = '┌' + '─'.repeat(padLen) + '┐'
    const mid = '│ ' + tagLine.padEnd(padLen - 1, ' ') + '│'
    const bot = '└' + '─'.repeat(padLen) + '┘'
    cardLabel += `\n${top}\n${mid}\n${bot}`
  }

  const fixedLines = 5
  const descLineCount = Math.max(descLines.length, 1)
  const totalLines = fixedLines + descLineCount - 1 + tagLineCount
  const lineHeight = 18
  const padding = 36
  const cardHeight = Math.max(80, totalLines * lineHeight + padding)

  // 根据最长行计算宽度
  const allLines = cardLabel.split('\n')
  let maxChars = 0
  allLines.forEach(line => { maxChars = Math.max(maxChars, line.length) })
  const nodeWidth = Math.max(160, Math.min(300, maxChars * 12 + 32))

  return { cardLabel, cardHeight, nodeWidth }
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
  // LA-035-P19: 支持 paragraph / heading / document / child / markdown / image 所有 chunk 类型
  const chunkNodes = cy.nodes().filter(n => {
    const t = n.data('type')
    return t === 'child' || t === 'markdown' || t === 'image' ||
           t === 'paragraph' || t === 'heading' || t === 'document'
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

  // P19-FIX-2: 收集所有从根可达的节点（用于识别孤立节点）
  const treeReachable = new Set()
  rootIds.forEach(rootId => {
    const stack = [rootId]
    while (stack.length > 0) {
      const nid = stack.pop()
      if (treeReachable.has(nid)) continue
      treeReachable.add(nid)
      const children = childrenMap[nid] || []
      children.forEach(cid => stack.push(cid))
    }
  })

  // P19-FIX-2: 孤立节点 = 在 chunkNodes 中但不可从任何根到达
  // 这些节点也视为单节点树，排在最下方
  const orphanIds = []
  chunkNodes.forEach(n => {
    const nid = n.id()
    if (!treeReachable.has(nid)) {
      orphanIds.push(nid)
    }
  })

  // 合并根节点和孤立节点
  const allRootIds = [...rootIds, ...orphanIds]

  // P19-FIX-2: 按树大小排序（大节点多的树排在上面，孤立节点排在最后）
  const treeSizeMap = {}
  allRootIds.forEach(rootId => {
    const visited = new Set()
    const stack = [rootId]
    while (stack.length > 0) {
      const nid = stack.pop()
      if (visited.has(nid)) continue
      visited.add(nid)
      const children = childrenMap[nid] || []
      children.forEach(cid => stack.push(cid))
    }
    treeSizeMap[rootId] = visited.size
  })

  allRootIds.sort((a, b) => treeSizeMap[b] - treeSizeMap[a])

  console.log('[runTreeLayout] 根节点数:', rootIds.length, '孤立节点数:', orphanIds.length, '总树数:', allRootIds.length)
  console.log('[runTreeLayout] 节点类型统计:', [...chunkNodes].map(n => n.data('type')).reduce((acc, t) => { acc[t] = (acc[t] || 0) + 1; return acc }, {}))
  if (orphanIds.length > 0) {
    console.log('[runTreeLayout] 孤立节点:', orphanIds)
  }

  // 3. 复制共享子节点（入度 > 1 的节点）
  cy.nodes('[isCopy = 1]').remove()
  cy.edges('[isCopyEdge = 1]').remove()

  const copyNodes = []
  const copyEdges = []
  const originalToCopies = {}

  // P19-FIX-2: 使用排序后的 allRootIds（替代原来的 rootIds）
  allRootIds.forEach((rootId, treeIdx) => {
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
              media_refs: origNode.data('media_refs'), // LA-035-P24: 修复副本媒体数据缺失
              image_path: origNode.data('image_path'), // LA-035-P24
              thumbnail_path: origNode.data('thumbnail_path'), // LA-035-P24
              width: origNode.data('width'), // LA-035-P24
              height: origNode.data('height'), // LA-035-P24
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
  // P19-FIX-2: 使用排序后的 allRootIds（替代原来的 rootIds）
  allRootIds.forEach((rootId, treeIdx) => {
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
    return t === 'child' || t === 'markdown' || t === 'image' ||
           t === 'paragraph' || t === 'heading' || t === 'document' ||
           n.data('isCopy') === 1
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
    // P19-FIX: 包含所有非 chunk 节点（包括 type 为 undefined 的 concept 节点）
    // 只排除明确的 chunk / 图片类型
    if (t === 'child' || t === 'parent' || t === 'markdown' || t === 'image') return false
    return true
  })

  const semanticEdges = cy.edges().filter(e => {
    const t = e.data('type')
    return t === 'SOLUTION' || t === 'DEPENDS_ON'
  })

  // 收集边：过滤自环边，但自环节点仍作为普通节点显示
  // P19-FIX-3: 先记录所有节点，再过滤自环边，确保自环节点不被当作 orphan 隐藏
  const connectedNodeIds = new Set()
  const edgeList = []
  semanticEdges.forEach(e => {
    const src = e.source().id()
    const tgt = e.target().id()
    connectedNodeIds.add(src)
    connectedNodeIds.add(tgt)
    if (src !== tgt) {
      edgeList.push({
        source: src,
        target: tgt,
        type: e.data('type'),
        edgeRef: e
      })
    }
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
            nodeWidth: originalNode.data('nodeWidth') || 160,
            borderColor: originalNode.data('borderColor') || '#27ae60',
            type: originalNode.data('type'),
            description: originalNode.data('description'),
            parent_hint: originalNode.data('parent_hint'),
            source_chunks: originalNode.data('source_chunks'),
            media_refs: originalNode.data('media_refs'), // LA-035-P24: 修复副本媒体数据缺失
            has_media: originalNode.data('has_media'), // LA-035-P24
            hasImage: originalNode.data('hasImage'), // LA-035-P24
            hasTable: originalNode.data('hasTable'), // LA-035-P24
            hasFormula: originalNode.data('hasFormula'), // LA-035-P24
            image_path: originalNode.data('image_path'), // LA-035-P24
            thumbnail_path: originalNode.data('thumbnail_path'), // LA-035-P24
            width: originalNode.data('width'), // LA-035-P24
            height: originalNode.data('height'), // LA-035-P24
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
  // P19-FIX-3: visibleEdges 也过滤自环，确保自环节点入度=0，成为根节点
  const visibleEdges = cy.edges().filter(e => {
    const t = e.data('type')
    const isSemantic = t === 'SOLUTION' || t === 'DEPENDS_ON'
    const isVisible = e.style('display') !== 'none'
    const isSelfLoop = e.source().id() === e.target().id()
    return isSemantic && isVisible && !isSelfLoop
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

  // P19-FIX-3: 处理漏掉的节点（不在任何树中的连通节点，通常是环状结构）
  const nodesInTrees = new Set()
  allTrees.forEach(tree => {
    tree.nodes.forEach(id => nodesInTrees.add(id))
  })
  const leakedIds = []
  allConceptIds.forEach(id => {
    if (!nodesInTrees.has(id)) leakedIds.push(id)
  })
  if (leakedIds.length > 0) {
    console.warn(`[runConceptLayout] ${leakedIds.length} leaked nodes not in any tree:`, leakedIds)
    // 按连通分量将漏掉的节点分组，每组创建一个伪树
    const leakedVisited = new Set()
    leakedIds.forEach(startId => {
      if (leakedVisited.has(startId)) return
      const comp = new Set()
      const stack = [startId]
      while (stack.length > 0) {
        const nid = stack.pop()
        if (comp.has(nid)) continue
        comp.add(nid)
        leakedVisited.add(nid)
        // 遍历可见边，找同分量的节点
        visibleEdges.forEach(e => {
          const src = e.source().id()
          const tgt = e.target().id()
          if (src === nid && !comp.has(tgt) && leakedIds.includes(tgt)) stack.push(tgt)
          if (tgt === nid && !comp.has(src) && leakedIds.includes(src)) stack.push(src)
        })
      }
      if (comp.size > 0) {
        // 用第一个节点作为伪根
        const pseudoRoot = comp.values().next().value
        allTrees.push({ rootId: pseudoRoot, nodes: comp, isPseudo: true })
      }
    })
    console.log(`[runConceptLayout] Added ${allTrees.length - (allTrees.length - leakedIds.length)} pseudo-trees for leaked nodes`)
  }

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

    // P19-FIX-3: 伪树（漏掉的环状节点）直接用网格，不跑 dagre
    if (tree.isPseudo) {
      const pseudoNodes = layoutCollection.nodes()
      const pCols = Math.max(1, Math.ceil(Math.sqrt(pseudoNodes.length)))
      const pGap = 180
      // P19-FIX-3b: 网格起始位置偏移 50，避免被 stuckNodes 误判
      pseudoNodes.forEach((n, i) => {
        const col = i % pCols
        const row = Math.floor(i / pCols)
        n.position({ x: 50 + col * pGap, y: 50 + row * pGap })
      })
    } else {
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

      // P19-FIX: dagre fallback — 如果所有节点仍在原点（dagre 失败，可能有环），使用简单网格
      const dagreNodes = layoutCollection.nodes()
      const allAtOrigin = dagreNodes.length > 0 && dagreNodes.every(n => {
        const x = n.position('x')
        const y = n.position('y')
        return Math.abs(x) < 1 && Math.abs(y) < 1
      })
      if (allAtOrigin && dagreNodes.length > 1) {
        console.warn(`[runConceptLayout] Tree ${idx} dagre failed (all at origin), using fallback grid`)
        const fCols = Math.max(1, Math.ceil(Math.sqrt(dagreNodes.length)))
        const fGapX = 200
        const fGapY = 120
        // P19-FIX-3b: 网格起始位置偏移 50，避免被 stuckNodes 误判
        dagreNodes.forEach((n, i) => {
          const col = i % fCols
          const row = Math.floor(i / fCols)
          n.position({ x: 50 + col * fGapX, y: 50 + row * fGapY })
        })
      }
    }

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

  // ===== 步骤3: 二维网格排列所有树（替代原来的纵向堆叠）=====
  // P19-FIX: 将纵向堆叠改为二维网格，避免总高度过大
  const container = cy.container()
  const containerW = container.clientWidth || 1200
  const containerH = container.clientHeight || 800
  const maxRowWidth = Math.max(600, containerW * 0.9) // 每行最大宽度

  // 按节点数降序排列（大的树优先）
  const sortedTrees = allTrees
    .map((tree, i) => ({ treeIdx: i, count: tree.nodes.size, bbox: treeBboxes[i] }))
    .filter(t => t.bbox.h > 0)
    .sort((a, b) => b.count - a.count)

  // 网格排列：每行尽可能多地放树
  const rows = [] // 每行包含的 tree indices
  let currentRow = []
  let currentRowWidth = 0
  const treeGapX = 60  // 树之间水平间距
  const treeGapY = 80  // 行之间垂直间距

  sortedTrees.forEach(({ treeIdx, bbox }) => {
    const treeWidth = bbox.w + treeGapX
    // 如果当前行放不下这棵树，换行
    if (currentRow.length > 0 && currentRowWidth + treeWidth > maxRowWidth) {
      rows.push(currentRow)
      currentRow = []
      currentRowWidth = 0
    }
    currentRow.push({ treeIdx, bbox })
    currentRowWidth += treeWidth
  })
  if (currentRow.length > 0) {
    rows.push(currentRow)
  }

  console.log(`[runConceptLayout] Grid layout: ${rows.length} rows, maxRowWidth=${Math.round(maxRowWidth)}`)
  rows.forEach((row, ridx) => {
    console.log(`[runConceptLayout] Row ${ridx}: ${row.length} trees, totalWidth=${Math.round(row.reduce((sum, t) => sum + t.bbox.w + treeGapX, 0))}`)
  })

  // 放置每棵树
  let rowStartY = 30
  rows.forEach(row => {
    let rowHeight = 0
    let currentX = 30

    row.forEach(({ treeIdx, bbox }) => {
      const tree = allTrees[treeIdx]
      rowHeight = Math.max(rowHeight, bbox.h)

      const dx = currentX - bbox.x1
      const dy = rowStartY - bbox.y1

      // 移动该树所有节点
      tree.nodes.forEach(id => {
        const node = cy.getElementById(id)
        if (node.length > 0) {
          node.position('x', node.position('x') + dx)
          node.position('y', node.position('y') + dy)
        }
      })

      currentX += bbox.w + treeGapX
    })

    rowStartY += rowHeight + treeGapY
  })

  const totalGridHeight = rowStartY

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

  // P19-FIX: 二维网格布局，优先 fit 宽度，高度可滚动
  const zoomByWidth = (containerW * 0.85) / totalW
  const zoomByHeight = (containerH * 0.8) / totalH
  const zoom = Math.min(zoomByWidth, zoomByHeight, 0.5)
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

  // LA-035-P11: 处理非概念 chunk 节点（heading/paragraph/document）—— 排列成网格避免重叠
  const nonConceptChunkNodes = cy.nodes().filter(n => {
    const t = n.data('type')
    return t === 'heading' || t === 'paragraph' || t === 'document'
  })
  if (nonConceptChunkNodes.length > 0) {
    console.log(`[runConceptLayout] Arranging ${nonConceptChunkNodes.length} non-concept chunk nodes in grid`)
    const chunkCols = Math.max(1, Math.floor(containerW / 220))
    const chunkGapX = 200
    const chunkGapY = 100
    nonConceptChunkNodes.forEach((n, i) => {
      const col = i % chunkCols
      const row = Math.floor(i / chunkCols)
      // 放在概念树下方，避免重叠
      n.position({ x: 50 + col * chunkGapX, y: totalH + 50 + row * chunkGapY })
      n.style('display', 'element')
      n.style('opacity', 0.7)  // 半透明，表示是辅助节点
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

  // P19-FIX: 最终安全检查 — 遍历所有显示中的节点，将仍在原点的节点重新定位
  const visibleNodes = cy.nodes().filter(n => n.style('display') !== 'none')
  // P19-FIX-3b: 收紧阈值，避免误判正常布局的节点（网格第一列 x=0 但 y>0 不是 stuck）
  const stuckNodes = visibleNodes.filter(n => {
    const x = n.position('x')
    const y = n.position('y')
    return Math.abs(x) < 2 && Math.abs(y) < 2
  })
  if (stuckNodes.length > 0) {
    console.warn(`[runConceptLayout] ${stuckNodes.length} nodes stuck at origin, repositioning`)
    const sCols = Math.max(1, Math.ceil(Math.sqrt(stuckNodes.length)))
    const sGap = 150
    stuckNodes.forEach((n, i) => {
      try {
        const col = i % sCols
        const row = Math.floor(i / sCols)
        n.position({ x: 100 + col * sGap, y: totalH + 100 + row * sGap })
      } catch (e) {
        console.warn(`[runConceptLayout] Failed to reposition node ${n.id()}:`, e)
      }
    })
  }

  // 动态调整边曲率
  adjustEdgeCurvature(cy)
}
