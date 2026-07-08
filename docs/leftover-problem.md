

---

## 2026-07-07 新增/更新

### ✅ 已完成

#### 1. 四层数据模型 v2.0
- **状态**: ✅ **已完成**
- **Schema 变更**:
  - Chunk -(HAS_CONCEPT)-> ExtractedConcept -(DERIVED_FROM)-> CanonicalConcept -(SOLUTION/DEPENDS_ON)-> CanonicalConcept
  - 删除旧关系：REQUIRES/IMPLEMENTS/HAS_SUB/HAS_IMPL/DEFINES/HAS_LAW/APPLIES_TO/EXTENDS
- **关键提交**: `2b61f42`, `41e90be`, `b8f453a`, `a559d86`, `3fb426c`, `2dd13d8`, `f71105c`
- **数据**: 553 CanonicalConcept, 364 语义边 (SOLUTION 131 + DEPENDS_ON 233)

#### 2. 详情面板来源引用
- **状态**: ✅ **已完成**
- **内容**: canonical 概念节点显示人类可读的来源引用（文件名|章节|页码），Chunk ID 折叠显示

### 🔴 遗留问题

#### LA-030: 部分 PDF 文档未提取出概念
- **状态**: 🔴 **高优先级**
- **描述**: generic_v1 学科导入了 4 篇文档（164 chunks），但概念提取只涉及 2 篇
  - AI大模型公司项目落地实战.pdf (120 chunks) → 提取出概念
  - AI大模型高校千行百业实战.pdf (40 chunks) → ❌ 未提取出任何概念
  - Graph RAG前沿研究.pdf (2 chunks) → ❌ 未提取出任何概念
- **根因**: 未知，需调查 SemanticExtractor 的提取逻辑或文档内容
- **影响**: 图谱来源单一，知识覆盖不完整

#### LA-031: PDF 导入缺少章节/页码信息
- **状态**: 🔴 **高优先级**
- **描述**: PDF 分块后 heading_path 为空，page_number 为 0，导致来源引用只有文件名
- **根因**: 当前 PDF 文本提取只保留了纯文本，没有保留章节结构和页码
- **影响**: 来源引用信息不完整，用户无法追溯到具体章节段落
- **方向**: 需要重新设计 PDF 提取流程，保留 heading_path 和 page_number

#### LA-032: 批量 embedding API 400 错误
- **状态**: 🟡 **中优先级**
- **描述**: SemanticLinker Stage 2/3（embedding 相似度 + LLM 确认）无法执行
- **根因**: 智谱 embedding-3 API 批量请求返回 400
- **影响**: Stage 1 (parent_hint) 已覆盖主要连接，Stage 2/3 可暂不处理

#### LA-029 (更新): 概念节点详情来源信息
- **状态**: ✅ **已修复**
- **说明**: 详情面板已显示来源引用（文件名），但章节页码信息待 LA-031 解决后自动改善

### ✅ 已解决并归档

#### LA-028: 孤立概念过多 → 四层模型解决
- **解决**: CanonicalConcept 层有 364 条语义边，无孤立节点
- **归档**: 2026-07-07

---

## 2026-07-06 新增/更新

### ✅ 已完成

#### 1. 前端重写（LA-023）
- **状态**: ✅ **已完成**
- **提交**: `704330b`
- **内容**: 基于 `web_bak/` 重建 `web-vue/` 目录
  - 保留稳定组件：Sidebar、ChatView、QuizView、EvaluateView、ImportView、KnowledgeBaseView
  - 重写 GraphView：从 1200+ 行拆分为 6 个模块文件
  - 新增：GraphLayout.js、GraphStyles.js、NodeDetailPanel.vue、BuildOptions.vue、ConceptTable.vue
  - 构建成功：`npm run build` 输出到 `../web/dist`

#### 2. 概念边截断修复（LA-024）
- **状态**: ✅ **已修复**
- **提交**: `deeec7d`
- **根因**: `get_concept_links()` 将 `limit=500` 均分给 10 种关系类型，每种只查 51 条
- **修复**: `core/graph_store.py` 去掉 per-type 限制，改为 `LIMIT {limit}`
- **效果**: API 返回全部 167 条语义边（SOLUTION 60 + DEPENDS_ON 107）

#### 3. 孤立节点隐藏
- **状态**: ✅ **已完成**
- **提交**: `f0953a7`
- **内容**: 隐藏 1303 个无连接的孤立概念节点（`display: 'none'`）
- **效果**: 画布只显示 186 个有语义边连接的节点

#### 4. 树布局交错问题修复（LA-026）
- **状态**: ✅ **已修复**
- **最终提交**: `3ffd230`（经过多次迭代和回退）
- **根因**: 51 节点分量含 8 个根节点，但整分量当作 1 棵树跑 dagre，导致视觉交错
- **修复**: 副本处理后按根拆分为独立子树，每棵子树独立 dagre LR + 重置位置
- **效果**: 恢复到 7月2日版本效果 ✅

#### 5. 节点详情面板优化
- **状态**: ✅ **已完成**
- **内容**: 概念节点不再显示空的"来源"/"页码"，改为显示节点类型标签

---

### 🔴 遗留问题

#### LA-028: 孤立节点过多（1303个，占87.5%）
- **状态**: 🔴 **待解决**
- **描述**: generic 学科 1489 个概念节点中，仅 186 个有语义边连接，1303 个完全孤立
- **根因**: 语义连接算法仅建立 167 条边，覆盖率极低
- **数据**:
  - Chunk 节点: 163
  - Concept 节点: 1489
  - 有连接的 Concept: 186 (12.5%)
  - 孤立 Concept: 1303 (87.5%)
  - 语义边: 167 (SOLUTION 60 + DEPENDS_ON 107)
- **方向**: 需要改进 chunk 分层提取、关键词匹配、语义连接算法

#### LA-029: 概念节点详情缺少来源信息
- **状态**: 🟡 **部分修复**
- **描述**: 节点详情面板中，概念节点的"来源"和"页码"显示为空（`-`）
- **根因**: 概念节点本身没有 `source`/`page_number` 字段（这些是 chunk 节点的属性）
- **修复**: 面板已根据节点类型显示不同信息（概念节点显示 type 标签，隐藏 source/page）
- **遗留**: `source_chunks` 字段显示为纯文本（如 `generic_text_67`），可读性待优化

---

### Git 提交记录（2026-07-06）

| 提交 | 内容 | 状态 |
|:---|:---|:---:|
| `704330b` | rebuild web-vue frontend v2.0 | ✅ |
| `deeec7d` | fix graph: remove cy.fit() overlay | ✅ |
| `f0953a7` | hide orphan nodes + tighten tree gap | ✅ |
| `5cf1756` | 2D grid layout | ❌ 回退 |
| `60ca22a` | vertical stack | ❌ 回退 |
| `3ffd230` | reset positions before dagre | ✅ 最终采用 |
| `0ac744c` | remove premature node hiding | ✅ 已合并 |
| `cf18c20` | manual bbox + tighter dagre | ❌ 回退 |
| `3b5cf71` | debug bbox logging | ❌ 回退 |
| `50f5ed6` | global dagre TB | ❌ 回退 |
| `6b13ba1` | correct component detection + 2D grid | ❌ 回退 |
| `46cb719` | split by roots (失败) | ❌ 回退 |
| `d8b4f61` | split by roots after dedup | ❌ 回退 |

**当前代码**: `3ffd230`（重置位置 + 分量级 dagre LR + 纵向堆叠）

---

*记录日期：2026-07-07 02:00*

---

## 2026-07-09 新增/更新

### ✅ 已完成

#### 1. LA-030 修复：PDF文档提取概念
- **状态**: ✅ **已修复**
- **根因**: 旧版导入未使用 Parent-Child 双层分块，chunk type 为 `markdown`（非 `child`），导致 `extract_all_concepts` 跳过
- **修复**: 重写 `_process_pdf`，使用正确的 `type=child` + `type=parent`
- **结果**: 12 个 PDF 全部提取出概念

#### 2. LA-031 修复：PDF章节/页码信息
- **状态**: ✅ **已修复**
- **根因**: `page_numbers` 列表 ≠ `page_number` 单值；PDF 文本无 Markdown 标题结构
- **修复**: 新增 `_extract_page_headings()`；统一字段映射
- **结果**: 125/125 child chunks 有 `page_number`，115/125 有 `heading_path`

#### 3. LA-032 修复：详情面板来源引用
- **状态**: ✅ **已修复**
- **内容**: 概念节点详情面板显示人类可读的来源引用（文件名 | 章节路径 | 第 X 页）
- **关键提交**: `a559d86`, `d43f8f7`

#### 4. 文档视图删除
- **状态**: ✅ **已完成**
- **原因**: 文档视图卡死（循环引用导致的无限递归），且概念视图已满足需求
- **操作**: 删除工具栏中文档视图按钮、批量提取按钮、去重按钮
- **关键提交**: `a90663b`

### 🔴 遗留问题

#### LA-033: 部分概念节点未显示描述（cardLabel为空）
- **状态**: 🔴 **高优先级** ⬅️ **明日优先**
- **描述**: 概念视图中部分节点卡片只显示节点类型标签，不显示概念名称和描述
- **根因待排查**:
  1. 后端提取时 `name`/`description` 字段为空？
  2. 前端 `buildUMLCardLabel()` 函数处理异常？
  3. 特定类型（definition/law/application/extension）的处理逻辑缺失？
- **排查方向**:
  - 检查 API `/concepts` 返回数据中问题节点的 `name` 和 `description`
  - 检查 `buildUMLCardLabel()` 对各种类型的处理
  - 对比正常节点和异常节点的数据差异

#### LA-034: 贝塞尔曲线连接点系统（原LA-020）
- **状态**: 🟡 **待实现**
- **描述**: Cytoscape.js 边端点不精确，无法像 Visio 一样固定在节点边缘特定位置
- **技术方案**: 已设计（docs/design-edge-endpoints.md），使用 `source-endpoint: '100% 50%'` 等字符串格式
- **阻塞**: 需先解决 LA-033

#### LA-035: 图片chunk提取与嵌入
- **状态**: 🟡 **设计阶段**
- **描述**: 将 PDF 中的图片提取为独立 chunk，在概念图谱中显示缩略图
- **技术方案**: 已设计（docs/design-image-chunk.md）
- **前置条件**: 需先解决 LA-033 和 LA-034

### 📋 明日计划

1. **上午**: 排查并修复 LA-033（节点描述显示问题）
2. **下午**: 实现 LA-034（贝塞尔曲线连接点）
3. **后续**: 启动 LA-035（图片chunk）Phase 1 后端实现
