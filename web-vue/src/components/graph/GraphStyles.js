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

// 概念类型使用稳定的语义色，而不是按范式统一涂色。
// 所有颜色均与白色正文保持足够对比；节点卡片中的类型文字同时提供非颜色线索。
export const CONCEPT_TYPE_COLORS = Object.freeze({
  requirement: '#C0392B',
  sub_requirement: '#C0392B',
  technology: '#2874A6',
  sub_technology: '#2874A6',
  concept: '#237A45',
  definition: '#2563EB',
  law: '#7E22CE',
  application: '#C2410C',
  extension: '#0F766E',
})

export const CONCEPT_TYPE_BORDER_COLORS = Object.freeze({
  requirement: '#922B21',
  sub_requirement: '#922B21',
  technology: '#1B4F72',
  sub_technology: '#1B4F72',
  concept: '#196F3D',
  definition: '#1D4ED8',
  law: '#6B21A8',
  application: '#9A3412',
  extension: '#115E59',
})

export function getConceptTypeColor(type) {
  return CONCEPT_TYPE_COLORS[type] || CONCEPT_TYPE_COLORS.concept
}

export function getConceptTypeBorderColor(type) {
  return CONCEPT_TYPE_BORDER_COLORS[type] || CONCEPT_TYPE_BORDER_COLORS.concept
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
    // Gap Flow M2: frontend-only placeholder; never persisted as CanonicalConcept.
    {
      selector: 'node[?isVirtualGap]',
      style: {
        'label': 'data(label)',
        'width': 34,
        'height': 34,
        'shape': 'ellipse',
        'background-color': '#fff8f0',
        'background-opacity': 0.75,
        'border-width': 3,
        'border-style': 'dashed',
        'border-color': '#e67e22',
        'color': '#9a4d08',
        'font-size': '10px',
        'font-weight': 700,
        'text-outline-width': 0,
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
    // 需求类型 -- 背景色红色
    {
      selector: 'node[type="requirement"], node[type="sub_requirement"]',
      style: {
        'background-color': '#e74c3c',
      }
    },
    // 技术类型 -- 背景色蓝色
    {
      selector: 'node[type="technology"], node[type="sub_technology"]',
      style: {
        'background-color': '#3498db',
      }
    },
    // 通用概念
    {
      selector: 'node[type="concept"]',
      style: {
        'background-color': CONCEPT_TYPE_COLORS.concept,
      }
    },
    // Theory 范式：定义、规律、应用、扩展使用可辨识的语义色。
    {
      selector: 'node[type="definition"]',
      style: {
        'background-color': CONCEPT_TYPE_COLORS.definition,
      }
    },
    {
      selector: 'node[type="law"]',
      style: {
        'background-color': CONCEPT_TYPE_COLORS.law,
      }
    },
    {
      selector: 'node[type="application"]',
      style: {
        'background-color': CONCEPT_TYPE_COLORS.application,
      }
    },
    {
      selector: 'node[type="extension"]',
      style: {
        'background-color': CONCEPT_TYPE_COLORS.extension,
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
    // Heading 节点 -- 红色
    {
      selector: 'node[chunkType="heading"]',
      style: {
        'background-color': '#e74c3c',
        'border-color': '#c0392b',
      }
    },
    // Paragraph 节点 -- 蓝色
    {
      selector: 'node[chunkType="paragraph"]',
      style: {
        'background-color': '#3498db',
        'border-color': '#2980b9',
      }
    },
    // Document 节点 -- 绿色
    {
      selector: 'node[chunkType="document"]',
      style: {
        'background-color': '#27ae60',
        'border-color': '#1e8449',
      }
    },
    // 其他 chunk 节点 -- 灰色
    {
      selector: 'node[chunkType="child"], node[chunkType="markdown"]',
      style: {
        'background-color': '#7f8c8d',
        'border-color': '#616a6b',
      }
    },
    // ========== 图片节点样式（P41: 背景图预览）==========
    // LA-035-P43: 图片节点宽度与其他文档树节点一致（nodeWidth），高度根据图片比例自适应
    {
      selector: 'node[chunkType="image"], node[chunkType="image_pseudo"]',
      style: {
        'label': '',
        'background-image': 'data(bgImage)',
        'background-fit': 'contain',           // ← 改为 contain，完整显示图片不裁剪
        'background-color': '#f39c12',
        'width': 'data(nodeWidth)',            // ← 与其他文档树节点宽度一致
        'height': 'data(cardHeight)',          // ← 根据图片比例自适应的高度
        'border-width': 2,
        'border-color': '#e67e22',
        'shape': 'round-rectangle',
        'corner-radius': 6,
      }
    },
    // 图片节点加载失败时的回退样式（bgImage 为 'none' 时显示相机）
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
    // Gap completion: supplemented records resolve to real concepts, not virtual nodes.
    {
      selector: 'node.gap-supplemented-node',
      style: {
        'border-width': 5,
        'border-color': '#2f9e62',
      }
    },
    {
      selector: 'node.gap-completion-focus',
      style: {
        'border-width': 5,
        'border-color': '#15864c',
        'underlay-color': '#43b977',
        'underlay-opacity': 0.24,
        'underlay-padding': 12,
      }
    },
    // 使用角度值精确固定在节点边界：
    // - 0deg = 12点钟方向（上中）
    // - 90deg = 3点钟方向（右中）<- 源端点
    // - 180deg = 6点钟方向（下中）
    // - 270deg = 9点钟方向（左中）<- 目标端点
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
    {
      selector: 'edge[type="VIRTUAL_GAP_EDGE"]',
      style: {
        'line-color': '#d59a61',
        'target-arrow-color': '#d59a61',
        'line-style': 'dashed',
        'width': 2,
        'opacity': 0.82,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.7,
      }
    },
    {
      selector: 'edge.gap-skip-edge',
      style: {
        'line-style': 'dashed',
        'opacity': 0.14,
        'width': 1,
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
    // Theory paradigm semantic relationships.
    {
      selector: 'edge[type="DEFINES"]',
      style: {
        'line-color': '#2980b9',
        'target-arrow-color': '#2980b9',
        'line-style': 'solid',
        'width': 2,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    {
      selector: 'edge[type="HAS_LAW"]',
      style: {
        'line-color': '#8e44ad',
        'target-arrow-color': '#8e44ad',
        'line-style': 'solid',
        'width': 2,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    {
      selector: 'edge[type="APPLIES_TO"]',
      style: {
        'line-color': '#16a085',
        'target-arrow-color': '#16a085',
        'line-style': 'solid',
        'width': 2,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    {
      selector: 'edge[type="EXTENDS"]',
      style: {
        'line-color': '#d35400',
        'target-arrow-color': '#d35400',
        'line-style': 'dashed',
        'width': 2,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
      }
    },
    // DERIVED_FROM: ExtractedConcept -> CanonicalConcept
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
    // HAS_CONCEPT: Chunk -> ExtractedConcept
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
