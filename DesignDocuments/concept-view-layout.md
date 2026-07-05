# LearnAnything 概念视图布局设计文档

## 1. 设计目标

实现一个清晰、可读的概念知识图谱可视化，支持：
- 文档视图（chunk 节点的小圆点树形布局）
- 概念视图（UML 卡片节点的树形布局）

本文档聚焦于**概念视图**的布局设计。

## 2. 数据结构

### 2.1 节点类型

```
节点类型（type 字段）:
- concept          - 通用概念
- requirement      - 需求/目标
- sub_requirement  - 子需求
- technology       - 技术/方法
- sub_technology   - 子技术
- child            - 文档 chunk（仅在文档视图显示）
- parent           - 文档父节点（仅在文档视图显示）
- markdown         - Markdown 节点（仅在文档视图显示）
```

### 2.2 节点属性

```
节点 data 属性:
- id: string              - 唯一标识（与后端 concept_id 一致）
- label: string            - 显示名称（不超过 12 字符）
- cardLabel: string        - UML 卡片完整标签（含类型、描述）
- cardHeight: number       - 根据描述长度计算的自适应高度
- type: string             - 节点类型（见 2.1）
- description: string      - 概念描述（不超过 60 字，显示 4 行）
- parent_hint: string      - 父节点提示
- source_chunks: string    - 来源 chunk
- isCopy: '1' | undefined  - 副本标记
- originalId: string       - 副本指向的原始节点 ID
```

### 2.3 边类型

```
边类型（type 字段）:
- SOLUTION      - 解决关系（红色实线，箭头指向"被解决"的概念）
- DEPENDS_ON    - 依赖关系（蓝色虚线，箭头指向"依赖"的概念）
- BELONGS_TO    - 归属关系（chunk → 父 chunk，文档视图）
- ADJACENT_TO   - 相邻关系（chunk → chunk，文档视图）
- isCopyEdge: '1' - 副本边标记（橙色虚线，指向副本节点）
```

## 3. 布局设计原则

### 3.1 分树（Forest）策略

原始数据是 DAG（有向无环图），可能存在多棵独立的树。每棵树必须独立布局，避免相互干扰。

**分树算法**（BFS）：
1. 找到所有根节点（入度为 0 的节点）
2. 从每个根节点出发，双向 BFS 遍历所有可达节点
3. 收集到的节点集合构成一棵树
4. 处理循环中的未分配节点（作为额外树）

### 3.2 树内副本策略

dagre 布局算法不支持 DAG（多父节点）。当树内节点有多个父节点时：

1. **保留原始节点**：连接第一个父节点
2. **创建副本节点**：连接其他父节点
3. **副本标记**：`isCopy: '1'`，样式为橙色虚线边框
4. **副本 ID**：`{originalId}_copy{index}_tree{treeIndex}`

**关键约束**：副本只在**同一棵树内**创建，不跨树创建副本。

### 3.3 独立 dagre 布局

每棵树使用 cytoscape-dagre 独立布局：
- `rankDir: 'LR'` - 从左到右
- `rankSep: 250` - 层间距
- `nodeSep: 80` - 节点间距
- `fit: false` - 禁用自动 fit，避免 zoom 跳动

**布局前重置**：将树内所有节点位置设为 (0, 0)，避免前一棵树的布局影响当前树。

### 3.4 垂直堆叠

多棵树按从上到下排列：
1. 计算每棵树布局后的 bbox
2. `currentY = 0`
3. 平移第 i 棵树：`dy = currentY - bbox.y1`
4. 更新 `currentY += bbox.height + treeGap`（treeGap = 200）

## 4. 渲染设计

### 4.1 节点样式（概念节点）

```javascript
{
  'label': 'data(cardLabel)',
  'text-wrap': 'wrap',
  'text-max-width': '110px',
  'text-valign': 'center',
  'text-halign': 'center',
  'font-size': '12px',
  'color': '#fff',
  'text-outline-color': 'rgba(0,0,0,0.6)',
  'text-outline-width': 2,
  'width': 160,               // 固定宽度
  'height': 'data(cardHeight)', // 自适应高度
  'padding': '18px',
  'border-width': 2,
  'border-color': 'rgba(255,255,255,0.5)',
  'shape': 'round-rectangle',
  'corner-radius': 8,
}
```

### 4.2 节点颜色（按类型）

| 类型 | 颜色 | 用途 |
|------|------|------|
| requirement | `#3b82f6` | 需求/目标 |
| sub_requirement | `#60a5fa` | 子需求 |
| technology | `#10b981` | 技术/方法 |
| sub_technology | `#6ee7b7` | 子技术 |
| concept | `#8b5cf6` | 通用概念 |
| 副本 | 橙色虚线边框 | 多父节点副本 |

### 4.3 边样式

```javascript
// SOLUTION 边（红色实线）
{
  'line-color': '#ef4444',
  'target-arrow-color': '#ef4444',
  'curve-style': 'straight',
  'target-arrow-shape': 'triangle',
}

// DEPENDS_ON 边（蓝色虚线）
{
  'line-color': '#3b82f6',
  'target-arrow-color': '#3b82f6',
  'line-style': 'dashed',
  'curve-style': 'straight',
  'target-arrow-shape': 'triangle',
}

// 副本边（橙色虚线）
{
  'line-style': 'dashed',
  'line-color': '#ff9f43',
  'target-arrow-color': '#ff9f43',
}
```

## 5. 交互设计

### 5.1 视图切换
- 📄 文档视图：显示 chunk 节点，运行自定义树形布局
- 🧩 概念视图：显示概念节点，运行 dagre 布局
- ⬜ 适应：fit 到容器
- 🔄 重置：重新运行当前视图的布局

### 5.2 搜索
- 输入关键字实时过滤节点
- 匹配节点高亮，其他节点淡化
- 支持重置搜索

### 5.3 节点交互
- 悬停：高亮节点和关联边
- 点击：显示详情面板（名称、类型、描述、来源 chunks）

## 6. 数据加载流程

```
1. 清除 cytoscape 中所有现有元素（cy.elements().remove()）
2. 加载 chunk 节点（BELONGS_TO/ADJACENT_TO 边）
3. 加载概念节点（SOLUTION/DEPENDS_ON 边）
4. 判断：如果存在概念节点 → 概念视图；否则 → 文档视图
5. 运行对应布局
6. 固定 zoom（min(容器宽/图宽, 容器高/图高, 0.5)，限制 0.15~0.5）
7. 居中显示
```

## 7. 错误处理

- API 加载失败：控制台报错，不影响已有显示
- 边悬空（source/target 节点不存在）：控制台警告，不添加边
- 数据库无数据：显示空图，不报错

## 8. Git 提交策略

每次修改后必须提交：
```bash
git add .
git commit -m "feat: 描述修改内容"
```

关键提交点：
- 基础 cytoscape 初始化
- 文档视图布局
- 概念视图加载
- 分树布局
- 副本策略
- 样式优化
- 交互功能
