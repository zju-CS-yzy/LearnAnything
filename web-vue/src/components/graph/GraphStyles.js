/**
 * GraphStyles.js — Cytoscape.js 样式配置
 * 集中管理所有节点/边样式，便于统一调整
 * LA-052 FIX: 移除所有无效的 isVirtual CSS 选择器（Cytoscape 不支持属性值匹配）
 * 虚拟节点样式通过 ele.style() 在 GraphView.vue 中动态设置（优先级最高）
 */

export const COLORS = {
  child: '#3498db',
  concept: '#2ecc71',
  belongs_to: '#3498db',
  adjacent_to: '#95a5a6',
  selected: '#f39c12',
  highlight: '#e74c3c',
  solution: '#e67e22',
  depends_on: '#9b59b6',
}

/**
 * 构建完整的 Cytoscape 样式数组
 * @param {Object} paradigmConfig - 可选的范式配置（LA-052: 动态生成语义边样式）
 */
export function buildCyStyles(paradigmConfig = null) {
  const styles = [
    // ========== 基础节点样式（Chunk 节点）==========
    {
      selector: 'node',
      style: {
        'label': 'data(label)',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '11px',
        'color': '#fff',
        'text-outline-color': '#2c3e50',
        'text-outline-width': 1,
        'width': 28,
        'height': 28,
        'border-width': 2,
        'border-color': '#2c3e50',
        'background-color': COLORS.child,
        'shape': 'ellipse',
      }
    },
    // 中心高亮节点
    {
      selector: 'node[?isCenter]',
      style: {
        'border-width': 4,
        'border-color': COLORS.selected,
        'width': 38,
        'height': 38,
      }
    },
    // 选中节点
    {
      selector: 'node:selected',
      style: {
        'border-width': 4,
        'border-color': COLORS.selected,
      }
    },
    // ========== Chunk 节点卡片样式（文档树）==========
    // heading/paragraph/document/child/markdown 统一卡片风格
    {
      selector: 'node[chunkType="heading"], node[chunkType="paragraph"], node[chunkType="document"], node[chunkType="child"], node[chunkType="markdown"]',
      style: {
        'label': 'data(cardLabel)',
        'text-wrap': 'wrap',
        'text-max-width': 'data(nodeWidth)',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '11px',
        'color': '#fff',
        'text-outline-color': 'rgba(0,0,0,0.5)',
        'text-outline-width': 1,
        'width': 'data(nodeWidth)',
        'height': 'data(cardHeight)',
        'border-width': 3,
        'border-color': 'data(borderColor)',
        'shape': 'round-rectangle',
        'corner-radius': 10,
      }
    },
    // Heading 节点 — 红色
    {
      selector: 'node[chunkType="heading"]',
      style: {
        'background-color': '#e74c3c',
      }
    },
    // Paragraph 节点 — 蓝色
    {
      selector: 'node[chunkType="paragraph"]',
      style: {
        'background-color': '#3498db',
      }
    },
    // Document 节点 — 绿色
    {
      selector: 'node[chunkType="document"]',
      style: {
        'background-color': '#27ae60',
      }
    },
    // Child/Markdown 节点 — 灰色
    {
      selector: 'node[chunkType="child"], node[chunkType="markdown"]',
      style: {
        'background-color': '#7f8c8d',
        'border-color': '#616a6b',
      }
    },
    // 图片节点
    {
      selector: 'node[chunkType="image"], node[chunkType="image_pseudo"]',
      style: {
        'label': '',
        'background-image': 'data(bgImage)',
        'background-fit': 'cover',
        'background-color': '#f39c12',
        'width': 60,
        'height': 60,
        'shape': 'round-rectangle',
      }
    },
    // 图片节点无图片时显示图标
    {
      selector: 'node[chunkType="image"][bgImage = "none"], node[chunkType="image_pseudo"][bgImage = "none"]',
      style: {
        'label': '📷',
        'font-size': '24px',
        'text-valign': 'center',
        'text-halign': 'center',
        'color': '#fff',
        'background-color': '#f39c12',
      }
    },
    // 图片节点选中效果
    {
      selector: 'node[chunkType="image"]:selected, node[chunkType="image_pseudo"]:selected',
      style: {
        'border-width': 4,
        'border-color': COLORS.selected,
      }
    },
    // ========== 概念节点样式（UML 类图卡片风格）==========
    // LA-052: 虚拟节点的样式通过 ele.style() 在 GraphView.vue 中设置（优先级高于 CSS）
    // 此处不再使用 :not([isVirtual = true])（Cytoscape 不支持该语法）
    {
      selector: 'node[type="concept"], node[type="requirement"], node[type="sub_requirement"], node[type="technology"], node[type="sub_technology"], node[type="definition"], node[type="law"], node[type="application"], node[type="extension"]',
      style: {
        'label': 'data(cardLabel)',
        'text-wrap': 'wrap',
        'text-max-width': 'data(nodeWidth)',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '11px',
        'color': '#fff',
        'text-outline-color': 'rgba(0,0,0,0.5)',
        'text-outline-width': 1,
        'width': 'data(nodeWidth)',
        'height': 'data(cardHeight)',
        'border-width': 3,
        'border-color': 'data(borderColor)',
        'shape': 'round-rectangle',
        'corner-radius': 10,
      }
    },
    // 需求类型 — 背景色红色
    {
      selector: 'node[type="requirement"], node[type="sub_requirement"]',
      style: {
        'background-color': '#e74c3c',
      }
    },
    // 技术类型 — 背景色蓝色
    {
      selector: 'node[type="technology"], node[type="sub_technology"]',
      style: {
        'background-color': '#3498db',
      }
    },
    // 通用概念 — 背景色绿色
    {
      selector: 'node[type="concept"], node[type="definition"], node[type="law"], node[type="application"], node[type="extension"]',
      style: {
        'background-color': '#2ecc71',
      }
    },
    // ========== 全局边默认样式 ==========
    {
      selector: 'edge',
      style: {
        'curve-style': 'bezier',
        'source-endpoint': '100% 50%',
        'target-endpoint': '0% 50%',
      }
    },
    // ========== chunk-level 边样式（概念-段落归属 / 文档树层级）==========
    // BELONGS_TO: 文档树结构边（父→子）
    // HAS_CONCEPT: 概念-段落归属边
    {
      selector: 'edge[type="BELONGS_TO"], edge[type="HAS_CONCEPT"]',
      style: {
        'width': 1.5,
        'line-color': COLORS.belongs_to,
        'target-arrow-shape': 'triangle',
        'target-arrow-color': COLORS.belongs_to,
        'curve-style': 'bezier',
        'source-endpoint': '100% 50%',
        'target-endpoint': '0% 50%',
        'arrow-scale': 0.8,
      }
    },
    // ========== 相邻关系（段落-段落）==========
    {
      selector: 'edge[type="ADJACENT_TO"]',
      style: {
        'width': 1,
        'line-color': COLORS.adjacent_to,
        'line-style': 'dashed',
        'curve-style': 'bezier',
      }
    },
    // ========== SOLUTION: 概念层"解决"关系（上层→下层）==========
    {
      selector: 'edge[type="SOLUTION"]',
      style: {
        'line-color': COLORS.solution,
        'target-arrow-color': COLORS.solution,
        'line-style': 'solid',
        'width': 2,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    // ========== DEPENDS_ON: 概念层"依赖"关系（旧名，有S）==========
    {
      selector: 'edge[type="DEPENDS_ON"]',
      style: {
        'line-color': COLORS.depends_on,
        'target-arrow-color': COLORS.depends_on,
        'line-style': 'dashed',
        'width': 1.5,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    // ========== IMPLEMENTS: 概念层"实现"关系（新名，YAML v2.0）==========
    {
      selector: 'edge[type="IMPLEMENTS"]',
      style: {
        'line-color': COLORS.solution,
        'target-arrow-color': COLORS.solution,
        'line-style': 'solid',
        'width': 2,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    // ========== DEPEND_ON: 概念层"依赖"关系（新名，YAML v2.0，无S）==========
    {
      selector: 'edge[type="DEPEND_ON"]',
      style: {
        'line-color': COLORS.depends_on,
        'target-arrow-color': COLORS.depends_on,
        'line-style': 'dashed',
        'width': 1.5,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    // ========== DERIVED_FROM: ExtractedConcept → CanonicalConcept ==========
    {
      selector: 'edge[type="DERIVED_FROM"]',
      style: {
        'width': 1.5,
        'line-color': '#8e44ad',
        'line-style': 'dashed',
        'target-arrow-shape': 'triangle',
        'target-arrow-color': '#8e44ad',
        'curve-style': 'bezier',
        'arrow-scale': 0.8,
      }
    },
    // ========== 高亮状态（搜索高亮 / hover）==========
    {
      selector: '.highlighted',
      style: {
        'border-width': 3,
        'border-color': COLORS.highlight,
      }
    },
    {
      selector: '.highlighted-edge',
      style: {
        'line-color': COLORS.highlight,
        'target-arrow-color': COLORS.highlight,
        'width': 2.5,
      }
    },
    // ========== 其他语义边类型（通用兜底）==========
    {
      selector: 'edge[type="DEFINES"]',
      style: {
        'line-color': '#8e44ad',
        'target-arrow-color': '#8e44ad',
        'width': 1.5,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    {
      selector: 'edge[type="REQUIRES"]',
      style: {
        'line-color': '#c0392b',
        'target-arrow-color': '#c0392b',
        'width': 1.5,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    {
      selector: 'edge[type="HAS_LAW"]',
      style: {
        'line-color': '#16a085',
        'target-arrow-color': '#16a085',
        'width': 1.5,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    {
      selector: 'edge[type="APPLIES_TO"]',
      style: {
        'line-color': '#d35400',
        'target-arrow-color': '#d35400',
        'width': 1.5,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    {
      selector: 'edge[type="EXTENDS"]',
      style: {
        'line-color': '#2980b9',
        'target-arrow-color': '#2980b9',
        'width': 1.5,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    {
      selector: 'edge[type="HAS_SUB"]',
      style: {
        'line-color': '#27ae60',
        'target-arrow-color': '#27ae60',
        'width': 1.5,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    {
      selector: 'edge[type="HAS_IMPL"]',
      style: {
        'line-color': '#f39c12',
        'target-arrow-color': '#f39c12',
        'width': 1.5,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    // ========== 副本样式 ==========
    {
      selector: 'edge[isCopyEdge = 1]',
      style: {
        'line-style': 'dashed',
        'line-color': '#f39c12',
        'width': 1.5,
      }
    },
  ]

  // LA-052: 如果提供了范式配置，动态生成语义边样式（覆盖硬编码）
  if (paradigmConfig && paradigmConfig.styles) {
    for (const [relType, styleCfg] of Object.entries(paradigmConfig.styles)) {
      // 移除已有的同类型样式（如果有）
      const existingIdx = styles.findIndex(s => 
        s.selector === `edge[type="${relType}"]`
      )
      if (existingIdx >= 0) {
        styles.splice(existingIdx, 1)
      }
      // 添加动态样式
      styles.push({
        selector: `edge[type="${relType}"]`,
        style: {
          'line-color': styleCfg.color || '#95a5a6',
          'target-arrow-color': styleCfg.color || '#95a5a6',
          'line-style': styleCfg.lineStyle || 'solid',
          'width': styleCfg.width || 1.5,
          'target-arrow-shape': 'triangle',
          'arrow-scale': 0.8,
        }
      })
    }
  }

  return styles
}
