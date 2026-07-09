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
 */
export function buildCyStyles() {
  return [
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
        'text-max-width': '110px',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '12px',
        'color': '#fff',
        'text-outline-color': 'rgba(0,0,0,0.6)',
        'text-outline-width': 2,
        'width': 160,
        'height': 'data(cardHeight)',
        'padding': '18px',
        'border-width': 2,
        'border-color': 'rgba(255,255,255,0.5)',
        'shape': 'round-rectangle',
        'corner-radius': 8,
      }
    },
    // 需求类型
    {
      selector: 'node[type="requirement"], node[type="sub_requirement"]',
      style: {
        'background-color': '#e74c3c',
        'border-color': '#c0392b',
      }
    },
    // 技术类型
    {
      selector: 'node[type="technology"], node[type="sub_technology"]',
      style: {
        'background-color': '#3498db',
        'border-color': '#2980b9',
      }
    },
    // 通用概念（含 Phase 2 提取的 definition/law/application/extension）
    {
      selector: 'node[type="concept"], node[type="definition"], node[type="law"], node[type="application"], node[type="extension"]',
      style: {
        'background-color': '#2ecc71',
        'border-color': '#27ae60',
      }
    },
    // ========== 图片节点样式（LA-035）==========
    {
      selector: 'node[chunkType="image"], node[?isImage]',
      style: {
        'label': '📷',
        'font-size': '24px',
        'text-valign': 'center',
        'text-halign': 'center',
        'color': '#fff',
        'width': 40,
        'height': 40,
        'border-width': 2,
        'border-color': '#e67e22',
        'background-color': '#f39c12',
        'shape': 'round-rectangle',
        'corner-radius': 6,
      }
    },
    // 图片节点高亮
    {
      selector: 'node[chunkType="image"]:selected, node[?isImage]:selected',
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
}
