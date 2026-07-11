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

### 明日计划（2026-07-12）

| 优先级 | 任务 | 内容 |
|:---|:---|:---|
| P0 | LA-035-P10 | 图片缩略图显示（Cytoscape.js 节点背景图片） |
| P0 | LA-035-P11 | 多媒体chunk融合可视化（融合来源标识 + 特殊边样式） |
| P1 | LA-035-P12 | 讨论并确认上层chunk融合方案 |

---

*记录日期：2026-07-11 23:59*
