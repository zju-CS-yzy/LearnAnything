/**
 * GraphStyles.js — Cytoscape.js 样式配置
 * 集中管理所有节点/边样式，便于统一调整
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
    // ========== 概念节点样式（UML 类图卡片风格）==========
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
    // 通用概念（含 Phase 2 提取的 definition/law/application/extension）— 背景色绿色
    {
      selector: 'node[type="concept"], node[type="definition"], node[type="law"], node[type="application"], node[type="extension"]',
      style: {
        'background-color': '#2ecc71',
      }
    },
    // ========== 文档树节点卡片风格（P34）==========
    // 通用卡片样式（heading/paragraph/document/child/markdown）
    {
      selector: 'node[chunkType="heading"], node[chunkType="paragraph"], node[chunkType="document"], node[chunkType="child"], node[chunkType="markdown"]',
      style: {
        'label': 'data(cardLabel)',
        'text-wrap': 'wrap',
        'text-max-width': 'data(nodeWidth)',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '10px',
        'color': '#fff',
        'text-outline-color': 'rgba(0,0,0,0.5)',
        'text-outline-width': 1,
        'width': 'data(nodeWidth)',
        'height': 'data(cardHeight)',
        'border-width': 2,
        'shape': 'round-rectangle',
        'corner-radius': 8,
      }
    },
    // Heading 节点 — 红色
    {
      selector: 'node[chunkType="heading"]',
      style: {
        'background-color': '#e74c3c',
        'border-color': '#c0392b',
      }
    },
    // Paragraph 节点 — 蓝色
    {
      selector: 'node[chunkType="paragraph"]',
      style: {
        'background-color': '#3498db',
        'border-color': '#2980b9',
      }
    },
    // Document 节点 — 绿色
    {
      selector: 'node[chunkType="document"]',
      style: {
        'background-color': '#27ae60',
        'border-color': '#1e8449',
      }
    },
    // 其他 chunk 节点 — 灰色
    {
      selector: 'node[chunkType="child"], node[chunkType="markdown"]',
      style: {
        'background-color': '#7f8c8d',
        'border-color': '#616a6b',
      }
    },
    // ========== 图片节点样式（P41: 背景图预览）==========
    {
      selector: 'node[chunkType="image"], node[chunkType="image_pseudo"]',
      style: {
        'label': '',
        'background-image': 'data(bgImage)',
        'background-fit': 'cover',
        'background-color': '#f39c12',
        'width': 80,
        'height': 80,
        'border-width': 2,
        'border-color': '#e67e22',
        'shape': 'round-rectangle',
        'corner-radius': 6,
      }
    },
    // 图片节点加载失败时的回退样式（bgImage 为 'none' 时显示 📷）
    {
      selector: 'node[chunkType="image"][bgImage = "none"], node[chunkType="image_pseudo"][bgImage = "none"]',
      style: {
        'label': '📷',
        'font-size': '24px',
        'text-valign': 'center',
        'text-halign': 'center',
        'color': '#fff',
        'width': 40,
        'height': 40,
      }
    },
    // 图片节点高亮
    {
      selector: 'node[chunkType="image"]:selected, node[chunkType="image_pseudo"]:selected',
      style: {
        'border-width': 4,
        'border-color': COLORS.selected,
      }
    },
    // 使用角度值精确固定在节点边界：
    // - 0deg = 12点钟方向（上中）
    // - 90deg = 3点钟方向（右中）← 源端点
    // - 180deg = 6点钟方向（下中）
    // - 270deg = 9点钟方向（左中）← 目标端点
    {
      selector: 'edge',
      style: {
        'curve-style': 'unbundled-bezier',
        'source-endpoint': '90deg',
        'target-endpoint': '270deg',
      }
    },
    // BELONGS_TO: 文档树结构边
    {
      selector: 'edge[type="BELONGS_TO"]',
      style: {
        'line-color': COLORS.belongs_to,
        'target-arrow-color': COLORS.belongs_to,
        'line-style': 'solid',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    // ADJACENT_TO: 相邻 chunk 边
    {
      selector: 'edge[type="ADJACENT_TO"]',
      style: {
        'line-color': COLORS.adjacent_to,
        'target-arrow-color': COLORS.adjacent_to,
        'line-style': 'dashed',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    // SOLUTION: 概念层"解决"关系
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
    // DEPENDS_ON: 概念层"依赖"关系
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
    // LA-027 FIX: IMPLEMENTS（新类型，同 SOLUTION 样式）
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
    // LA-027 FIX: DEPEND_ON（新类型，同 DEPENDS_ON 样式）
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
    // DERIVED_FROM: ExtractedConcept → CanonicalConcept
    {
      selector: 'edge[type="DERIVED_FROM"]',
      style: {
        'line-color': '#9b59b6',
        'target-arrow-color': '#9b59b6',
        'line-style': 'dotted',
        'width': 1.5,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    // HAS_CONCEPT: Chunk → ExtractedConcept
    {
      selector: 'edge[type="HAS_CONCEPT"]',
      style: {
        'line-color': '#1abc9c',
        'target-arrow-color': '#1abc9c',
        'line-style': 'solid',
        'width': 1.5,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    // ========== 虚拟节点样式（LA-046 / LA-052）==========
    // Cytoscape [isVirtual] 只要属性存在就匹配，必须指定值
    {
      selector: 'node[isVirtual = true]',
      style: {
        'label': 'data(label)',
        'text-wrap': 'wrap',
        'text-max-width': '80px',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '9px',
        'color': '#E67E22',
        'text-outline-color': '#fff',
        'text-outline-width': 1,
        // LA-052 FIX: 固定为小圆形，不依赖 nodeWidth/cardHeight
        'width': 24,
        'height': 24,
        'border-width': 2,
        'border-style': 'dashed',
        'border-color': '#E67E22',
        'background-color': 'rgba(230, 126, 34, 0.15)',
        'shape': 'ellipse',
      }
    },
    // ========== 副本样式 ==========
    {
      selector: 'node[isCopy = 1]',
      style: {
        'border-style': 'dashed',
        'border-width': 2,
        'border-color': '#f39c12',
        'opacity': 0.9,
      }
    },
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
