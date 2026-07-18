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

#### LA-035-P21: 公式未作为独立多媒体 chunk 提取（线性代数课件测试）
- **状态**: 🔴 **新增（明日优先）**
- **测试素材**: 线性代数课件（已存入线性代数学科 knowledge_base 原始材料）
- **问题描述**:
  1. 公式完全没有被作为独立的多媒体 chunk 提取（`chunk_type` 应为 `formula` 但实际未被标记）
  2. 使用 [理论归纳] 范式处理后，生成的树形图结构不正确
- **排查方向**:
  - MinerU 是否提取了 LaTeX 公式并生成 `formula` 类型 chunk？
  - `document_processor.py` / `markdown_chunker.py` 是否支持 `formula` chunk_type？
  - 理论归纳范式的提示词是否被正确加载（YAML 配置生效？）
  - 对比 [理论归纳] 和 [工程分解] 范式在同一份文档上的表现差异
- **验证点**:
  - 公式 chunk 是否有 `chunk_type = "formula"`？
  - 公式 chunk 的 `text` 是否包含 LaTeX 代码？
  - 构建图谱时，公式节点是否出现在概念视图中？
- **优先级**: P1

#### LA-035-P22: YAML 范式配置在 [理论归纳] 范式下未生效
- **状态**: 🔴 **新增（明日优先）**
- **问题描述**: 用户选择 [理论归纳] 范式后，实际效果与预期不符，怀疑 YAML 配置未正确加载或生效
- **排查方向**:
  - 检查 `config/` 目录下是否有 YAML 范式配置文件
  - 检查 `semantic_extractor.py` 中范式参数是否从 YAML 读取还是硬编码
  - 检查前端选择范式后，后端是否实际使用了对应参数
  - 检查理论归纳范式的 system prompt 是否包含 YAML 中的配置参数
- **优先级**: P1

无新增遗留问题。P19 已完全解决。

---

*记录日期：2026-07-15*

## 明日计划（2026-07-15 → 07-16）

| 优先级 | 任务编号 | 任务内容 | 说明 |
|:---|:---|:---|:---|
| **P0** | Agent | 图谱教育 Agent 开发 | 基于四层图架构的 P1 阶段：SQLite 持久化 + LLM 集成 |
| **P1** | P21 | 公式提取优化 | 线性代数课件测试，确认公式是否被识别为 formula chunk |
| **P1** | P22 | YAML 范式配置验证 | 确认 [理论归纳] 范式配置是否在前端生效 |
| **P2** | P14 | 两阶段提取优化 | 基于 heading 上下文的连接建立（nodes-first → edges-with-context） |
| **P2** | P17 | 公式/表格提取增强技术方案 | 待 P21 排查后确定技术方案 |
| **P3** | P20 | 前端范式管理 UI | 前端连接 YAML 配置，支持新建/编辑范式 |

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

## 2026-07-16 更新

### 🔴 遗留问题更新

#### LA-035-P21: 公式图片识别为 LaTeX（修正方向）
- **状态**: 🔴 **进行中**
- **问题描述**: MinerU 从 PDF 提取的公式实际是图片，不是文本 LaTeX。当前流程中这些公式图片被当作普通图片用 VLM 描述，导致 SemanticExtractor 无法获取精确的公式语义。
- **根因**: 
  - MinerU 输出的 Markdown 中公式以 `![...](images/xxx.jpg)` 图片形式存在
  - `ImageConceptExtractor` 对所有图片统一调用 VLM `task="describe"`，而非 `task="formula"`
  - 公式图片生成的 pseudo_chunk text 是"图片描述"而非 LaTeX 代码
- **修复方案**:
  - 在 `ImageConceptExtractor` 中增加公式图片检测（宽高比特征）
  - 对疑似公式图片调用 VLM `task="formula"` 识别 LaTeX
  - 公式图片的 pseudo_chunk text 设为识别出的 LaTeX（而非描述）
  - `media_refs` 中同时添加 `{"type": "formula", "latex": "..."}`
- **修改范围**: `core/image_concept_extractor.py`, `core/mineru_client.py`
- **优先级**: P0

#### LA-035-P23: 缺少[删除学科]前端方法
- **状态**: ✅ **已完成**
- **内容**: Sidebar.vue 学科选择器区域增加 🗑️ 删除按钮，点击确认后调用 `apiDeleteSubject` 删除学科并更新前端状态
- **修改文件**: `web-vue/src/components/Sidebar.vue`
- **功能**: 支持删除非默认学科，带二次确认对话框，防止误删；删除成功后自动切换至剩余学科

---

#### LA-035-P24: 节点有图片 tag 但详情面板无图片（media_ref 数据链断裂）
- **状态**: ✅ **已完成**
- **根因**: `GraphLayout.js` 的 `runTreeLayout` 和 `runConceptLayout` 创建副本节点时，遗漏了 `media_refs` 字段。导致图谱显示"图片×N"（cardLabel 已复制），但点击详情面板为空（副本节点无 media_refs 数据）。
- **修复**: 
  - `runTreeLayout` 副本增加: media_refs, image_path, thumbnail_path, width, height
  - `runConceptLayout` 副本增加: media_refs, has_media, hasImage, hasTable, hasFormula, image_path, thumbnail_path, width, height
- **修改文件**: `web-vue/src/components/graph/GraphLayout.js`
- **构建状态**: `npm run build` 通过（2026-07-16）
- **验证**: 诊断脚本 `scripts/diagnose_media_refs.py` 确认 CanonicalConcept 节点 media_refs 数据存储正确（5/20 个有图片），问题仅在前端副本节点未复制数据。
- **优先级**: P1

#### LA-035-P26: 图片不显示 + 公式渲染失败（双重根因）
- **状态**: ✅ **已完成**
- **根因分析**:
  1. **图片不显示**: `_escape_cypher_string` 将 Windows 绝对路径中的 `\` 替换为 `/`，导致 `image_path` 变成 `D:/.../学科_v1_images/...`。`NodeDetailPanel` 的 `imageUrl` 解析 `path.split('/')[0]` 得到 `D:` 而不是学科名，URL 错误
  2. **公式不渲染**: `_escape_cypher_string` 将 JSON 中的反斜杠转义 `\\` 替换为 `//`，导致 LaTeX 命令 `\sum` 变成 `//sum`，KaTeX 无法识别
- **修复**:
  - 后端 `graph_store.py`: 新增 `_escape_cypher_string_safe` 函数（不替换反斜杠），用于 `media_refs` 存储；`image_path` 存储前转换为相对路径
  - 前端 `NodeDetailPanel.vue`: `imageUrl`/`thumbnailUrl`/`getImageUrl` 从路径中查找 `_v1_images`/`_v1_thumbnails` 提取学科名；`renderFormulaContent` 将 `//` 替换为 `\`
- **修改文件**: `core/graph_store.py`, `web-vue/src/components/graph/NodeDetailPanel.vue`
- **构建状态**: `npm run build` 通过（2026-07-16）
- **优先级**: P1
- **备注**: 旧数据库中的数据仍受 `_escape_cypher_string` 影响，前端修复兼容旧数据；新数据使用 `_escape_cypher_string_safe` 存储正确

#### LA-035-P25: 公式 LaTeX 前端渲染
- **状态**: ✅ **已完成**
- **内容**: 使用 katex 库在 GraphNodeTooltip.vue 和 NodeDetailPanel.vue 中渲染 LaTeX 公式为数学符号
- **实现方式**: OpenCode 自动执行（DeepSeek/deepseek-chat 模型）
- **修改文件**:
  - 新增: `web-vue/src/utils/latex.js` — 封装 renderLatex 工具函数
  - 修改: `web-vue/src/components/graph/GraphNodeTooltip.vue` — 悬浮预览公式渲染
  - 修改: `web-vue/src/components/graph/NodeDetailPanel.vue` — 详情面板公式渲染
- **构建状态**: `npm run build` 通过（2026-07-16，Vite v5.4.21）
- **备注**: 构建产物含 KaTeX 字体文件，chunk 大小 1.04MB（可后续优化按需加载）
- **优先级**: P1

### 明日计划（2026-07-16）

| 优先级 | 任务编号 | 任务内容 | 说明 |
|:---|:---|:---|:---|
| **P0** | P21 | 公式图片识别为 LaTeX | ImageConceptExtractor + mineru_client 公式识别 |
| **P1** | P23 | 删除学科前端方法 | 前端增加删除按钮 + 后端 API |
| **P1** | P24 | media_ref 断裂排查 | 对比悬浮窗 vs 详情面板数据来源 |

---

*记录日期：2026-07-16*

---

## 2026-07-11 终版更新

[旧内容保留...]

---

## LA-040-P0 Agent 集成遗留问题（2026-07-16 新增）

### P0-INT-1: Coordinator 未集成 P0 模块
- **状态**: 🔴 **新增**
- **问题描述**: `agents/coordinator.py` 仍只使用旧版 `TutorAgent`/`QuizAgent`/`CoachAgent`/`HeadhunterAgent`，未导入 `core.graph_education` 的任何模块（ConceptRetriever、SubgraphBuilder、ContextAssembler、IRTEstimator、GroupManager）。
- **代码证据**: `grep` 确认 `coordinator.py` 无任何 `graph_education` 导入，时序图 5.2 中规划的 P0 调用链未实现。
- **影响**: P0 模块无法通过 Coordinator 统一入口使用，成为"死代码"。
- **优先级**: P0

### P0-INT-2: QuizAgent 未使用 ContextAssembler
- **状态**: 🔴 **新增**
- **问题描述**: `agents/quiz_agent.py` 仍直接检索 chunks 拼接为 LLM prompt（`QUIZ_GENERATION_PROMPT`），未调用 `ContextAssembler` 组装结构化上下文。
- **代码证据**: `grep` 确认 `quiz_agent.py` 无任何 `graph_education` 导入，未使用 `ContextBudget`、`Subgraph` 等类型。
- **影响**: 出题上下文未按 P0 设计进行 token budget 控制、子图构建、来源文档显示。
- **优先级**: P0
- **依赖**: P0-INT-1

### P0-INT-3: CoachAgent 未使用 IRTEstimator
- **状态**: 🔴 **新增**
- **问题描述**: `agents/coach_agent.py` 的评分逻辑使用简单规则评分（客观题精确匹配 + 主观题关键词匹配），未调用 `IRTEstimator` 进行能力估计。
- **代码证据**: `grep` 确认 `coach_agent.py` 无任何 `graph_education` 导入，未使用 `IRTParams`、`UserKnowledgeState` 等类型。
- **影响**: 用户能力画像无 IRT 参数（theta / 置信度），无法自适应出题难度，无法实现设计文档中的按组选题 + 批量画像。
- **优先级**: P0
- **依赖**: P0-INT-1

### P0-INT-4: UserKnowledgeState 无持久化
- **状态**: 🔴 **新增**
- **问题描述**: `core/graph_education/types.py` 中定义了 `UserKnowledgeState` dataclass，但无 SQLite/Redis 持久化实现。`graph_store.py` 中无 `UserKnowledgeState` 节点表的创建逻辑。
- **影响**: 用户答题历史无法保存，IRT 无法校准，能力画像无法跨会话保持。
- **优先级**: P1

### P0-INT-5: 图中心性预计算未集成
- **状态**: 🔴 **新增**
- **问题描述**: `SubgraphBuilder` 有 `centrality_cache` 参数，但无预计算脚本。`GraphStore` 中没有 `PageRank`/`Betweenness` 的离线计算和缓存逻辑。
- **影响**: 每次构建子图需实时计算中心性，性能开销大。
- **优先级**: P1

### P0-INT-6: Agent 间消息总线未实现
- **状态**: 🔴 **新增**
- **问题描述**: 设计文档中 MetaGPT 风格的 Agent 间消息池（事件订阅/发布）未实现。各 Agent 独立工作，无状态共享机制。
- **影响**: CoachAgent 更新的能力画像，QuizAgent 无法感知；TutorAgent 无法根据用户历史错误模式调整讲解策略。
- **优先级**: P2
- **依赖**: P0-INT-4


---

## 2026-07-17 更新

### P0-INT 状态修正

#### P0-INT-1~6 已完成（2026-07-16 实现）
- P0-INT-1: Coordinator 集成 P0 模块
- P0-INT-2: QuizAgent 使用 ContextAssembler
- P0-INT-3: CoachAgent 使用 IRTEstimator
- P0-INT-4: UserKnowledgeState SQLite 持久化
- P0-INT-5: 图中心性预计算整合进主程序
- P0-INT-6: Agent 间消息总线

### 新增遗留问题（2026-07-17）

#### LA-035-P27: 前端图片仍无法显示（RAG 学科重建后）
- **状态**: ✅ **已解决（2026-07-18 验证通过）**
- **根因确认** (2026-07-17 更新):
  - Chunk 节点 `media_refs` 存储了 Windows 绝对路径（`D:\\MyCS\\...`），反斜杠在 JSON 中未转义，导致 `json.loads` 失败：`Invalid \escape`
  - `get_canonical_concepts` fallback 从 source_chunks 获取图片时，Chunk 的 `media_refs` 解析失败，返回空数组
  - 概念节点自身 `media_refs` 为空，且 fallback 也失败，导致前端 `hasMedia` 为 false，不渲染图片
- **修复**:
  1. 新增 `GraphStore._sanitize_media_refs()` 方法：使用 `relative_path` 替代 `path`，反斜杠替换为正斜杠
  2. 在所有写入路径调用：add_chunk_nodes、store_extracted_concepts、store_canonical_concepts
  3. 批量修复现有数据：rag_v1（168/756 有图片，新增 123 个），transformer_v1（54/139 有图片，新增 27 个）
  4. 节点 concept_canonical_b9dcd94454（"文本生成"）已修复为：`path: "rag_v1_images/tmpmevygvhq_mineru_2_2108b2b2.png"`
- **待验证**: 刷新前端后点击有图片标签的节点（如"文本生成"），检查：
  1. NodeDetailPanel 中显示图片
  2. Network 中出现 `/api/images/rag/...` 请求
  3. 图片正确显示（非空白/404）

#### LA-035-P28: 节点悬浮窗图片自适应大小
- **状态**: ✅ **已解决（2026-07-18 验证通过）**
- **问题描述**: 悬浮窗（GraphNodeTooltip.vue）中的图片被固定尺寸裁剪压缩，无法完整显示图片内容。首次修复使用 `aspect-ratio: 16/10` 强制容器比例，但用户反馈未成功实现。
- **根因分析**: `aspect-ratio` 强制容器为固定比例，不适合所有图片（竖图、横图、正方形混用）。`width: 100%; height: 100%` 在容器内仍可能拉伸。
- **二次修复** (2026-07-18):
  1. 去掉 `.tooltip-media-thumb` 的 `aspect-ratio` 限制
  2. 使用 `max-width: 100%; max-height: 100%; width: auto; height: auto` 让图片保持原始比例自适应
  3. 容器使用 `max-height: 200px`（单张 260px）限制最大高度，防止图片过高
  4. 保留 `object-fit: contain` 确保不裁剪
- **修改文件**: `web-vue/src/components/graph/GraphNodeTooltip.vue`
- **验证结果**: 悬浮在带图片的节点上，图片完整显示、比例正确、不裁剪不拉伸
- **优先级**: P1 → 已关闭

#### LA-035-P29: 删除学科后数据库未完全清除
- **状态**: 🟡 **已修复（待验证）**
- **根因** (2026-07-17 已确认): `delete_subject` 只删除了 SQLite 记录、学科文件夹和向量库，但遗漏了：
  1. KuzuDB 图数据库（`knowledge_base/graph_db/{subject}_v1_graph`）
  2. 图片目录（`knowledge_base/{subject}_v1_images/`）
  3. 缩略图目录（`knowledge_base/{subject}_v1_thumbnails/`）
  4. 向量库附属文件（`.db-wal`, `.db-shm`, `.db-journal`）
  5. 历史残留：旧删除操作留下了大量乱码命名的 graph DB 文件（编码问题导致重复创建）
- **修复**:
  1. `core/subject_manager.py` `delete_subject` 函数补充删除上述所有遗漏项
  2. 清理历史残留：删除了 10+ 个旧 graph DB 文件（`RAG_graph`、乱码命名文件等）
- **待验证**: 删除一个学科后重建同名学科，确认：
  1. `knowledge_base/graph_db/` 下无旧 graph DB 残留
  2. 新学科的所有节点都是新创建的（无旧节点混入）
- **优先级**: P1

#### LA-035-P30: 文档树功能卡死 / 效果错乱
- **状态**: 🔴 **重新设计（2026-07-18）**
- **根因 1（2026-07-17 已确认）**: BELONGS_TO / ADJACENT_TO 关系结构错误导致布局算法失败
  - BELONGS_TO 被误用于同级段落顺序，ADJACENT_TO 混入跨层级关系
  - document 节点无出边，导致 167 个 heading 成为"伪根"
- **根因 2（2026-07-18 已确认）**: 文档树视图中加载了 ADJACENT_TO 边，导致长水平边线交叉；节点标签 30 字符过长互相重叠；节点间距太小
- **修复尝试 1** (2026-07-17):
  1. 重写 `build_belongs_to_relations` / `build_adjacent_relations` 建立正确结构
  2. 删除旧数据错误边，重建为 564 BELONGS_TO + 216 ADJACENT_TO
  3. 根节点仅剩 5 document + 7 orphan paragraph
- **修复尝试 2** (2026-07-18):
  1. `GraphView.vue` `loadEdges`: 过滤只加载 BELONGS_TO 边，排除 ADJACENT_TO（文档树视图不需要同级顺序边）
  2. `GraphLayout.js` `runTreeLayout`: `layerWidth` 250→350, `nodeGap` 60→80, `treeGap` 120→150
  3. `GraphLayout.js` `generateNodeLabel`: 标签截断从 30 字符缩短到 20 字符
- **验证结果**: 2026-07-18 用户测试反馈："文档树视图和原先相比没变化" — 效果未改善，需要重新检查设计
- **后续方向**: 需要重新审查文档树布局的整体设计，可能需要：
  1. 检查前端是否正确切换视图（文档树 vs 知识图谱）
  2. 检查后端 BELONGS_TO 边是否正确写入数据库
  3. 重新设计文档树布局方案（dagre / 自定义 / 其他布局算法）
- **优先级**: P1 → 延后处理

---

## 2026-07-18 更新（P30 文档树问题深度修复）

### 🔴 根因分析（基于用户反馈）

用户反馈的三大问题：
1. **paragraph 和 heading 没有明显区分** — 所有 chunk 节点使用相同的 Cytoscape 样式
2. **heading 包含被截断的 JSON 内容** — `generateNodeLabel` 未过滤 JSON 代码块，导致标签显示异常
3. **heading 层级判断和 BELONGS_TO 算法可能有误** — 怀疑 `build_belongs_to_relations` 中层级关系判断不正确

### 修复内容

#### 修复1: 前端样式区分（P30-1）
- **文件**: `web-vue/src/components/graph/GraphStyles.js`
- **修改**: 添加 heading/paragraph/document 三种 chunk 类型的独立样式
  - Heading: 圆角矩形、红色、90x36px
  - Paragraph: 椭圆、蓝色、50x30px
  - Document: 矩形、绿色、100x40px
- **效果**: 文档树中不同类型节点一目了然

#### 修复2: 边查询 LIMIT 截断（P30-2）
- **文件**: `app/backend_api.py` `list_graph_edges`
- **问题**: 硬编码 `LIMIT 100`，当 BELONGS_TO 边超过 100 时（如 RAG 学科 564 条），82% 的边被截断，导致大量节点断开连接
- **修改**: 去掉硬编码 LIMIT，使用参数 `limit`（默认 500，最大 2000）
- **文件**: `web-vue/src/components/graph/GraphView.vue` `loadEdges`
- **修改**: limit 从 200 → 1000

#### 修复3: 节点查询 LIMIT 截断（P30-3）
- **文件**: `app/backend_api.py` `list_graph_nodes`
- **修改**: 默认 limit 从 500 → 1000
- **文件**: `web-vue/src/components/graph/GraphView.vue` `loadChunkNodes`
- **修改**: limit 从 500 → 1000

#### 修复4: chunk_type 不匹配（P30-4）
- **问题**: `image_pseudo` / `formula_pseudo` 类型节点未被文档树布局识别
- **修改**:
  - `backend_api.py` `list_graph_nodes`: 图片字段条件从 `row[4] == 'image'` 放宽为 `in ('image', 'image_pseudo', 'formula_pseudo')`
  - `GraphLayout.js` `runTreeLayout`: 兼容 `image_pseudo` 和 `formula_pseudo` 类型（5 处过滤）
  - `GraphStyles.js`: 图片节点样式选择器兼容 `image_pseudo` 和 `formula_pseudo`

#### 修复5: 大文档树触发简化网格（P30-5）
- **问题**: `MAX_CHUNK_NODES = 200` 导致大文档树强制使用网格布局而非树形布局
- **修改**: `MAX_CHUNK_NODES` 从 200 → 500

#### 修复6: JSON 内容过滤（P30-6）
- **文件**: `web-vue/src/components/graph/GraphLayout.js` `generateNodeLabel`
- **修改**:
  - 如果 text 以 JSON 开头（`{` 或 `[`），优先使用 `headingPath` 或 `fallback` 生成标签
  - 清理逻辑增加代码块、图片引用、表格行过滤
  - 避免 JSON 代码块被截断后显示为乱码标签

### 待验证（用户回家后测试）
1. 清除 Vite 缓存 + 浏览器缓存（`Ctrl+Shift+R`）
2. 切换到文档树视图，检查节点类型是否区分（颜色/形状）
3. 检查 heading 节点标签是否显示标题文本（而非 JSON 片段）
4. 检查文档树是否呈现树形结构（document → heading → paragraph）
5. 检查是否还有大量节点重叠在左上角
6. 查看 DevTools Console 中的 `[runTreeLayout]` 日志

### 潜在问题（待确认）
- `build_belongs_to_relations` 中 `heading_by_path` 使用 heading_path 作为 key，如果文档中有相同的标题层次结构（重复 heading_path），只保留第一个，可能导致子段落连接到错误的 heading
- 该问题在大多数文档中不常见，但如果用户文档中有重复标题，需要进一步修复

---

#### LA-040-P0-QUIZ: Agent 出题流程回退到旧方式
- **状态**: ✅ **已解决（2026-07-18 验证通过）**
- **修复历史**:
  - 修复1 (2026-07-17): KuzuDB 文件锁定、API 端点绕过 Coordinator、消息总线订阅、TutorAgent P0 接入
  - 修复2 (2026-07-18): `QuizRequest` / `EvaluateStartRequest` 添加 `user_id` 字段
  - 修复3 (2026-07-18): `_extract_topic_from_query` 正则重写，支持 "on {topic}" / "evaluate my {topic} level" 模式
  - 修复4 (2026-07-18): `ConceptRetriever.resolve` 不再抛异常，添加 PageRank Top-5 兜底策略
  - 修复5 (2026-07-18): `_match_fuzzy` 双向包含匹配 + case-insensitive Python 回退（关键修复：Cypher 大小写敏感导致 "rag 技术" 不匹配 "RAG"，Python 回退逻辑成功匹配）
  - 修复6 (2026-07-18): `Coordinator._get_retriever` 传入 `HybridRetriever` 作为 `vector_store`，使 embedding 语义检索可用
- **验证结果** (2026-07-18 01:27): 出题成功走 P0 流程，从 "RAG" 种子扩展出 11 节点 10 边，返回 RAG 相关题目
- **日志**: `[Coordinator] 解析到 1 个种子概念` → `[Coordinator] 构建子图: 11 节点, 10 边` → `[Coordinator] 组装上下文: 910 tokens` → `[QuizAgent] P0-INT-2: 使用 P0 图谱上下文出题`
- **改进建议（待实现）**:
  1. `resolve` 当前只取 `nodes[0]`（Top-1），可改为返回所有模糊匹配结果，让前端/用户选择基于 Top-N 出题
  2. 调试打印已生效，可后续清理或保留为 `logging.debug`
- **优先级**: P0 → 已关闭

---

### LA-040-P0-QUIZ-IMPROV: Top-N 种子概念选择（用户可选出题范围）
- **状态**: 🟡 **新增改进点（2026-07-18）**
- **问题描述**: `ConceptRetriever.resolve()` 在模糊匹配成功后只取 `nodes[0]`（Top-1），用户无法选择其他相关概念。例如查询 "RAG 技术" 时系统只选 "RAG" 一个种子概念，忽略了图谱中 "检索增强生成"、"向量检索" 等相关概念。
- **期望效果**:
  1. `resolve()` 返回所有模糊匹配结果（而非只取 Top-1）
  2. 前端出题界面展示候选概念列表，用户可勾选/取消
  3. 支持"全选"模式：使用所有匹配到的概念作为种子，构建更大的子图
  4. 默认行为保持 Top-1（向后兼容），但提供 Top-N 选项
- **技术方案**:
  1. `ConceptRetriever.resolve()` 新增参数 `max_seeds: int = 1`
  2. 当 `max_seeds > 1` 时返回 `nodes[:max_seeds]`
  3. `SubgraphBuilder.build()` 支持多种子概念输入（已有支持）
  4. 前端 Quiz 页面新增"出题范围"配置面板：
     - 种子概念数量滑块（1~10）
     - 展示候选概念列表（名称 + 描述 + 匹配度）
     - 用户可手动勾选/取消
- **依赖**: 前端 UI 设计 + API 参数扩展
- **优先级**: P2
- **备注**: 这是一个体验改进，不是 bug 修复。当前 Top-1 模式下子图扩展已能产生丰富的题目（11 节点 10 边），Top-N 模式会让出题覆盖更多相关知识点。

