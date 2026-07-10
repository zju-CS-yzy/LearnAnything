# Markdown Chunk 优化与语义聚合方案

> 版本: 1.0
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

**MinerU 模式（新引入）:**
```
MinerU CLI → 结构化 Markdown → 按 ## 标题分块
```
- 标题层级自动准确（`##` / `###`）
- 按阅读顺序输出，跨页段落自然连续
- 图片嵌入在正确章节位置
- 但缺少细粒度段落分割和语义聚合

### 1.2 核心矛盾

| 维度 | 需要 | 当前状况 |
|------|------|---------|
| 细粒度 | 段落级 chunk（用于精确检索） | MinerU 按 `##` 分块太粗 |
| 粗粒度 | 标题级 chunk（用于主题聚合） | PyMuPDF 标题检测不准 |
| 语义聚合 | 同标题下段落概念的综合 | 无聚合机制 |
| 层级关系 | 概念间的上下级关系 | 扁平结构 |

---

## 2. 新分块架构：三层树形结构

### 2.1 架构总览

```
Document (文档根)
  │
  ├── TitleChunk L1 (按 ## 分割) ──→ "主题概念"聚合单元
  │     │
  │     ├── ParagraphChunk L2-A (按段落/###分割) ──→ 细粒度概念提取单元
  │     ├── ParagraphChunk L2-B
  │     │
  │     └── TitleChunk L1-1 (按 ### 分割，嵌套)
  │           ├── ParagraphChunk L2-C
  │           └── ParagraphChunk L2-D
  │
  └── TitleChunk L1' (下一个 ## 标题)
        └── ...
```

### 2.2 各层级职责

| 层级 | 类型 | 分割依据 | 核心职责 | 元数据 |
|------|------|---------|---------|--------|
| **L0** | Document | 整个文档 | 全局上下文 | doc_name, total_pages |
| **L1** | TitleChunk | `##` 二级标题 | 主题聚合、综合概念提取 | heading_path, level=1, parent_heading |
| **L2** | ParagraphChunk | 段落 / `###` 标题 | 细粒度概念提取、精确检索 | heading_path, level=2, parent_id, paragraph_index |

### 2.3 与现有系统的兼容性

```
旧格式: [{"id", "text", "metadata", "source"}]  (扁平列表)
新格式: 同上，但 metadata 增加层级字段

DocumentChunker.chunk_document(pages) 
  → 输出 parent_chunks (L1 TitleChunk) + child_chunks (L2 ParagraphChunk)
  → 与现有 pipeline 兼容
```

---

## 3. 语义聚合策略

### 3.1 聚合流程

```
阶段 1: Markdown 分块
  MinerU Markdown → MarkdownChunker → 树形 chunk 结构

阶段 2: 细粒度概念提取
  每个 L2 ParagraphChunk → SemanticExtractor → 细粒度概念列表
  
  示例:
    Chunk "5.4 逆向排名融合(RRF)" → 
      Concept: "逆向排名融合"(type: method)
      Concept: "RRF"(type: abbreviation)
      Concept: "倒数排名公式"(type: formula)

阶段 3: 标题级语义聚合
  每个 L1 TitleChunk 内，收集所有子 L2 的概念:
    
    a. 去重合并（基于 embedding 相似度 > 0.85）
    b. 提取"主题概念"（基于标题文本 + 子概念综合）
    c. 建立概念层级关系:
       
       主题概念 ──[HAS_DETAIL]──→ 细节概念 A
              ──[HAS_DETAIL]──→ 细节概念 B
              ──[HAS_DETAIL]──→ 细节概念 C

阶段 4: 跨标题连接
  基于标题层级关系建立跨 TitleChunk 概念连接:
    
    TitleChunk "五、RAG-Fusion工作流程" 
      ──[CONTAINS]──→ TitleChunk "5.4 逆向排名融合(RRF)"
    
    对应概念关系:
    "RAG-Fusion工作流程" ──[DEPENDS_ON]──→ "逆向排名融合"
```

### 3.2 聚合算法

```python
def aggregate_concepts(title_chunk: TitleChunk, child_concepts: List[Concept]) -> AggregatedResult:
    """
    在单个 TitleChunk 内进行语义聚合。
    
    输入:
      - title_chunk: 标题文本 + 标题内所有段落文本
      - child_concepts: 所有子 ParagraphChunk 提取的概念列表
    
    输出:
      - theme_concepts: 主题概念列表（去重后的高层概念）
      - detail_concepts: 细节概念列表（保留的子概念）
      - relations: 主题概念 → 细节概念的关系边
    """
    
    # 1. 去重合并（基于 embedding 相似度）
    unique_concepts = deduplicate_by_embedding(child_concepts, threshold=0.85)
    
    # 2. 提取主题概念
    # 方法 A: 标题本身作为主题概念
    theme_from_title = extract_concept_from_heading(title_chunk.heading)
    
    # 方法 B: LLM 综合标题 + 子概念，生成主题概念
    theme_from_llm = llm_synthesize_theme(
        heading=title_chunk.heading,
        child_concepts=unique_concepts,
        context=title_chunk.text[:2000]
    )
    
    # 3. 建立层级关系
    relations = []
    for theme in theme_from_llm:
        for detail in unique_concepts:
            if is_subordinate(theme, detail):  # 判断从属关系
                relations.append((theme, "HAS_DETAIL", detail))
    
    return AggregatedResult(theme_concepts, unique_concepts, relations)
```

### 3.3 多层聚合（逐层向上）

```
Level 2 (ParagraphChunk):
  → 提取细粒度概念

Level 1 (TitleChunk):
  → 聚合子 ParagraphChunk 的概念
  → 提取主题概念
  → 建立主题→细节关系

Level 0 (Document):
  → 聚合所有 TitleChunk 的主题概念
  → 提取文档级核心概念
  → 建立文档→主题关系
```

---

## 4. 与概念提取流程的整合

### 4.1 当前流程

```
DocumentProcessor → Chunks → SemanticExtractor → Concepts → Deduper → Graph
```

### 4.2 新流程（MinerU 模式）

```
DocumentProcessor (MinerU)
  → MarkdownChunker → 树形 Chunks (L1 + L2)
  
  ├── 路径 A: 细粒度提取（用于检索）
  │     L2 ParagraphChunks → SemanticExtractor → 细粒度 Concepts
  │     → 存入向量库（精确匹配）
  │
  └── 路径 B: 聚合提取（用于图谱构建）
        L2 ParagraphChunks → SemanticExtractor → 细粒度 Concepts
        → SemanticAggregator (按 L1 聚合) → 主题 Concepts + 层级关系
        → ConceptDeduper → 去重合并
        → GraphBuilder → 构建层级图谱（主题→细节）
```

### 4.3 两种模式并存

```
DocumentProcessor
  │
  ├─ pdf_engine="pymupdf" (默认)
  │     → 旧流程：页级 Parent + 段落级 Child
  │     → 适用：纯文字型 PDF、快速处理
  │
  └─ pdf_engine="mineru" (高级)
        → 新流程：标题级 L1 + 段落级 L2 + 语义聚合
        → 适用：含图片/公式/表格的 PDF、需要精准结构
```

---

## 5. 实现计划

### Phase 1: MarkdownChunker（今天）
- [ ] 实现 `MarkdownChunker` 类
- [ ] 按 `##` / `###` 层级分块
- [ ] 生成标准 chunk 格式（兼容现有 pipeline）
- [ ] 单元测试

### Phase 2: SemanticAggregator（明天）
- [ ] 实现概念去重合并（embedding 相似度）
- [ ] 实现主题概念提取（LLM 综合）
- [ ] 实现层级关系建立
- [ ] 与 ConceptDeduper 整合

### Phase 3: 集成测试（后天）
- [ ] 5 个 PDF 端到端测试
- [ ] 对比 PyMuPDF / MinerU 模式的概念提取质量
- [ ] 评估语义聚合效果

---

## 6. 关键设计决策

### Q1: 聚合粒度——每级标题都聚合还是只到二级标题？

**决策**: 二级标题（`##`）作为聚合单元，三级标题（`###`）作为 ParagraphChunk 的边界。

**理由**:
- `##` 通常对应文档的主要章节（如 "5.4 逆向排名融合"）
- `###` 通常对应章节内的小节，内容不足以形成独立主题概念
- 过度聚合会导致概念层级过深，增加复杂度

### Q2: 主题概念从哪来？

**决策**: 双源提取
1. **标题本身** → 直接作为主题概念（如 "逆向排名融合"）
2. **LLM 综合** → 基于标题 + 子概念 + 上下文生成补充主题概念

**理由**:
- 标题本身是作者给出的最准确主题
- LLM 综合可以捕获标题未明确表达但内容中隐含的主题

### Q3: 层级关系怎么判断？

**决策**: 三维度判断
1. **命名包含**: 主题概念的名称是否包含细节概念的名称
2. **Embedding 相似度**: 主题概念与细节概念的向量距离
3. **LLM 判断**: 让 LLM 判断 "A 是否是 B 的从属概念"

**理由**:
- 单一维度不够准确
- 三维度投票机制提高准确率

### Q4: 与现有 ConceptDeduper 的关系？

**决策**: SemanticAggregator 在 ConceptDeduper 之前运行

```
旧: Chunks → SemanticExtractor → ConceptDeduper → Graph
新: Chunks → SemanticExtractor → SemanticAggregator → ConceptDeduper → Graph
```

**理由**:
- SemanticAggregator 解决"同标题内概念的层级关系"
- ConceptDeduper 解决"跨标题概念的合并去重"
- 两者互补，不重复

---

## 7. 预期效果

| 指标 | PyMuPDF 模式 | MinerU 模式（新） | 提升 |
|------|-------------|------------------|------|
| 标题准确率 | ~60%（启发式） | ~95%（Markdown 原生） | +58% |
| 章节 chunk 数 | 6 页级 Parent | 13-18 标题级 | 更精准 |
| 概念层级关系 | 无 | 主题→细节 | 新增 |
| 公式识别 | 无 | LaTeX 提取 | 新增 |
| 图片上下文 | 孤立 chunk | 章节内引用 | 显著改善 |
| 表格结构 | 纯文本噪音 | Markdown 表格 | 显著改善 |

---

## 8. 附录：核心数据结构

### Chunk 格式（扩展）

```python
{
    "id": "md_generic_doc_0_abc123",
    "text": "## 逆向排名融合(RRF)\n\nRRF是一种将多个搜索结果列表的排名...",
    "metadata": {
        "source": "doc.pdf",
        "subject": "generic",
        "chunk_type": "title",        # "title" | "paragraph" | "image"
        "heading_path": "五、RAG-Fusion工作流程/5.4 逆向排名融合(RRF)",
        "heading_level": 2,           # 1=##, 2=###, 3=paragraph
        "parent_id": "md_generic_doc_0_parent",  # 上级 chunk ID（L1 为空）
        "child_ids": ["..."],         # 下级 chunk IDs（L2 为空）
        "paragraph_index": 0,         # 在同标题内的段落序号
        "page_number": 5,             # 估算页码
        "image_refs": [...],          # 关联图片
        "formula_count": 1,           # 公式数量
        "table_lines": 0,             # 表格行数
        "aggregated": False,          # 是否已语义聚合
        "theme_concepts": ["..."],    # 聚合后的主题概念（仅 L1）
    },
    "source": "doc.pdf"
}
```

### AggregatedResult 格式

```python
{
    "title_chunk_id": "md_generic_doc_0_abc123",
    "theme_concepts": [
        {"name": "逆向排名融合", "type": "method", "confidence": 0.95}
    ],
    "detail_concepts": [
        {"name": "RRF", "type": "abbreviation", "confidence": 0.9},
        {"name": "倒数排名公式", "type": "formula", "confidence": 0.85}
    ],
    "relations": [
        {"from": "逆向排名融合", "type": "HAS_DETAIL", "to": "RRF"},
        {"from": "逆向排名融合", "type": "HAS_DETAIL", "to": "倒数排名公式"}
    ]
}
```
