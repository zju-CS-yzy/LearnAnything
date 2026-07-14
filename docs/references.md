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

## 四、按主题分类索引

### 4.1 教育 AI / 智能出题

| 论文 | 年份 | 引用位置 |
|:---|:---:|:---|
| KAQG: Knowledge-Graph-Enhanced RAG for Difficulty-Controlled Question Generation | 2025 | LA-040 总体方案 |
| Retrieval-Augmented Generation for Educational Application | 2025 | LA-040 总体方案 |
| 北京市教育领域人工智能应用实施导引 | 2025 | LA-040 总体方案 |
| 人工智能赋能基础教育应用蓝皮书 | 2025 | LA-040 总体方案 |

### 4.2 GraphRAG / 知识图谱

| 论文 | 年份 | 引用位置 |
|:---|:---:|:---|
| Graph Retrieval-Augmented Generation: A Survey | 2025 | LA-040 总体方案 |
| Knowledge Graph Prompting for Multi-Document Question Answering | 2024 | LA-040 总体方案 |
| G-Retriever: Retrieval-Augmented Generation for Textual Graph Understanding | 2024 | LA-040 总体方案 |
| Self-RAG | 2023 | LA-040 总体方案 |
| MegaRAG | 2026 | 图片语义分类设计 |

### 4.3 多 Agent 系统

| 论文 | 年份 | 引用位置 |
|:---|:---:|:---|
| G-Memory: Hierarchical Memory for Multi-Agent Systems | 2024 | Agent 协作架构 |
| A-MEM: Agentic Memory for LLM Agents | 2025 | Agent 协作架构 |
| Mem0: Scalable Long-Term Memory | 2025 | Agent 协作架构 |
| MetaGPT: Multi-Agent Collaborative Framework | 2024 | Agent 协作架构 |
| Chain-of-Agents | 2024 | Agent 协作架构 |
| MA-RAG: Multi-Agent RAG via Collaborative Chain-of-Thought | 2025 | Agent 协作架构 |

### 4.4 文本分块与语义评估

| 论文 | 年份 | 引用位置 |
|:---|:---:|:---|
| MoC: Mixtures of Text Chunking Learners | 2025 | 语义质量评估五维度 |

---

## 五、按设计文档分类索引

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

---

## 六、获取途径

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

---

*文档结束 — 随项目进展持续更新*
