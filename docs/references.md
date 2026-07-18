# LearnAnything 项目参考文献汇总表

> 版本: 1.0  
> 创建日期: 2026-07-14  
> 说明: 本文档汇总了 LearnAnything 项目所有设计文档中引用的论文、报告和技术资料。

---

## 一、图谱教育 Agent 体系（LA-040 系列）

| # | 论文/资料标题 | 作者/来源 | 年份 | 核心贡献 | 在本项目中的应用 |
|:---|:---|:---|:---:|:---|:---|
| 1 | **KAQG: Knowledge-Graph-Enhanced RAG for Difficulty-Controlled Question Generation** | Chen et al., arXiv:2505.07618 | 2025 | IRT + Bloom + KG + 多 Agent RAG 整合框架；多图谱隔离；PageRank 概念权重；难度控制 | 整体架构参考；IRT 难度校准；多 Agent 协作模式 |
| 2 | **Graph Retrieval-Augmented Generation: A Survey** | ACM Computing Surveys | 2025 | GraphRAG 全面综述；图拓扑增强检索；子图构建方法 | 图谱感知 RAG 设计；子图构建策略 |
| 3 | **Retrieval-Augmented Generation for Educational Application** | ScienceDirect | 2025 | RAG 在教育场景的系统综述；51 项研究综合分析；教育内容生成与评估 | 教育场景需求分析；出题/测评/讲解的功能定义 |
| 4 | **Knowledge Graph Prompting for Multi-Document Question Answering** | AAAI 2024 | 2024 | KG 增强多文档问答；动态图遍历检索 | 概念检索器设计；跨 chunk 上下文组装 |
| 5 | **G-Retriever: Retrieval-Augmented Generation for Textual Graph Understanding** | NeurIPS 2024 | 2024 | 文本图理解与问答的 RAG 方法；图结构编码 | 子图编码为 LLM 上下文 |
| 6 | **Self-RAG** | NeurIPS Workshop 2023 | 2023 | 自反思检索生成；检索决策的自适应性 | Quiz Agent 的检索决策优化 |
| 7 | **北京市教育领域人工智能应用实施导引** | 北京市教委 | 2025 | 政策层面定义智能出题/组卷/答疑的能力要求 | 功能需求对齐；知识图谱关联评测的合理性验证 |
| 8 | **人工智能赋能基础教育应用蓝皮书** | 北京师范大学 | 2025 | 智能出题应聚焦核心素养培育、认知轨迹、复杂问题解析 | 出题策略设计；认知层级映射 |

**关联设计文档**:
- `docs/design-graph-education-agent.md` — LA-040 总体方案
- `docs/design-graph-education-agent-irt-analysis.md` — IRT 与实时计算分析
- `docs/design-p0-graph-education-agent-detailed.md` — P0 详细设计
- `docs/test-plan-p0-graph-education-agent.md` — P0 测试计划

---

## 二、多 Agent 记忆与协作架构

| # | 论文/资料标题 | 作者/来源 | 年份 | 核心贡献 | 在本项目中的应用 |
|:---|:---|:---|:---:|:---|:---|
| 9 | **G-Memory: Hierarchical Memory for Multi-Agent Systems** | — | 2024 | 为每个 Agent 设计分层记忆结构（集体/团队/个体） | L3 集体记忆（知识图谱）、L2 团队记忆（用户状态/IRT 参数）、L1 个体记忆（Agent 策略） |
| 10 | **A-MEM: Agentic Memory for LLM Agents** | — | 2025 | Agent 主动管理记忆（检索策略、更新策略、优先级排序） | Coach Agent 主动决定画像更新时机；Tutor Agent 主动检索相关知识子图 |
| 11 | **Mem0: Scalable Long-Term Memory** | — | 2025 | 分层记忆存储架构（Vector DB + Graph DB + KV Store） | Graph DB（KùzuDB）用于概念关系；后续补充 Vector DB 和 KV Store |
| 12 | **MetaGPT: Multi-Agent Collaborative Framework** | — | 2024 | 角色分工 + 标准化输出 + 共享消息池 | Agent 标准化输出格式（QuestionGroup, KnowledgeProfile）；Agent 间消息总线 |
| 13 | **Chain-of-Agents** | NeurIPS 2024 | 2024 | 长文本多 Agent 协作链 | 出题流程链式处理：Retriever → Builder → Assembler → LLM |
| 14 | **MA-RAG: Multi-Agent RAG via Collaborative Chain-of-Thought** | — | 2025 | 多 Agent 协作式 RAG，每个 Agent 负责不同检索策略 | Concept Retriever 多策略（名称匹配 + Embedding + 别名）；结果融合机制 |

**关联设计文档**:
- `docs/design-agent-memory-collaboration.md` — 多 Agent 记忆与协作架构

---

## 三、知识图谱构建与语义提取

| # | 论文/资料标题 | 作者/来源 | 年份 | 核心贡献 | 在本项目中的应用 |
|:---|:---|:---|:---:|:---|:---|
| 15 | **MegaRAG** | arXiv:2512.20626v2 | 2026 | 使用 MLLM 对 PDF 每页进行实体关系提取，构建多模态知识图谱 | MinerU 预处理思路借鉴；图片作为实体处理；跨模态关联 |
| 16 | **MoC: Mixtures of Text Chunking Learners** | ACL 2025 | 2025 | Chunk Stickiness / 连接覆盖率 | 语义质量评估五维度中的"连接覆盖率"指标 |

**关联设计文档**:
- `docs/design-image-semantic-classification.md` — 图片语义分类设计
- `docs/effective-decisions.md` — 有效决策记录（决策 2: 语义质量评估五维度）
- `docs/chat-record-brief.md` — 对话简要记录

---

## 五、RAG 架构对比与检索策略

| # | 论文/资料标题 | 作者/来源 | 年份 | 核心贡献 | 在本项目中的应用 |
|:---|:---|:---|:---:|:---|:---|
| 17 | **RAG vs. GraphRAG: A Systematic Evaluation and Key Insights** | arXiv:2502.11371v2 | 2025 | 系统对比 RAG 与 GraphRAG 在单跳/多跳/全局摘要任务上的性能差异；提出 Selection + Integration 混合策略（+6.4 points） | 四层架构检索策略定位；图查询与向量检索的互补性论证 |
| 18 | **SR-RAG: From Evidence-Based Medicine to Knowledge Graph** | arXiv:2601.00216v2 | 2026 | 医学领域 GraphRAG 基准测试；证据召回 R@10 0.812 vs 向量基线 0.643-0.738 | 图检索在复杂领域召回率优势；对比指标设计参考 |
| 19 | **TGS-RAG: A Bidirectional Verification and Completion Framework for RAG** | arXiv:2605.05643v1 | 2026 | 对比 NaiveRAG / HybridRAG / GraphRAG 在 QA 和摘要任务上的表现；GraphRAG 多跳推理优势 | 评估基准设计参考；图检索在 QA 上的优势验证 |
| 20 | **AMG-RAG: Agentic Medical Knowledge Graphs Enhance Medical QA** | arXiv:2502.13010v2 | 2025 | 医学知识图谱增强 RAG 在 MEDQA 上达 73.92%（移除 KG 后降至 67.16%）；验证结构化检索对复杂领域至关重要 | 知识图谱在领域问答中的必要性论证；检索策略消融分析 |
| 21 | **CatRAG: Breaking the Static Graph** | arXiv:2602.01965v1 | 2026 | 提出"Static Graph Fallacy"——固定转移概率导致语义漂移；LLM 引导的动态图遍历 | 图检索中的语义漂移风险；动态遍历优化方向 |
| 22 | **ReMindRAG: Low-Cost LLM-Guided KG Traversal for Efficient RAG** | arXiv:2510.13193v2 | 2025 | LLM 引导图遍历 + 记忆回放；相比传统图遍历降低 50% 查询成本，提升 5-10% 性能 | 图检索效率优化方向；LLM 引导遍历的权衡 |
| 23 | **GraphRAG: RAG pipeline with semantic chunking, cross-encoder reranking, and KG traversal** | GitHub (amruth6002) | 2026 | 工业级 GraphRAG 实现：5-stage pipeline（Query Rewrite → FAISS → Rerank → Dijkstra → LLM） | 混合检索架构设计参考；Dijkstra 图遍历实现 |
| 24 | **GraphRAG vs. Vector RAG: When Knowledge Graphs Outperform Semantic Search** | Fluree Blog / SingleStore Blog | 2026 | 7 种 GraphRAG 优于向量检索的场景：多跳推理、组织层级导航、实体消歧、时间推理等 | 应用场景分析；图检索优势边界定义 |
| 25 | **Microsoft GraphRAG** | Edge et al., arXiv | 2024 | 实体提取 + 社区检测 + 全局/局部搜索；Entity Resolution 合并实体 | 单层实体图谱对比基准；社区检测作为全局摘要方法 |
| 26 | **LightRAG** | Guo et al., arXiv | 2024 | 双级检索（低阶实体 + 高阶社区）；实体与关系嵌入 | 双级检索设计对比；实体嵌入化方案对比 |
| 27 | **HippoRAG** | Gutiérrez et al., arXiv | 2024 | 神经生物学启发的图检索；Personalized PageRank + 认知记忆模型 | PageRank 用于概念重要性排序；认知记忆与图检索结合 |
| 28 | **DA-RAG** | arXiv:2602.08545 | 2026 | 双层架构：Chunk Layer + Knowledge Graph Layer；LLM 判断检索策略切换 | 双层（Chunk+KG）架构对比；我们的"保留两层概念" vs DA-RAG 的"单层 KG" |
| 29 | **RAPTOR** | Sarthi et al., arXiv | 2024 | 树形摘要：叶节点为 chunk，内部节点为聚类摘要；支持多粒度上下文 | 层级树设计对比；RAPTOR 的摘要节点 vs 我们的概念节点 |
| 30 | **RAGAS** | VibrantLabs | 2024 | 专门评估 RAG 系统的框架：Faithfulness, Answer Relevancy, Context Precision, Context Recall | 评估指标设计参考；RAG 系统基准测试方法论 |
| 31 | **KET-RAG** | Huang et al., arXiv:2505.04836 | 2025 | 基于关键词-实体-三元组的分层检索；KG 到文本的桥接 | 关键词→实体→chunk 的桥接设计；层级检索对比 |
| 32 | **StructRAG** | Li et al., arXiv | 2024 | 结构化知识提取 + 层次推理；逻辑结构保持用于复杂文档理解 | 结构保持与知识提取；层次推理设计参考 |
| 33 | **Embeddings + Knowledge Graphs: The Ultimate Tools for RAG** | Towards Data Science | 2025 | 系统对比向量嵌入与知识图谱在 RAG 中的互补作用；7 种 KG 增强检索的场景 | 嵌入与 KG 的协同设计；混合检索架构论证 |
| 34 | **LLM retrieval mechanisms: Graph Traversal vs. Document Search** | ACME AI Tech | 2024 | GraphRAG 与 Notebook LM（文档搜索）的对比；7 场景优劣分析 | 检索机制选择指南；场景化决策框架 |
| 35 | **SOPRAG: Multi-view Graph Experts Retrieval for SOP** | arXiv:2602.01858v1 | 2026 | 工业 SOP 场景的 GraphRAG；MRR 和 Accuracy@K 评估；生成质量（Faithfulness + Answer Relevancy + Context Precision） | 工业场景图检索评估；检索与生成质量联合评估 |
| 36 | **VersionRAG: Version-Aware Retrieval-Augmented Generation** | arXiv:2510.08109v1 | 2025 | 版本感知 RAG；GraphRAG 在版本化文档上仅 64% 准确率；时间动态性挑战 | 图检索的局限性；版本/时间动态性作为未来优化方向 |
| 37 | **Hyper-KGGen: A Skill-Driven Knowledge Extractor** | arXiv:2602.19543 | 2026 | 知识超图生成；对比 NativeRAG / GraphRAG / LightRAG / HiRAG / Hyper-RAG 等 | 超图作为更高阶关系表示；多基线对比方法论 |

**关联设计文档**:
- `docs/DESIGN.md` — §3.4 RAG 架构定位与现有工作对比
- `docs/DESIGN.md` — §3.5 层级知识图谱查询与向量检索的优势比较
- `docs/leftover-problem.md` — 检索策略优化项（P2 优先级）

---

## 六、按主题分类索引

### 6.1 教育 AI / 智能出题

| 论文 | 年份 | 引用位置 |
|:---|:---:|:---|
| KAQG: Knowledge-Graph-Enhanced RAG for Difficulty-Controlled Question Generation | 2025 | LA-040 总体方案 |
| Retrieval-Augmented Generation for Educational Application | 2025 | LA-040 总体方案 |
| 北京市教育领域人工智能应用实施导引 | 2025 | LA-040 总体方案 |
| 人工智能赋能基础教育应用蓝皮书 | 2025 | LA-040 总体方案 |

### 6.2 GraphRAG / 知识图谱

| 论文 | 年份 | 引用位置 |
|:---|:---:|:---|
| Graph Retrieval-Augmented Generation: A Survey | 2025 | LA-040 总体方案 |
| Knowledge Graph Prompting for Multi-Document Question Answering | 2024 | LA-040 总体方案 |
| G-Retriever: Retrieval-Augmented Generation for Textual Graph Understanding | 2024 | LA-040 总体方案 |
| Self-RAG | 2023 | LA-040 总体方案 |
| MegaRAG | 2026 | 图片语义分类设计 |
| **Microsoft GraphRAG** | 2024 | DESIGN §3.4 架构对比 |
| **LightRAG** | 2024 | DESIGN §3.4 架构对比 |
| **HippoRAG** | 2024 | DESIGN §3.4 架构对比 |
| **DA-RAG** | 2026 | DESIGN §3.4 架构对比 |
| **RAPTOR** | 2024 | DESIGN §3.4 架构对比 |
| **KET-RAG** | 2025 | DESIGN §3.4 架构对比 |
| **StructRAG** | 2024 | DESIGN §3.4 架构对比 |
| **RAG vs. GraphRAG: A Systematic Evaluation** | 2025 | DESIGN §3.5 检索对比 |
| **SR-RAG** | 2026 | DESIGN §3.5 检索对比 |
| **TGS-RAG** | 2026 | DESIGN §3.5 检索对比 |
| **AMG-RAG** | 2025 | DESIGN §3.5 检索对比 |
| **CatRAG** | 2026 | DESIGN §3.5 检索对比 |
| **ReMindRAG** | 2025 | DESIGN §3.5 检索对比 |
| **SOPRAG** | 2026 | DESIGN §3.5 检索对比 |
| **VersionRAG** | 2025 | DESIGN §3.5 检索对比 |
| **Hyper-KGGen** | 2026 | DESIGN §3.5 检索对比 |
| **Embeddings + Knowledge Graphs: The Ultimate Tools for RAG** | 2025 | DESIGN §3.4-3.5 架构与检索对比 |
| **GraphRAG vs. Vector RAG: When Knowledge Graphs Outperform Semantic Search** | 2026 | DESIGN §3.5 检索对比 |

### 6.3 多 Agent 系统

| 论文 | 年份 | 引用位置 |
|:---|:---:|:---|
| G-Memory: Hierarchical Memory for Multi-Agent Systems | 2024 | Agent 协作架构 |
| A-MEM: Agentic Memory for LLM Agents | 2025 | Agent 协作架构 |
| Mem0: Scalable Long-Term Memory | 2025 | Agent 协作架构 |
| MetaGPT: Multi-Agent Collaborative Framework | 2024 | Agent 协作架构 |
| Chain-of-Agents | 2024 | Agent 协作架构 |
| MA-RAG: Multi-Agent RAG via Collaborative Chain-of-Thought | 2025 | Agent 协作架构 |

### 6.4 文本分块与语义评估

| 论文 | 年份 | 引用位置 |
|:---|:---:|:---|
| MoC: Mixtures of Text Chunking Learners | 2025 | 语义质量评估五维度 |

### 6.5 评估框架与方法论

| 论文 | 年份 | 引用位置 |
|:---|:---:|:---|
| **RAGAS** | 2024 | DESIGN §3.5 检索对比；评估指标设计参考 |
| **FDABench: A Benchmark for Data Agents** | 2025 | 多系统基准测试方法论 |
| **GraphRAG RAG pipeline (GitHub)** | 2026 | 工业级 GraphRAG 实现参考；5-stage pipeline 设计 |

---

## 七、按设计文档分类索引

| 设计文档 | 引用的论文 # |
|:---|:---|
| `design-graph-education-agent.md` | 1, 2, 3, 4, 5, 6, 7, 8 |
| `design-graph-education-agent-irt-analysis.md` | 1, 2, 3 |
| `design-p0-graph-education-agent-detailed.md` | 1, 2, 3, 4, 5, 6 |
| `test-plan-p0-graph-education-agent.md` | 1, 2, 3, 4, 5, 6 |
| `design-agent-memory-collaboration.md` | 9, 10, 11, 12, 13, 14 |
| `design-image-semantic-classification.md` | 15 |
| `effective-decisions.md` | 16 |
| `chat-record-brief.md` | 16 |
| **DESIGN.md §3.4** | 17, 25, 26, 27, 28, 29, 32, 33, 34 |
| **DESIGN.md §3.5** | 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37 |
| **leftover-problem.md (P2 优化项)** | 21, 22, 30, 33, 34 |

---

## 八、获取途径

| 论文 | 获取方式 |
|:---|:---|
| KAQG (arXiv:2505.07618) | https://arxiv.org/abs/2505.07618 |
| MegaRAG (arXiv:2512.20626v2) | https://arxiv.org/abs/2512.20626v2 |
| MoC (ACL 2025) | ACL Anthology (待发布) |
| GraphRAG Survey | ACM Computing Surveys |
| RAG for Education | ScienceDirect |
| Self-RAG | NeurIPS 2023 Workshop |
| G-Retriever | NeurIPS 2024 |
| Knowledge Graph Prompting | AAAI 2024 |
| Chain-of-Agents | NeurIPS 2024 |
| MetaGPT | 技术报告 / GitHub |
| G-Memory / A-MEM / Mem0 | 技术博客 / 公司文档 |
| MA-RAG | 技术报告 |
| 北京市教育领域 AI 导引 | 北京市教委官网 |
| 北师大蓝皮书 | 北京师范大学出版社 |
| RAG vs. GraphRAG (arXiv:2502.11371v2) | https://arxiv.org/abs/2502.11371v2 |
| SR-RAG (arXiv:2601.00216v2) | https://arxiv.org/abs/2601.00216v2 |
| TGS-RAG (arXiv:2605.05643v1) | https://arxiv.org/abs/2605.05643v1 |
| AMG-RAG (arXiv:2502.13010v2) | https://arxiv.org/abs/2502.13010v2 |
| CatRAG (arXiv:2602.01965v1) | https://arxiv.org/abs/2602.01965v1 |
| ReMindRAG (arXiv:2510.13193v2) | https://arxiv.org/abs/2510.13193v2 |
| GraphRAG vs. Vector RAG (Fluree/SingleStore) | https://www.singlestore.com/blog/rethinking-rag-how-graphrag-improves-multi-hop-reasoning- |
| Embeddings + Knowledge Graphs (Towards Data Science) | https://towardsdatascience.com/embeddings-knowledge-graphs-the-ultimate-tools-for-rag-systems-cbbcca29f0fd/ |
| SOPRAG (arXiv:2602.01858v1) | https://arxiv.org/abs/2602.01858v1 |
| VersionRAG (arXiv:2510.08109v1) | https://arxiv.org/abs/2510.08109v1 |
| Hyper-KGGen (arXiv:2602.19543) | https://arxiv.org/abs/2602.19543 |
| RAGAS | https://docs.ragas.io |
| FDABench (arXiv:2509.02473v1) | https://arxiv.org/abs/2509.02473v1 |

---

*文档结束 — 随项目进展持续更新*
