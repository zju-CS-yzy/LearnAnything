# LearnAnything Phase 2 进展与遗留问题

> 记录时间: 2026-07-01 01:30
> 会话: 2026-06-30 树状图（LearnAnything 项目经理）

---

## 一、已完成的工作

### 1. 语义提取器（`core/semantic_extractor.py`）
- 单 chunk 概念提取，支持多范式
- 新增模糊概念过滤（"完整聚合""微调嵌入"等没头没尾的概念自动丢弃）
- 支持 3 种内置范式：理论归纳 / 工程分解 / 层级归纳
- 兼容 LLM 返回数组 `[{...}]` 和对象 `{"concepts": [...]}` 两种格式

### 2. 概念去重器（`core/concept_deduper.py`）
- 基于智谱 embedding-3 的贪婪合并算法（阈值 0.85）
- 输出 canonical 概念表（含别名、来源 chunks、主导类型）
- 自动导出 CSV 到 `knowledge_base/{subject}_concepts.csv`

### 3. 语义质量评估器（`core/semantic_quality_evaluator.py`）
- 五维度评估：稳定性(25%) + 覆盖度(20%) + 忠实度(20%) + 多样性(15%) + 连接覆盖率(20%)
- 连接覆盖率（Chunk Stickiness）参考 ACL 论文设计：
  - 相邻 chunk 概念 Jaccard 相似度 > 0.3 视为逻辑连接
  - 覆盖率 = 度数 >= 2 的 chunk 数 / 总 chunk 数
- 稳定性评估：同一 chunk 提取 3 次，取与其他结果重叠度最高的作为最佳结果

### 4. GraphBuilder 扩展（`core/graph_builder.py`）
- `extract_all_concepts()`：批量对所有 chunk 提取概念，记录质量分数
- `dedupe_concepts()`：调用去重器并导出表格

### 5. 后端 API（`app/backend_api.py`）
- `POST /api/knowledge-graph/{subject}/extract/{chunk_id}`：单 chunk 提取（支持 paradigm 参数）
- `POST /api/knowledge-graph/{subject}/build/semantic`：批量提取（支持 paradigm 参数）
- `POST /api/knowledge-graph/{subject}/dedupe`：全局去重
- `GET /api/knowledge-graph/paradigms`：获取可用范式列表
- `GET /api/knowledge-graph/{subject}/concepts`：获取概念节点
- `GET /api/knowledge-graph/{subject}/chunk/{chunk_id}/concepts`：获取 chunk 已提取概念

### 6. 前端 GraphView（`web-vue/src/components/GraphView.vue`）
- 右侧信息面板新增「🧩 概念分解」区域
- 自动加载已提取概念 + 「🔬 提取概念」按钮
- 新增「🧠 批量提取」和「🔗 去重」按钮
- 全局概念表格（分页、搜索、弹窗详情）

---

## 二、遗留问题（Outstanding Issues）

### ❌ 问题 1：前端表格增强不完整
**状态**: 代码已写，待测试验证

具体遗留项：
- 分页逻辑已添加（10/20/50/100 条每页），但页码切换和每页大小切换的前端交互需要验证
- 搜索过滤逻辑已添加，但搜索框渲染和实时过滤需要验证
- 概念详情弹窗已添加，但点击行触发弹窗的行为需要验证
- 表格样式（`concept-table-wrapper`）需要确认与现有布局不冲突

**待验证**：
1. 构建后刷新前端，去重后表格是否正确显示
2. 分页按钮是否正常工作
3. 搜索框是否能过滤概念
4. 点击概念行是否弹出详情

---

### ✅ 问题 2：多分解范式没有前端接口（已修复 2026-07-02）
**状态**: ✅ 已修复

修复内容：
1. 在工具栏「🧠 批量提取」按钮左侧添加了范式选择下拉框（理论归纳 / 工程分解 / 层级归纳）
2. `batchExtract()` 现在正确携带 `paradigm` 参数 POST 到 `/build/semantic`
3. `extractConcepts()` 现在正确携带 `paradigm` 参数 POST 到 `/extract/{chunk_id}`
4. 添加了 `.paradigm-select` 样式

用户现在可以在工具栏直接选择范式，批量提取和单 chunk 提取都会使用选中的范式。

---

### ❌ 问题 3：概念质量仍需优化
**状态**: 已改进，但效果未充分验证

已做的改进：
- 模糊概念过滤（丢弃"完整聚合"等没头没尾的概念）
- 多范式支持（工程分解更适合技术文本）
- Prompt 明确要求"概念名称必须能在原文中找到直接对应"

仍待验证和优化：
- 模糊概念过滤规则是否足够全面（目前只过滤长度<=4且以特定词结尾/开头的概念）
- 工程分解范式对技术类文本的实际效果
- 层级归纳范式对通用知识的效果
- 概念类型的准确性（如"多GPU并行训练流程"被标为"规律"是否合理）

**建议后续优化方向**：
1. 收集更多错误案例，扩展模糊概念过滤规则
2. 对提取结果进行人工抽样检查，计算准确率
3. 考虑引入概念名称的命名规范（如禁止纯动词短语、要求包含名词等）

---

### ❌ 问题 4：连接覆盖率未接入质量评估流程
**状态**: 算法已实现，但未在批量提取时自动计算

`evaluate_linkage()` 方法需要完整的 chunk 列表作为输入，当前在 `extract_all_concepts()` 中只评估了前 10 个 chunk 的单 chunk 质量，没有计算全局连接覆盖率。

**建议**：
- 在批量提取完成后，调用 `evaluate_linkage()` 计算全局连接覆盖率
- 将连接覆盖率显示在批量提取的结果中

---

## 三、下一步行动计划（2026-07-02 更新）

### 已确认设计决策（2026-07-02）

**多根平行树：** 文档不强制作为虚拟根。每篇文档提取出的多个独立需求各自作为独立树根，其上层位置由知识库全局结构决定（可能连接到其他文档的子需求或技术）。

**连接构建流程：** 先提取 → 后全局语义推断 → 再显式标记。提取时不做跨文档推断，避免缺少全局信息导致的错误。批量构建完成后统一做一次全局推断，生成持久化标记，降低后续操作成本。

**连接判定算法：** embedding 相似度初筛 + LLM 二次确认。

**底层存储：** DAG（有向无环图），允许多父节点。可视化层再做树形渲染策略。

### 优先级 P0（必须完成）
1. **全局语义推断模块** (`semantic_linker.py`)：实现跨文档/跨 chunk 概念连接算法
2. **提取 Prompt 增强**：增加 `parent_hint` 字段（文本中明确提及的父级关联）
3. **GraphStore 语义边存储**：增加 `SEMANTIC_PARENT` 边类型
4. **批量构建流程更新**：extract → dedupe → **link** → write

### 优先级 P1（重要）
5. **连接覆盖率接入**：在批量提取完成后自动计算并显示
6. **概念质量抽样检查**：随机抽取 10-20 个概念，人工判断准确性
7. **模糊概念规则扩展**：根据抽样结果扩展过滤规则

### 优先级 P2（后续）
8. **自定义范式**：设计前端配置界面，允许用户自定义分解范式
9. **概念关系可视化**：在知识图谱中展示 Concept 节点和语义关系边
10. **社区发现**：基于概念关系运行 Louvain 算法，按社区着色

---

### ❌ 问题 5：LLM 调用成本过高（全局语义推断）
**状态**: 已实现，待优化

当前实现：
- 全局语义推断对每个候选对都调用 LLM 二次确认
- 候选对数量 = (上层概念数 × 下层概念数) × 层级数
- 100 个概念可能产生 2000+ 次 LLM 调用，成本较高

待优化方向：
1. 降低 embedding 相似度阈值，减少候选对数量
2. 用规则匹配（如子概念描述中包含父概念名称）作为初筛
3. 批量 LLM 调用（一次请求判断多对概念）
4. 缓存 LLM 判断结果，避免重复判断

---

## 四、技术债务

- `graph_store.py` 的 `add_concepts` 使用 `MERGE` 创建概念节点，但 KùzuDB 的 `MERGE` 行为可能与预期不同（需要去重后更新 ID 的场景需要删除重建）
- `semantic_extractor.py` 的 `_is_vague_concept` 规则是硬编码的，不够灵活
- 批量提取是串行的，142 个 chunk 可能需要 5-10 分钟，后续考虑并发优化
- 去重器对 embedding 做了本地缓存，但重启后会丢失，可考虑持久化

---

## 五、当前会话进展（2026-07-02 下午）

### 已完成修复
1. **P0: 同一 chunk 内概念重复** ✅ — `add_concepts` 增加 `seen_names` 去重
2. **P0: KùzuDB 锁冲突** ✅ — `ConceptDeduper` 复用 `GraphStore` 实例
3. **P1: parent_hint 为空** ✅ — `validated.append` 添加 `"parent_hint"` 字段
4. **P1: EmbeddingManager.encode 缺失** ✅ — 统一改为 `.embed()`
5. **P1: CSV numpy array 序列化** ✅ — 导出前 `.tolist()` 转换
6. **P1: SemanticLinker 概念加载** ✅ — 直接从 CSV 加载 canonical 概念
7. **P1: SemanticLinker 节点创建** ✅ — `MERGE` canonical 节点后再创建关系

### 最终构建结果
```
提取 (98 chunks, 499 概念) → 去重 (394 canonical) → 连接 (43 条语义边)
```

- **parent_hint 命中率**: 270/394 = 68.5% ✅
- **连接边**: 43 条（42 条 parent_hint 精确匹配 + 1 条 embedding+LLM）
- **平均质量分**: 0.648 ✅

### 仍存在的问题
- **连接覆盖率偏低**: 43/394 = 10.9%（孤立概念较多）
- **智谱 API 限流**: 降级为 HashEmbedding，影响相似度计算质量
- **前端未验证**: 概念节点和语义连接的可视化效果待确认

### 下一步建议
1. 启动前端验证可视化效果
2. 优化连接覆盖率（降低阈值/增加跨层级规则）
3. 处理 API 限流（降低并发/增加重试间隔）

---

## 六、参考文档

### 已完成
1. **API 配置**: 从 API.txt 读取并配置了 DeepSeek + 智谱 GLM API key
2. **Schema 修复**: 添加了工程分解范式的 Chunk→Concept 关系表（REQUIRES/IMPLEMENTS/HAS_SUB/HAS_IMPL）
3. **数据库重建**: generic_v1 重建成功（113 chunks）
4. **语义提取**: 98 个 chunk 全部提取完成，生成 545 个概念
   - technology: 136 | sub_technology: 257 | requirement: 88 | sub_requirement: 64
5. **评估报告**: 生成 `docs/evaluation_report_2026-07-02.md`

### 发现的关键问题（需修复）
1. **P0: 同一 chunk 内概念重复** → 导致 KùzuDB 主键冲突，约 10-15% 概念丢失
2. **P0: 去重阶段 KùzuDB 锁冲突** → `extract` 和 `dedupe` 各自创建 GraphStore 实例
3. **P1: parent_hint 全部为空** → 无法建立阶段1精确匹配连接
4. **P1: EmbeddingManager.encode 方法缺失** → 质量评估失败

### 下一步（建议修复顺序）
1. 修复 `add_concepts` 同一 chunk 内去重
2. 修复 `dedupe_concepts` 复用 GraphStore 实例
3. 优化 parent_hint prompt
4. 重新运行完整构建（提取→去重→连接）
5. 验证连接覆盖率

---

## 六、参考文档

### 已完成
1. **全局语义连接模块** (`core/semantic_linker.py`)：
   - 三阶段连接算法：parent_hint 精确匹配 → embedding 相似度初筛 → LLM 二次确认
   - 工程分解范式连接规则：requirement -(SOLUTION)-> technology -(DEPENDS_ON)-> sub_requirement -(SOLUTION)-> sub_technology
   - DAG 存储（SOLUTION / DEPENDS_ON 关系表）

2. **前端可视化增强** (`web-vue/src/components/GraphView.vue`)：
   - 新增 Concept 节点渲染（需求节点菱形红色、技术节点圆角矩形蓝色、其他概念绿色）
   - 新增语义连接边渲染（SOLUTION 橙色实线、DEPENDS_ON 紫色虚线）
   - 新增 `loadConceptNodes()` 和 `loadSemanticEdges()` 函数
   - 图例更新，包含概念节点和语义边类型

3. **后端 API 扩展** (`app/backend_api.py`)：
   - `POST /build/semantic` 增加 `with_dedupe` / `with_link` 参数
   - 新增 `POST /build/link` 接口（独立执行语义连接）
   - 新增 `GET /concept-links` 接口（获取语义连接边）

4. **数据流增强**：
   - 提取器增加 `parent_hint` 字段
   - GraphStore 增加概念详情 JSONL 存储
   - 去重器导出 embedding / description / parent_hint

### 阻塞项
- **LLM 未配置**：当前环境 `DEEPSEEK_API_KEY` 未设置，无法执行语义提取和 LLM 二次确认
- **数据库已重建**：generic_v1 已重建（113 chunks），但无概念节点

### 下一步（待用户配置 API key 后）
1. 在前端选择「工程分解」范式，点击「🧠 批量提取」
2. 等待提取完成后点击「🔗 去重」
3. 调用 `POST /build/link` 执行全局语义连接
4. 刷新图谱，查看 Concept 节点和语义连接边的可视化效果

- ACL 2025 "MoC: Mixtures of Text Chunking Learners" — Chunk Stickiness 概念
- OpenReview LLM-judge 框架 — 概念质量评估方法
- 质量评估权重设计：稳定性(25%) + 覆盖度(20%) + 忠实度(20%) + 多样性(15%) + 连接覆盖率(20%)

---

## 七、2026-07-03 新增遗留问题

### 🟡 问题 6：LA-020 贝塞尔曲线端点
**状态**: 🟡 待验证（2026-07-04）

**根本原因**: Cytoscape.js 的 `bezier`/`unbundled-bezier` 不支持精确连接点控制（如 Visio 的连接点系统）。端点仍由 Cytoscape 自动计算，无法固定在"右边界中点→左边界中点"。

**当前状态**: COSE 布局下 bezier 曲线效果正常，无明显端点问题。待用户在实际前端中验证。

**待优化方向**:
1. 尝试自定义 Cytoscape.js 渲染扩展（如 `edgehand` 或自定义 SVG 边）
2. 改用 `segments` 边类型手动控制分段路径
3. 考虑切换到 D3.js 以获得完全自由的连接点控制

---

### ✅ 问题 7：LA-021 纵向连线（多根树共享子节点）
**状态**: ✅ **已修复**（2026-07-04 最终版）

**根本原因**: 
1. `loadAllNodes()` 被改为只加载概念节点（230→1489 个），导致一次性显示过多节点
2. dagre 布局在 6 个 rank 上分布 230+ 节点，纵向需要 12000+ px
3. 之前的 `fit=true` 或固定 zoom 方案都无法在视口中清晰显示
4. **最终 bug**: 自定义布局算法中 `chunkEdges.forEach(e => e.style('display', 'none'))` 隐藏了所有原始边，但 `treeChildren` 只从副本边构建。当没有共享子节点（copyEdges=0）时，treeChildren 为空，所有节点被视为叶节点，全部重叠在 depth=0。

**最终修复方案**: 
1. **恢复 chunk 节点加载**：`loadAllNodes()` 恢复为先前版本，加载 chunk 节点 + BELONGS_TO/ADJACENT_TO 边
2. **修复 chunk 类型查询**：修改 `/nodes` 和 `/edges` API，包含 `markdown` 类型节点
3. **自定义树形布局算法**：
   - 自底向上计算子树高度（叶节点数）
   - 父节点 y = 子节点 y 范围的中点
   - 叶节点在最右侧，间隔相同
   - 共享子节点复制到各自的树中
4. **修复边显示 bug**：保留原始边显示，`treeChildren` 同时包含原始边 + 副本边
5. **恢复 dagre fit=true**：chunk 节点数量适中，fit 效果正常

**文件修改**:
- `app/backend_api.py`: `/nodes` 和 `/edges` 端点，`chunk_type <> 'parent'`
- `web-vue/src/components/GraphView.vue`: 自定义树形布局算法 + 修复边显示

---

### 🟡 问题 8：LA-024 构建脚本执行（原编号冲突，LA-022 已用于"题库-知识库关联可视化"）
**状态**: 🟡 待验证

**根本原因**: PowerShell 默认执行策略限制（Restricted/AllSigned），导致 `scripts/build.ps1` 无法直接执行。

**当前方案**: 使用 `powershell -ExecutionPolicy Bypass -File` 绕过限制

**待优化方向**:
1. 验证 `Bypass` 方案在开发者环境中的可行性
2. 考虑提供 `.cmd` 批处理包装器自动调用 PowerShell 并设置执行策略
3. 文档中明确标注执行策略要求

---

## 八、2026-07-05 进展与新增遗留问题

### 今日完成

1. **创建设计文档** (`docs/DESIGN.md`)：
   - 项目简要说明、目标效果、知识图谱构建思想
   - 数据模型（Chunk/Concept/边/学科元数据）
   - 技术栈与架构（前端/后端/Agent/数据层）
   - 各模块实现方式（7个核心模块）
   - 数据流（导入/提取/查询）
   - 前端架构（Vue3 + Cytoscape + 自定义布局算法）
   - **扩展性设计**（新学科/Agent/前端/后端）
   - **测试策略**（单元/集成/E2E/CI）
   - **数据迁移**（Schema/备份/恢复/导出）

2. **修复导入流程 bug**（核心修复）：
   - `app/backend_api.py`: `import_file` 和 `import_text` 现在同时写入 **向量数据库 + KùzuDB**
   - 之前只写入 ChromaDB，导致新学科 graph DB 为空（0 chunks）
   - `core/subject_manager.py`: `record_import` 同时更新 `document_count` + `raw_files_count`

3. **修复前端样式错误**：
   - `GraphView.vue`: `'height': 'label'` → `'height': 60`（Cytoscape 废弃语法导致崩溃）

4. **修复 chunk 类型查询**：
   - `/nodes` 和 `/edges` API：`chunk_type = 'child'` → `chunk_type <> 'parent'`
   - 数据库中 chunk 实际类型为 `markdown`（162 个），`child` 仅 1 个

5. **更新布局算法**（进行中）：
   - `runLayout()`: 自定义树形布局（自底向上计算子树高度、父节点居中、复制共享子节点）
   - `runConceptLayout()`: 概念节点布局（dagre LR + 共享子节点复制），保留为独立函数

### 新增/更新遗留问题

### 🔴 问题 9：LA-025 前端图谱不显示（新学科 ai_llm）
**状态**: 🔴 **未解决**

**根本原因**: 多因素叠加
1. **ai_llm graph DB 为空**：之前导入时未写入 KùzuDB（代码已修复，但 ai_llm 数据需重新导入）
2. **前端布局算法**：自定义树形布局对 ADJACENT_TO 链式结构（无共享子节点）处理可能仍有 bug
3. **通用学科（generic）有数据但布局效果差**：164 chunks + 159 ADJACENT_TO 边，自定义布局后节点可能仍重叠

**已修复**：
- ✅ 导入时自动写入 KùzuDB
- ✅ 前端样式崩溃（height: 'label'）
- ✅ chunk 类型查询包含 markdown
- ✅ treeChildren 同时包含原始边 + 副本边

**待验证**：
- 🔄 重新导入 ai_llm PDF 后验证 graph DB 数据
- 🔄 验证自定义布局算法在 ADJACENT_TO 链式结构上的效果
- 🔄 验证节点间距、层次结构是否符合设计

**下一步**：
1. 删除 ai_llm 旧数据，重新导入 3 个 PDF
2. 验证 `/api/knowledge-graph/ai_llm/nodes` 返回 chunk 节点
3. 验证 `/api/knowledge-graph/ai_llm/edges` 返回 ADJACENT_TO 边
4. 浏览器打开前端，检查图谱渲染效果
5. 如仍有问题，检查浏览器控制台报错 + network 请求/响应

### 🟡 问题 10：LA-026 前端布局与 7月2日效果差距
**状态**: 🟡 **进行中**

**背景**: 用户期望恢复到 7月2日的图谱效果（节点: 302 | 边: 253，文档层树形结构清晰）

**当前状态 vs 目标**：
| 维度 | 7月2日效果 | 当前效果 |
|:---|:---|:---|
| 节点 | 302（Chunk + Concept 混合）| 待验证 |
| 边 | 253（ADJACENT_TO + BELONGS_TO）| 待验证 |
| 布局 | 自定义树形布局（根左、叶右、父居中）| 自定义树形布局（新实现）|
| 显示 | 节点清晰、不重叠 | 可能仍有重叠 |

**关键差异**：
- 7月2日的代码经过多轮调试，布局参数（layerWidth/nodeGap/treeGap）已调优
- 当前代码经过大量修改（dagre 尝试 → COSE 尝试 → 自定义布局），可能参数未完全对齐

**下一步**：
1. 优先解决 LA-025（确保有数据可显示）
2. 对比 7月2日 `GraphView.vue` 的 `runLayout()` 实现（如 git 历史可用）
3. 调整布局参数：layerWidth（250px）、nodeGap（60px）、treeGap（120px）
4. 验证 zoom 计算逻辑（当前按宽度 fit，可能需要调整）

### 🟢 问题 11：LA-027 设计文档维护
**状态**: 🟢 **已完成**

**文档**: `docs/DESIGN.md` 已创建，含 13 章节

**待补充**（按需）：
- 安全设计（API 认证、数据隔离）
- 性能指标（吞吐量、延迟、容量上限）
- 前端组件详细规范

---

*记录日期：2026-07-05 00:42*
