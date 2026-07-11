# Hyper-Extract 项目分析与参考报告

> 项目: https://github.com/yifanfeng97/hyper-extract
> 本地路径: `D:\MyCS\AI\Project\hyper-extract`
> 分析日期: 2026-07-11

---

## 1. 项目概述

**Hyper-Extract** 是一个 LLM 驱动的知识提取与演进框架，核心定位是"一条命令把文档变成知识图谱"。

与 LearnAnything 的定位对比：

| 维度 | Hyper-Extract | LearnAnything |
|:---|:---|:---|
| 核心定位 | 知识提取工具（CLI + Python SDK） | 知识学习系统（RAG + 知识图谱 + 出题评测） |
| 知识结构 | 8 种（List/Set/Model/Graph/Hypergraph/Temporal/Spatial/Spatio-Temporal） | 5 层（Document → Chunk → ExtractedConcept → CanonicalConcept → 全局关系） |
| 提取引擎 | 10+（GraphRAG, LightRAG, KG-Gen, Cog-RAG 等） | 1 种（SemanticExtractor + 多范式提示词） |
| 存储方式 | 内存 + 本地序列化（JSON/pickle） | KùzuDB（图数据库）+ SQLite 向量库 |
| 增量演进 | 内置 `feed()` 方法 | 支持 `feed()` 追加 |
| 查询交互 | 语义搜索 + chat | 语义搜索 + 出题评测 + Agent 协作 |
| 可视化 | 内置 `show()`（OntoSight） | 前端 Cytoscape.js 图谱 |
| 导出 | Obsidian vault（Markdown + wikilinks） | 无 |

---

## 2. 核心架构分析

### 2.1 三层架构（Auto-Types / Methods / Templates）

```
Hyper-Extract
├── Auto-Types（数据结构层）— 定义"抽成什么"
│   ├── AutoModel: 单个结构化对象
│   ├── AutoList: 有序列表
│   ├── AutoSet: 去重集合
│   ├── AutoGraph: 二元关系图（节点+边）
│   ├── AutoHypergraph: 超图（3+ 实体关系）
│   ├── AutoTemporalGraph: 时序图
│   ├── AutoSpatialGraph: 空间图
│   └── AutoSpatioTemporalGraph: 时空图
│
├── Methods（提取方法层）— 定义"怎么抽"
│   ├── RAG-based: GraphRAG, LightRAG, Hyper-RAG, Cog-RAG...
│   └── Typical: KG-Gen, iText2KG, ATOM...
│
└── Templates（模板配置层）— 定义"抽什么"
    └── 80+ YAML presets（Finance, Legal, Medical, TCM, Industry, General）
```

**对 LearnAnything 的启示**：

我们的 "学科集合" 概念可以借鉴这个三层架构。目前 `semantic_extractor.py` 的 `PARADIGM_CONFIGS` 是硬编码在 Python 中的，可以考虑：

1. **将范式配置 YAML 化**：把 `theory`/`engineering`/`hierarchical` 的提示词和规则提取为 YAML 模板
2. **支持学科模板**：为不同学科（AI/数学/法律）定义专门的提取模板，用户可以选择而非从零配置
3. **模板化 Chunk 结构**：当前 `MarkdownChunker` 的分块策略是代码硬编码，可以模板化

### 2.2 Pydantic 类型安全

Hyper-Extract 的所有数据结构都是 Pydantic BaseModel，核心优势：

```python
# Hyper-Extract 的 Node/Edge 定义
class NodeSchema(BaseModel):
    name: str = Field(description="实体名称")
    type: str = Field(description="实体类型")
    description: str = Field(description="实体描述")

class EdgeSchema(BaseModel):
    source: str = Field(description="源实体名称")
    target: str = Field(description="目标实体名称")
    relation_type: str = Field(description="关系类型")
```

**当前 LearnAnything 的问题**：

我们的 `Chunk`、`ExtractedConcept`、`CanonicalConcept` 等数据结构目前用 `Dict[str, Any]` 传递，没有类型约束：

```python
# 当前代码
chunk = {"id": "...", "text": "...", "metadata": {...}}  # 没有类型检查
concept = {"id": "...", "name": "...", "concept_type": "..."}  # 容易拼写错误
```

**建议改进**：

```python
# 引入 Pydantic 定义
from pydantic import BaseModel, Field
from typing import List, Optional

class Chunk(BaseModel):
    id: str
    text: str
    metadata: ChunkMetadata
    source: str

class ChunkMetadata(BaseModel):
    chunk_type: str = Field(..., pattern="^(heading|paragraph|document|image_pseudo)$")
    heading_path: str = ""
    heading_level: int = Field(..., ge=0, le=6)
    media_refs: List[MediaRef] = []
    
class MediaRef(BaseModel):
    type: str = Field(..., pattern="^(image|formula|table)$")
    path: str
    description: str = ""
```

### 2.3 两阶段提取策略（Nodes First → Edges with Context）

Hyper-Extract 的 `AutoGraph` 支持两种提取模式：

```python
# one_stage: 一次 LLM 调用提取所有节点和边（快但可能 hallucination）
# two_stage: 先提取节点，再用节点列表作为上下文提取边（准但慢）
```

**two_stage 的核心优势**：
1. 第一阶段提取所有节点，建立"已知实体列表"
2. 第二阶段提取边时，prompt 中注入已知实体列表，LLM 只能在这些实体之间建立关系
3. 这大幅减少了边的 hallucination（不会编造不存在的节点）

**当前 LearnAnything 的问题**：

我们的 `SemanticExtractor` 在单个 chunk 内提取概念时，没有显式区分"节点提取"和"关系提取"。概念和关系在一次 LLM 调用中完成，虽然通过严格的 JSON schema 约束了输出格式，但缺乏"已知实体列表"的上下文控制。

**建议改进**：

在 `semantic_extractor.py` 中引入两阶段提取（可选）：

```python
class SemanticExtractor:
    def extract_concepts_two_stage(self, text: str, media_context: List = None):
        # Stage 1: 提取所有概念（节点）
        nodes = self._extract_nodes(text, media_context)
        
        # Stage 2: 提取关系（边），注入已知节点列表
        edges = self._extract_edges(text, known_nodes=[n["name"] for n in nodes])
        
        # 合并为统一格式
        return self._merge_nodes_edges(nodes, edges)
```

### 2.4 OMem 去重框架

Hyper-Extract 的去重依赖 **OMem**（OntoMem）库，核心设计：

```python
# OMem 去重策略
MergeStrategy.KEEP_EXISTING    # 保留已有，丢弃新数据
MergeStrategy.LLM.BALANCED     # LLM 智能合并（平衡策略）
MergeStrategy.LLM.CONSERVATIVE # LLM 保守合并（保留更多信息）
MergeStrategy.LLM.AGGRESSIVE   # LLM 激进合并（尽可能合并）
```

OMem 的合并策略基于 embedding 相似度 + LLM 判断，这比我们的纯 embedding 相似度合并更智能。

**当前 LearnAnything 的问题**：

我们的 `ConceptDeduper` 使用固定的 embedding 相似度阈值（0.85），没有区分"保守/激进"策略。对于不同学科（如数学概念需要精确匹配，文学概念可以模糊匹配），固定阈值可能不够灵活。

**建议改进**：

引入可配置的去重策略：

```python
class DedupStrategy(Enum):
    EXACT = "exact"           # 名称完全匹配（数学/法律概念）
    CONSERVATIVE = 0.90       # 高阈值，少合并
    BALANCED = 0.85          # 当前默认值
    AGGRESSIVE = 0.75        # 低阈值，多合并（文学/社科）
```

### 2.5 YAML 模板系统

Hyper-Extract 的模板定义：

```yaml
# 示例: general/graph 模板
language: en
name: Knowledge Graph
type: graph
tags: [general]
description: 'Extract entities and their relationships.'
output:
  entities:
    fields:
    - name: name
      type: str
    - name: type
      type: str
  relations:
    fields:
    - name: source
      type: str
    - name: target
      type: str
    - name: type
      type: str
identifiers:
  entity_id: name
  relation_id: '{source}|{type}|{target}'
```

**对 LearnAnything 的启示**：

我们的 `semantic_extractor.py` 中的 `PARADIGM_CONFIGS` 可以 YAML 化：

```yaml
# ai_llm.yaml — AI 学科提取模板
name: AI 大模型
subject: ai_llm
paradigms:
  engineering:
    levels: [requirement, technology, sub_requirement, sub_technology]
    transitions:
      requirement -> technology: SOLUTION
      technology -> sub_requirement: DEPENDS_ON
    prompt: |
      你是一名技术文档分析专家...
  theory:
    levels: [definition, law, application, extension]
    ...
```

### 2.6 增量演进（Incremental Evolution）

Hyper-Extract 的 `feed()` 方法：

```python
# 已提取的知识可以追加新文档
ka = Template.create("general/graph")
result = ka.parse(text1)      # 第一次提取
result = ka.feed(result, text2)  # 追加新文档，增量合并
```

**当前 LearnAnything 的问题**：

我们的 `feed()` 方法实现了追加，但增量去重可能不够完善。Hyper-Extract 的 OMem 框架专门处理增量合并（新节点与已有节点去重、新边与已有边去重）。

**建议改进**：

1. 增量去重时，新提取的节点需要先与已有节点进行 embedding 相似度比较
2. 已有节点的 embedding 应该缓存，避免重复计算
3. 增量边提取时，需要考虑已有边的覆盖/合并策略

---

## 3. 对 LearnAnything 的具体建议

### 3.1 高优先级（值得尽快实现）

| 建议 | 说明 | 预计工时 |
|:---|:---|:---:|
| **Pydantic 类型定义** | 将 Chunk/Concept/Edge 等核心数据结构从 Dict 改为 Pydantic BaseModel | 1-2 天 |
| **YAML 范式配置** | 将 `PARADIGM_CONFIGS` 硬编码改为 YAML 模板文件，支持学科级配置 | 半天 |
| **两阶段提取** | SemanticExtractor 支持 nodes-first → edges-with-context 模式（可选开关） | 1 天 |
| **增量去重缓存** | feed() 时缓存已有节点的 embedding，避免重复计算 | 半天 |

### 3.2 中优先级（有价值，可后续）

| 建议 | 说明 | 预计工时 |
|:---|:---|:---:|
| **学科 YAML 模板** | 为 AI/数学/法律等学科提供专门的提取模板 | 2-3 天 |
| **去重策略配置** | 支持保守/平衡/激进三种去重策略，按学科配置 | 半天 |
| **Obsidian 导出** | 将 CanonicalConcept 导出为 Markdown notes + wikilinks | 1 天 |
| **超图支持** | 支持 3+ 实体参与的复杂关系（Hypergraph） | 2-3 天 |

### 3.3 低优先级（观察后决定）

| 建议 | 说明 | 备注 |
|:---|:---|:---|
| 多种提取引擎 | 引入 GraphRAG, KG-Gen 等引擎 | 当前 SemanticExtractor 已满足需求，暂不优先 |
| MCP Server | 给 Agent 查询知识抽象 | 当前已有知识库 API，暂不优先 |
| 时序/空间图 | 支持时间/空间维度的知识图谱 | 当前场景暂不需要 |

---

## 4. 代码参考（可借鉴的具体实现）

### 4.1 两阶段提取的 prompt 设计

```python
# Hyper-Extract 的 edge extraction prompt（注入 known_nodes）
EDGE_PROMPT = """
Extract relationships between the provided entities.

CRITICAL RULES:
1. ONLY extract edges connecting entities from the known list
2. DO NOT invent new entities not in the list
3. Focus on explicit relationships in the text

# Provided Entities
{known_nodes}

# Source Text:
{source_text}
"""
```

### 4.2 节点去重的 SemHash 实现

```python
from semhash import SemHash

# 使用 SemHash 进行自去重
semhash = SemHash.from_records(
    embeddings=embeddings,
    records=node_names,
)
result = semhash.self_deduplicate(threshold=0.9)

# 去重映射
mapping = {}
for record in result.filtered:
    if record.duplicates:
        mapping[record.record] = record.duplicates[0][0]
```

### 4.3 Obsidian 导出

```python
# Hyper-Extract 的 Obsidian 导出将每个节点变为 Markdown 笔记
# 边变为 wikilinks: [[目标节点]]

# 示例输出：
# Transformer.md
# ---
# type: definition
# description: 基于自注意力机制的深度学习架构
# ---
# 
# 相关概念：
# - [[自注意力机制]]
# - [[多头注意力层]]
```

---

## 5. 总结

**Hyper-Extract 是一个优秀的知识提取工具，但在"学习系统"（出题评测、Agent 协作）方面不如 LearnAnything 完整。**

**最值得借鉴的三点**：

1. **Pydantic 类型安全** — 将核心数据结构从 Dict 改为 BaseModel，提升代码健壮性
2. **YAML 模板系统** — 将范式配置从代码硬编码改为可配置模板，支持学科扩展
3. **两阶段提取** — 引入 nodes-first → edges-with-context 模式，减少 hallucination

**建议优先级**：先实现 Pydantic 类型定义（这是代码质量的基础），然后 YAML 模板化，最后两阶段提取。

---

*报告完成。Hyper-Extract 本地副本位于 `D:\MyCS\AI\Project\hyper-extract\`，可直接参考。*
