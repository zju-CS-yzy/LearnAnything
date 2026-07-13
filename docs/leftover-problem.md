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

## 2026-07-11 终版更新

[旧内容保留...]
