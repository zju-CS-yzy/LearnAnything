const fs = require('fs');

const file = 'D:\\MyCS\\AI\\Project\\LearnAnything\\web-vue\\src\\components\\GraphView.vue';
let content = fs.readFileSync(file, 'utf-8');

// 1. 修改连线样式
const oldEdgeStyle = `      // 语义层连接边样式（从左到右曲线）
      {
        selector: 'edge[type="SOLUTION"], edge[type="DEPENDS_ON"]',
        style: {
          'curve-style': 'bezier',
          'control-point-step-size': 60,
          'source-endpoint': 'outside-to-node',
          'target-endpoint': 'outside-to-node',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 0.9,
          'width': 1.5,
        }
      },`;

const newEdgeStyle = `      // 语义层连接边样式（从右到左曲线）
      {
        selector: 'edge[type="SOLUTION"], edge[type="DEPENDS_ON"]',
        style: {
          'curve-style': 'bezier',
          'control-point-step-size': 80,
          'source-endpoint': '0deg',
          'target-endpoint': '180deg',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 0.9,
          'width': 1.5,
        }
      },`;

content = content.replace(oldEdgeStyle, newEdgeStyle);

// 2. 添加 isConceptNode 和 getNodeLinks 函数
const beforeFitGraph = `function fitGraph() {`;
const newFunctions = `function isConceptNode(node) {
  if (!node) return false
  const t = node.type || ''
  return ['concept', 'requirement', 'sub_requirement', 'technology', 'sub_technology'].includes(t)
}

function getNodeLinks(nodeId) {
  if (!window.cy) return []
  const links = []
  const node = cy.getElementById(nodeId)
  if (!node) return links
  
  // 出边（当前节点是父节点）
  node.outgoers('edge').forEach(e => {
    links.push({
      id: e.id(),
      direction: 'out',
      type: e.data('type'),
      targetId: e.target().id(),
      targetName: e.target().data('label') || e.target().id(),
    })
  })
  
  // 入边（当前节点是子节点）
  node.incomers('edge').forEach(e => {
    links.push({
      id: e.id(),
      direction: 'in',
      type: e.data('type'),
      targetId: e.source().id(),
      targetName: e.source().data('label') || e.source().id(),
    })
  })
  
  return links
}

function fitGraph() {`;

content = content.replace(beforeFitGraph, newFunctions);

fs.writeFileSync(file, content);
console.log('Done');
