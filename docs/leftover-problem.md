

---

## 2026-07-09 新增/更新

### ✅ 已完成

#### 1. LA-033 修复：v2.0 Schema 兼容
- **状态**: ✅ **已完成**
- **根因**: 后端 `get_subgraph/get_concepts_for_chunk/get_semantic_edges` 使用旧 Schema（`Concept` 节点类型 + `DEFINES` 关系），与新 v2.0 Schema（`CanonicalConcept`/`ExtractedConcept` + `SOLUTION`/`DEPENDS_ON`/`DERIVED_FROM`）不兼容
- **修复**:
  - `graph_store.py`: 三个函数更新为 v2.0 Schema
  - `backend_api.py`: `list_graph_concepts` 合并 KùzuDB 和 CSV 的 description
  - `GraphStyles.js`: 添加 DERIVED_FROM/HAS_CONCEPT 边样式
  - `NodeDetailPanel.vue`: 语义关联去重 + 新增边类型样式类
- **关键提交**: `cb2d335`

#### 2. LA-034 实现：贝塞尔曲线连接点系统
- **状态**: ✅ **已完成**
- **内容**:
  - 统一端点规则：源节点右中（90deg）→ 目标节点左中（270deg）
  - 曲线类型：unbundled-bezier（自适应曲率）
  - 动态曲率调整：根据目标节点相对 y 位置自动凹凸方向
- **提交序列**: `eeb0a6d` → `f3d4532` → `51ed14c` → `87318be` → `d98b347`

#### 3. LA-035 Phase 1：PDF 图片提取与展示
- **状态**: ✅ **已完成**
- **内容**:
  - `document_processor.py`: `_extract_pdf_page_images()` 提取 PDF 内嵌图片
  - 保存路径：`knowledge_base/<subject>_v1_images/` + `_thumbnails/`
  - `backend_api.py`: `/api/images/<subject>/<filename>` 静态文件路由
  - 前端：图片节点样式（📷 橙色）+ 详情面板缩略图预览
- **关键提交**: `19dcb93`, `2225b28`, `c918a63`

#### 4. LA-035 Phase 2.1：CanonicalConcept 多媒体扩展 Schema + 数据层
- **状态**: ✅ **已完成**
- **内容**:
  - `graph_store.py`: CanonicalConcept Schema 增加 `media_refs` 字段
  - `add_canonical_concepts()`: 支持写入 media_refs JSON
  - `get_canonical_concepts()`: 返回 media_refs 列表（兼容旧数据库回退）
  - `concept_deduper.py`: 合并时聚合 media_refs（去重）
  - `semantic_extractor.py`: 新增 `media_context` 参数支持多媒体上下文
- **关键提交**: `f987636`, `584c3c0`

#### 5. 设计文档
- **docs/design-image-semantic-classification.md**: 图片语义分类策略（含前人方案对比）
- **docs/design-canonicalconcept-multimedia.md**: CanonicalConcept 多媒体扩展完整设计

### 🔄 进行中

#### LA-035 Phase 2.2：图片概念提取流程
- **状态**: 🔄 **待实现**
- **内容**: 图片 → VLM 描述 → 伪文本 chunk → 概念提取 → 关联/合并到现有 CanonicalConcept
- **设计文档**: `docs/design-canonicalconcept-multimedia.md`
- **实施计划**:
  - Phase 2.2（1-2 天）：图片/公式/表格 → VLM 描述 → 概念提取流程
  - Phase 2.3（1 天）：节点创建/合并逻辑
  - Phase 2.4（1 天）：前端展示优化

### 🔴 遗留问题

#### LA-030: 部分 PDF 文档未提取出概念
- **状态**: ✅ **已解决**（7月9日确认）
- **解决**: 重写 PDF 处理流程，所有 PDF 正常提取概念
- **归档**: 2026-07-09

#### LA-031: PDF 导入缺少章节/页码信息
- **状态**: ✅ **已解决**（7月9日确认）
- **解决**: `_extract_page_headings()` + 字段统一映射
- **归档**: 2026-07-09

#### LA-032: 批量 embedding API 400 错误
- **状态**: 🟡 **保持**（Stage 1 parent_hint 已满足主要需求）

#### LA-035: 图片chunk提取与嵌入
- **状态**: 🔄 **Phase 2.1 完成，Phase 2.2 待实现**
- **已完成**: Schema 扩展、旧数据库兼容、API 字段补全
- **待实现**: 
  - `document_processor.py`: 图片 chunk VLM 预处理（生成伪文本）
  - `semantic_extractor.py`: 图片描述参与概念提取
  - `concept_deduper.py`: 图片概念与文本概念融合
  - 前端：概念节点展示关联媒体（📎 图标）

---

*记录日期：2026-07-09 23:10*
