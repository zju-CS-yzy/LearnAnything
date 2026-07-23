# LearnAnything 设计文档

> 版本: 1.0  
> 创建日期: 2026-07-05  
> 项目路径: `D:\MyCS\AI\Project\LearnAnything\`  
> 定位: AI驱动的通用知识学习系统，支持任意学科的RAG知识库+知识图谱+Agent协作

---

## 目录

1. [项目简要说明](#1-项目简要说明)
2. [目标效果](#2-目标效果)
3. [知识图谱构建思想](#3-知识图谱构建思想)
4. [数据模型](#4-数据模型)
5. [技术栈与架构](#5-技术栈与架构)
6. [各模块实现方式](#6-各模块实现方式)
7. [数据流](#7-数据流)
8. [前端架构](#8-前端架构)
9. [部署与打包](#9-部署与打包)
10. [已知问题与限制](#10-已知问题与限制)

---

## 相关设计文档

| 文档 | 说明 | 创建日期 |
|:---|:---|:---|
| [docs/DESIGN.md](DESIGN.md) | 本文件：总体设计文档 | 2026-07-05 |
| [docs/data-model-v2.md](data-model-v2.md) | 四层数据模型设计（v2.0）：ExtractedConcept + CanonicalConcept 分层 | 2026-07-07 |
| [docs/concept-view-layout.md](concept-view-layout.md) | 概念视图布局设计：DAG 分树 + 副本策略 + dagre 布局 | 2026-07-07 |
| [docs/design-canonicalconcept-multimedia.md](design-canonicalconcept-multimedia.md) | CanonicalConcept 多媒体展示设计 | 2026-07-11 |
| [docs/design-image-semantic-classification.md](design-image-semantic-classification.md) | 图片语义分类设计 | 2026-07-11 |
| [docs/design-markdown-chunk-semantic-aggregation.md](design-markdown-chunk-semantic-aggregation.md) | Markdown 分块语义聚合设计 | 2026-07-11 |
| [docs/leftover-problem.md](leftover-problem.md) | 遗留问题跟踪 | 持续更新 |
| [docs/effective-decisions.md](effective-decisions.md) | 有效决策记录 | 持续更新 |

---

## 1. 项目简要说明

### 1.1 背景

LearnAnything 是一个**通用知识学习系统**，从 IWork（AI大模型求职学习系统）重构而来。核心目标是让任意学科的材料（PDF、文本、图片）经过AI处理后，生成结构化的知识图谱，辅助用户高效学习。

### 1.2 核心能力

| 能力 | 说明 |
|:---|:---|
| 多格式导入 | 支持文本、Markdown、PDF（文字型/扫描件）、图片（OCR） |
| 智能分块 | 标题分块 + 语义分块，支持学科专用分块策略 |
| 混合检索 | BM25 + 向量检索 + RRF融合 + Cross-Encoder重排序 |
| 知识图谱 | 双层图谱：文档层（Chunk树）+ 概念层（语义概念网络） |
| 多Agent协作 | Tutor（讲解）、Quiz（出题）、Coach（评测）、Coordinator（协调） |
| 多范式提取 | 理论归纳 / 工程分解 / 层级归纳 三种概念提取范式 |
| 可视化 | 树形知识图谱 + 卡片化节点 + 交互式浏览 |

### 1.3 与 IWork 的区别

| 维度 | IWork | LearnAnything |
|:---|:---|:---|
| 目标用户 | 求职者 | 任意学习者 |
| 学科范围 | 固定（大模型/后端/算法） | 插件式，任意学科 |
| 文档输入 | 主要是文本 | 多格式（PDF/图片/OCR） |
| 检索 | 纯向量 | 混合检索（BM25 + 向量） |
| 图谱 | 无 | 双层知识图谱 |
| 前端 | 命令行 | Vue3 + FastAPI + 桌面应用 |

---

## 2. 目标效果

### 2.1 用户使用流程

```
导入材料 → 自动分块 → 构建文档树 → 概念提取 → 去重连接 → 可视化图谱 → 学习/问答
```

### 2.2 可视化目标

#### 文档层（Chunk Tree）
- **树形结构**：根节点（文档）→ 章节 → 段落 → 知识点
- **布局原则**：
  1. 单向的树，根节点在最左侧
  2. 同层节点在横向位置上并列
  3. 叶节点（无子节点）在最右侧，上下间隔相同
  4. 有子节点的节点，纵向位置位于所有下层节点的中部
  5. 不同树共享子节点时，复制子节点到各自的树中
- **效果参考**：类似 Visio 灵感触发图，同层上下并列不重叠

#### 概念层（Concept Network）
- **工程分解范式**：需求节点 → SOLUTION → 技术节点 → DEPENDS_ON → 子需求节点
- **卡片化显示**：每个概念显示为UML风格卡片（标题+类型+描述）
- **层次方向**：从左到右（需求→技术→子需求）

### 2.3 学科管理目标

- 任意学科独立知识库
- 导入文件自动统计（原始资料数、知识片段数）
- 学科配置自动生成（关键词、分块策略、题型偏好）

---

## 3. 知识图谱构建思想

### 3.1 双层图谱架构

```
┌─────────────────────────────────────────────────────┐
│                  概念层（Concept Layer）              │
│  ┌──────────┐      SOLUTION       ┌──────────┐   │
│  │ 需求概念  │ ─────────────────────→│ 技术概念  │   │
│  │(req)     │                      │(tech)    │   │
│  └──────────┘                      └──────────┘   │
│       │                                  │          │
│       │ DEPENDS_ON                       │         │
│       ▼                                  ▼          │
│  ┌──────────┐                      ┌──────────┐   │
│  │ 子需求   │                      │ 子技术   │   │
│  └──────────┘                      └──────────┘   │
│  [Phase 2 生成：LLM提取 + 去重 + 语义连接]           │
├─────────────────────────────────────────────────────┤
│                  文档层（Document Layer）              │
│  ┌──────────┐   ADJACENT_TO   ┌──────────┐         │
│  │ Chunk 1  │ ───────────────→│ Chunk 2  │         │
│  │(文档A-1) │                  │(文档A-2) │         │
│  └──────────┘                  └──────────┘         │
│       │                                              │
│       │ BELONGS_TO（同heading_path层级）              │
│       ▼                                              │
│  ┌──────────┐                                       │
│  │ Chunk 3  │                                       │
│  └──────────┘                                       │
│  [Phase 1 生成：导入时自动构建]                        │
└─────────────────────────────────────────────────────┘
```

### 3.2 概念提取范式

| 范式 | 适用场景 | 提取逻辑 | 边类型 |
|:---|:---|:---|:---|
| **理论归纳** | 理论型材料（论文/教材） | 提取内在逻辑链（事实→概念→方法→评价） | 层级关系 |
| **工程分解** | 技术型材料（需求文档/设计） | 需求→技术→子需求→子技术 | SOLUTION + DEPENDS_ON |
| **层级归纳** | 通用知识（百科/综述） | 认知层次分类（基础→进阶→应用） | 层级关系 |

### 3.3 去重与连接

- **概念去重**：基于 embedding 相似度（阈值 0.85），合并相似概念
- **语义连接**：基于 parent_hint + LLM 二次确认，构建概念间关系
- **质量评估**：五维度评估（稳定性25%、覆盖度20%、忠实度20%、多样性15%、连接覆盖率20%）

---

### 3.4 RAG 架构定位与现有工作对比

#### 3.4.1 四层架构在 RAG 系统中的定位

标准 RAG 架构通常分为四个模块，我们的四层架构对应关系如下：

| 模块 | 我们的对应部分 | 说明 |
|------|-------------|------|
| **分块（Chunking）** | MarkdownChunker | 生成 document / heading / paragraph / image_pseudo chunk |
| **嵌入/索引（Embedding/Indexing）** | BM25 稀疏向量 + 智谱 GLM 密集向量 | 存储于 SQLite 向量库 |
| **知识图谱构建（KG Construction）** | ✅ **四层图架构核心** | ExtractedConcept → CanonicalConcept → 关系边 |
| **检索（Retrieval）** | 混合检索（BM25 + 向量 + 图谱遍历） | 由 HybridRetriever + ConceptRetriever 协同 |

四层架构的工作位置：**在分块和嵌入之后，检索之前**。它不是"文本分块的 Embedding 部分"，而是**独立的知识图谱构建层**，在学术界常被称为 **GraphRAG Indexing Pipeline** 或 **Knowledge Graph Construction for RAG**。

```
输入文档 → [分块] → [嵌入] → [四层图构建] → [检索]
              ↓         ↓            ↓
         Chunk节点   向量表示   ExtractedConcept
                                    ↓
                              CanonicalConcept（去重）
                                    ↓
                              关系边（语义关联）
```

#### 3.4.2 设计独特性：与现有工作的对比

**结论**：四层架构在现有文献中没有完全对应的等价设计，属于工程上的独特组合，但并非"从零发明的全新理论"。

| 架构 | 节点类型 | 层级 | 概念去重 | 最接近我们的层 | 关键差异 |
|------|---------|------|---------|------------|---------|
| **Microsoft GraphRAG** [25] | Entity | 单层实体 | 有（Entity Resolution） | 单层实体 + 社区分层 | 单层实体，合并后删除旧节点；我们保留两层概念 |
| **HippoRAG** [27] | Entity | 单层实体 | 无 | 单层实体 + PageRank | 无去重，无层级概念分离 |
| **LightRAG** [26] | Entity | 单层实体 | 无 | 单层实体 + 高低级检索 | 双级检索但实体单层；无概念去重中间层 |
| **DA-RAG** [28] | Chunk + Entity | 双层（Chunk + KG） | 无 | Chunk Layer + KG Layer | Chunk 对应我们的 Chunk，但 KG Layer 只有单层实体 |
| **RAPTOR** [29] | Summary | 树形层级 | 无（聚类摘要） | 层级树 | 节点是文本摘要而非概念；无去重机制 |
| **KET-RAG** [31] | Keyword-Entity-Triple | 三层 | 有 | 关键词→实体→三元组 | 桥接设计类似但粒度不同 |
| **StructRAG** [32] | 结构化知识 | 层次推理 | 有 | 结构保持与提取 | 侧重逻辑结构保持，非概念去重分离 |

**核心区别**：我们保留了"提取概念"（ExtractedConcept）和"规范概念"（CanonicalConcept）之间的**显式分离**。

- **Microsoft GraphRAG** [25]：提取 entity → 直接做 entity resolution → 合并为统一节点。**没有保留"原始提取"和"去重后"两个层级。**
- **DA-RAG** [28]：有 Chunk Layer 和 Knowledge Graph Layer，但 KG Layer 直接就是实体关系，没有"概念去重"的中间层。
- **RAPTOR** [29]：有层级树（document → summary → higher-level），但节点是文本摘要，不是概念。

我们的设计独特之处在于：
1. **保留提取概念层**：每个 ExtractedConcept 可精确追溯回其来源 chunk，支持溯源和局部上下文重建。
2. **独立规范概念层**：CanonicalConcept 通过 embedding 相似度去重合并，但不删除原始提取实例，而是建立映射关系。
3. **source_chunks 字段**：规范概念直接关联原始 chunk ID，实现图→chunk→原始文本的精确回溯。

> **准确表述**："我们采用了一种双层概念图谱架构：从文本 chunk 提取概念实例（ExtractedConcept），通过嵌入相似度去重合并为规范概念（CanonicalConcept），并保留原始提取实例以支持溯源。这种设计在保留概念溯源能力的同时，实现了语义去重，是对标准 GraphRAG 实体提取-消解流程的一种变体。"

---

### 3.5 层级知识图谱查询与向量检索的优势比较

#### 3.5.1 学术界的一致结论

**核心结论**：这不是"哪个更好"的问题，而是**不同场景下各自有优势，混合使用通常优于单一方法**。

| 场景 | 向量检索 (Embedding→Chunk) | 图查询 (Graph Traversal) | 胜出方 | 证据来源 |
|------|---------------------------|------------------------|--------|---------|
| **单跳事实查找** | 直接匹配语义相似文本，速度快 | 需要遍历路径，开销大 | **向量** ✅ | RAG vs GraphRAG [17] |
| **多跳推理** (如"A的妻子是谁？") | 无法发现跨 chunk 的关联 | 显式遍历关系链 A→marriedTo→B | **图** ✅ | RAG vs GraphRAG [17] |
| **实体消歧** (同名不同人) | 容易混淆语义相似但实体不同的内容 | 节点唯一标识 + 关系上下文 | **图** ✅ | GraphRAG vs Vector RAG [24] |
| **全局摘要/聚合** | 只能返回局部文本片段 | 社区检测 + 全局聚合 | **图** ✅ | Microsoft GraphRAG [25] |
| **细粒度细节检索** | 精确匹配文本内容 | 实体粒度粗，可能丢失细节 | **向量** ✅ | RAG vs GraphRAG [17] |

**关键论文证据**：

> **RAG vs. GraphRAG: A Systematic Evaluation [17]**：
> "RAG performs better on single-hop questions and those requiring fine-grained details, whereas GraphRAG is more effective for multi-hop and global summarization." 混合策略（Selection + Integration）在 MultiHop-RAG 上提升 **QA accuracy +6.4 points**。

> **AMG-RAG [20]**：GraphRAG + 医学知识图谱在 MEDQA 上达到 **73.92%**，但移除搜索功能后下降到 **67.16%**（-6.76%），说明结构化检索对复杂领域至关重要。

> **SR-RAG [18]**：在证据召回 R@10 上，GraphRAG 类方法（0.812）**显著优于**纯向量基线（0.643-0.738），但细粒度 PICOT 匹配上传统 RAG 仍有优势。

#### 3.5.2 可衡量的评估指标

从论文和业界实践中，指标分为**四个维度**：

| 维度 | 指标 | 含义 | 适用场景 |
|------|------|------|---------|
| **检索质量** | Recall@K (R@K), MRR, Accuracy@K, Nugget Coverage (NC), Context Precision, Context Recall | 评估是否找全、排序质量、端到端准确率 | 检索阶段验证 |
| **生成质量** | Faithfulness (忠实度), Answer Relevancy, Semantic Similarity (SS) | 答案是否基于检索内容、是否回答了问题、与参考答案的语义相似度 | 端到端 QA 评估 |
| **多跳能力** | 多跳准确率, 证据链完整性, 推理步骤正确性 | 需要 N 步推理的问题的正确率、检索路径是否覆盖所有必要节点 | 复杂推理任务 |
| **效率与成本** | Latency (P50/P95), Indexing Cost, Query Cost, Storage Overhead | 查询延迟、构建索引的 Token/时间成本、每次查询的 Token/计算成本、存储开销 | 工程部署 |

> **RAGAS [30]** 框架专门评估 RAG 系统：Faithfulness (0.0-1.0) 衡量生成答案是否基于检索内容且无幻觉；Answer Relevancy 评估答案与问题的相关性；Context Precision/Recall 评估检索上下文的质量。

#### 3.5.3 我们的检索策略：图优先 + 向量为辅

当前 P0 模块（ConceptRetriever）的检索策略设计：

| 策略 | 方法 | 数据层 | 是否使用 Embedding | 优势 |
|------|------|--------|-------------------|------|
| **1. 精确匹配** | `name = 'RAG'` | KùzuDB CanonicalConcept | ❌ 纯图查询 | 100% 精确，可解释性强 |
| **2. 模糊匹配** | `name CONTAINS 'RAG'` | KùzuDB CanonicalConcept | ❌ 纯图查询 | 容错性强，无需 embedding 计算 |
| **3. 别名匹配** | `aliases CONTAINS 'RAG'` | KùzuDB CanonicalConcept | ❌ 纯图查询 | 支持同义词和缩写 |
| **4. Embedding 回退** | `vector_store.query("RAG")` | HybridRetriever → 向量检索 | ✅ **唯一使用 embedding** | 发现图查询未覆盖的新关联 |

**关键设计原则**：前 3 个策略是**确定性的**（结果可预测、可解释），只有在全部失败时才触发 embedding 回退。**这与学术界推荐的"混合策略"方向一致。**

> **CatRAG [21]** 指出"Static Graph Fallacy — 固定转移概率导致语义漂移"，但我们的设计通过**保留精确匹配作为最高优先级策略**，避免了纯 embedding 检索的语义漂移风险。

> **ReMindRAG [22]** 的 LLM 引导图遍历 + 记忆回放虽然降低了 50% 查询成本，但引入了额外的 LLM 推理开销。我们的设计**不需要运行时 LLM 调用**，仅依赖图数据库查询和（可选的）向量检索，更适合低延迟场景。

#### 3.5.4 为什么不全部 Embedding 化？

**将 CanonicalConcept 全部 embedding 化并替换图查询，不会更好，反而会削弱图查询的核心优势。**

| 维度 | 当前策略（图优先 + embedding 回退） | 全部 Embedding 化 |
|------|-----------------------------------|-------------------|
| **精确匹配** | 图查询 `name = 'RAG'` → 100% 准确 | 向量相似度 → 可能返回"RAG 综述"等近似结果 |
| **同义词匹配** | 别名列表（手动/LLM 生成） | 向量天然支持语义相似 |
| **未录入概念** | embedding 回退可找到新关联 | 能发现新关联 |
| **多跳能力** | 图遍历 O(1)~O(n) 邻域遍历 | 需要多次向量查询 + 二次查询，效率低 |
| **可解释性** | 路径清晰：RAG → DEPENDS_ON → 向量检索 | 黑盒：为什么返回这个概念？ |
| **延迟** | 图查询 < 10ms | 向量检索 + 重排序 ≈ 50-200ms |

**改进方向（不替换图查询，而是增强）**：
1. **并行执行**：图查询与向量检索同时执行，结果融合
2. **embedding 增强别名**：用 embedding 预计算概念别名，扩展别名列表
3. **向量验证**：用 embedding 验证图查询结果的语义相关性（过滤伪命中）

> **Embeddings + Knowledge Graphs: The Ultimate Tools for RAG [33]** 系统论证了向量嵌入与知识图谱的**互补性**：知识图谱提供显式结构和多跳能力，向量嵌入提供语义相似性和容错能力。两者的协同是 RAG 系统的最优架构。

---

## 4. 数据模型

### 4.1 节点类型

#### Chunk 节点（文档层）

```cypher
(:Chunk {
  chunk_id: string,        // 唯一标识（文件hash+序号）
  text: string,            // 文本内容
  heading_path: string,    // 标题路径（如 "第1章 > 1.1节"）
  source: string,          // 来源文件名
  page_number: int,       // 页码
  chunk_type: string,     // 类型：parent / child / markdown
})
```

#### Concept 节点（概念层）

```cypher
(:Concept {
  id: string,              // 唯一标识（UUID）
  name: string,            // 概念名称
  concept_type: string,    // 类型：requirement / technology / sub_requirement / sub_technology / concept
  description: string,     // 描述
  parent_hint: string,     // 父概念提示（用于去重后重建连接）
  source_chunks: [string], // 来源 chunk ID 列表
})
```

### 4.2 边类型

| 边类型 | 方向 | 含义 | 生成阶段 |
|:---|:---|:---|:---|
| **ADJACENT_TO** | Chunk → Chunk | 相邻 chunk（文档顺序） | Phase 1（导入时） |
| **BELONGS_TO** | Chunk → Chunk | 同 heading_path 层级关系 | Phase 1（导入时） |
| **SOLUTION** | Concept → Concept | 需求 → 技术（解决方案） | Phase 2.5（语义连接） |
| **DEPENDS_ON** | Concept → Concept | 技术 → 子需求（实现依赖） | Phase 2.5（语义连接） |
| **REQUIRES** | Concept → Concept | 通用依赖关系 | Phase 2.5（语义连接） |

### 4.3 学科元数据

```python
Subject {
  id: str                    # 学科标识（如 "ai_llm"）
  name: str                  # 显示名称
  description: str           # 描述
  keywords: [str]           # 关键词（用于自动识别）
  created_at: datetime       # 创建时间
  document_count: int        # 知识片段总数（chunks）
  raw_files_count: int       # 原始文件数
}
```

---

## 5. 技术栈与架构

### 5.1 整体架构

```
┌────────────────────────────────────────────────────────────┐
│                        前端层（Vue3）                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ 知识图谱  │ │ 学习对话  │ │ 出题评测  │ │ 导入管理  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│                      Vite + Cytoscape.js                     │
├────────────────────────────────────────────────────────────┤
│                        API层（FastAPI）                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ 文档导入  │ │ 知识检索  │ │ 图谱构建  │ │ 问答对话  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
├────────────────────────────────────────────────────────────┤
│                        Agent层                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │Coordinator│ │ TutorAgent│ │ QuizAgent│ │ CoachAgent│     │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
├────────────────────────────────────────────────────────────┤
│                        核心引擎层                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │文档处理   │ │ 向量检索  │ │ 图数据库  │ │ LLM调用  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  PyMuPDF / PaddleOCR / ChromaDB / KùzuDB / DeepSeek API    │
├────────────────────────────────────────────────────────────┤
│                        数据层                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │向量数据库 │ │ 图数据库  │ │ 监控数据库│ │ 学科配置  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  ChromaDB      KùzuDB       SQLite        JSON + SQLite   │
└────────────────────────────────────────────────────────────┘
```

### 5.2 技术栈明细

| 层级 | 组件 | 技术 | 版本 |
|:---|:---|:---|:---|
| 前端 | 框架 | Vue 3 + Vite | 3.4+ |
| 前端 | 图谱渲染 | Cytoscape.js + cytoscape-dagre | 3.26+ |
| 前端 | UI组件 | 原生CSS（未使用组件库） | — |
| 后端 | API框架 | FastAPI | 0.110+ |
| 后端 | 进程管理 | Uvicorn | 0.27+ |
| 核心 | 文档处理 | PyMuPDF + PaddleOCR + **MinerU CLI** | — |
| 核心 | Markdown 分块 | **MarkdownChunker v2.0**（自然段 + 树形 heading 层级） | — |
| 核心 | 图片解析 | **VLM 视觉语言模型**（智谱 AI GLM-4V，图片描述生成） | — |
| 核心 | 向量检索 | ChromaDB + BM25 + RRF | 0.4+ |
| 核心 | Embedding | 智谱AI Embedding API | 2048维 |
| 核心 | 图数据库 | KùzuDB | 0.4+ |
| 核心 | LLM | DeepSeek API (Chat) + Zhipu API | — |
| 核心 | **语义聚合** | **SemanticAggregator**（Heading 层级聚合） | — |
| 核心 | 图片概念提取 | **ImageConceptExtractor** | — |
| 数据 | 学科配置 | SQLite + JSON | — |
| 数据 | 监控 | SQLite | — |
| 打包 | 桌面应用 | PyInstaller + PyQt5 | 6.0+ |

---

## 6. 各模块实现方式

### 6.1 文档处理层（`core/document_processor.py`）

```python
# 处理流程
process_file(path) → 格式检测 → 内容提取 → 分块 → 返回 chunks

# 支持格式
- .txt / .md: 直接读取，标题分块
- .pdf（文字型）: PyMuPDF 提取文字 + 页面类型检测
- .pdf（扫描件）: 逐页渲染为图片 → PaddleOCR 识别
- .png/.jpg: PaddleOCR 提取文字

# 分块策略
- 标题分块：基于 heading_path 层级结构
- 语义分块：基于段落语义完整性
- 学科专用分块：由学科配置驱动（如化学公式特殊处理）
```

### 6.2 向量检索层（`core/`）

```python
# 索引构建（导入时）
chunks → Embedding（智谱AI API）→ ChromaDB 存储

# 查询流程（运行时）
query → 查询重写 → BM25检索 + 向量检索 → RRF融合 → Cross-Encoder重排序 → TopK返回

# 核心组件
- VectorStore: ChromaDB 封装，支持多集合（按学科隔离）
- HybridRetriever: BM25 + 向量检索 + RRF
- Reranker: Cross-Encoder 交叉编码器重排序
- QueryRewriter: LLM 驱动的查询扩展重写
```

### 6.3 图数据库层（`core/graph_store.py`）

```python
# 双层存储（KùzuDB）
Chunk 层: (:Chunk)-[:ADJACENT_TO|:BELONGS_TO]->(:Chunk)
Concept 层: (:Concept)-[:SOLUTION|:DEPENDS_ON|:REQUIRES]->(:Concept)

# 关键操作
- init_schema(): 初始化 schema（Chunk + Concept + 边类型）
- add_chunk_nodes(chunks): 批量写入 chunk 节点
- build_adjacent_relations(): 构建相邻关系（按文档顺序）
- build_belongs_to_relations(): 构建层级关系（同 heading_path）
- extract_concepts(chunk_id, paradigm): 基于范式提取概念
- build_semantic_links(): 构建概念间语义连接
- dedupe_concepts(): 基于 embedding 相似度去重
```

### 6.4 概念提取层（`core/semantic_extractor.py`）

```python
# 三种范式
extract(chunk_text, paradigm="engineering"):
  # 理论归纳：提取内在逻辑链
  # 工程分解：提取需求→技术关系
  # 层级归纳：提取认知层次
  → 返回 {concepts: [{name, type, description, parent_hint}], relations: [{source, target, type}]}

# 去重器（`core/concept_deduper.py`）
dedupe(concepts):
  # 计算 embedding 相似度矩阵
  # 合并相似度 > 0.85 的概念
  # 返回 canonical_concepts + merge_map
```

### 6.5 语义连接层（`core/semantic_linker.py`）

```python
# 连接构建流程
build_links(canonical_concepts, chunks):
  # 1. 基于 parent_hint 构建初始连接
  # 2. 基于 embedding 相似度补充连接
  # 3. LLM 二次确认连接合理性
  # 4. 写入 KùzuDB（SOLUTION / DEPENDS_ON / REQUIRES）
```

### 6.6 Agent 层（`agents/`）

```python
# Coordinator（协调器）
# 职责：意图路由 + Agent 分发 + 监控贯穿

# TutorAgent（讲解）
# 输入：用户问题 + 检索结果
# 输出：结构化讲解（概念定义 + 示例 + 关联）

# QuizAgent（出题）
# 输入：学科配置 + 知识点
# 输出：动态生成的选择题/填空题

# CoachAgent（评测）
# 输入：用户答案 + 标准答案
# 输出：评分 + 能力评估报告
```

### 6.7 API 层（`app/backend_api.py`）

| 端点 | 方法 | 功能 |
|:---|:---|:---|
| `/api/health` | GET | 健康检查 |
| `/api/subjects` | GET/POST | 学科列表/创建 |
| `/api/import/text` | POST | 文本导入 |
| `/api/import/file` | POST | 文件导入（PDF/图片等） |
| `/api/knowledge-graph/{subject}/nodes` | GET | Chunk 节点列表 |
| `/api/knowledge-graph/{subject}/edges` | GET | Chunk 边列表 |
| `/api/knowledge-graph/{subject}/concepts` | GET | Concept 节点列表 |
| `/api/knowledge-graph/{subject}/concept-links` | GET | Concept 边列表 |
| `/api/knowledge-graph/{subject}/build` | POST | 构建概念层（Phase 2） |
| `/api/ask` | POST | 问答对话 |
| `/api/quiz` | POST | 出题 |
| `/api/evaluate` | POST | 评测 |

---

## 7. 数据流

### 7.1 导入流程（Phase 1）

**完整链路（PDF → Markdown → Chunk → 图片 VLM 描述 → 向量索引）：**

```
用户上传 PDF
    │
    ▼
┌──────────────────┐
│ MinerU CLI       │ 提取结构化 Markdown（标题层级、图片、公式、表格）
│ (mineru-open-api)│
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ MarkdownChunker  │ 按自然段分块 + 树形 heading 层级结构
│ v2.0             │ 生成：DocumentChunk / HeadingChunk / ParagraphChunk / image_pseudo
└──────────────────┘
    │
    ├──────────────┬──────────────┐
    ▼              ▼              ▼
┌────────┐  ┌────────────┐  ┌────────────┐
│ 文本段落 │  │ 图片 chunk  │  │ 公式/表格  │  ← 图片 → VLM 描述生成
│(Paragraph│  │(image_pseudo│  │(待提取)   │  ← 公式/表格（LA-035-P17 待优化）
│ Chunk)  │  │ Chunk)     │  │           │
└────────┘  └────────────┘  └────────────┘
    │              │              │
    ▼              ▼              ▼
┌─────────────────────────────────────┐
│  VLMClient (GLM-4V)                 │
│  - 图片 chunk → VLM 描述文本        │
│  - 描述注入 chunk.text 中            │
│  - media_refs 关联原始图片路径       │
└─────────────────────────────────────┘
    │
    ▼
┌────────┐  ┌────────────┐  ┌────────────┐
│VectorStore│  │ GraphStore │  │ SubjectManager│
│ChromaDB │  │  KùzuDB    │  │  SQLite    │
│(embedding)│  │ (chunk节点)│  │ (导入记录) │
└────────┘  └────────────┘  └────────────┘
    │              │              │
    │              ▼              │
    │         ┌────────────┐      │
    │         │ build_adjacent │  │
    │         │ build_belongs_to│ │
    │         └────────────┘      │
    │              │              │
    ▼              ▼              ▼
  向量索引      Chunk 树形结构   统计信息更新
```

### 7.2 概念提取流程（Phase 2）

```
用户选择范式（理论归纳/工程分解/层级归纳）
    │
    ▼
┌──────────────────┐
│ 按 heading_path 分组 │ 同一 heading 下的 Paragraph + image_pseudo Chunk 归为一组
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ Heading 上下文提取 │ 提取 HeadingChunk 文本作为【上下文声明】
│ (LA-035-P12)     │ 截断到 300 字符，注入到 LLM prompt
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ SemanticExtractor│ 小批量提取（系统提示词 + 上下文声明 + chunk 内容）
│ (extract_concepts_batch_v2) │
│ - 只从 ParagraphChunk 提取概念（Heading 不提取）
│ - 上下文声明帮助 LLM 理解段落语义位置
│ - 图片 chunk 携带 VLM 描述和 media_refs
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ ConceptDeduper   │ 基于 embedding 相似度去重
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ SemanticLinker   │ 构建概念间连接（SOLUTION/DEPENDS_ON）
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  GraphStore      │ 写入 KùzuDB（Concept 节点 + 语义边）
└──────────────────┘
```

### 7.3 查询流程（运行时）

```
用户问题
    │
    ▼
┌──────────────────┐
│ QueryRewriter    │ 查询重写/扩展
└──────────────────┘
    │
    ├──────────────┬──────────────┐
    ▼              ▼              ▼
┌────────┐  ┌────────────┐  ┌────────────┐
│ BM25   │  │ VectorSearch│  │ KnowledgeGraph│
│ 检索   │  │ 向量检索    │  │ 图谱检索（预留）│
└────────┘  └────────────┘  └────────────┘
    │              │              │
    └──────────────┴──────────────┘
                   │
                   ▼
            ┌────────────┐
            │ RRF融合     │
            │ k=60        │
            └────────────┘
                   │
                   ▼
            ┌────────────┐
            │ Reranker   │ Cross-Encoder 重排序
            └────────────┘
                   │
                   ▼
            ┌────────────┐
            │ LLM        │ 生成回答（DeepSeek API）
            │ (context)  │
            └────────────┘
                   │
                   ▼
              用户看到回答
```

---

## 8. 前端架构

### 8.1 技术栈

- **框架**: Vue 3（Composition API）+ Vite
- **图谱渲染**: Cytoscape.js（自定义树形布局，不使用 dagre）
- **HTTP**: 原生 fetch（无 Axios）
- **状态管理**: 原生响应式（ref/reactive），无 Pinia/Vuex

### 8.2 页面结构

```
App.vue
├── 侧边栏（学科切换 + 功能导航）
│   ├── 导入材料
│   ├── 知识库
│   ├── 学习图谱
│   └── 对话学习
│
├── 主内容区
│   ├── GraphView.vue（知识图谱）
│   │   ├── 工具栏（搜索/筛选/布局）
│   │   ├── 图谱画布（Cytoscape.js）
│   │   ├── 节点详情面板（右侧抽屉）
│   │   └── 构建配置覆盖层（范式选择）
│   │
│   ├── ChatView.vue（对话学习）
│   ├── QuizView.vue（出题评测）
│   └── ImportView.vue（导入管理）
│
└── 状态栏（节点数/边数/学科信息）
```

### 8.3 图谱布局算法

**自定义树形布局**（`runLayout()` 函数）：

```javascript
// 核心逻辑：后序遍历分配位置
// 1. 找到所有根节点（入度为0）
// 2. 复制共享子节点到各自的树
// 3. 自底向上计算子树高度（叶节点数）
// 4. 父节点 y = 所有子节点 y 范围的中点
// 5. 叶节点间隔相同（nodeGap = 60px）
// 6. 层间距固定（layerWidth = 250px）
// 7. 多棵树之间留间隙（treeGap = 120px）
```

### 8.4 节点样式

| 节点类型 | 形状 | 颜色 | 尺寸 | 标签 |
|:---|:---|:---|:---|:---|
| Chunk | 椭圆 | `#3498db` | 28×28 | 标题（前30字符） |
| 副本 | 椭圆（虚线边框） | `#e74c3c` | 28×28 | 标题 |
| Concept（需求） | 圆角矩形 | `#e74c3c` | 160×60 | 卡片标签（标题+类型+描述） |
| Concept（技术） | 圆角矩形 | `#3498db` | 160×60 | 卡片标签 |
| Concept（通用） | 圆角矩形 | `#2ecc71` | 160×60 | 卡片标签 |

---

## 9. 部署与打包

### 9.1 开发模式

```bash
# 后端
python -m app.backend_api

# 前端（dev server）
cd web-vue && npm run dev
```

### 9.2 生产模式

```bash
# 前端构建（输出到 web/dist/）
cd web-vue && npm run build

# 后端启动（静态文件服务）
python -m app.backend_api
```

### 9.3 桌面应用打包（PyInstaller）

```bash
# 打包为单文件 exe
python build.py
# 输出：dist/LearnAnything.exe
```

### 9.4 数据目录结构

```
~/.learnanything/
├── subjects.db              # 学科元数据（SQLite）
├── quiz_bank.db             # 题库
├── sessions.db              # 聊天会话
└── knowledge_base/
    ├── <subject_id>/
    │   ├── raw/             # 原始文件
    │   ├── visual/          # 可视化数据
    │   └── meta.json        # 学科配置
    ├── vector_db/           # ChromaDB 数据
    ├── graph_db/            # KùzuDB 数据
    └── cache/               # 缓存（BM25索引、查询缓存等）
```

---

## 10. 已知问题与限制

### 10.1 高优先级（影响核心功能）

| # | 问题 | 影响 | 状态 |
|:---|:---|:---|:---:|
| LA-020 | 贝塞尔曲线端点不精确 | 概念层边渲染效果 | 🟡 |
| LA-021 | 树形布局共享子节点处理 | 文档层布局 | ✅ |
| LA-024 | PowerShell 执行策略限制 | 构建脚本无法执行 | 🟡 |
| — | 导入后未自动写入 KùzuDB | 新学科图谱为空 | ✅ |
| — | `raw_files_count` 统计未更新 | 导入统计显示为0 | ✅ |
| — | 前端样式错误（height: 'label'）| 图谱不显示 | ✅ |

### 10.2 中优先级（影响体验）

| # | 问题 | 影响 |
|:---|:---|:---|
| — | 后端进程在 exec 环境不稳定 | 后台服务管理 |
| — | 概念层 zoom 范围过大 | 节点显示不清晰 |
| — | 缺少设计文档 | 上下文丢失风险 |
| LA-001 | HeadhunterAgent 未接入职位数据源 | 职位推荐不可用 |

### 10.3 技术限制

| 限制 | 说明 | 缓解方案 |
|:---|:---|:---|
| KùzuDB 并发支持 | Python 客户端在 async/多线程下不稳定 | 使用 threading.Lock 保护 |
| 智谱AI Embedding API | 需要联网，有调用限额 | 缓存 embedding 结果 |
| DeepSeek API 延迟 | 概念提取（Phase 2）耗时较长 | 异步处理 + 进度反馈 |
| PyInstaller 打包 | 前端资源需要内嵌 | 静态文件复制到 _MEIPASS |
| 前端无组件库 | 所有 UI 手写，维护成本高 | 考虑引入 Element Plus |

---

## 附录

### A. 术语表

| 术语 | 含义 |
|:---|:---|
| **Chunk** | 文档分块后的文本片段，知识库的基本单元 |
| **Concept** | 从 Chunk 中提取的语义概念，知识图谱的节点 |
| **Phase 1** | 文档导入阶段：分块 → 向量化 → 构建 Chunk 树 |
| **Phase 2** | 概念提取阶段：LLM提取 → 去重 → 语义连接 |
| **范式** | 概念提取的策略：理论归纳 / 工程分解 / 层级归纳 |
| **SOLUTION** | 需求 → 技术的解决关系边 |
| **DEPENDS_ON** | 技术 → 子需求的实现依赖边 |
| **RRF** | Reciprocal Rank Fusion，检索结果融合算法 |
| **MMR** | Maximal Marginal Relevance，多样性重排算法 |

### B. 文件索引

| 文件 | 说明 |
|:---|:---|
| `config/settings.py` | 全局配置 |
| `core/document_processor.py` | 文档处理 |
| `core/vector_store.py` | 向量数据库封装 |
| `core/graph_store.py` | KùzuDB 图数据库封装 |
| `core/semantic_extractor.py` | 概念提取（LLM） |
| `core/concept_deduper.py` | 概念去重 |
| `core/semantic_linker.py` | 语义连接构建 |
| `agents/coordinator.py` | Agent 协调器 |
| `app/backend_api.py` | FastAPI 后端 |
| `web-vue/src/components/GraphView.vue` | 知识图谱可视化 |
| `docs/data-model-v2.md` | 四层数据模型设计（v2.0） |
| `docs/concept-view-layout.md` | 概念视图布局设计 |
| `docs/design-canonicalconcept-multimedia.md` | CanonicalConcept 多媒体展示设计 |
| `docs/design-image-semantic-classification.md` | 图片语义分类设计 |
| `docs/design-markdown-chunk-semantic-aggregation.md` | Markdown 分块语义聚合设计 |
| `docs/leftover-problem.md` | 遗留问题跟踪 |
| `docs/effective-decisions.md` | 有效决策记录 |

---

---

## 11. 扩展性设计

### 11.1 新学科接入

#### 自动接入流程

```
用户导入材料
    │
    ▼
┌──────────────────┐
│ SubjectAnalyzer  │ 自动分析材料内容
│ (LLM + 统计)     │ 提取关键词、识别学科类型
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ 自动生成配置     │ 生成 <subject_id>.json
│                  │ 含分块策略、题型偏好、示例问题
└──────────────────┘
    │
    ▼
  新学科可用
```

#### 学科配置模板（`subjects/<subject_id>.json`）

```json
{
  "id": "chemistry",
  "name": "化学",
  "keywords": ["化学键", "分子", "反应", "元素"],
  "chunking": {
    "strategy": "heading_semantic",
    "formula_handling": "preserve",
    "special_sections": ["实验步骤", "化学方程式"]
  },
  "quiz": {
    "preferred_types": ["multiple_choice", "fill_blank"],
    "difficulty_distribution": [0.3, 0.5, 0.2]
  },
  "extraction_paradigm": "theoretical"
}
```

#### 学科隔离机制

| 层级 | 隔离方式 | 说明 |
|:---|:---|:---|
| 向量数据库 | 按学科分集合 | `VectorStore("<subject>_v1")` 独立集合 |
| 图数据库 | 按学科分实例 | `GraphStore("<subject>_v1")` 独立 KùzuDB |
| 原始文件 | 按学科分文件夹 | `knowledge_base/<subject_id>/raw/` |
| 缓存 | 按学科分索引 | `bm25_<subject>_v1.pkl` |
| 监控 | 按学科分表 | 同一张 SQLite 表，subject_id 字段区分 |

### 11.2 新 Agent 开发

#### Agent 接口规范

```python
class BaseAgent(ABC):
    """所有 Agent 必须实现的接口"""
    
    @abstractmethod
    def can_handle(self, intent: str) -> bool:
        """判断是否能处理该意图"""
        pass
    
    @abstractmethod
    async def process(self, query: str, context: dict) -> dict:
        """处理请求，返回结构化结果"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称"""
        pass
```

#### 注册新 Agent

```python
# 在 agents/coordinator.py 中注册
from agents.new_agent import NewAgent

AGENT_REGISTRY = [
    TutorAgent(),
    QuizAgent(),
    CoachAgent(),
    NewAgent(),  # 新增 Agent
]
```

#### 意图路由扩展

```python
# 在 coordinator.py 中添加新的意图匹配规则
INTENT_PATTERNS = {
    "tutor": ["讲解", "解释", "什么是", "为什么"],
    "quiz": ["出题", "测试", "quiz", "题目"],
    "coach": ["评测", "评估", "能力", "分数"],
    "new": ["新关键词1", "新关键词2"],  # 新增
}
```

### 11.3 前端插件机制

#### 视图组件扩展

```javascript
// 新增视图页面：在 views/ 目录下创建 NewView.vue
// 在 App.vue 的侧边栏导航中添加菜单项
const menuItems = [
  { name: '知识图谱', component: GraphView, icon: 'graph' },
  { name: '对话学习', component: ChatView, icon: 'chat' },
  { name: '出题评测', component: QuizView, icon: 'quiz' },
  { name: '新功能', component: NewView, icon: 'new' },  // 新增
]
```

#### 图谱渲染扩展

```javascript
// 在 GraphView.vue 的 style 配置中添加新节点/边样式
const newNodeStyle = {
  selector: 'node[type="new_type"]',
  style: {
    'background-color': '#9b59b6',
    'shape': 'hexagon',
  }
}
```

### 11.4 后端 API 扩展

```python
# 在 app/backend_api.py 中添加新端点
@app.post("/api/new-feature")
async def new_feature(request: NewRequest):
    """新功能端点"""
    return {"result": "ok"}
```

### 11.5 扩展性评估

| 扩展方向 | 当前状态 | 难度 | 建议 |
|:---|:---|:---:|:---|
| 新学科 | 自动分析+手动微调 | 低 | 已支持，只需导入材料 |
| 新 Agent | 需实现接口+注册 | 中 | 遵循 BaseAgent 规范 |
| 新前端视图 | 新增 Vue 组件 | 低 | 遵循现有组件结构 |
| 新节点/边类型 | 修改 KùzuDB schema | 中 | 需重新初始化 schema |
| 新数据源 | 实现 DocumentProcessor 子类 | 中 | 继承 BaseProcessor |
| 新 Embedding | 修改 ApiEmbeddingClient | 低 | 仅替换 API 调用 |

---

## 12. 测试策略

### 12.1 测试金字塔

```
        ┌─────────┐
        │ E2E测试 │  < 5%（关键用户流程）
        │(浏览器) │
       ┌┴─────────┴┐
       │ 集成测试   │  ~15%（API + 数据库 + 外部服务）
       │(TestClient)│
      ┌┴─────────────┴┐
      │   单元测试      │  ~80%（核心算法、工具函数）
      │  (pytest)       │
      └─────────────────┘
```

### 12.2 单元测试（`tests/`）

#### 已覆盖模块

| 模块 | 测试文件 | 覆盖率 | 说明 |
|:---|:---|:---:|:---|
| DocumentProcessor | `test_document_processor.py` | ~60% | 文本/Markdown/PDF 处理 |
| SubjectAnalyzer | `test_subject_analyzer.py` | ~50% | 学科配置生成 |
| VectorStore | ❌ | 0% | 未测试 |
| GraphStore | ❌ | 0% | 未测试 |
| SemanticExtractor | ❌ | 0% | 未测试 |
| ConceptDeduper | ❌ | 0% | 未测试 |
| SemanticLinker | ❌ | 0% | 未测试 |
| Agents | ❌ | 0% | 未测试 |
| API | ❌ | 0% | 未测试 |

#### 待补充测试清单

```python
# tests/test_graph_store.py
class TestGraphStore:
    """KùzuDB 操作测试"""
    
    def test_init_schema(self):
        """Schema 初始化后应包含 Chunk 和 Concept 节点"""
        pass
    
    def test_add_chunk_nodes(self):
        """添加 chunk 后应能查询到"""
        pass
    
    def test_build_adjacent_relations(self):
        """相邻关系应按文档顺序建立"""
        pass
    
    def test_thread_safety(self):
        """多线程并发操作不应崩溃"""
        pass

# tests/test_semantic_extractor.py
class TestSemanticExtractor:
    """概念提取测试"""
    
    def test_extract_requirements(self):
        """工程分解范式应提取需求节点"""
        pass
    
    def test_extract_technologies(self):
        """工程分解范式应提取技术节点"""
        pass

# tests/test_concept_deduper.py
class TestConceptDeduper:
    """概念去重测试"""
    
    def test_merge_similar(self):
        """相似度 > 0.85 的概念应合并"""
        pass
    
    def test_keep_distinct(self):
        """相似度 < 0.5 的概念应保留独立"""
        pass
```

### 12.3 集成测试

#### API 端点测试（FastAPI TestClient）

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from app.backend_api import app

client = TestClient(app)

class TestImportAPI:
    def test_import_text(self):
        response = client.post("/api/import/text", json={
            "subject": "test",
            "text": "测试内容",
            "source_name": "test.txt"
        })
        assert response.status_code == 200
        assert response.json()["chunks_added"] > 0
    
    def test_import_pdf(self):
        # 上传 PDF 文件
        pass
    
    def test_graph_nodes_after_import(self):
        # 导入后应能查询到节点
        pass

class TestGraphAPI:
    def test_list_nodes(self):
        response = client.get("/api/knowledge-graph/test/nodes")
        assert response.status_code == 200
        assert "nodes" in response.json()
    
    def test_list_edges(self):
        response = client.get("/api/knowledge-graph/test/edges")
        assert response.status_code == 200
        assert "edges" in response.json()
    
    def test_build_concepts(self):
        response = client.post("/api/knowledge-graph/test/build", json={
            "paradigm": "engineering"
        })
        assert response.status_code == 200
```

#### 数据流测试

```python
class TestDataFlow:
    """端到端数据流测试"""
    
    def test_full_pipeline(self):
        """完整流程：导入 → 分块 → 向量化 → 建图 → 提取概念 → 去重 → 连接"""
        # 1. 导入测试材料
        # 2. 验证 Chunk 节点存在
        # 3. 验证向量索引存在
        # 4. 运行概念提取
        # 5. 验证 Concept 节点存在
        # 6. 验证语义边存在
        pass
```

### 12.4 E2E 测试

#### 关键用户流程

| 流程 | 步骤 | 验证点 |
|:---|:---|:---|
| **导入材料** | 选择文件 → 上传 → 等待处理 → 查看图谱 | 节点数 > 0，边数 > 0 |
| **查看图谱** | 打开图谱页 → 等待渲染 → 缩放/拖拽 | 节点可见，不重叠，可交互 |
| **提取概念** | 选择范式 → 点击提取 → 等待完成 → 查看结果 | Concept 节点出现，有语义边 |
| **问答对话** | 输入问题 → 等待回答 → 查看来源 | 回答有内容，显示引用来源 |
| **出题评测** | 选择题型 → 生成题目 → 作答 → 查看评分 | 题目生成成功，评分合理 |

### 12.5 测试环境配置

```bash
# 测试专用配置（config/settings.py 中读取环境变量）
export LEARNANYTHING_ENV=test

# 测试环境特点：
# - 使用内存数据库（不写入文件系统）
# - LLM 调用使用 mock（不消耗 API 配额）
# - 使用小数据集（快速执行）
```

### 12.6 持续集成（CI）建议

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: pip install -r requirements-test.txt
      - run: pytest tests/ --cov=core --cov=agents --cov=app
      - run: npm run build  # 前端构建检查
```

---

## 13. 数据迁移

### 13.1 Schema 版本管理

#### 当前 Schema 版本

```python
# core/graph_store.py
SCHEMA_VERSION = "1.0"  # 当前版本

# Schema 变更历史：
# v1.0 (2026-07-05): 初始版本
#   - 节点: Chunk(chunk_id, text, heading_path, source, page_number, chunk_type)
#   - 节点: Concept(id, name, concept_type, description, parent_hint, source_chunks)
#   - 边: ADJACENT_TO, BELONGS_TO, SOLUTION, DEPENDS_ON, REQUIRES
```

#### Schema 升级流程

```python
def migrate_schema(from_version: str, to_version: str):
    """
    Schema 升级函数
    
    示例：v1.0 → v1.1（添加 Concept 的 confidence 字段）
    """
    if from_version == "1.0" and to_version == "1.1":
        # 1. 备份数据
        # 2. 添加新属性
        # 3. 更新版本号
        pass
```

### 13.2 备份与恢复

#### 备份策略

| 数据类型 | 备份方式 | 频率 | 保留策略 |
|:---|:---|:---|:---|
| 向量数据库 | ChromaDB 导出 | 每日 | 保留7天 |
| 图数据库 | KùzuDB 文件复制 | 每日 | 保留7天 |
| 学科配置 | SQLite 导出 | 每次变更 | 保留全部 |
| 原始文件 | 文件系统备份 | 每次导入 | 永久保留 |
| 监控数据 | SQLite 导出 | 每周 | 保留30天 |

#### 备份脚本

```python
# scripts/backup.py
def backup_subject(subject_id: str, backup_dir: str):
    """备份单个学科的全部数据"""
    
    # 1. 备份向量数据库
    shutil.copytree(
        f"knowledge_base/vector_db/{subject_id}_v1.db",
        f"{backup_dir}/vector_db/{subject_id}_v1.db"
    )
    
    # 2. 备份图数据库
    shutil.copytree(
        f"knowledge_base/graph_db/{subject_id}_v1_graph",
        f"{backup_dir}/graph_db/{subject_id}_v1_graph"
    )
    
    # 3. 备份原始文件
    shutil.copytree(
        f"knowledge_base/{subject_id}/raw",
        f"{backup_dir}/raw/{subject_id}"
    )
    
    # 4. 备份学科配置
    shutil.copy(
        f"subjects/{subject_id}.json",
        f"{backup_dir}/config/{subject_id}.json"
    )
```

#### 恢复流程

```python
def restore_subject(subject_id: str, backup_dir: str):
    """从备份恢复单个学科"""
    # 1. 停止相关服务
    # 2. 恢复向量数据库
    # 3. 恢复图数据库
    # 4. 恢复原始文件
    # 5. 验证数据完整性
    # 6. 重启服务
```

### 13.3 学科数据迁移

#### 学科间迁移

```python
# 将学科 A 的数据复制到学科 B（用于分支/克隆）
def clone_subject(from_id: str, to_id: str):
    """克隆学科（复制全部数据，不共享）"""
    # 1. 复制向量数据库
    # 2. 复制图数据库
    # 3. 复制原始文件
    # 4. 修改配置中的 subject_id
    # 5. 注册新学科
```

#### 跨版本迁移

```python
# 系统升级时，将旧版本数据迁移到新版本格式
def migrate_subject_data(subject_id: str, old_version: str):
    """跨版本数据迁移"""
    
    if old_version == "0.9":
        # v0.9 → v1.0 的变更：
        # - Chunk 节点新增 chunk_type 字段
        # - Concept 节点新增 source_chunks 字段
        
        # 1. 读取旧数据
        # 2. 转换格式
        # 3. 写入新格式
        # 4. 验证
        pass
```

### 13.4 数据导出/导入

#### 标准导出格式

```json
{
  "version": "1.0",
  "subject": {
    "id": "ai_llm",
    "name": "AI大模型",
    "config": { ... }
  },
  "chunks": [
    {
      "id": "chunk_001",
      "text": "...",
      "heading_path": "第1章 > 1.1节",
      "source": "doc.pdf",
      "page_number": 1
    }
  ],
  "concepts": [
    {
      "id": "concept_001",
      "name": "Transformer",
      "type": "technology",
      "description": "..."
    }
  ],
  "relations": [
    {
      "source": "concept_001",
      "target": "concept_002",
      "type": "SOLUTION"
    }
  ]
}
```

#### 导出/导入接口

```python
# API 端点
@app.post("/api/subjects/{subject}/export")
def export_subject(subject: str, format: str = "json"):
    """导出学科数据"""
    pass

@app.post("/api/subjects/{subject}/import")
def import_subject_data(subject: str, file: UploadFile):
    """导入学科数据（从标准格式）"""
    pass
```

### 13.5 数据清理

```python
# 定期清理任务
def cleanup_old_data(days: int = 30):
    """清理过期数据"""
    # 1. 清理过期监控日志
    # 2. 清理过期查询缓存
    # 3. 清理已删除学科的残留数据
    # 4. 注意：不删除原始文件！
```

### 13.6 灾难恢复检查清单

```markdown
## 灾难恢复步骤

### 场景：数据库损坏
1. [ ] 停止所有写入操作
2. [ ] 从备份恢复向量数据库
3. [ ] 从备份恢复图数据库
4. [ ] 验证数据完整性（对比原始文件）
5. [ ] 重启服务

### 场景：误删除学科
1. [ ] 停止服务（防止写入冲突）
2. [ ] 从备份恢复学科数据
3. [ ] 重新注册学科（更新 subjects.db）
4. [ ] 重启服务

### 场景：Schema 不兼容升级
1. [ ] 备份全部数据
2. [ ] 运行迁移脚本
3. [ ] 验证迁移结果
4. [ ] 更新 SCHEMA_VERSION
5. [ ] 清理旧格式数据
```

---

*本文档是 LearnAnything 项目的权威设计参考，任何数据模型或架构变更都应同步更新此文档。*

---

## 14. 范式与记忆系统增强设计（2026-07-20 更新）

> 本章节整合三个增强设计：
> 1. 跨学科记忆分层（对话上下文 L0/L1/L2 架构增强）
> 2. 关系作用域映射与降级策略（tier 分级 + allow_skip_levels）
> 3. 断裂点可视化与用户协作填充（Gap + VirtualNode）

---

### 14.1 跨学科记忆分层（对话上下文增强）

#### 14.1.1 问题背景

原始对话上下文（L0 层）完全缺失，每次 Agent 调用都是独立查询。实现阶段 1 后，虽然加入了会话持久化，但出现了新问题：**跨学科对话时，RAG 的对话历史会污染 Transformer 的上下文**。

#### 14.1.2 三层记忆架构（增强版）

| 层级 | 名称 | 共享范围 | 存储位置 | 数据内容 |
|:---|:---|:---|:---|:---|
| **L0** | 对话上下文 | 学科隔离 | `dialog_messages` | 当前会话的对话历史、当前话题 |
| **L1** | Agent 集体记忆 | 学科隔离 | `dialog_sessions` + `user_knowledge_states` | 学科内薄弱点、能力评估、会话摘要 |
| **L2** | 全局知识库 | 全局共享 | `user_profiles` + 向量库 | 用户画像、通用薄弱领域、学科知识图谱 |
| **L2.5** | 跨学科共享画像 | 全局共享 | `user_profiles` | 职业、技术栈、学习风格、通用薄弱点 |

#### 14.1.3 跨学科切换机制

```
用户请求: "给我讲讲 Transformer"（学科=transformer）
         │
         ▼
[DialogContextManager]
  1. 检查用户最近活跃会话（任意学科）
  2. 发现活跃会话是 rag（不同学科！）
  3. 暂停 rag 会话（status='suspended'）
  4. 创建 transformer 新会话
  5. 但保留全局画像（L2.5）
         │
         ▼
[Prompt 分层输出]
  【用户画像】(跨学科共享)
  职业: 后端工程师, 技术栈: [C++, Python]
  通用薄弱领域: [线性代数]
  
  【当前学科】(学科隔离)
  学科: transformer, 当前话题: None
  
  【对话历史】(学科隔离)
  （新会话，无历史）
```

#### 14.1.4 记忆分类矩阵

| 记忆类型 | 是否跨学科共享 | 存储位置 | 说明 |
|:---|:---|:---|:---|
| 用户画像（职业/技术栈/经验） | ✅ 全局 | `user_profiles` | 所有学科一致 |
| 通用薄弱领域（数学基础等） | ✅ 全局 | `user_profiles.weak_areas_global` | 影响所有技术学科 |
| 学科薄弱点 | ❌ 隔离 | `user_knowledge_states` | 只与当前学科相关 |
| 当前话题 | ❌ 隔离 | `dialog_sessions.current_topic` | "RAG" 不能带到 "Transformer" |
| 对话历史 | ❌ 隔离 | `dialog_messages` | 每学科独立会话链 |
| 会话摘要 | ❌ 隔离 | `dialog_sessions.context_summary` | 学科内的知识脉络 |
| IRT 能力值 theta | ❌ 隔离 | `user_knowledge_states.theta` | 不同学科能力不同 |

#### 14.1.5 核心类设计

```python
class DialogContextManager:
    """对话上下文管理器（跨学科记忆分层）"""
    
    def get_or_create_session(self, user_id, subject_id, session_id=None):
        # 跨学科切换检测
        active_session = self._find_active_session(user_id)
        if active_session and active_session.subject_id != subject_id:
            self._suspend_session(active_session.session_id)  # 暂停旧学科
            return self._create_session(user_id, subject_id)   # 创建新学科会话
    
    def build_context(self, session_id) -> DialogContext:
        # 分层组装：全局画像 + 学科隔离记忆
        session = self._load_session(session_id)
        history = self.get_history(session_id)
        profile = self.get_or_create_profile(session.user_id)  # L2.5 全局画像
        weak_areas_subject = self._get_weak_areas(session.user_id, session.subject_id)
        
        return DialogContext(
            history=history,                    # L0 学科隔离
            current_topic=session.current_topic, # L0 学科隔离
            weak_areas=weak_areas_subject,       # L1 学科隔离
            user_profile=profile,                # L2.5 全局共享
            weak_areas_global=profile.weak_areas_global,  # L2.5 全局共享
        )
```

---

### 14.2 关系作用域映射与降级策略

#### 14.2.1 问题背景

原始范式配置只有 types 和 relations，缺少 type 间的连接合法性约束。导致实际提取时出现：
- `technology --HAS_SUB--> sub_technology`（关系语义错误）
- `technology --REQUIRES--> requirement`（方向反了）

根本原因是：**Prompt 中缺少 type-relation-type 的合法性校验**。

#### 14.2.2 关系作用域映射（relation_map）

在范式配置中显式定义合法的概念间连接：

```yaml
relation_map:
  # parent_type:
  #   relation: [child_types]
  #
  # 表示: parent 节点可以通过 relation 连接到哪些 child 节点
  requirement:
    IMPLEMENTS: [technology]    # 需求实现为技术
  technology:
    DEPEND_ON: [requirement]    # 技术分解出子需求/约束
```

**方向约定**：relation_map 定义的是 **parent → child** 方向的合法关系。

**图谱结构说明**：
- 工程分解范式的图谱是 **有向无环图（DAG）**，不是严格的树
- `requirement` 既可以是顶层驱动（无 parent），也可以是 technology 分解出的子需求
- `IMPLEMENTS` 和 `DEPEND_ON` 是两种语义完全不同的关系，不可互换

| 关系 | 语义 | 方向 | 示例 |
|:---|:---|:---|:---|
| `IMPLEMENTS` | 需求驱动技术 | requirement → technology | "为了提升效率，采用多GPU并行训练" |
| `DEPEND_ON` | 技术分解出子需求 | technology → requirement | "多GPU并行训练需要保证梯度同步正确" |

#### 14.2.3 parent_rules（DAG 层级约束）

```yaml
parent_rules:
  requirement: [technology]    # 子需求的 parent 可以是技术（通过 DEPEND_ON）
  technology: [requirement]    # 技术的 parent 是需求（通过 IMPLEMENTS）
```

注意：DAG 结构允许 requirement 既为顶层节点（无 parent），又为 technology 的子节点（子需求）。

#### 14.2.4 降级策略（fallback）

当用户资料不完整时，允许跳过缺失层：

```yaml
fallback:
  allow_skip_levels: true      # 允许跳过缺失的中间层
  mark_as_gap: true            # 降级连接时创建 gap 记录
  create_virtual_nodes: false  # 不自动创建虚拟节点（避免幻觉）
```

**gap 层数自然计算**（按 ideal_chain 中位置差）：
```python
# 对于理想链条 [requirement, technology, requirement]（技术分解出子需求）
# 顶层需求 → 技术: gap = 0（理想连接）
# 技术 → 子需求: gap = 0（理想连接，理想链中 technology 到下一个 requirement）
# 顶层需求 → 子需求（跳过技术）: gap = 1（跳过了 technology 层）
```

**示例**：
```
资料: "采用多GPU并行训练"

理想提取（资料完整）:
  requirement(顶层): "提升训练效率"
  technology: "多GPU并行训练", parent_hint="提升训练效率"
  requirement(子需求): "保证梯度同步正确", parent_hint="多GPU并行训练"

实际提取（资料缺少子需求）:
  requirement: "提升训练效率"
  technology: "多GPU并行训练", parent_hint="提升训练效率"
  （不提取子需求，因为资料未提及）

实际提取（资料缺少顶层需求）:
  technology: "多GPU并行训练", parent_hint=""（降级：无需求）
  → 标记为 gap: missing_type="requirement"
```

#### 14.2.5 Prompt 注入策略

在 `prompt_addon` 中增加"关系合法性约束"和"降级策略"段落。以工程分解范式为例：

```markdown
## 关系类型判断标准
- "IMPLEMENTS": 需求驱动技术
  → 语义: "为了解决[需求]，采用[技术]"
  → 方向: requirement --IMPLEMENTS--> technology
  → 使用场景: 文本先提需求/问题，再给出技术方案
- "DEPEND_ON": 技术分解出子需求
  → 语义: "[技术]需要满足[子需求]"、"[技术]的前提是[约束条件]"
  → 方向: technology --DEPEND_ON--> requirement
  → 使用场景: 文本描述某个技术时，提到该技术必须满足的约束或子目标
  → ⚠️ 注意: DEPEND_ON 的 child 是"从该技术分解出的子需求"，不是顶层驱动需求

## parent_hint 填写规则

【IMPLEMENTS 边】（requirement → technology）
- technology 的 parent_hint → 驱动它的顶层 requirement
- 示例: "多GPU并行训练" 的 parent_hint = "提升训练效率"

【DEPEND_ON 边】（technology → requirement）
- 子 requirement 的 parent_hint → 分解出它的 technology
- 示例: "保证梯度同步正确" 的 parent_hint = "多GPU并行训练"

【降级】（资料不完整时）
- 如果资料中只有技术没有需求: technology 的 parent_hint 留空
- 如果技术描述中未明确提及子需求: 不提取子需求，不编造

## 关系合法性约束
【合法连接】
- requirement --IMPLEMENTS--> technology（需求驱动技术）
- technology --DEPEND_ON--> requirement（技术分解出子需求）

【非法连接】
- technology --IMPLEMENTS--> requirement（语义颠倒: 技术不能"实现"需求）
- requirement --DEPEND_ON--> technology（语义错误: 需求不能"依赖"技术）
- 同一 type 的自我连接（如 requirement → requirement）
- 循环连接（如 A IMPLEMENTS B, B DEPEND_ON A）
```

#### 14.2.6 复杂度控制

| 策略 | 说明 |
|:---|:---|
| 方向性约束 | relation 是有向的，A→B 合法不代表 B→A 合法 |
| 稀疏化设计 | 不是所有 type 之间都有 relation，大部分为 `[]` |
| 层级限定 | `parent_rules` 限制 parent_hint 的 type，避免跨层跳跃 |
| 自动推导 | 文本中缺少明确 parent 时，系统根据 type 自动推断最可能的合法 parent |

**实际复杂度**：
- N 种 type，每种的 relation_map 最多 N 个条目
- 总条目数：O(N²)，但非常稀疏（大部分为 `[]`）
- 人类可管理的上限：type ≤ 8，relation ≤ 6

#### 14.2.7 环检测（增量式）

**问题**：虽然 relation_map 在 type 层面定义了合法连接，但实例层面仍可能形成环。以 engineering 范式为例：

```
# 错误示例（会形成环）
"提升训练效率" --IMPLEMENTS--> "多GPU并行训练"
"多GPU并行训练" --DEPEND_ON--> "提升训练效率"  # 非法！同一个需求既驱动技术，又作为技术的子需求
```

**解决方案**：增量式环检测

每次建立边 `source → target` 前，检查从 target 出发是否已可达 source：

```python
def would_form_cycle(graph, source, target):
    """
    检查添加边 source→target 是否会形成环。
    方法：从 target 出发 DFS，看能否到达 source。
    """
    visited = set()
    stack = [target]
    
    while stack:
        node = stack.pop()
        if node == source:
            return True  # 会形成环！
        if node in visited:
            continue
        visited.add(node)
        for neighbor in graph.get(node, []):
            stack.append(neighbor)
    
    return False
```

**处理策略**：

| 场景 | 处理 |
|:---|:---|
| 不会形成环 | 允许建边 |
| 会形成环 | 拒绝建边，记录日志：`[降级] 边 X→Y 会形成环，跳过` |
| 自环（X→X） | 直接拒绝 |

**适用范围**：
- 所有内置范式（theory / engineering / hierarchical）
- 所有用户自定义范式
- 前端用户手动添加的边

**实现位置**：`core/cycle_detector.py`

---

### 14.3 断裂点可视化与用户协作填充

#### 14.3.1 核心概念

| 术语 | 定义 | 视觉表现 |
|:---|:---|:---|
| **Gap（断裂点）** | 范式链条中缺失的 type 层 | 空心节点，颜色=缺失 type |
| **Skip Link（降级连接）** | 跨越缺失层的连接 | 虚线，灰色 |
| **Virtual Node（虚拟节点）** | 占位符，非真实概念 | 半透明，可点击 |
| **Supplemented Node（补充节点）** | 用户填充的真实概念 | 实色，替换 virtual node |

#### 14.3.2 Gap 识别流程

```python
def detect_gaps(extracted_concepts, paradigm_config):
    """
    检测范式链条中的断裂点。
    
    输入: 提取到的概念列表 + 范式配置（ideal_chain, parent_rules）
    输出: Gap 记录列表
    """
    gaps = []
    ideal_chain = paradigm_config["ideal_chain"]
    
    for concept in extracted_concepts:
        expected_parents = paradigm_config["parent_rules"][concept.type]
        actual_parent = concept.parent_hint
        
        if not actual_parent and expected_parents:
            # 情况1: 应该有 parent 但缺失（顶层断裂）
            gaps.append(Gap(
                target_id=concept.canonical_id,
                missing_type=expected_parents[0],
                tier=1,
            ))
        elif actual_parent and actual_parent.type not in expected_parents:
            # 情况2: parent 存在但 type 不匹配（降级连接）
            skipped_types = find_skipped_types(
                source_type=actual_parent.type,
                target_type=concept.type,
                ideal_chain=ideal_chain
            )
            if skipped_types:
                gaps.append(Gap(
                    source_id=actual_parent.canonical_id,
                    target_id=concept.canonical_id,
                    missing_type=skipped_types[0],
                    tier=2,
                ))
    
    return gaps
```

#### 14.3.3 Gap 数据模型

```python
class GapRecord:
    """知识链条断裂点记录"""
    gap_id: str              # UUID
    subject_id: str          # 所属学科
    source_id: str           # 源概念 canonical_id
    target_id: str           # 目标概念 canonical_id
    missing_type: str        # 缺失的 type（如 "sub_requirement"）
    relation: str            # 降级使用的 relation
    tier: int                # 1=理想缺失, 2=降级连接
    status: str              # "open" / "supplemented" / "ignored"
    created_at: str          # ISO 8601
    supplemented_by: Optional[str]  # 用户补充后的新节点 canonical_id
```

#### 14.3.4 前端交互设计

**图谱渲染**：

```javascript
// Gap 节点样式
{
  data: { type: 'virtual_gap', gap_type: 'sub_requirement', status: 'open' },
  style: {
    'shape': 'ellipse',
    'width': 24, 'height': 24,
    'background-color': 'transparent',
    'border-width': 2,
    'border-style': 'dashed',
    'border-color': getTypeColor('sub_requirement'),  // 与缺失 type 同色
    'label': '+ 子需求',
  }
}

// Skip Link 样式
{
  style: {
    'line-style': 'dashed',
    'line-color': '#bdc3c7',
    'width': 1,
  }
}
```

**用户交互流程**：

```
用户看到图谱：
  ┌─────────────┐
  │ 多GPU并行训练 │───dashed───○───dashed───▶│ Ring AllReduce │
  │  (technology)│              +            │  (sub_technology)│
  └─────────────┘         子需求              └─────────────────┘
                               
用户悬停 ○：
  提示框: "缺少「子需求」层
          按工程分解范式，此处应有子需求节点
          [点击补充] [忽略]"
          
用户点击 ○ → 弹窗输入 → 保存
  后端：创建新 Concept 节点 "保证梯度同步正确"
  删除 VirtualGap → 重建边
  图谱更新：实色节点替代空心节点
```

#### 14.3.5 断裂点统计面板

```
┌─────────────────────────────┐
│  🔍 知识完整性检查              │
├─────────────────────────────┤
│  本学科共 3 处断裂：            │
│                             │
│  ⚠ 缺少「需求」 (1)           │
│    - 多GPU并行训练 ← 缺 requirement │
│    [补充] [忽略]              │
│                             │
│  ⚠ 缺少「子需求」 (2)         │
│    - Ring AllReduce ← 缺 sub_requirement │
│    - 分布式存储 ← 缺 sub_requirement │
│    [补充] [忽略]              │
│                             │
│  已完成补充: 0                │
└─────────────────────────────┘
```

#### 14.3.6 范式配置中的 gap_visualization

```yaml
gap_visualization:
  enabled: true
  virtual_node:
    shape: "circle"
    radius: 12
    fill: "transparent"
    stroke_width: 2
    stroke_dasharray: "4,2"
    label_template: "+ {{type_label}}"
    hover_hint: "缺少{{type_label}}，点击补充"
  skip_link:
    stroke_dasharray: "4,4"
    color: "#bdc3c7"
    opacity: 0.6
  supplemented_node:
    badge: "✓"
    badge_color: "#27ae60"
```

---

### 14.4 实施路线图

| 阶段 | 内容 | 工作量 | 状态 |
|:---|:---|:---|:---|
| **阶段 1** | 更新 `paradigms.yaml`（补全 relation_map + parent_rules + ideal_chain + gap_visualization） | 1 小时 | ✅ 已完成 |
| **阶段 2** | 更新 `semantic_extractor.py`（从 YAML 加载，替代硬编码） | 30 分钟 | ✅ 已完成 |
| **阶段 3** | 后端 Gap 检测（提取后识别 skip_level） | 1 小时 | 🟡 待实现 |
| **阶段 4** | 后端 API（list_gaps / supplement_gap / ignore_gap） | 1 小时 | 🟡 待实现 |
| **阶段 5** | 前端图谱渲染（VirtualGap 节点 + SkipLink 虚线边） | 1.5 小时 | 🟡 待实现 |
| **阶段 6** | 前端补充交互（点击弹窗 → 提交 → 图谱更新） | 1.5 小时 | 🟡 待实现 |
| **阶段 7** | 断裂点统计面板 | 1 小时 | 🟡 待实现 |
| **阶段 8** | YAML 范式配置面板（前端 UI + CRUD API） | 3-4 小时 | 🟡 待实现 |

---

### 14.5 配置校验 Schema

```yaml
schema:
  version: "2.0"
  required_fields:
    - name
    - description
    - types
    - relations
    - relation_map
    - parent_rules
    - ideal_chain
    - prompt_addon
  type_constraints:
    types:
      min_count: 2
      max_count: 8
      key_pattern: "^[a-z_]+$"
      value_max_length: 50
    relations:
      min_count: 2
      max_count: 8
      key_pattern: "^[A-Z_]+$"
      value_max_length: 20
  relation_map_constraints:
    relation_must_exist_in_relations: true
    target_must_exist_in_types: true
  parent_rules_constraints:
    each_type_must_have_entry: true
    empty_list_means_root: true
```

---

## 15. 新增范式功能设计（2026-07-23）

### 15.1 概述

本章节定义用户在前端界面创建自定义知识提取范式的完整设计方案。支持通过可视化表单配置概念类型、关系类型、连接规则等，系统自动生成范式 YAML 配置并持久化。

### 15.2 前端功能面板

#### 15.2.1 入口位置
- **位置**: `BuildOptions.vue` 的"范式选择"下拉框旁新增"➕ 新建范式"按钮
- **交互方式**: 抽屉式面板（Drawer）或独立路由 `/paradigm-designer`

#### 15.2.2 分步表单（Wizard 4步）

**Step 1: 基础信息**
| 字段 | 类型 | 必填 | 示例 | 校验规则 |
|:---|:---|:---:|:---|:---|
| 范式ID | 输入框 | ✅ | `medical_diagnosis` | `^[a-z_]+$`，唯一 |
| 显示名称 | 输入框 | ✅ | `医疗诊断` | 长度 ≤ 50 |
| 描述 | 文本域 | ✅ | `适合临床知识` | 长度 ≤ 200 |
| 图标 | Emoji选择器 | | `🏥` | 单个字符 |
| 主题色 | 颜色选择器 | | `#E74C3C` | 有效 HEX 颜色 |

**Step 2: 概念类型（Type）配置**
- 动态表格，可增删行
- 每行：`type_key`（英文ID，如 `symptom`）+ `type_label`（中文名，如 `症状`）
- 最少2个，最多8个
- 第一个 type 自动标记为顶层根节点

**Step 3: 关系类型（Relation）配置**
- 动态表格，可增删行
- 每行：`rel_key`（大写+下划线，如 `REQUIRES`）+ `rel_label`（中文名，如 `需要`）
- 最少2个，最多6个
- 自动为每个关系分配默认样式（颜色+线型）

**Step 4: 连接规则（Relation Map）配置**
- 表格形式（MVP阶段）：选择 `source_type` → `relation` → `target_types`（多选）
- 未来版本：可视化DAG拖拽编辑器
- 实时 CycleDetector 校验，防止 type-level 环

**Step 5: 高级配置（可折叠）**
| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| 理想链条 | 拖拽排序 | type 定义顺序 | 用于 gap 检测 |
| 循环范式 | 开关 | false | engineering 类交替递归 |
| 允许跳过层级 | 开关 | true | fallback 策略 |
| Gap检测-同类型连接 | 开关 | false | 循环范式专用 |
| LLM提示词附加 | 文本域 | 自动生成 | 可编辑的基础模板 |

#### 15.2.3 实时预览面板
- **DAG 结构预览**: 基于 relation_map 实时渲染有向图
- **YAML 预览**: 实时生成最终 YAML 配置
- **校验提示**: 每步完成时显示校验结果（错误/警告）

### 15.3 后端 API 设计

#### 15.3.1 接口列表

| 方法 | 路径 | 说明 | 状态 |
|:---|:---|:---|:---:|
| GET | `/api/paradigms` | 获取所有范式列表 | 已有 |
| GET | `/api/paradigms/{paradigm_id}` | 获取单个范式完整配置 | 已有 |
| POST | `/api/paradigms` | 创建新范式 | **新增** |
| PUT | `/api/paradigms/{paradigm_id}` | 修改范式（自定义） | 预留 |
| DELETE | `/api/paradigms/{paradigm_id}` | 删除范式（自定义） | 预留 |

#### 15.3.2 POST /api/paradigms 详细设计

**请求体（最小必填）**:
```json
{
  "paradigm_id": "medical_diagnosis",
  "name": "医疗诊断",
  "description": "适合临床知识：症状→检查→诊断→治疗",
  "icon": "🏥",
  "color": "#E74C3C",
  "types": {
    "symptom": "症状",
    "examination": "检查",
    "diagnosis": "诊断",
    "treatment": "治疗"
  },
  "relations": {
    "REQUIRES": "需要",
    "LEADS_TO": "导致",
    "TREATS": "治疗"
  },
  "relation_map": {
    "symptom": {
      "REQUIRES": ["examination"]
    },
    "examination": {
      "LEADS_TO": ["diagnosis"]
    },
    "diagnosis": {
      "TREATS": ["treatment"]
    }
  }
}
```

**校验链**:
1. schema 校验（必填字段、类型、格式）
2. `paradigm_id` 唯一性（不与内置/已有自定义冲突）
3. `types` 数量 `[2, 8]`，key 匹配 `^[a-z_]+$`
4. `relations` 数量 `[2, 6]`，key 匹配 `^[A-Z_]+$`
5. `relation_map` 合法性（所有 type/relation 必须在已定义范围内）
6. CycleDetector.type_level 校验（relation_map 无 type-level 环）
7. `parent_rules` 自动生成（从 relation_map 反向推导）
8. `styles` 自动生成（为每个 relation 分配默认样式）
9. `prompt_addon` 自动生成（基础提示词模板）

**响应**:
```json
{
  "success": true,
  "paradigm_id": "medical_diagnosis",
  "warnings": ["未设置 cycle_pattern，非循环范式可忽略"],
  "auto_generated": {
    "parent_rules": {
      "symptom": [],
      "examination": ["symptom"],
      "diagnosis": ["examination"],
      "treatment": ["diagnosis"]
    },
    "styles": {
      "REQUIRES": {"color": "#e67e22", "lineStyle": "solid", "width": 2},
      "LEADS_TO": {"color": "#9b59b6", "lineStyle": "dashed", "width": 1.5},
      "TREATS": {"color": "#3498db", "lineStyle": "solid", "width": 2}
    },
    "prompt_addon": "## 医疗诊断范式 — 概念类型判断标准..."
  }
}
```

#### 15.3.3 数据持久化

- **写入位置**: `config/paradigms.yaml` 的 `paradigms:` 下新增条目
- **内置 vs 自定义标记**: 新增 `is_builtin: false`
- **文件锁**: 写入时加文件锁（`filelock` 库），防止并发修改
- **备份**: 修改前自动备份 `paradigms.yaml.bak.YYYYMMDD_HHMMSS`
- **热加载**: 写入后自动刷新 `_PARADIGMS_YAML` 内存缓存

### 15.4 后端组件设计

#### 15.4.1 ParadigmManager 服务

```python
class ParadigmManager:
    """范式管理服务：CRUD + 校验 + 持久化"""
    
    YAML_PATH = Path("config/paradigms.yaml")
    
    def list_paradigms(self) -> List[Dict]
    def get_paradigm(self, paradigm_id: str) -> Optional[Dict]
    def create_paradigm(self, data: Dict) -> Dict  # 返回 {success, warnings, auto_generated}
    def update_paradigm(self, paradigm_id: str, data: Dict) -> Dict
    def delete_paradigm(self, paradigm_id: str) -> bool
    def _auto_generate_fields(self, data: Dict) -> Dict
    def _backup_yaml(self)
    def _reload_cache(self)
```

#### 15.4.2 ParadigmValidator 校验器

```python
class ParadigmValidator:
    """范式配置校验器"""
    
    def validate(self, data: Dict) -> ValidationResult
    def _validate_schema(self, data: Dict) -> List[str]  # 错误列表
    def _validate_types(self, types: Dict) -> List[str]
    def _validate_relations(self, relations: Dict) -> List[str]
    def _validate_relation_map(self, data: Dict) -> List[str]
    def _check_type_level_cycles(self, relation_map: Dict) -> List[str]
    def _auto_parent_rules(self, relation_map: Dict, types: Dict) -> Dict
    def _auto_styles(self, relations: Dict) -> Dict
    def _auto_prompt_addon(self, data: Dict) -> str
```

### 15.5 前端组件设计

```
ParadigmDesigner.vue（路由 /paradigm-designer）
├── StepIndicator（步骤指示器 1-5）
├── Step1_BasicInfo.vue（基础信息表单）
├── Step2_TypesConfig.vue（类型配置表格）
├── Step3_RelationsConfig.vue（关系配置表格）
├── Step4_RelationMap.vue（连接规则表格）
├── Step5_Advanced.vue（高级配置）
└── PreviewPanel.vue（右侧实时预览）
    ├── DagPreview.vue（DAG结构预览）
    └── YamlPreview.vue（YAML实时生成）
```

### 15.6 开发计划

| 阶段 | 内容 | 预计耗时 | 依赖 |
|:---|:---|:---:|:---|
| 1 | ParadigmValidator + 测试 | 2h | 无 |
| 2 | ParadigmManager + 持久化 | 1.5h | 阶段1 |
| 3 | 后端 API 端点（POST/GET） | 1h | 阶段2 |
| 4 | 联调测试 | 0.5h | 阶段3 |
| **总计** | | **~5h** | |

---

*本章节记录日期：2026-07-23*

---

*本章节的实现状态请参阅 docs/leftover-problem.md 中的 LA-027 和 LA-044 条目。*
