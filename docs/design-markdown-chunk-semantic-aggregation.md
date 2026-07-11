# Markdown Chunk 优化与语义聚合方案 v2.0

> 版本: 2.0
> 日期: 2026-07-11
> 关联任务: LA-035 Phase 2.2, LA-035 Phase 2.3

---

## 1. 背景与问题

### 1.1 当前分块策略的局限

**PyMuPDF 模式（当前默认）:**
```
PDF 逐页提取 → 页级 ParentChunk + 段落级 ChildChunk
```
- 标题检测是启发式规则（基于书签/文本特征），不可靠
- 跨页段落被切断，需要后处理合并
- 图片提取为独立 chunk，与文本无上下文关联
- 章节结构经常错乱

**MinerU 模式（v1.0 设计）:**
```
MinerU CLI → 结构化 Markdown → 按 ## 标题分块 → TitleChunk + ParagraphChunk
```
- 仅按 `##` 二级标题分块，忽略更深层的 `###` `####`
- TitleChunk 内容包含所有子标题下的段落（过于粗粒度）
- 层级关系扁平化（只有 L1 Title + L2 Paragraph 两层）
- 无法表达深层嵌套的文档结构

### 1.2 核心矛盾

| 维度 | 需要 | 当前状况 |
|------|------|---------|
| 细粒度 | 自然段级 chunk（用于精确检索） | 按 `##` 分块太粗 |
| 结构保留 | 保留 Markdown 的完整标题层级 | 只到 `##` 层级 |
| 递归聚合 | 自底向上逐层聚合（N 级 → N-1 级 → ... → 文档级） | 扁平两层结构 |
| 语义关联 | 同标题下段落概念的综合 + 跨标题聚合 | 无聚合机制 |

---

## 2. 新分块架构：树形递归结构

### 2.1 核心原则

> **段落级 chunk 是最小单位，基于语法意义上的"自然段"（换行分隔），而非标题层级。**

**自然段的定义**：前后两个 chunk 之间在文本上通过**一个或多个空行**实现分隔。一个自然段可以包含多行文本（如长段落折行），只要不出现空行。

### 2.2 架构总览

```
Document Level 0 (文档根)
  │
  ├── HeadingChunk Level 1 (# 一级标题)
  │     │
  │     ├── ParagraphChunk (直接属于该标题的自然段)
  │     ├── ParagraphChunk
  │     │
  │     ├── HeadingChunk Level 2 (## 二级标题)
  │     │     │
  │     │     ├── ParagraphChunk
  │     │     ├── ParagraphChunk
  │     │     │
  │     │     ├── HeadingChunk Level 3 (### 三级标题)
  │     │     │     ├── ParagraphChunk
  │     │     │     └── ParagraphChunk
  │     │     └── HeadingChunk Level 3' (### 另一个三级标题)
  │     │           └── ParagraphChunk
  │     │
  │     └── HeadingChunk Level 2' (## 另一个二级标题)
  │           └── ParagraphChunk
  │
  └── HeadingChunk Level 1' (# 另一个一级标题)
        └── ...
```

### 2.3 各层级职责

| 层级 | 类型 | 定义 | 核心职责 | 内容组成 |
|------|------|------|---------|---------|
| **Level 0** | Document | 整个文档 | 全局上下文容器 | 前言段落 + 所有 L1 标题引用 |
| **Level N** | HeadingChunk | `#` × N 级标题 | 主题聚合单元 | 标题文本 + **直接段落**（不含子标题内容） |
| **Leaf** | ParagraphChunk | 自然段 | 细粒度概念提取单元 | 单个自然段文本 |

**关键区别（与 v1.0）**：
- v1.0: TitleChunk 包含该标题下**所有内容**（包括子标题及其段落）
- v2.0: HeadingChunk 只包含**直接属于该标题的段落**（不含子标题下的内容）
- 树形关系通过 `parent_id` / `child_ids` 表达，而非内容嵌套

### 2.4 HeadingChunk 的内容边界

```markdown
# 一级标题

段落A（直接属于一级标题）

## 二级标题

段落B（直接属于二级标题）

### 三级标题

段落C（直接属于三级标题）

段落D（直接属于三级标题）

## 二级标题'

段落E（直接属于二级标题'）
```

**内容归属**：
- 一级标题 HeadingChunk: 包含「段落A」
- 二级标题 HeadingChunk: 包含「段落B」
- 三级标题 HeadingChunk: 包含「段落C、段落D」
- 二级标题' HeadingChunk: 包含「段落E」

**为什么这样设计？**
- 每个 HeadingChunk 的粒度更精确
- 语义聚合阶段可以对每个层级独立处理
- 避免高层 HeadingChunk 过于庞大（包含所有子内容）

---

## 3. 分块算法

### 3.1 三阶段分块流程

```
输入: Markdown 文本

Stage 1: 标题树解析
  识别所有 #/##/###/####/#####/###### 标题
  构建树形结构（每个节点: level, text, line_idx, end_line_idx, parent, children）

Stage 2: 自然段分割与归属
  按 \n\n+ 分割整个文档为自然段
  对每个自然段，找到"包含它的最深层标题"
  将该自然段归属为该标题的"直接段落"

Stage 3: Chunk 生成
  每个标题节点 → HeadingChunk
  每个自然段 → ParagraphChunk
  文档根 → DocumentChunk（可选）
```

### 3.2 标题区间计算

每个标题节点的**直接内容区间**：
```
直接内容起始 = 标题行号 + 1
直接内容结束 = min(下一个同级/更高级标题行号, 第一个子标题行号)
```

示例：
```markdown
Line 0: # H1
Line 1: 段落A
Line 2:  
Line 3: ## H2
Line 4: 段落B
Line 5:  
Line 6: ### H3
Line 7: 段落C
Line 8:  
Line 9: ## H2'
Line 10: 段落D
```

- H1 (L0, level=1): 区间 [1, 3) → 段落A
- H2 (L3, level=2): 区间 [4, 6) → 段落B
- H3 (L6, level=3): 区间 [7, 9) → 段落C
- H2' (L9, level=2): 区间 [10, end) → 段落D

### 3.3 自然段分割

```python
def split_to_paragraphs(text: str) -> List[str]:
    """
    按一个或多个空行分割为自然段。
    
    规则:
    - 分隔符: \n\n+（一个空行或多个连续空行）
    - 每个自然段 strip() 处理
    - 过滤空字符串
    """
    import re
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    return paragraphs
```

### 3.4 段落归属算法

```python
def assign_paragraph_to_heading(paragraph_line_range, heading_tree):
    """
    将自然段归属到包含它的最深层标题。
    
    策略:
    1. 找到该自然段的行号范围
    2. 从标题树中找到"区间包含该范围"且"层级最深"的标题节点
    3. 将该自然段添加到该节点的 direct_paragraphs 列表
    """
    pass
```

---

## 4. 输出数据结构

### 4.1 HeadingChunk

```python
{
    "id": "md_doc_h1_0_abc123",  # md_{source}_h{level}_{index}_{hash}
    "text": "# 一级标题\n\n段落A",  # 标题行 + 直接段落（用 \n\n 连接）
    "metadata": {
        "source": "doc.pdf",
        "subject": "generic",
        "chunk_type": "heading",  # "heading" | "paragraph" | "document"
        "heading_path": "一级标题",  # 从根到当前标题的路径，用 " > " 连接
        "heading_level": 1,  # 1=#, 2=##, ..., 6=######
        "parent_id": "md_doc_doc_0_root",  # 父 HeadingChunk ID（根节点为 None）
        "child_ids": ["md_doc_h2_1_def456", "md_doc_h2_3_ghi789"],  # 子 HeadingChunk IDs
        "paragraph_ids": ["md_doc_p1_0_jkl012"],  # 直接子 ParagraphChunk IDs
        "line_range": [0, 3],  # [起始行号, 结束行号)
        "image_refs": [],  # 直接段落中包含的图片引用
        "formula_count": 0,
        "table_lines": 0,
    },
    "source": "doc.pdf",
}
```

### 4.2 ParagraphChunk

```python
{
    "id": "md_doc_p1_0_jkl012",  # md_{source}_p{index}_{hash}
    "text": "段落A的完整文本内容...",
    "metadata": {
        "source": "doc.pdf",
        "subject": "generic",
        "chunk_type": "paragraph",
        "heading_path": "一级标题",  # 所属标题的路径
        "heading_level": 1,  # 所属标题的层级
        "parent_id": "md_doc_h1_0_abc123",  # 直接父 HeadingChunk ID
        "paragraph_index": 0,  # 在同父 HeadingChunk 下的段落序号
        "line_range": [1, 2],  # [起始行号, 结束行号)
        "image_refs": [],  # 本段落中包含的图片引用
        "formula_count": 0,
        "table_lines": 0,
    },
    "source": "doc.pdf",
}
```

### 4.3 DocumentChunk（可选，Level 0）

```python
{
    "id": "md_doc_doc_0_root",
    "text": "前言段落1\n\n前言段落2",  # 第一个标题之前的所有段落
    "metadata": {
        "source": "doc.pdf",
        "subject": "generic",
        "chunk_type": "document",
        "heading_path": "",  # 文档根无路径
        "heading_level": 0,
        "parent_id": None,
        "child_ids": ["md_doc_h1_0_abc123", "md_doc_h1_5_mno345"],  # 所有 L1 标题
        "paragraph_ids": ["md_doc_p0_0_pqr678"],  # 前言段落
    },
    "source": "doc.pdf",
}
```

---

## 5. 与现有系统的兼容性

### 5.1 接口兼容

`MarkdownChunker.chunk_markdown()` 返回 `List[Dict]`（扁平列表），与现有 pipeline 兼容：

```python
chunker = MarkdownChunker()
chunks = chunker.chunk_markdown(markdown_text, source_metadata)

# chunks 中同时包含 heading 和 paragraph
# 原有代码可通过 chunk["metadata"]["chunk_type"] 区分类型
```

### 5.2 与 image_concept_extractor.py 的兼容

`ImageConceptExtractor` 原通过 `chunk_type == "title"` 识别图片上下文。v2.0 中：
- `chunk_type == "heading"` 的 chunk 承担相同的"图片上下文容器"角色
- `ImageConceptExtractor` 需同时支持 `"title"`（旧数据）和 `"heading"`（新数据）

### 5.3 与 SemanticExtractor 的兼容

`SemanticExtractor.extract_concepts()` 接收 `chunk_text` 和 `media_context`：
- HeadingChunk: 包含标题 + 直接段落，适合提取**主题概念**
- ParagraphChunk: 包含单个自然段，适合提取**细粒度概念**
- 两者均可携带 `media_refs`（图片/表格/公式引用）

---

## 6. 语义聚合策略（Phase 2.3）

### 6.1 聚合方向

```
ParagraphChunk (Level Leaf)
  → 提取细粒度概念（via SemanticExtractor）

HeadingChunk (Level N)
  → 收集所有直接子 ParagraphChunk 的概念
  → 去重合并（embedding 相似度 > 0.85）
  → 提取"主题概念"（基于标题文本 + 子概念综合，via LLM）
  → 建立层级关系: 主题概念 --[HAS_DETAIL]--> 细节概念
  → 生成 HeadingChunk 的"缩印"（摘要）和"概述"

递归向上:
  HeadingChunk Level N → HeadingChunk Level N-1 → ... → DocumentChunk
```

### 6.2 HeadingChunk 语义增强

每个 HeadingChunk 在分块阶段只包含原始文本。语义聚合阶段可为其增加：

```python
# 聚合后附加的字段
{
    "metadata": {
        "aggregated": True,
        "summary": "该标题内容的 LLM 生成摘要",  # "缩印"
        "theme_concepts": ["主题概念A", "主题概念B"],  # 聚合提取的主题
        "concept_count": 5,  # 直接子概念数量
    }
}
```

### 6.3 层级关系类型

```
主题概念 --[HAS_DETAIL]--> 细节概念
主题概念 --[CONTAINS]--> 子标题主题概念
文档概念 --[HAS_THEME]--> 一级标题主题概念
```

**是否需要新增关系类型到 Schema？**

建议新增 `HAS_DETAIL` 关系（CanonicalConcept → CanonicalConcept），理由：
- `SOLUTION` / `DEPENDS_ON` 表达的是跨概念语义依赖
- `HAS_DETAIL` 表达的是同一主题下的层级从属
- 两者互补，不重复

---

## 7. 实现计划

### Phase 1: MarkdownChunker v2.0（今天）
- [x] 重写 `MarkdownChunker`：按自然段分块 + 树形标题结构
- [x] 适配 `mineru_client.py`：调用新接口
- [x] 适配 `image_concept_extractor.py`：支持 `"heading"` chunk_type
- [ ] 单元测试：验证树形结构正确性
- [ ] 集成测试：端到端 PDF 解析 → chunk 输出

### Phase 2: 语义聚合（下一步）
- [ ] 实现 `SemanticAggregator`：按 HeadingChunk 聚合 ParagraphChunk 概念
- [ ] 实现主题概念提取（LLM 综合标题 + 子概念）
- [ ] 实现层级关系建立（HAS_DETAIL）
- [ ] 集成 `ConceptDeduper`：去重合并

### Phase 3: 概念融合（下一步）
- [ ] 图片概念（image_pseudo chunks）+ 文本概念 → 统一 CanonicalConcept
- [ ] `media_refs` 合并验证
- [ ] 端到端测试：MinerU PDF → 概念图谱

---

## 8. 关键设计决策

### Q1: 分块粒度——自然段可能很长（>2000字符）怎么办？

**决策**: 自然段是"语义单元"，不应强行切分。如果段落过长（>4000字符），按句子边界切分为多个 ParagraphChunk，但标注它们为"同一自然段的延续"。

**理由**: 强行按字符切分会破坏语义完整性。

### Q2: 标题行本身是否作为独立 chunk？

**决策**: 标题行不单独作为 chunk，而是作为 HeadingChunk 的 text 前缀。

**理由**: 标题本身没有独立语义内容，它只是组织标记。

### Q3: 图片引用行（`![alt](path)`）是否作为独立 ParagraphChunk？

**决策**: 是。如果图片引用行单独成一个自然段（前后有空行），它是一个独立的 ParagraphChunk。如果图片引用嵌入在文本段落中，它作为该 ParagraphChunk 的一部分。

**理由**: 保持自然段定义的一致性。

### Q4: 与现有 ConceptDeduper 的关系？

**决策**: 分块器输出 → SemanticExtractor → SemanticAggregator（按 HeadingChunk 聚合）→ ConceptDeduper（全局去重）

**理由**: SemanticAggregator 解决"同 HeadingChunk 内概念的层级关系"，ConceptDeduper 解决"跨 HeadingChunk 概念的去重"。

---

## 9. 附录：与 v1.0 的对比

| 维度 | v1.0 | v2.0（当前） |
|------|------|-------------|
| 分块依据 | `##` 二级标题 | 自然段（空行分隔） |
| 标题层级 | 仅 `##` / `###` | 所有层级 `#`~`######` |
| 层级深度 | 固定 2 层 | 动态（取决于文档结构） |
| HeadingChunk 内容 | 包含所有子内容 | 只包含直接段落 |
| 树形关系 | 扁平（parent-child 两层） | 递归树形（N 层） |
| chunk_type | "title" / "paragraph" | "heading" / "paragraph" / "document" |
| 语义聚合 | 无 | 自底向上递归聚合 |

---

## 10. 风险与注意事项

1. **超长自然段**: 某些 Markdown 文件可能没有正确使用空行分段，导致单个 ParagraphChunk 过长。需监控并处理。
2. **标题层级不连续**: 如 `#` 后直接 `###`，需正确处理父节点查找。
3. **兼容性**: `image_concept_extractor.py` 需同时支持 `"title"` 和 `"heading"`。
4. **性能**: 深层嵌套文档（>6 层标题）可能产生大量 HeadingChunk，需评估性能影响。
