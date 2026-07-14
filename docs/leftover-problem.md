# 遗留问题追踪 (Leftover Problem Tracker)

## 2026-07-11 终版更新

---

### ✅ 已完成（今日）

#### LA-035 Phase 2.2+：MarkdownChunker v2.0 重写
- **状态**: ✅ **已完成**
- **内容**: 按自然段分块 + 树形标题结构（支持 `#`~`######` 任意层级）
- **修改文件**: `core/markdown_chunker.py`, `core/mineru_client.py`, `core/image_concept_extractor.py`
- **设计文档**: `docs/design-markdown-chunk-semantic-aggregation.md` v2.0

#### LA-035-P4：media_refs 传递链修复
- **状态**: ✅ **已完成**
- **内容**: ExtractedConcept + CanonicalConcept 两端接口匹配，确保传递链完整
- **测试**: `tests/test_media_refs_chain.py` 通过

#### LA-035 Phase 2.3：语义聚合
- **状态**: ✅ **已完成**
- **内容**: HeadingChunk 聚合 ParagraphChunk 概念 → 主题概念 + HAS_DETAIL 层级关系
- **实现文件**: `core/semantic_aggregator.py`

#### LA-035 Phase 3：图片概念与文本概念融合
- **状态**: ✅ **已完成**
- **内容**: 图片概念（image_pseudo chunks）+ 文本概念 → 去重合并 → 统一 CanonicalConcept
- **关键验证**: 图片 VLM 描述 → image_pseudo chunk → 概念提取 → 去重合并 → media_refs 保留

#### LA-035-P5：Pydantic 类型定义
- **状态**: ✅ **已完成**
- **内容**: `core/types.py` 定义所有核心类型的 Pydantic 模型，兼容旧 dict 访问方式
- **测试**: `tests/test_pydantic_types.py` 通过

#### LA-035-P6：SemanticLinker P1 优化
- **状态**: ✅ **已完成**
- **内容**: 排除已有 HAS_DETAIL 关系的概念对，减少冗余 LLM 调用

#### LA-035-P7：前端多媒体展示
- **状态**: ✅ **已完成**
- **内容**: NodeDetailPanel.vue 详情面板展示图片/公式/表格
- **修改文件**: `web-vue/src/components/graph/NodeDetailPanel.vue`, `GraphView.vue`

#### LA-035-P8：PDF 默认引擎改为 MinerU
- **状态**: ✅ **已完成**
- **内容**: `core/document_processor.py` 默认 `pdf_engine="mineru"`
- **效果**: 前端导入 PDF 自动使用 MinerU，支持图片 VLM 描述

#### LA-035-P9：Embedding API 错误处理增强
- **状态**: ✅ **已完成**
- **内容**: `core/embedding.py` 打印详细业务错误码，批量失败时自动降级到 HashEmbedding

---

### 🔴 遗留问题

#### LA-035-P10：图片缩略图显示
- **状态**: 🔴 **新增（明日优先）**
- **问题描述**: 基于图片提取的概念节点在 Cytoscape.js 图谱中与普通文本节点外观完全一致，没有缩略图标识。用户无法直观区分哪些是图片概念节点。
- **期望效果**: 图片概念节点上显示图片缩略图作为节点背景或图标
- **技术难点**: Cytoscape.js 对节点背景图片的支持方式
- **修改范围**: `web-vue/src/components/graph/GraphView.vue`
- **优先级**: P0

#### LA-035-P11：多媒体chunk融合可视化
- **状态**: 🔴 **新增（明日优先）**
- **问题描述**: 公式图片与讨论该公式的文本chunk是否实现了语义融合，在前端完全看不出来。用户无法判断融合是否成功。
- **期望效果**: 
  - 融合后的概念节点有明确的"融合来源"标识（如"来自 2 个文本chunk + 1 个图片chunk"）
  - 融合边（图片概念 → 文本概念）有特殊样式
  - 点击融合节点可查看所有来源chunk的列表
- **修改范围**: `web-vue/src/components/graph/` + 后端 API
- **优先级**: P0

#### LA-035-P12：上层chunk融合方案
- **状态**: 🟡 **新增（待讨论）**
- **问题描述**: MarkdownChunker v2.0 生成的多层chunk结构（Document → Heading L1 → Heading L2 → Paragraph）导致大量上层chunk出现。这些上层chunk（HeadingChunk）的内容是"标题 + 直接段落"，在概念提取时会产生与底层chunk重复或冲突的概念。
- **需要讨论的问题**:
  1. HeadingChunk 是否也需要提取概念？还是只作为聚合容器？
  2. HeadingChunk 提取的概念与 ParagraphChunk 提取的概念如何处理重复？
  3. 上层chunk的概念是否应该比下层chunk更"抽象"？
  4. SemanticAggregator 的 HAS_DETAIL 关系是否已经足够？
- **优先级**: P1

#### LA-035-P13：批量测试更多 PDF
- **状态**: 🔄 **待测试**
- **内容**: 3-5 个不同特征 PDF（表格密集/公式密集/纯文字/扫描件）验证整体流程
- **优先级**: P2

#### LA-035-P14：两阶段提取优化
- **状态**: 🔄 **待实现**
- **内容**: SemanticExtractor 支持 nodes-first → edges-with-context 模式
- **优先级**: P2

#### LA-035-P15：YAML 模板配置
- **状态**: 🟡 **低优先级**
- **内容**: 将范式配置从代码硬编码改为 YAML 模板文件
- **优先级**: P3

#### LA-035-P16：Token 过期检测
- **状态**: 🟡 **低优先级**
- **内容**: MinerU Token 有效期管理，自动刷新提示
- **优先级**: P3

#### LA-035-P17：公式/表格提取增强
- **状态**: 🟡 **低优先级**
- **内容**: MinerU 已提取 LaTeX/Markdown 表格，可进一步用于概念提取
- **优先级**: P3

---

## 2026-07-12 终版更新

### ✅ 已完成（今日）

#### LA-035-P10：图片概念节点标识（tag 显示）
- **状态**: ✅ **已完成**
- **内容**: 图片概念节点在 Cytoscape.js 中显示底部 ASCII 边框标签行（如 `┌────────┐│ 图片×2 │└────────┘`），节点边框根据媒体类型变色（图片→橙色）
- **修改文件**: `GraphLayout.js`, `GraphStyles.js`, `GraphView.vue`, `backend_api.py`
- **关键技术**: 节点大小自适应（根据内容长度计算 nodeWidth 和 cardHeight），取消截断

#### LA-035-P11：悬浮预览卡片
- **状态**: ✅ **已完成**
- **内容**: 新增 `GraphNodeTooltip.vue` 组件，鼠标悬停概念节点时显示：名称、类型徽章、描述、来源片段、关联媒体缩略图
- **修改文件**: `GraphNodeTooltip.vue`（新增）
- **技术**: Teleport 到 body，CSS 过渡动画，图片 URL 通过后端 `/api/media/` 静态服务获取

#### LA-035-P11：小批量概念提取（按 heading 分组）
- **状态**: ✅ **已完成**
- **内容**: `extract_concepts_batch_v2` 按 `heading_path` 分组，同一 heading 内 chunk 合并为一次 LLM 调用
- **效果**: Token 节省约 57%，构建速度提升 3-5x
- **修改文件**: `semantic_extractor.py`, `graph_builder.py`

#### LA-035：系统提示词隔离声明
- **状态**: ✅ **已完成**
- **内容**: 基础提示词添加 ⚠️ 隔离声明，明确告知 LLM 只从【知识片段】区域提取概念，禁止从指令中提取
- **效果**: 解决数据污染问题（虚假概念节点如"MinerU测试"、"知识片段分析"等）
- **修改文件**: `semantic_extractor.py`

#### LA-035：后端图片静态文件服务
- **状态**: ✅ **已完成**
- **内容**: 新增 `/api/media/{path:path}` 路由，提供知识库图片静态文件访问，支持 Windows 路径
- **修改文件**: `backend_api.py`

#### LA-035：Chunk schema 自动升级
- **状态**: ✅ **已完成**
- **内容**: `graph_store.py` 自动检测旧 schema（缺少 `media_refs` 字段），通过 `ALTER TABLE` 升级
- **修改文件**: `graph_store.py`

#### LA-035：MinerU chunk_type 修复
- **状态**: ✅ **已完成**
- **内容**: `mineru_client.py` 修复 `chunk_type` 判断逻辑，纯图片行（`![alt](path)`）正确标记为 `image` 类型
- **修改文件**: `mineru_client.py`

#### LA-035：图片 chunk VLM 描述生成
- **状态**: ✅ **已完成**
- **内容**: `graph_builder.py` 中对图片 chunk 调用 VLM 生成描述，使 LLM 可提取概念
- **修改文件**: `graph_builder.py`

#### LA-035：图片 chunk 回退兼容
- **状态**: ✅ **已完成**
- **内容**: `_get_media_refs_from_chunks` 兼容旧 schema（Chunk 无 `media_refs` 字段时回退到 `image_path`/`thumbnail_path`）
- **修改文件**: `graph_store.py`

#### LA-035：多媒体引用归一化
- **状态**: ✅ **已完成**
- **内容**: `_normalize_media_refs` 统一从 `media_refs`/`image_refs`/`image_path` 提取图片引用
- **修改文件**: `graph_builder.py`

---

### 🔴 遗留问题

#### LA-035-P18：部分节点有图片 tag 但悬浮窗/详情面板无图片
- **状态**: 🔴 **新增（明日优先）**
- **问题描述**: 部分概念节点被标记了图片 tag（底部标签行显示"图片×N"），但点击节点后：
  - 悬浮窗中"关联媒体"区域为空
  - 详情面板中"引用媒体"为空
- **根因分析**: 
  - 可能性1：前端 `selectedNode` 构造时未传递 `media_refs`（已修复但未验证）
  - 可能性2：`_get_media_refs_from_chunks` 回退查询时未返回数据
  - 可能性3：部分图片 chunk 的 text 为空，导致提取时无法生成概念，但去重时保留的 `media_refs` 在另一个路径上
- **验证方法**: 重建图谱时检查后端打印
- **优先级**: P0

#### LA-035-P19：非概念 chunk 节点重叠（左上角）
- **状态**: 🔴 **新增（明日优先）**
- **问题描述**: `document`/`heading`/`paragraph` 类型的 chunk 节点在概念视图中全部重叠在左上角 (0,0)，形成一团无法区分的节点
- **根因分析**: `runConceptLayout` 只处理 `parent`/`child` 类型的 chunk 节点和 `concept` 类型节点，但 `document`/`heading`/`paragraph` 类型的节点既不被隐藏，也不被布局
- **临时方案**: 已尝试添加 grid 布局但无效（节点未在 `runConceptLayout` 时存在，或 `runTreeLayout` 时加载了错误类型）
- **优先级**: P0

#### LA-035-P10：图片节点在 Cytoscape 中显示缩略图背景
- **状态**: 🟡 **降级为低优先级**
- **说明**: 当前方案（底部标签行 + 边框颜色）已能区分图片概念节点。缩略图背景受 Cytoscape 技术限制，暂不使用 `cytoscape-node-html-label` 扩展
- **优先级**: P3

#### LA-035-P12：上层chunk融合方案
- **状态**: 🟡 **未讨论**
- **说明**: 今日未讨论，推迟到后续
- **优先级**: P2

#### LA-035-P13：批量测试更多 PDF
- **状态**: 🔄 **待测试**
- **优先级**: P2

#### LA-035-P14：两阶段提取优化
- **状态**: 🔄 **待实现**
- **优先级**: P2

#### LA-035-P15：YAML 模板配置
- **状态**: 🟡 **低优先级**
- **优先级**: P3

#### LA-035-P16：Token 过期检测
- **状态**: 🟡 **低优先级**
- **优先级**: P3

#### LA-035-P17：公式/表格提取增强
- **状态**: 🟡 **低优先级**
- **优先级**: P3

---

### 明日计划（2026-07-13）

| 优先级 | 任务 | 内容 |
|:---|:---|:---|
| P0 | LA-035-P18 | 修复部分节点有图片 tag 但详情面板无图片的问题 |
| P0 | LA-035-P19 | 修复非概念 chunk 节点重叠问题（document/heading/paragraph） |
| P2 | LA-035-P12 | 讨论上层 chunk 融合方案 |

---

*记录日期：2026-07-12 23:59*

---

## 2026-07-13 更新

### ✅ 已完成（今日）

#### LA-035-P18：media_refs 显示不一致
- **状态**: ✅ **已完成**
- **问题**: 部分节点有图片 tag 但悬浮窗/详情面板无图片（数据链断裂）
- **根因**: 
  1. `add_chunk_nodes` 遗漏 `media_refs` 字段写入 Chunk 节点
  2. `_get_media_refs_from_chunks` 回退逻辑条件过严（字段存在但值为空时不会回退到 image_path）
- **修复**:
  1. `graph_store.py` `add_chunk_nodes`: 从 metadata 提取并序列化 `media_refs` 写入 Chunk
  2. `graph_store.py` `_get_media_refs_from_chunks`: 放宽条件为 `if not media_refs`（不需要检查字段是否存在）
- **修改文件**: `core/graph_store.py`
- **提交**: ef9633c

#### LA-035-P19：非概念 chunk 节点在概念视图中重叠
- **状态**: ✅ **已完成**
- **问题**: document/heading/paragraph 类型节点在概念视图中全部堆叠在 (0,0)
- **根因**: 前端 `GraphView.vue` 同时加载了 Chunk 节点和 CanonicalConcept 节点，通过 CSS 隐藏制造"概念视图"假象
- **修复**: 
  - 前端双视图严格分离：
    - 知识图谱视图：只加载 CanonicalConcept + 语义边
    - 文档树视图：只加载 Chunk + 结构边
  - 新增工具栏切换按钮：📄 文档树 / 🧩 知识图谱
- **修改文件**: `web-vue/src/components/graph/GraphView.vue`
- **提交**: ef9633c

#### LA-035-P12：上层 chunk 融合方案（Heading 作为上下文注入）
- **状态**: ✅ **已完成**
- **诊断**: RAG 学科同 heading_path 概念重叠率 84.2%（HeadingChunk vs ParagraphChunk）
- **方案**: HeadingChunk 不直接提取概念，作为 ParagraphChunk 的语义上下文注入
- **实现**:
  - `semantic_extractor.py`: `extract_concepts_batch_v2` 新增 `heading_context` 参数
  - `graph_builder.py`: 按 heading 分组 → 提取 heading 文本作为上下文声明 → 只提取非 heading chunk
- **效果**:
  - Heading 概念重叠率从 84.7% 降至 **0%**
  - Paragraph 提取在 heading 上下文指导下更精准
- **修改文件**: `core/semantic_extractor.py`, `core/graph_builder.py`
- **提交**: 87ccce6

#### LA-035：GraphStore 缓存一致性修复
- **状态**: ✅ **已完成**
- **问题**: `init_schema(force=True)` 时无法删除旧数据库（Windows 目录名损坏 + 缓存 key 不匹配）
- **修复**: `graph_store.py` 使用统一的 `db_path_str` 缓存 key（字符串类型），避免 `Path` 对象与 `str` 混用
- **修改文件**: `core/graph_store.py`
- **提交**: f2b7cf9

### 🔴 遗留问题更新

#### LA-035-P17：公式/表格提取增强（更新）
- **状态**: 🔴 **待测试**
- **问题描述**: 当前前端仅对图片 chunk 进行了多媒体适配（悬浮预览、详情面板）。公式和表格 chunk 在 MinerU 提取时会生成对应的公式/表格标记，但尚未接入 VLM 描述或前端展示。
- **待测试场景**: 表格密集型文档（如财务报表）、公式密集型文档（如数学/物理教材）
- **期望效果**:
  - 公式 chunk：VLM 生成公式文本描述（LaTeX 或自然语言）→ 可提取概念
  - 表格 chunk：VLM 生成表格结构描述 → 可提取概念
  - 前端：公式/表格节点显示专用标识，悬浮预览显示公式/表格内容
- **修改范围**: `core/document_processor.py`（公式/表格 chunk 类型标记）+ `core/vlm_client.py`（公式/表格描述任务）+ `web-vue/src/components/graph/`（前端展示）
- **优先级**: P2
- **备注**: 需要开发者提供表格/公式较多的测试文档

### 明日计划（后续）

| 优先级 | 任务 | 内容 |
|:---|:---|:---|
| P2 | LA-035-P14 | 两阶段提取优化：nodes-first → edges-with-context 模式 |
| P2 | LA-035-P17 | 公式/表格提取增强（等待测试文档） |
| P2 | LA-035-P13 | 批量测试更多 PDF（不同特征文档） |
| P3 | LA-035-P15 | YAML 模板配置 |
| P3 | LA-035-P16 | Token 过期检测 |

---

*记录日期：2026-07-13*

---

## 2026-07-15 更新

### ✅ 已完成（今日）

#### LA-035-P19-1/P19-2: 概念视图 dagre 环检测 + 文档树布局（彻底解决）
- **状态**: ✅ **已完成**
- **问题**: 概念视图中节点（含自环节点）重叠在左上角；文档树视图节点重叠
- **根因链**:
  1. **自环节点**: `transformer` 学科数据库中 3 个节点有自环（Q-K-V权重矩阵 → 自己、归一化方式 → 自己、SoftMax → 自己）
  2. **dagre 失败**: dagre 布局算法无法处理自环，导致包含自环的树布局后节点仍堆积在 (0,0)
  3. **stuckNodes 误判**: 安全检测阈值过宽，将正常网格布局的节点误判为"在原点"，重新定位到页面底部
  4. **Vite 缓存**: 构建产物 hash 未变化，浏览器加载旧代码
  5. **文档树过滤**: `runTreeLayout` 只处理 `type: "child"` 的节点，但 Chunk 类型是 `paragraph` / `heading` / `document`
- **修复**:
  1. **清除 Vite 缓存**: `Remove-Item -Recurse -Force node_modules/.vite`
  2. **放宽 allConceptNodes 过滤**: 包含 type 为 undefined 的节点，只排除明确的 chunk / 图片类型
  3. **过滤自环边不传给 dagre**: 先收集所有节点到 connectedNodeIds（包含自环节点），edgeList 再过滤自环边
  4. **visibleEdges 过滤自环**: 确保入度计算正确，自环节点成为根节点（单节点树）
  5. **dagre fallback**: 检测 dagre 失败后使用简单网格布局
  6. **stuckNodes 阈值收紧**: `|x|<2 && |y|<2`（原来 `<5`）
  7. **网格布局起始偏移**: `(50, 50)` 而非 `(0, 0)`，避免被 stuckNodes 误判
  8. **文档树支持所有 chunk 类型**: `paragraph` / `heading` / `document` / `child` / `markdown` / `image`
  9. **文档树孤立节点处理**: 从根不可达的 chunk 节点视为单节点树，排在最下方
  10. **概念图谱二维网格排列**: 树按节点数降序，每行按容器宽度排列，避免纵向堆叠
- **修改文件**: `web-vue/src/components/graph/GraphLayout.js`
- **验证数据**: transformer 学科（139 CanonicalConcept, 29 SOLUTION, 67 DEPENDS_ON, 3 自环）
- **提交**: `d08dc7e` → `1e1a22f` → `7e4a000` → `bfd760c` → `d772308` → `459540b` → `da57f3e` → `6451bd9`

### 🔴 遗留问题更新

无新增遗留问题。P19 已完全解决。

---

*记录日期：2026-07-15*

---

## 2026-07-14 凌晨更新

### ✅ 已完成（今日）

#### P18 修复确认：media_refs 数据链路完全打通
- **状态**: ✅ **已修复并验证**
- **用户验证**: "现在所有的节点都能正确显示图片了，也不存在只有tag没有图片的节点了"
- **修复内容**:
  1. `graph_store.py` `add_chunk_nodes`: 写入 `media_refs` 到 Chunk 节点
  2. `graph_store.py` `_get_media_refs_from_chunks`: 放宽回退条件
  3. `graph_store.py`: 当 `media_refs` 为空但 `image_path` 存在时，自动从 `image_path` 构建 `media_refs`
  4. `backend_api.py`: `/concepts` 和 `/nodes` 绕过 `_in_memory_graphs` 缓存，直接查询数据库
- **修改文件**: `core/graph_store.py`, `app/backend_api.py`

#### API 缓存隔离修复
- **状态**: ✅ **已修复**
- **问题**: `_in_memory_graphs` 缓存混合了 Chunk 和 Concept 节点，导致 `/concepts` 返回所有节点类型
- **修复**: `/concepts` 直接调用 `get_canonical_concepts()`，`/nodes` 直接调用 `get_all_nodes()`
- **修改文件**: `app/backend_api.py`

### 🔴 遗留问题更新

#### LA-035-P19-1: 概念视图 dagre 环检测
- **状态**: ✅ **已解决**（见 2026-07-15 更新）
- ~~问题: dagre 布局不支持有向环...~~

#### LA-035-P19-2: 文档树视图布局
- **状态**: ✅ **已解决**（见 2026-07-15 更新）
- ~~问题: 文档树中所有节点重叠在一起...~~

#### LA-035-P20: 前端范式管理 UI（新增）
- **状态**: 🟡 **已记录**
- **问题**: 前端尚未连接 YAML 配置，不支持新建/编辑范式
- **优先级**: P3

### 明日计划（2026-07-14）

| 优先级 | 任务 | 内容 |
|:---|:---|:---|
| **P1** | P19-1 | 确认 dagre 环检测修复生效（前端构建 + 浏览器缓存清除） |
| **P1** | P19-2 | 确认文档树布局修复生效（前端构建 + 检查 BELONGS_TO 边加载） |
| **P2** | P14 | 两阶段提取重新设计（基于 heading 上下文的连接建立） |
| **P2** | P17 | 公式/表格提取增强技术方案（等待测试文档） |
| **P3** | P20 | 前端范式管理 UI（可选） |

---

*记录日期：2026-07-14 凌晨*

---

## 2026-07-11 终版更新

[旧内容保留...]
