

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
