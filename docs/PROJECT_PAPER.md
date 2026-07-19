# LearnAnything：基于双层知识图谱的通用知识学习系统

> **工程论文草稿 v0.1**  
> 项目: LearnAnything  
> 日期: 2026-07-19  
> 状态: 草稿，待细化

---

## 摘要

LearnAnything 是一个面向通用知识学习的 RAG（检索增强生成）系统，采用**双层知识图谱架构**（文档层 + 概念层），支持多格式文档导入、智能分块、多范式概念提取、语义去重与连接、图谱可视化、以及基于多 Agent 协作的出题、测评与讲解功能。本文介绍系统的设计目标、核心功能、技术选型与实现流程，分析其在现有 RAG 系统生态中的定位，并总结项目的创新点与工程价值。

**关键词**: RAG, 知识图谱, GraphRAG, 智能学习, 多 Agent, 知识提取, 语义检索

---

## 1. 介绍

### 1.1 项目背景与用途

随着大语言模型（LLM）的快速发展，RAG 技术已成为解决 LLM 幻觉问题和知识时效性不足的核心方案。然而，传统的 RAG 系统通常采用"向量检索 + 文本块拼接"的范式，存在以下局限：

1. **检索碎片化**：用户问题往往涉及多个知识点的关联，纯向量检索只能返回语义相似的文本片段，无法发现跨文档、跨段落的概念关联
2. **缺乏结构化**：文本块之间的层级关系、依赖关系、解决方案关系等结构性知识被丢失
3. **教育场景不足**：现有 RAG 系统多用于问答和摘要，缺乏针对学习场景的系统性支持（出题、测评、知识追踪、能力画像）

LearnAnything 的设计目标是构建一个**面向通用知识学习的端到端 RAG 系统**，不仅解决传统 RAG 的检索问题，更通过**双层知识图谱**为知识提供结构化表示，支持从"知识点定位"到"出题→测评→讲解"的完整学习闭环。

### 1.2 开发目标

| 目标层级 | 目标描述 | 当前状态 |
|:---|:---|:---|
| **P0（核心）** | 构建双层知识图谱（文档层 + 概念层），支持多格式文档导入、智能分块、概念提取、语义去重与连接 | ✅ 已实现 |
| **P1（增强）** | 实现图谱可视化（文档树 + 概念树），支持多范式概念提取、图片概念提取、悬浮预览 | ✅ 已实现 |
| **P2（学习）** | 实现基于图谱的出题（Quiz Agent）、测评（Coach Agent）、讲解（Tutor Agent） | ✅ 已实现 |
| **P3（优化）** | 段落排序优化、自适应测评、IRT 难度校准、能力画像可视化 | 🟡 待完善 |
| **P4（扩展）** | 学科插件化、多模态支持（视频/音频）、协作学习 | 🔵 规划中 |

---

## 2. 功能说明

LearnAnything 的核心功能分为四大模块：

### 2.1 知识图谱构建（P0）

**功能定位**：系统的数据基础设施，将非结构化文档转化为结构化知识图谱。

**核心子功能**：
- 多格式文档导入（PDF/Markdown/图片/手写笔记）
- 智能分块（MarkdownChunker v2.0：自然段 + 树形 heading 层级）
- 图片解析（VLM 视觉语言模型：GLM-4V 图片描述）
- 双层图谱构建：
  - 文档层（Chunk）：BELONGS_TO（层级）+ ADJACENT_TO（相邻）
  - 概念层（CanonicalConcept）：SOLUTION（需求→技术）+ DEPENDS_ON（依赖）+ REQUIRES（通用依赖）
- 概念去重（基于 embedding 相似度，阈值 0.85）
- 语义连接（基于 parent_hint + LLM 二次确认）

### 2.2 知识图谱可视化（P1）

**功能定位**：将结构化知识以直观的图谱形式呈现，支持文档结构和概念关系的可视化。

**核心子功能**：
- 文档树视图：document → heading → paragraph 的树形结构，卡片风格节点，贝塞尔曲线连接
- 概念树视图：CanonicalConcept 的 UML 卡片布局，支持副本节点（DAG 共享子节点）
- 视图切换：文档树 ↔ 概念树 ↔ 适应 ↔ 重置
- 节点交互：悬浮预览（原文摘要/图片缩略图）、点击详情（完整原文/来源 chunks）
- 搜索与高亮：实时过滤节点，关联边高亮

### 2.3 智能学习 Agent（P2）

**功能定位**：基于知识图谱的智能化学习辅助，实现出题、测评、讲解的闭环。

**核心子功能**：
- **Quiz Agent（出题）**：基于概念子图生成覆盖度广、关联度高、难度可控的题目
- **Coach Agent（测评）**：基于知识状态图的自适应测评，定位薄弱知识点
- **Tutor Agent（讲解）**：基于概念关联网络的溯源讲解，从"点"到"面"构建知识理解
- **Coordinator（协调器）**：意图路由 + Agent 分发 + 消息总线贯穿

### 2.4 混合检索（P0）

**功能定位**：在查询阶段结合多种检索策略，平衡精确性与语义覆盖。

**核心子功能**：
- BM25 稀疏检索 + 智谱 GLM 密集向量检索
- RRF（Reciprocal Rank Fusion）融合排序
- Cross-Encoder 重排序
- 图查询（KùzuDB）：精确匹配 + 模糊匹配 + 别名匹配 + Embedding 回退

---

## 3. 分功能详细介绍

### 3.1 知识图谱构建模块

#### 3.1.1 详细流程

LearnAnything 的知识图谱构建分为三个阶段（Phase 1 → Phase 2 → Phase 2.5）：

**Phase 1：文档层构建（导入时）**

```
用户上传 PDF
    │
    ▼
MinerU CLI → 结构化 Markdown（标题层级、图片、公式、表格）
    │
    ▼
MarkdownChunker v2.0 → 自然段分块 + 树形 heading 层级
    │
    ├──────────────┬──────────────┐
    ▼              ▼              ▼
文本段落       图片 chunk      公式/表格
(Paragraph    (image_pseudo   (待提取)
 Chunk)       Chunk)
    │              │
    ▼              ▼
VLMClient (GLM-4V) → 图片描述 → 注入 chunk.text
    │
    ▼
VectorStore (ChromaDB) + GraphStore (KùzuDB) + SubjectManager (SQLite)
    │
    ▼
build_adjacent_relations() + build_belongs_to_relations()
```

**Phase 2：概念层提取（用户触发）**

```
用户选择范式（理论归纳/工程分解/层级归纳）
    │
    ▼
按 heading_path 分组 → 提取 heading 上下文（300 字符）
    │
    ▼
SemanticExtractor (extract_concepts_batch_v2)
    │
    ▼
ConceptDeduper → 基于 embedding 相似度去重（阈值 0.85）
    │
    ▼
SemanticLinker → 构建概念间连接（SOLUTION/DEPENDS_ON）
    │
    ▼
GraphStore → 写入 KùzuDB（CanonicalConcept + 语义边）
```

**Phase 2.5：语义连接增强**

- 基于 parent_hint 构建初始连接
- 基于 embedding 相似度补充连接
- LLM 二次确认连接合理性

#### 3.1.2 技术栈及选型对比

| 组件 | 选型 | 备选方案 | 选型理由 |
|:---|:---|:---|:---|
| **文档解析** | MinerU CLI + PyMuPDF | PDFMiner, OCRmyPDF, Marker | MinerU 在结构化 Markdown 提取（标题、图片、公式）上准确率最高，支持中文；PyMuPDF 作为 fallback 处理扫描件 |
| **分块策略** | MarkdownChunker v2.0（自然段 + 树形 heading） | LangChain RecursiveCharacterTextSplitter, LlamaIndex SentenceSplitter | 自然段是语义最小单元，树形 heading 保留文档结构；LangChain 的固定长度切分会破坏语义完整性 |
| **图片解析** | 智谱 GLM-4V | GPT-4V, Qwen-VL, MiniGPT-4 | 智谱 API 在中文场景下图片描述准确率高，且成本低于 GPT-4V |
| **向量数据库** | ChromaDB | Pinecone, Weaviate, Milvus, Qdrant | ChromaDB 支持本地文件存储，无需外部服务，适合个人桌面应用；Pinecone 等云服务需要网络依赖 |
| **图数据库** | KùzuDB | Neo4j, Dgraph, ArangoDB | KùzuDB 是嵌入式图数据库，单文件存储，Cypher 兼容，无需额外服务；Neo4j 需要独立服务器 |
| **Embedding** | 智谱 AI Embedding API | OpenAI text-embedding-3, BGE, M3E | 2048 维，中文语义效果好，成本可控 |
| **LLM** | DeepSeek API (Chat) + 智谱 API | GPT-4, Claude, Llama | DeepSeek 性价比高，推理能力强；智谱 API 用于 embedding 和图片理解 |
| **去重算法** | 基于 cosine 相似度的贪心合并 | 聚类（HDBSCAN, K-Means）、LSH | 贪心合并简单可控，阈值 0.85 可解释；聚类方法需要调参，且结果不稳定 |

#### 3.1.3 同类项目定位与优劣势

| 项目 | 架构 | 节点类型 | 层级 | 概念去重 | 最接近的层 | 关键差异 |
|:---|:---|:---|:---|:---|:---|:---|
| **Microsoft GraphRAG** | Entity | 单层实体 | 有（Entity Resolution） | 单层实体 + 社区分层 | 单层实体，合并后删除旧节点；我们保留两层概念 |
| **HippoRAG** | Entity | 单层实体 | 无 | 单层实体 + PageRank | 无去重，无层级概念分离 |
| **LightRAG** | Entity | 单层实体 | 无 | 单层实体 + 高低级检索 | 双级检索但实体单层；无概念去重中间层 |
| **DA-RAG** | Chunk + Entity | 双层（Chunk + KG） | 无 | Chunk Layer + KG Layer | Chunk 对应我们的 Chunk，但 KG Layer 只有单层实体 |
| **RAPTOR** | Summary | 树形层级 | 无（聚类摘要） | 层级树 | 节点是文本摘要而非概念；无去重机制 |
| **KET-RAG** | Keyword-Entity-Triple | 三层 | 有 | 关键词→实体→三元组 | 桥接设计类似但粒度不同 |
| **StructRAG** | 结构化知识 | 层次推理 | 有 | 结构保持与提取 | 侧重逻辑结构保持，非概念去重分离 |
| **LearnAnything (本项目)** | Chunk + Concept | 双层（ExtractedConcept + CanonicalConcept） | 有 | 保留提取概念层 + 规范概念层 | 显式分离提取概念和去重概念，保留溯源能力 |

**核心优势**：
1. **保留提取概念层**：每个 ExtractedConcept 可精确追溯回其来源 chunk，支持溯源和局部上下文重建
2. **独立规范概念层**：CanonicalConcept 通过 embedding 相似度去重合并，但不删除原始提取实例，而是建立映射关系
3. **source_chunks 字段**：规范概念直接关联原始 chunk ID，实现图→chunk→原始文本的精确回溯

**劣势**：
1. 去重阈值（0.85）需要手动调参，不同学科的最优阈值可能不同
2. 概念提取依赖 LLM，存在幻觉风险，需要人工校验
3. 图数据库 KùzuDB 的社区生态较 Neo4j 弱，高级功能（如社区检测、图算法）需要自行实现

### 3.2 知识图谱可视化模块

#### 3.2.1 详细流程

**数据加载流程**：

```
用户切换学科 → 触发 loadAllNodes()
    │
    ▼
loadChunkNodes() → 后端 API /api/knowledge-graph/{subject}/nodes
    │
    ▼
后端 GraphStore → KùzuDB 查询 Chunk 节点
    │
    ▼
前端生成卡片数据（cardLabel, cardHeight, nodeWidth）
    │
    ▼
cy.add(chunkNodes) → Cytoscape.js 渲染
    │
    ▼
loadEdges() → 后端 API /api/knowledge-graph/{subject}/edges
    │
    ▼
前端过滤 BELONGS_TO 边 → cy.add(edges)
    │
    ▼
runTreeLayout() → 逐棵树分别 dagre + 左右排列
```

**布局算法（当前方案）**：

1. 从 BELONGS_TO 边构建邻接表，找到所有根节点（document/入度为0）
2. 对每棵树：BFS 收集节点 → 单独跑 dagre LR（rankDir=LR, rankSep=120）
3. 计算每棵树的 bbox，从左到右排列（树间距 150px）
4. 孤立节点放最右侧网格
5. 调整边曲率（adjustEdgeCurvature）：子节点在上→向上凸，在下→向下凸
6. 手动 fit（zoom = min(容器高/图高, 容器宽/图宽, 0.5)，限制 0.15-0.5）

#### 3.2.2 技术栈及选型对比

| 组件 | 选型 | 备选方案 | 选型理由 |
|:---|:---|:---|:---|
| **前端框架** | Vue 3 + Vite | React, Angular, Svelte | Vue 3 Composition API 简洁，适合中小型项目；Vite 构建速度快 |
| **图谱渲染** | Cytoscape.js + cytoscape-dagre | D3.js, vis.js, Sigma.js, ECharts | Cytoscape.js 节点/边样式系统强大，性能优秀，支持大规模图；D3.js 更灵活但实现成本高 |
| **布局算法** | dagre（LR 方向） + 手动排列 | COSE, Grid, Circle, Cola | dagre 层次清晰，适合树形数据；COSE 适合力导向网络图 |
| **节点样式** | 原生 CSS（无 UI 组件库） | Element Plus, Ant Design, Vuetify | 项目初期未引入 UI 库，自定义 CSS 更灵活但维护成本高 |

#### 3.2.3 同类项目定位与优劣势

| 项目 | 可视化方案 | 布局算法 | 节点风格 | 与本项目对比 |
|:---|:---|:---|:---|:---|
| **GraphRAG (Microsoft)** | 无原生可视化 | 无 | 无 | 仅提供后端 API，无前端可视化；本项目自研可视化 |
| **LightRAG** | 无原生可视化 | 无 | 无 | 同上 |
| **Neo4j Browser** | 内置可视化 | 力导向 | 圆形标签 | 通用图数据库浏览器，不针对学习场景；本项目面向教育，支持卡片节点 + 原文预览 |
| **Obsidian (Graph View)** | 本地笔记图谱 | 力导向 | 文本标签 | 面向笔记关联，节点是笔记文件；本项目节点是概念/段落，粒度更细 |
| **LearnAnything (本项目)** | 自研 Vue + Cytoscape | dagre LR + 手动排列 | UML 卡片（自适应宽高） | 支持文档树 + 概念树双视图，卡片节点显示原文摘要，悬浮预览图片 |

**核心优势**：
1. **双视图切换**：文档树（chunk 层级结构）和概念树（概念语义关系）两种视图，满足不同学习场景
2. **卡片节点**：自适应宽高的 UML 卡片风格，显示节点类型、标题、原文摘要，信息密度高
3. **悬浮预览**：鼠标悬停显示原文摘要和图片缩略图，无需点击即可快速浏览
4. **详情面板**：点击节点显示完整原文内容、来源 chunks、章节路径，支持精确溯源

**劣势**：
1. 布局算法复杂（多棵树分别 dagre + 手动排列），实现成本高
2. 段落排序尚未实现（dagre 内部排序不可控），同级节点顺序依赖原始数据
3. 大规模图（>1000 节点）性能需要优化（当前渲染 441 节点流畅，但 1000+ 可能有卡顿）

### 3.3 智能学习 Agent 模块

#### 3.3.1 详细流程

**Quiz Agent（出题）流程**：

```
用户输入出题请求（如"出题：Transformer 注意力机制，难度中等"）
    │
    ▼
Coordinator → IntentRouter → "quiz" 意图
    │
    ▼
ConceptRetriever.resolve(["Transformer 注意力机制"])
    ├─ 策略1: 精确匹配
    ├─ 策略2: 模糊匹配（双向包含 + case-insensitive）
    ├─ 策略3: 别名匹配
    ├─ 策略4: Embedding 语义检索
    └─ 兜底: PageRank Top-5
    │
    ▼
SubgraphBuilder.build(seed_concepts, max_depth=2, max_nodes=15)
    │
    ▼
ContextAssembler.assemble(subgraph) → Graph-to-Text 上下文
    │
    ▼
QuizAgent.handle(query, graph_context=graph_context)
    │
    ▼
LLM 生成题目（基于图谱上下文）
    │
    ▼
MessageBus.publish(quiz_generated) → CoachAgent 订阅
```

**Coach Agent（测评）流程**：

```
用户开始自适应测评
    │
    ▼
获取用户知识状态子图（UserKnowledgeState）
    │
    ▼
识别信息增益最高的概念区域（掌握度不确定 + 图中心性高）
    │
    ▼
选择目标概念 → 检索候选题目池（难度匹配）
    │
    ▼
IRT 最大信息量准则选择最优下一题
    │
    ▼
用户提交答案 → 更新知识状态（直接概念 + 沿 DEPENDS_ON 传播）
    │
    ▼
生成能力画像（整体掌握度、概念聚类、知识缺口、学习路径）
```

**Tutor Agent（讲解）流程**：

```
用户提交错题
    │
    ▼
获取题目关联的概念子图（SOLUTION/DEPENDS_ON/DERIVED_FROM）
    │
    ▼
获取用户在这些概念上的历史状态
    │
    ▼
确定讲解深度（L1 点讲解 → L2 链讲解 → L3 面讲解 → L4 溯源讲解）
    │
    ▼
组装讲解上下文（概念子图 + 用户状态 + 来源 chunks + 媒体素材）
    │
    ▼
LLM 生成结构化讲解（核心错因 → 知识定位 → 原文依据 → 选项分析 → 推荐学习）
```

#### 3.3.2 技术栈及选型对比

| 组件 | 选型 | 备选方案 | 选型理由 |
|:---|:---|:---|:---|
| **Agent 框架** | 自研（Coordinator + 消息总线） | LangChain, AutoGen, CrewAI | 自研框架更轻量，不需要引入 LangChain 的复杂依赖；消息总线实现 Agent 间通信 |
| **意图识别** | 正则 + 关键词匹配 | 意图分类模型（BERT, FastText） | 当前意图类别少（quiz/evaluate/tutor），正则足够；分类模型需要训练数据 |
| **知识追踪** | 基于图的状态传播（自定义） | Deep Knowledge Tracing (DKT), Bayesian Knowledge Tracing (BKT) | DKT/BKT 需要大量历史数据训练；本项目基于图拓扑的状态传播不需要预训练 |
| **IRT 难度校准** | 简化 IRT（单参数 Rasch） | 完整三参数 IRT（a, b, c） | 单参数 IRT 实现简单，足够用于自适应选题；三参数需要更多数据 |
| **Bloom 认知层级** | 手动映射（concept_type + 图位置） | 自动分类模型 | 手动映射可解释性强，但可能不够精确；自动分类需要标注数据 |

#### 3.3.3 同类项目定位与优劣势

| 项目 | 出题能力 | 测评能力 | 讲解能力 | 知识图谱驱动 | 与本项目对比 |
|:---|:---|:---|:---|:---|:---|
| **Khan Academy** | 固定题库 | 无自适应 | 视频讲解 | 无 | 传统题库+视频，无知识图谱；本项目基于图谱动态出题 |
| **Quizlet** | 用户自建 | 无 | 无 | 无 | 闪卡记忆工具，无智能分析；本项目有知识追踪和能力画像 |
| **Knewton** | 自适应出题 | 自适应测评 | 无 | 有（知识图谱） | 2014 年产品，已停止运营；知识图谱不透明 |
| **Squirrel AI** | 自适应出题 | 知识追踪 | 讲解视频 | 有（知识图谱） | 商业化产品，封闭系统；本项目开源，透明可溯源 |
| **KAQG (论文)** | 图谱出题 | 难度控制 | 无 | 有（知识图谱） | 学术论文原型，无完整系统；本项目有完整工程实现 |
| **LearnAnything (本项目)** | 图谱动态出题 | 图状态自适应测评 | 图谱溯源讲解 | 有（双层知识图谱） | 从出题到测评到讲解的完整闭环，全链路可溯源 |

**核心优势**：
1. **全链路可溯源**：题目 → 答案 → 讲解，均可追溯到规范概念 → 原始概念 → Chunk → 文档位置
2. **图谱动态出题**：基于概念子图的拓扑结构生成题目，覆盖度高、关联度强、难度可控
3. **图状态自适应测评**：基于知识状态图选择最优下一题，信息增益最大化
4. **分层讲解**：从单概念到概念链到知识网络，根据用户状态自动调整讲解深度

**劣势**：
1. 答题数据积累不足，IRT 参数估计不够可靠（需要 ≥100 人次/题）
2. Bloom 认知层级映射是启发式的，可能不够精确
3. 出题质量依赖 LLM，存在幻觉风险，需要人工校验
4. 概念难度初始值是启发式的（描述文本复杂度 + 图中心性），需要历史数据校准

### 3.4 混合检索模块

#### 3.4.1 详细流程

```
用户查询
    │
    ▼
QueryRewriter → 查询重写/扩展
    │
    ├──────────────┬──────────────┐
    ▼              ▼              ▼
BM25 检索      VectorSearch    KnowledgeGraph
(稀疏向量)     (密集向量)       (图谱检索)
    │              │              │
    └──────────────┴──────────────┘
                   │
                   ▼
            RRF 融合（k=60）
                   │
                   ▼
            Reranker（Cross-Encoder）
                   │
                   ▼
            LLM 生成回答（DeepSeek API）
                   │
                   ▼
              用户看到回答
```

**Graph 检索策略（ConceptRetriever）**：

| 策略 | 方法 | 数据层 | 使用 Embedding | 优势 |
|:---|:---|:---|:---|:---|
| 1. 精确匹配 | `name = 'RAG'` | KùzuDB CanonicalConcept | 否 | 100% 精确，可解释性强 |
| 2. 模糊匹配 | `name CONTAINS 'RAG'` | KùzuDB CanonicalConcept | 否 | 容错性强，无需 embedding 计算 |
| 3. 别名匹配 | `aliases CONTAINS 'RAG'` | KùzuDB CanonicalConcept | 否 | 支持同义词和缩写 |
| 4. Embedding 回退 | `vector_store.query("RAG")` | HybridRetriever | 是 | 发现图查询未覆盖的新关联 |

#### 3.4.2 技术栈及选型对比

| 组件 | 选型 | 备选方案 | 选型理由 |
|:---|:---|:---|:---|
| **BM25** | 自研（基于 rank_bm25） | Elasticsearch, Whoosh | 轻量，无需外部服务；Elasticsearch 需要独立服务器 |
| **向量检索** | ChromaDB + 智谱 Embedding | Faiss, Annoy, HNSW | ChromaDB 支持本地文件存储，API 简洁；Faiss 需要自行管理索引 |
| **重排序** | Cross-Encoder（自研） | BGE-Reranker, Cohere Rerank | 自研 Cross-Encoder 可针对特定领域微调；BGE-Reranker 通用但可能不够精确 |
| **融合策略** | RRF（k=60） | 加权求和, Borda Count | RRF 简单有效，不需要训练参数；加权求和需要调参 |

#### 3.4.3 同类项目定位与优劣势

| 场景 | 向量检索 | 图查询 | 混合策略 | 胜出方 |
|:---|:---|:---|:---|:---|
| 单跳事实查找 | 直接匹配语义相似文本，速度快 | 需要遍历路径，开销大 | 向量优先 | **向量** ✅ |
| 多跳推理 | 无法发现跨 chunk 关联 | 显式遍历关系链 | 图优先 | **图** ✅ |
| 实体消歧 | 容易混淆语义相似但实体不同 | 节点唯一标识 + 关系上下文 | 图优先 | **图** ✅ |
| 全局摘要/聚合 | 只能返回局部文本片段 | 社区检测 + 全局聚合 | 图优先 | **图** ✅ |
| 细粒度细节检索 | 精确匹配文本内容 | 实体粒度粗，可能丢失细节 | 向量优先 | **向量** ✅ |

**核心优势**：
1. **图优先 + 向量回退**：前 3 个策略是确定性的（结果可预测、可解释），只有全部失败时才触发 embedding 回退，避免了纯 embedding 检索的语义漂移风险
2. **并行执行潜力**：图查询与向量检索可以并行执行，结果融合，兼顾延迟和覆盖度
3. **可解释性**：图查询的路径清晰（RAG → DEPENDS_ON → 向量检索），而纯向量检索是黑盒

**劣势**：
1. 当前实现是串行策略（精确 → 模糊 → 别名 → Embedding），未实现并行执行，延迟较高
2. 图查询与向量检索的结果融合策略是简单的 RRF，未实现更复杂的融合算法（如 Learned Fusion）
3. 向量验证（用 embedding 验证图查询结果的语义相关性）尚未实现，可能引入伪命中

---

## 4. 整体创新点

### 4.1 架构创新：双层知识图谱

**传统 RAG**：文档 → 分块 → Embedding → 向量检索 → 文本拼接 → LLM  
**GraphRAG**：文档 → 分块 → 实体提取 → 实体消解 → 单层实体图谱 → 图查询 → LLM  
**LearnAnything**：文档 → 分块 → **ExtractedConcept（提取概念层）** → **CanonicalConcept（规范概念层）** → 双层图谱 → 图查询 + 向量检索 → LLM

**创新点**：显式保留"提取概念"和"规范概念"之间的分离，既支持语义去重，又保留原始溯源能力。

### 4.2 功能创新：从"检索"到"学习闭环"

传统 RAG 系统的边界在"检索 + 生成"。LearnAnything 将边界扩展到：

```
导入材料 → 构建图谱 → 可视化探索 → 出题 → 测评 → 讲解 → 学习路径推荐
```

这是一个完整的**知识学习闭环**，而非简单的问答系统。

### 4.3 工程创新：端到端溯源

**每一层都保留溯源信息**：
- CanonicalConcept → source_chunks（原始 chunk ID）
- ExtractedConcept → 来源 chunk 文本
- Chunk → heading_path（章节路径）+ page_number（页码）
- 题目 → knowledge_trace（概念链）+ source_trace（文档位置）

**全链路可验证**：用户可以随时点击节点，查看原始文档内容，验证 LLM 生成的题目和讲解是否基于真实材料。

### 4.4 技术整合创新：多范式概念提取

支持三种概念提取范式（理论归纳、工程分解、层级归纳），不同范式适用于不同材料类型：
- 理论型材料（论文/教材）→ 理论归纳：提取内在逻辑链
- 技术型材料（需求文档/设计）→ 工程分解：提取需求→技术关系
- 通用知识（百科/综述）→ 层级归纳：提取认知层次

**动态范式选择**：用户可以根据材料类型选择最适合的提取范式，提高概念提取质量。

---

## 5. 总结与展望

### 5.1 项目总结

LearnAnything 是一个面向通用知识学习的 RAG 系统，通过**双层知识图谱架构**（文档层 + 概念层）实现了从非结构化文档到结构化知识的转化。系统支持多格式文档导入、智能分块、多范式概念提取、语义去重与连接、图谱可视化、以及基于多 Agent 协作的出题、测评与讲解功能。

**已实现的核心能力**：
- 双层知识图谱构建（Phase 1 + Phase 2 + Phase 2.5）
- 文档树 + 概念树双视图可视化
- 图谱动态出题（Quiz Agent）
- 图状态自适应测评（Coach Agent）
- 图谱溯源讲解（Tutor Agent）
- 混合检索（BM25 + 向量 + 图查询）

**待完善的方向**：
- 段落排序优化（递归子树布局）
- IRT 难度校准（需要积累答题数据）
- 能力画像可视化
- 学科插件化
- 多模态支持（视频/音频）

### 5.2 学术价值

本项目在学术上的贡献包括：
1. **双层概念图谱架构**：在 GraphRAG 的实体提取-消解流程基础上，增加了显式的"提取概念层"保留，实现了语义去重与溯源能力的平衡
2. **多范式概念提取**：将不同领域的知识提取需求抽象为三种范式，提高了概念提取的灵活性和质量
3. **图状态知识追踪**：基于知识图谱拓扑结构的用户状态追踪，不依赖深度学习模型，适合数据稀缺的场景

### 5.3 工程价值

本项目的工程价值包括：
1. **端到端开源**：从文档导入到知识图谱构建到可视化到学习 Agent，完整链路可复用
2. **模块化设计**：文档处理、分块、提取、去重、连接、可视化、Agent 各模块独立，可替换升级
3. **本地优先**：所有组件（ChromaDB、KùzuDB、SQLite）都支持本地运行，无需外部云服务，保护数据隐私

---

## 附录 A：项目文件结构

```
LearnAnything/
├── app/
│   ├── backend_api.py          # FastAPI 主入口
│   └── ...
├── core/
│   ├── document_processor.py   # 文档处理（PDF/Markdown/图片）
│   ├── markdown_chunker.py     # Markdown 分块（v2.0）
│   ├── graph_store.py          # KùzuDB 图数据库封装
│   ├── vector_store.py         # ChromaDB 向量数据库封装
│   ├── semantic_extractor.py   # 概念提取（LLM）
│   ├── concept_deduper.py      # 概念去重（embedding）
│   ├── semantic_linker.py      # 语义连接（LLM）
│   ├── hybrid_retriever.py     # 混合检索（BM25 + 向量）
│   ├── vlm_client.py           # VLM 图片解析（GLM-4V）
│   └── ...
├── agents/
│   ├── coordinator.py          # Agent 协调器
│   ├── quiz_agent.py           # 出题 Agent
│   ├── coach_agent.py          # 测评 Agent
│   └── tutor_agent.py          # 讲解 Agent
├── web-vue/
│   ├── src/
│   │   ├── components/
│   │   │   ├── graph/
│   │   │   │   ├── GraphView.vue      # 主图谱视图
│   │   │   │   ├── GraphLayout.js     # 布局算法
│   │   │   │   ├── GraphStyles.js     # 样式配置
│   │   │   │   ├── NodeDetailPanel.vue # 节点详情
│   │   │   │   └── GraphNodeTooltip.vue # 悬浮提示
│   │   │   ├── ChatView.vue          # 对话学习
│   │   │   ├── QuizView.vue          # 出题评测
│   │   │   └── ImportView.vue        # 导入管理
│   │   └── App.vue
│   └── ...
├── docs/
│   ├── DESIGN.md                   # 总体设计文档
│   ├── data-model-v2.md            # 数据模型设计
│   ├── design-two-phase-extraction.md  # 两阶段提取设计
│   ├── design-graph-education-agent.md   # 图谱教育 Agent 设计
│   ├── design-markdown-chunk-semantic-aggregation.md  # 分块与聚合设计
│   ├── concept-view-layout.md      # 概念视图布局设计
│   └── leftover-problem.md         # 遗留问题追踪
└── README.md
```

## 附录 B：关键技术指标

| 指标 | 数值 | 说明 |
|:---|:---|:---|
| 支持文档格式 | 5+ | PDF, Markdown, TXT, PNG, JPG |
| 分块策略 | 3 | 标题分块, 语义分块, 学科专用分块 |
| 概念提取范式 | 3 | 理论归纳, 工程分解, 层级归纳 |
| 去重阈值 | 0.85 | cosine 相似度 |
| 图数据库 | KùzuDB | 嵌入式, Cypher 兼容 |
| 向量维度 | 2048 | 智谱 AI Embedding |
| 检索策略 | 4 | 精确匹配, 模糊匹配, 别名匹配, Embedding 回退 |
| Agent 数量 | 3+ | Quiz, Coach, Tutor, Coordinator |
| 可视化节点数 | 441+ | 单学科测试数据 |
| 可视化边数 | 967+ | BELONGS_TO 关系 |

---

*本文档为草稿版本，待后续细化补充技术细节、实验数据和性能评估。*
