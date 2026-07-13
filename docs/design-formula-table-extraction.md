# LA-035-P17: 公式与表格提取增强技术方案

## 1. 问题背景

当前 LearnAnything 的 MinerU → Markdown → Chunk 流程中，图片已完整接入 VLM 描述和前端展示。但 MinerU 同时提取的 **公式** 和 **表格** 尚未被充分利用：

- 公式：MinerU 输出为 `$$...$$` 或 `$...$` 的 LaTeX 标记，当前作为普通文本段落处理
- 表格：MinerU 输出为 Markdown 表格（`| col1 | col2 |`），当前作为普通文本段落处理

这导致：
1. 公式和表格的语义信息丢失（无法提取为独立概念）
2. 前端无法展示公式（LaTeX 渲染）和表格（结构化展示）
3. 公式和表格与关联文本的语义连接断裂

## 2. 目标

1. **公式提取**：MinerU 的 LaTeX 公式 → 独立 chunk → VLM 生成自然语言描述 → 可提取概念
2. **表格提取**：MinerU 的 Markdown 表格 → 独立 chunk → VLM 生成结构描述 → 可提取概念
3. **前端展示**：公式节点显示 LaTeX 渲染预览，表格节点显示表格结构预览
4. **语义连接**：公式/表格与其解释文本建立明确的 HAS_DETAIL / EXPLAINS 关系

## 3. 技术方案

### 3.1 MinerU 输出格式分析

MinerU 对公式和表格的 Markdown 输出示例：

```markdown
## 注意力机制

注意力机制的核心公式如下：

$$Attention(Q, K, V) = softmax(\frac{QK^T}{\sqrt{d_k}})V$$

其中，$Q$、$K$、$V$ 分别代表查询、键和值矩阵。

| 模型 | 参数量 | 训练数据 | 准确率 |
|------|--------|----------|--------|
| BERT | 110M | BookCorpus | 84.6% |
| GPT-3 | 175B | CommonCrawl | 76.2% |
| T5 | 11B | C4 | 89.7% |

从上表可以看出，模型规模与准确率呈正相关。
```

### 3.2 Chunk 类型扩展

在 MarkdownChunker 中新增两种 chunk 类型：

| 类型 | 来源 | 说明 |
|:---|:---|:---|
| `formula` | MinerU 提取的 `$$...$$` 或 `$...$` | 独立公式块 |
| `table` | MinerU 提取的 Markdown 表格 | 独立表格块 |

**Chunk 数据结构：**

```python
# Formula Chunk
{
    "id": "formula_001",
    "text": "$$Attention(Q, K, V) = softmax(\\frac{QK^T}{\\sqrt{d_k}})V$$",
    "metadata": {
        "chunk_type": "formula",
        "source": "test.pdf",
        "heading_path": "注意力机制",
        "formula_type": "display",  # display ($$) or inline ($)
        "formula_latex": "Attention(Q, K, V) = softmax(\\frac{QK^T}{\\sqrt{d_k}})V",
        "media_refs": [
            {
                "type": "formula",
                "latex": "Attention(Q, K, V) = softmax(\\frac{QK^T}{\\sqrt{d_k}})V",
                "description": "缩放点积注意力公式"
            }
        ]
    }
}

# Table Chunk
{
    "id": "table_001",
    "text": "| 模型 | 参数量 | 训练数据 | 准确率 |\\n|------|--------|----------|--------|\\n| BERT | 110M | BookCorpus | 84.6% |",
    "metadata": {
        "chunk_type": "table",
        "source": "test.pdf",
        "heading_path": "注意力机制",
        "table_headers": ["模型", "参数量", "训练数据", "准确率"],
        "table_rows": 3,
        "media_refs": [
            {
                "type": "table",
                "headers": ["模型", "参数量", "训练数据", "准确率"],
                "data": [
                    ["BERT", "110M", "BookCorpus", "84.6%"],
                    ["GPT-3", "175B", "CommonCrawl", "76.2%"],
                    ["T5", "11B", "C4", "89.7%"]
                ],
                "description": "不同语言模型的规模与准确率对比"
            }
        ]
    }
}
```

### 3.3 MarkdownChunker 修改

在 `_split_to_paragraphs` 中，公式和表格的提取逻辑：

```python
def _extract_formulas_and_tables(self, content: str) -> Tuple[str, List[Dict], List[Dict]]:
    """
    从 Markdown 内容中提取公式和表格，返回剩余文本 + 公式列表 + 表格列表。
    
    公式模式：
    - 行间公式：$$...$$（独立行）
    - 行内公式：$...$（嵌入文本中）
    
    表格模式：
    - Markdown 表格：| col1 | col2 | ... |
    """
    formulas = []
    tables = []
    
    # 1. 提取行间公式（$$...$$）
    display_pattern = r'^\$\$.*?\$\$\s*$'
    
    # 2. 提取表格
    table_pattern = r'^\|.*\|(?:\n\|[-:]+\|)?(?:\n\|.*\|)*'
    
    # ... 实现逻辑
    
    return remaining_text, formulas, tables
```

### 3.4 VLM 描述生成

公式和表格也需要 VLM 描述（但描述方式不同）：

**Formula 描述：**
- VLM 任务："描述这个公式的数学含义"
- 输出：自然语言描述（如"缩放点积注意力公式，用于计算查询与键之间的相似度"）
- 描述文本注入到 `chunk["text"]` 中，用于概念提取

**Table 描述：**
- VLM 任务："描述这个表格的内容和结构"
- 输出：表格摘要（如"不同语言模型的参数量、训练数据源和准确率对比"）
- 描述文本注入到 `chunk["text"]` 中，用于概念提取

### 3.5 GraphStore Schema 扩展

Chunk 节点新增字段：

```cypher
CREATE NODE TABLE Chunk (
    chunk_id STRING PRIMARY KEY,
    text STRING,
    heading_path STRING,
    source STRING,
    page_number INT64,
    chunk_type STRING,           -- 新增: formula | table
    image_path STRING,
    thumbnail_path STRING,
    width INT64,
    height INT64,
    media_refs STRING,           -- JSON 数组
    formula_latex STRING,        -- 新增: 公式 LaTeX 源码
    table_headers STRING,        -- 新增: JSON 数组
    table_rows INT64,            -- 新增
    table_data STRING            -- 新增: JSON 数组
)
```

### 3.6 前端展示

#### 公式节点

```vue
<!-- FormulaNodePreview.vue -->
<template>
  <div class="formula-preview">
    <div class="formula-icon">📐</div>
    <div class="formula-latex" v-html="renderedLatex"></div>
    <div class="formula-description">{{ description }}</div>
  </div>
</template>
```

使用 MathJax 或 KaTeX 渲染 LaTeX。

#### 表格节点

```vue
<!-- TableNodePreview.vue -->
<template>
  <div class="table-preview">
    <div class="table-icon">📊</div>
    <table>
      <thead>
        <tr><th v-for="h in headers">{{ h }}</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in data"><td v-for="cell in row">{{ cell }}</td></tr>
      </tbody>
    </table>
  </div>
</template>
```

### 3.7 语义连接策略

公式/表格与其解释文本的连接：

```
ParagraphChunk: "注意力机制的核心公式如下..."
    ↓ EXPLAINS
FormulaChunk: "$$Attention(Q,K,V)...$$"
    ↓ HAS_DETAIL
ParagraphChunk: "其中，Q、K、V 分别代表..."
```

连接建立方式：
1. **位置相邻**：公式/表格前后的段落自动建立连接
2. **文本引用**：段落文本中出现"公式X""表X"等引用时建立连接
3. **SemanticLinker**：LLM 判断公式/表格与段落之间的语义关系

## 4. 实现步骤

### Phase 1: 后端（MarkdownChunker + GraphStore）

1. [ ] 修改 `MarkdownChunker._split_to_paragraphs`：识别公式和表格标记
2. [ ] 新增 `FormulaChunk` 和 `TableChunk` 的生成逻辑
3. [ ] 修改 `GraphStore` Schema：新增 `formula_latex`、`table_headers` 等字段
4. [ ] 修改 `GraphStore.add_chunk_nodes`：处理公式/表格的 media_refs
5. [ ] 修改 `VLMClient`：支持公式/表格描述任务

### Phase 2: 后端（SemanticExtractor + GraphBuilder）

6. [ ] 修改 `SemanticExtractor`：公式/表格 chunk 也能提取概念
7. [ ] 修改 `SemanticLinker`：支持公式/表格与文本的连接类型

### Phase 3: 前端

8. [ ] 新增 `FormulaNodePreview.vue`（LaTeX 渲染）
9. [ ] 新增 `TableNodePreview.vue`（表格渲染）
10. [ ] 修改 `NodeDetailPanel.vue`：公式/表格的特殊展示
11. [ ] 修改 `GraphNodeTooltip.vue`：悬浮预览公式/表格
12. [ ] 引入 MathJax/KaTeX 依赖

### Phase 4: 测试

13. [ ] 使用公式密集型 PDF 测试
14. [ ] 使用表格密集型 PDF 测试

## 5. 风险与注意事项

| 风险 | 影响 | 缓解方案 |
|:---|:---|:---|
| LaTeX 渲染性能 | 大量公式节点时前端卡顿 | 懒加载，只渲染可视范围内的公式 |
| MinerU 公式提取质量 | 复杂公式可能提取错误 | 保留原始图片作为 fallback |
| VLM 公式描述准确性 | 数学公式描述可能不准确 | 结合 LaTeX 源码辅助判断 |
| 表格过大 | 表格数据量过大影响存储 | 限制表格行数（如最多 50 行） |

## 6. 测试需求

需要开发者提供以下测试文档：

| 类型 | 特征 | 示例 |
|:---|:---|:---|
| **公式密集型** | 大量数学公式（LaTeX） | 数学教材、机器学习论文、物理教材 |
| **表格密集型** | 大量数据表格 | 财务报表、实验数据表、对比表格 |
| **混合类型** | 既有公式又有表格 | 学术论文、技术文档 |

## 7. 与现有架构的兼容性

| 现有模块 | 兼容性 | 修改范围 |
|:---|:---:|:---|
| MarkdownChunker v2.1 | ✅ | 新增公式/表格提取逻辑 |
| GraphStore (四层层模型) | ✅ | Schema 新增字段，向后兼容 |
| SemanticExtractor | ✅ | 公式/表格作为可提取 chunk |
| ConceptDeduper | ✅ | 无修改 |
| SemanticLinker | ✅ | 新增连接类型 |
| 前端 GraphView | ✅ | 新增节点类型渲染 |
| media_refs 传递链 | ✅ | 扩展公式/表格类型 |

## 8. 总结

本方案将公式和表格从"普通文本段落"提升为"一等公民 chunk"，与图片 chunk 同级处理：

- **提取**：MinerU 识别 → 独立 chunk
- **描述**：VLM 生成自然语言描述
- **概念**：可提取为独立概念
- **展示**：前端专用渲染（LaTeX/表格）
- **连接**：与解释文本建立语义连接

**核心改动范围**：MarkdownChunker + GraphStore Schema + VLMClient + 前端渲染组件

**预计工作量**：后端 2-3 天，前端 2-3 天，测试 1-2 天
