# LA-040: 基于四层图架构的知识图谱出题/测评/答案讲解 Agent 优化技术方案

> 版本: 1.0  
> 创建日期: 2026-07-14  
> 项目: LearnAnything  
> 关联: 知识图谱四层架构、Quiz Agent、Coach Agent、Tutor Agent  
> 参考论文: KAQG (arXiv:2505.07618, 2025), GraphRAG Survey (2025), RAG for Education (2025)

---

## 一、背景与目标

### 1.1 当前问题

LearnAnything 已构建双层知识图谱（文档层 + 概念层），但 Quiz Agent、Coach Agent、Tutor Agent 尚未充分利用图谱信息：

| 维度 | 当前状态 | 问题 |
|:---|:---|:---|
| 出题 | 纯向量检索 + LLM 生成 | 题目与知识点关联弱，无法跨概念综合出题 |
| 测评 | 逐题评分，无知识追踪 | 无法定位薄弱知识点，无法生成靶向学习路径 |
| 答案讲解 | 基于检索到的文本块讲解 | 缺乏概念关联，讲解碎片化，难以形成知识网络 |
| 溯源 | source_chunks 字段 | 仅关联到 chunk，未关联到规范概念和文档结构 |

### 1.2 最终目标

建立**图谱驱动的智能教育 Agent 体系**，实现：

1. **精准出题**：基于知识图谱的拓扑结构和认知层级，生成覆盖度广、关联度高、难度可控的题目
2. **智能测评**：基于图的知识追踪（Graph-based Knowledge Tracing），定位薄弱节点，生成能力画像
3. **深度讲解**：基于概念关联网络的溯源讲解，从"点"到"面"构建知识理解
4. **全链路溯源**：题目 → 答案 → 讲解，均可追溯到规范概念 → 原始概念 → Chunk → 文档位置

---

## 二、四层图架构的教育价值映射

### 2.1 各层在出题/测评/讲解中的角色

```
┌──────────────────────────────────────────────────────────────────────────┐
│  L4: 语义连接层 (CanonicalConcept 间)                                     │
│  ├── SOLUTION: 需求概念 ──→ 技术概念（"用什么解决什么"）                   │
│  ├── DEPENDS_ON: 技术概念 ──→ 需求概念（"依赖什么前提"）                   │
│  └── 教育价值: 出题关联性、跨概念综合题、解题路径分析                        │
├──────────────────────────────────────────────────────────────────────────┤
│  L3: 规范概念层 (CanonicalConcept)                                       │
│  ├── 186 个全局去重概念节点                                               │
│  ├── 概念类型: requirement / sub_requirement / technology / sub_technology │
│  ├── 属性: description, parent_hint, source_chunks, media_refs, aliases   │
│  └── 教育价值: 题目锚点、知识点标签、能力目标单元                           │
├──────────────────────────────────────────────────────────────────────────┤
│  L2: 原始概念层 (ExtractedConcept)                                       │
│  ├── 1489 个提取概念节点（chunk 内去重）                                   │
│  ├── extract_role: DEFINES / HAS_LAW / APPLIES_TO / EXTENDS              │
│  ├── HAS_CONCEPT 边: Chunk → ExtractedConcept                            │
│  └── 教育价值: 题目上下文、原始表述多样性、同义改写来源                       │
├──────────────────────────────────────────────────────────────────────────┤
│  L1: 文档片段层 (Chunk)                                                  │
│  ├── BELONGS_TO: 文档层级结构 (document → heading → paragraph)            │
│  ├── ADJACENT_TO: 页码相邻关系                                            │
│  ├── heading_path: 章节路径溯源                                           │
│  └── 教育价值: 题目出处定位、原文证据引用、多媒体素材                         │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 图谱 → 教育能力的映射矩阵

| 图谱元素 | 出题能力 | 测评能力 | 讲解能力 |
|:---|:---|:---|:---|
| **CanonicalConcept.name** | 题目知识点标签 | 能力维度评估 | 核心概念解释 |
| **CanonicalConcept.description** | 题干素材来源 | — | 答案要点依据 |
| **concept_type** | 题型映射（req→应用题, tech→概念题） | 能力层级（Bloom分类） | 讲解侧重点 |
| **SOLUTION 边** | 跨概念综合题（A的解决方案是B） | 关联知识点掌握度 | 解题思路引导 |
| **DEPENDS_ON 边** | 前置知识检测题 | 知识依赖缺口识别 | 前置知识回顾 |
| **DERIVED_FROM 边** | 多源表述改写 | — | 多角度解释 |
| **HAS_CONCEPT 边** | 上下文约束 | — | 原文定位 |
| **BELONGS_TO 树** | 章节覆盖度 | — | 文档结构导航 |
| **heading_path** | 题目出处 | — | 章节定位 |
| **media_refs** | 图文题素材 | — | 多媒体讲解 |

---

## 三、核心设计方案

### 3.1 总体架构：Graph-Education-Agent (GEA)

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户交互层                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  出题界面    │  │  测评界面    │  │  答案讲解/错题本界面      │  │
│  └──────┬──────┘  └──────┬──────┘  └────────────┬────────────┘  │
└─────────┼────────────────┼──────────────────────┼───────────────┘
          │                │                      │
          ▼                ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent 编排层 (Coordinator)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Quiz Agent  │  │ Coach Agent │  │      Tutor Agent        │  │
│  │   (出题)     │  │   (测评)    │  │    (答案讲解/辅导)       │  │
│  └──────┬──────┘  └──────┬──────┘  └────────────┬────────────┘  │
└─────────┼────────────────┼──────────────────────┼───────────────┘
          │                │                      │
          └────────────────┼──────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                图谱感知 RAG 层 (Graph-Aware RAG)                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  3.1.1 概念检索器 (Concept Retriever)                      │  │
│  │  3.1.2 子图构建器 (Subgraph Builder)                       │  │
│  │  3.1.3 路径增强器 (Path Augmentor)                         │  │
│  │  3.1.4 上下文组装器 (Context Assembler)                    │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌─────────────────┐ ┌─────────────┐ ┌─────────────────┐
│  L3 概念语义层   │ │ L2 原始语境层 │ │  L1 文档证据层   │
│ CanonicalConcept│ │ExtractedConcept│ │     Chunk       │
└─────────────────┘ └─────────────┘ └─────────────────┘
```

### 3.2 图谱感知 RAG：四大核心模块

#### 3.2.1 概念检索器 (Concept Retriever)

**功能**：将用户查询/出题需求映射到知识图谱中的 CanonicalConcept 节点。

**输入**：用户查询（如"出题：Transformer 注意力机制，难度中等"）

**处理流程**：
```python
# 步骤 1: 查询理解 → 提取目标概念
query = "Transformer 注意力机制，难度中等"
# → 识别概念: ["Transformer", "注意力机制"]
# → 识别难度: "中等"
# → 识别题型偏好: 未指定 → 默认混合

# 步骤 2: 图谱语义检索
# 方法 A: 名称精确/模糊匹配
matched_concepts = graph.query("""
    MATCH (c:CanonicalConcept)
    WHERE c.name CONTAINS '注意力' OR c.name CONTAINS 'Attention'
       OR ANY(alias IN c.aliases WHERE alias CONTAINS '注意力')
    RETURN c.canonical_id, c.name, c.concept_type, c.description
""")

# 方法 B: Embedding 语义检索（名称+描述+aliases 的联合 embedding）
# 使用 CanonicalConcept 的 embedding 做向量相似度检索
semantic_matches = vector_search(
    query_embedding, 
    index="canonicalconcept_embeddings",
    top_k=5
)

# 步骤 3: 概念扩展（基于图拓扑）
# 获取相关概念：1-hop 邻居 + 2-hop 可达概念
expanded_concepts = graph.expand(
    seed=matched_concepts,
    hop=2,
    edge_types=["SOLUTION", "DEPENDS_ON"],
    max_nodes=20
)
```

**输出**：目标概念集 + 相关概念集 + 概念子图

#### 3.2.2 子图构建器 (Subgraph Builder)

**功能**：围绕目标概念构建用于出题/测评/讲解的局部子图。

**三种子图模式**：

| 模式 | 用途 | 构建规则 |
|:---|:---|:---|
| **Star Subgraph** | 单概念深入考察 | 中心节点 + 1-hop 邻居 + 所有 DERIVED_FROM 来源 |
| **Chain Subgraph** | 跨概念推理题 | SOLUTION/DEPENDS_ON 路径上的所有节点 |
| **Tree Subgraph** | 综合应用题 | 共同前置概念 → 多个平行概念 → 综合应用 |

**构建示例**（Chain Subgraph 用于跨概念推理题）：
```cypher
// 查找 "多头注意力" → "缩放点积注意力" → "注意力机制" 的依赖链
MATCH path = (start:CanonicalConcept {name: "多头注意力"})-
             [:DEPENDS_ON*1..3]->(end:CanonicalConcept)
WHERE end.name = "注意力机制"
RETURN path, nodes(path) as concept_chain, relationships(path) as edges
```

#### 3.2.3 路径增强器 (Path Augmentor)

**功能**：基于子图拓扑，为 LLM 生成提供"图感知的推理路径"。

**核心算法**：

1. **概念权重计算（PageRank 变体）**
   ```python
   # 基于图拓扑计算概念重要性
   # SOLUTION 出度高的概念 = 核心解决方案（常作为出题切入点）
   # DEPENDS_ON 入度高的概念 = 基础依赖（常作为前置考察点）
   concept_importance = pagerank(graph, 
       alpha=0.85,
       weight_attr='confidence',
       direction='both'
   )
   ```

2. **认知层级映射（Bloom's Taxonomy）**
   ```python
   # 将 concept_type + 图位置 映射到 Bloom 认知层级
   bloom_mapping = {
       # 根节点 / 高入度 → 记忆/理解
       ('requirement', 'high_in_degree'): 'remember/understand',
       # SOLUTION 边中间节点 → 应用/分析
       ('technology', 'mid_chain'): 'apply/analyze',
       # 多依赖汇聚节点 → 评价/创造
       ('requirement', 'high_betweenness'): 'evaluate/create',
   }
   ```

3. **难度系数计算（参考 KAQG 的 IRT 整合思路）**
   ```python
   # 难度 = f(概念图中心性, 关联概念数, 概念描述复杂度, 历史答题数据)
   difficulty_score = (
       0.3 * (1 - concept_importance[concept_id]) +  # 越边缘越难
       0.3 * min(len(neighbors) / 10, 1.0) +         # 关联越多越难
       0.2 * min(len(description) / 500, 1.0) +      # 描述越长越难
       0.2 * historical_difficulty                   # 历史难度数据
   )
   ```

#### 3.2.4 上下文组装器 (Context Assembler)

**功能**：将图谱子图组装为 LLM 可理解的结构化上下文。

**组装格式**（Graph-to-Text）：
```markdown
## 目标知识点
- 概念: [多头注意力机制]
- 类型: [technology]
- 描述: [描述文本...]
- 关联媒体: [图片1, 公式1]

## 前置知识（依赖链）
1. [注意力机制] → 类型: [concept] → 描述: [...]
2. [缩放点积注意力] → 类型: [sub_technology] → 描述: [...]

## 应用场景（解决方案指向）
1. [Transformer编码器] 使用 [多头注意力] 解决 [长距离依赖捕获]
2. [BERT模型] 依赖 [多头注意力] 实现 [双向上下文理解]

## 来源文档
- 文档: [Attention_Is_All_You_Need.pdf]
- 章节: [3.2 Multi-Head Attention]
- 页码: [4-5]
- 原文摘录: ["多头注意力允许模型在不同位置共同关注来自不同表示子空间的信息..."]
```

---

## 四、Quiz Agent：图谱驱动出题

### 4.1 出题流程

```
用户输入 ──→ 意图解析 ──→ 概念检索 ──→ 子图构建 ──→ 难度校准 ──→ LLM 出题 ──→ 后处理 ──→ 输出
                │           │           │           │
                ▼           ▼           ▼           ▼
            [提取目标    [名称匹配   [选择子图   [Bloom层级
             概念/难度/   + Embedding + 拓扑分析 + 历史数据
             题型偏好]    语义检索]   确定关联]   校准难度]
```

### 4.2 题型与图谱结构的映射

| 题型 | 图谱触发条件 | 出题策略 |
|:---|:---|:---|
| **概念定义题** | 单个 CanonicalConcept，高描述完整性 | 直接考察 description 中的核心定义 |
| **概念辨析题** | 两个相似 CanonicalConcept（aliases 重叠） | 利用 aliases 和 description 差异设计干扰项 |
| **关系推理题** | 存在 SOLUTION/DEPENDS_ON 边的概念对 | 考察"A 如何解决 B"或"C 依赖 D 的什么前提" |
| **跨概念综合题** | 多跳路径（2-hop+）上的概念链 | 设计需要多步推理的应用场景题 |
| **前置知识检测题** | 高 DEPENDS_ON 入度的概念 | 考察依赖链上的基础概念 |
| **图文结合题** | Chunk 包含 media_refs（图片/公式/表格） | 结合媒体素材设计分析题 |

### 4.3 题目溯源机制

**每道题目必须携带溯源信息**：

```json
{
  "question_id": "q_transformer_001",
  "question_text": "多头注意力机制中，缩放点积注意力的计算为什么要除以√d_k？",
  "options": [...],
  "correct_answer": "B",
  
  "knowledge_trace": {
    "primary_concepts": ["concept_canonical_xxx"],
    "secondary_concepts": ["concept_canonical_yyy", "concept_canonical_zzz"],
    "concept_chain": ["注意力机制", "缩放点积注意力", "多头注意力"],
    "bloom_level": "understand",
    "difficulty_score": 0.45,
    "difficulty_label": "中等"
  },
  
  "source_trace": {
    "canonical_sources": [
      {
        "concept_id": "concept_canonical_xxx",
        "derived_from": ["extracted_001", "extracted_045"],
        "source_chunks": ["chunk_003", "chunk_012"],
        "documents": ["Attention_Is_All_You_Need.pdf"],
        "heading_paths": ["3.2.1 Scaled Dot-Product Attention", "3.2.2 Multi-Head Attention"],
        "page_numbers": [4, 5],
        "media_refs": ["fig_1_attention_diagram", "eq_1_scaled_dot_product"]
      }
    ]
  }
}
```

### 4.4 Prompt 设计（图谱感知出题）

```markdown
# Role: 教育领域出题专家
# Task: 基于知识图谱生成高质量测试题目

## 输入信息
{assembled_context}  // 来自 Context Assembler

## 出题要求
1. 题目必须锚定于目标知识点: {primary_concept}
2. 认知层级要求: {bloom_level}（记忆/理解/应用/分析/评价/创造）
3. 难度系数: {difficulty_score}（0-1，越高越难）
4. 题型: {question_type}
5. 前置知识: 题目应隐含考察前置概念链: {prerequisite_chain}

## 出题规则
- 题干必须基于真实文档内容，不得虚构知识点
- 选项设计需利用概念别名(aliases)设计合理干扰项
- 正确答案必须在来源文档中有明确依据
- 每道题必须可追溯到具体的 Chunk 和文档位置

## 输出格式
```json
{{
  "question": "...",
  "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
  "correct_answer": "B",
  "explanation": "...",
  "bloom_level": "...",
  "knowledge_tags": ["..."],
  "prerequisites": ["..."]
}}
```
```

---

## 五、Coach Agent：图谱驱动测评

### 5.1 测评模式升级

| 模式 | 传统方式 | 图谱升级方式 |
|:---|:---|:---|
| **诊断测评** | 随机抽题 | 图谱覆盖度采样：确保各概念区域都有题目覆盖 |
| **自适应测评** | 基于正确率调整难度 | 基于知识状态图（Knowledge State Graph）选择最优下一题 |
| **靶向测评** | 用户指定主题 | 基于概念依赖链自动选择检测路径 |
| **综合测评** | 固定试卷 | 基于图中心性动态组卷：核心概念权重更高 |

### 5.2 知识状态图 (Knowledge State Graph)

**定义**：每个用户在 CanonicalConcept 层上的掌握状态子图。

```cypher
// 用户知识状态节点（动态创建）
CREATE NODE TABLE UserKnowledgeState (
    state_id STRING PRIMARY KEY,
    user_id STRING,
    canonical_id STRING,           // 关联的规范概念
    mastery_level FLOAT,           // 掌握程度 0.0-1.0
    confidence FLOAT,              // 置信度
    last_tested TIMESTAMP,         // 上次测试时间
    test_count INT64,              // 测试次数
    streak INT64                   // 连续正确次数
)

// 用户状态与概念图谱的关联
CREATE REL TABLE HAS_STATE (
    FROM User TO UserKnowledgeState,
    MANY_MANY
)
```

**更新规则（参考 IRT + 图传播）**：
```python
def update_knowledge_state(user_id, question, is_correct):
    """
    更新用户知识状态，并沿图传播
    """
    # 1. 更新直接关联概念的掌握度（IRT 似然更新）
    for concept_id in question.primary_concepts:
        state = get_state(user_id, concept_id)
        state.mastery_level = irt_update(
            state.mastery_level,
            question.difficulty_score,
            is_correct
        )
    
    # 2. 沿 DEPENDS_ON 边传播（前置知识推理）
    # 如果用户答对了依赖 X 的题目，则 X 的掌握度也提升
    if is_correct:
        for concept_id in question.primary_concepts:
            prerequisites = graph.get_predecessors(concept_id, edge_type="DEPENDS_ON")
            for prereq in prerequisites:
                state = get_state(user_id, prereq)
                state.mastery_level = min(1.0, state.mastery_level + 0.05)
    
    # 3. 沿 SOLUTION 边传播（应用能力推理）
    # 如果用户答错了 X 的应用题，则 X 的掌握度需重新评估
    if not is_correct:
        for concept_id in question.primary_concepts:
            applications = graph.get_successors(concept_id, edge_type="SOLUTION")
            for app in applications:
                state = get_state(user_id, app)
                state.confidence *= 0.9  # 降低置信度
```

### 5.3 自适应选题算法（Graph-based Adaptive Testing）

```python
def select_next_question(user_id, subject_id):
    """
    基于知识状态图选择最优下一题
    """
    # 1. 获取用户当前知识状态子图
    user_graph = get_user_knowledge_subgraph(user_id, subject_id)
    
    # 2. 识别"信息增益最高"的概念区域
    # 优先选择：掌握度不确定（confidence 低）+ 图中心性高（重要）的概念
    candidate_concepts = []
    for state in user_graph.states:
        info_gain = (1 - state.confidence) * state.centrality
        candidate_concepts.append((state.canonical_id, info_gain))
    
    # 3. 选择信息增益最高的概念
    target_concept = max(candidate_concepts, key=lambda x: x[1])[0]
    
    # 4. 围绕目标概念检索候选题目池
    candidate_questions = question_bank.query(
        concept_id=target_concept,
        difficulty_range=[target_mastery - 0.2, target_mastery + 0.2]
    )
    
    # 5. 选择与用户当前状态最匹配的题
    # 使用 IRT 最大信息量准则
    best_question = max(candidate_questions, 
        key=lambda q: irt_information(q.difficulty, user_graph.get_ability()))
    
    return best_question
```

### 5.4 能力画像生成

**输出**：基于知识状态图的可视化能力报告

```json
{
  "user_id": "user_xxx",
  "subject_id": "transformer",
  "assessment_date": "2026-07-14",
  
  "overall_mastery": 0.67,
  "total_concepts": 186,
  "mastered_concepts": 89,
  "in_progress_concepts": 67,
  "weak_concepts": 30,
  
  "concept_clusters": {
    "核心机制": {"mastery": 0.82, "concepts": ["注意力机制", "多头注意力", "..."]},
    "架构设计": {"mastery": 0.61, "concepts": ["编码器", "解码器", "..."]},
    "训练优化": {"mastery": 0.45, "concepts": ["学习率调度", "..."]}
  },
  
  "knowledge_gaps": [
    {
      "concept": "位置编码",
      "mastery": 0.2,
      "prerequisites": ["序列建模基础"],
      "recommended_resources": ["chunk_023", "chunk_024"],
      "suggested_questions": ["q_pos_enc_001", "q_pos_enc_002"]
    }
  ],
  
  "learning_path": [
    "位置编码 → 注意力机制 → 多头注意力 → Transformer 完整架构"
  ]
}
```

---

## 六、Tutor Agent：图谱驱动答案讲解

### 6.1 讲解深度分级

| 层级 | 触发条件 | 讲解策略 |
|:---|:---|:---|
| **L1 点讲解** | 单概念选择题答错 | 定位到 CanonicalConcept，解释核心定义 |
| **L2 链讲解** | 关系推理题答错 | 展示 SOLUTION/DEPENDS_ON 路径，讲解概念关联 |
| **L3 面讲解** | 综合题答错 / 多次同区域错误 | 展示局部子图，从依赖到应用的完整知识网络 |
| **L4 溯源讲解** | 任意错题 | 追溯到原文 Chunk，展示 heading_path 和 media_refs |

### 6.2 讲解内容组装

**输入**：用户答案 + 题目溯源信息 + 用户知识状态

**组装流程**：
```python
def assemble_explanation(question, user_answer, user_id):
    """
    组装分层讲解内容
    """
    # 1. 获取题目关联的概念子图
    concept_subgraph = graph.get_subgraph(
        node_ids=question.knowledge_trace.primary_concepts,
        depth=2,
        include_edges=["SOLUTION", "DEPENDS_ON", "DERIVED_FROM"]
    )
    
    # 2. 获取用户在这些概念上的历史状态
    user_states = {
        c: get_state(user_id, c) 
        for c in concept_subgraph.nodes
    }
    
    # 3. 确定讲解深度
    if user_answer == question.correct_answer:
        depth = "L1"  # 简要确认
    elif len(question.knowledge_trace.concept_chain) > 2:
        depth = "L3"  # 综合题 → 面讲解
    elif get_error_count(user_id, question.primary_concepts[0]) > 2:
        depth = "L3"  # 重复错误 → 面讲解
    else:
        depth = "L2"  # 默认链讲解
    
    # 4. 组装讲解上下文
    context = {
        "concept_subgraph": concept_subgraph,
        "user_states": user_states,
        "source_chunks": get_source_chunks(question),
        "media_refs": get_media_refs(question),
        "heading_paths": get_heading_paths(question),
        "prerequisites": get_prerequisites(question)
    }
    
    return generate_explanation(depth, context)
```

### 6.3 讲解 Prompt 设计

```markdown
# Role: 耐心且专业的学习导师
# Task: 为用户的错题提供图谱化的深度讲解

## 题目信息
- 题目: {question_text}
- 用户答案: {user_answer}
- 正确答案: {correct_answer}

## 关联知识子图
{concept_subgraph_text}

## 用户知识状态
- 目标概念掌握度: {target_mastery}%
- 前置知识掌握度: {prereq_mastery}%
- 该概念历史错误次数: {error_count}

## 来源文档
{source_context}

## 讲解要求
1. **先定位**: 指出用户错误的核心概念
2. **再关联**: 展示该概念在知识网络中的位置（前置依赖 → 核心定义 → 应用场景）
3. **给证据**: 引用原文 Chunk 的内容作为依据
4. **做对比**: 如果选项利用了 aliases 差异，解释为何干扰项不正确
5. **推路径**: 根据用户当前状态，推荐下一步学习内容

## 输出格式
```
【核心错因】
...

【知识定位】
- 概念: ...（在图谱中的位置）
- 前置知识: ...
- 应用场景: ...

【原文依据】
> "..."（来源: {heading_path}, 第{page}页）

【选项分析】
A. ...（为什么不选）
B. ...（正确原因）
...

【推荐学习】
1. 优先补强: {weak_prerequisite}
2. 巩固练习: {recommended_questions}
3. 延伸阅读: {related_chunks}
```
```

---

## 七、关键技术实现

### 7.1 新增数据库 Schema

```cypher
// ========== 题目库 ==========
CREATE NODE TABLE Question (
    question_id STRING PRIMARY KEY,
    subject_id STRING,
    question_text STRING,
    question_type STRING,          // choice/fill_blank/essay
    options STRING,                // JSON: {"A": "...", "B": "..."}
    correct_answer STRING,
    explanation STRING,
    difficulty_score FLOAT,
    difficulty_label STRING,       // 简单/中等/困难
    bloom_level STRING,            // remember/understand/apply/analyze/evaluate/create
    primary_concepts STRING,       // JSON 数组: [canonical_id, ...]
    secondary_concepts STRING,     // JSON 数组
    concept_chain STRING,          // JSON 数组: 概念依赖链
    source_trace STRING,           // JSON: 溯源信息
    created_at TIMESTAMP,
    usage_count INT64,             // 使用次数
    correct_rate FLOAT             // 历史正确率
)

// ========== 用户知识状态 ==========
CREATE NODE TABLE UserKnowledgeState (
    state_id STRING PRIMARY KEY,
    user_id STRING,
    canonical_id STRING,
    mastery_level FLOAT,           // 0.0-1.0
    confidence FLOAT,              // 0.0-1.0
    test_count INT64,
    correct_count INT64,
    last_tested TIMESTAMP,
    streak INT64                   // 连续正确次数
)

// ========== 答题记录 ==========
CREATE NODE TABLE AnswerRecord (
    record_id STRING PRIMARY KEY,
    user_id STRING,
    question_id STRING,
    user_answer STRING,
    is_correct BOOL,
    time_spent INT64,              // 答题用时（秒）
    timestamp TIMESTAMP
)

// ========== 关系表 ==========
CREATE REL TABLE TESTS_CONCEPT (
    FROM Question TO CanonicalConcept,
    MANY_MANY
)

CREATE REL TABLE HAS_STATE (
    FROM User TO UserKnowledgeState,
    ONE_MANY
)

CREATE REL TABLE ANSWERS (
    FROM User TO AnswerRecord,
    ONE_MANY
)

CREATE REL TABLE RECORDS_ANSWER (
    FROM AnswerRecord TO Question,
    MANY_ONE
)
```

### 7.2 新增 API 接口

```python
# ========== 出题 API ==========
@router.post("/quiz/generate")
async def generate_questions(
    subject_id: str,
    target_concepts: List[str] = None,     # 目标概念列表（可选）
    count: int = 5,
    difficulty: str = "mixed",              # easy/medium/hard/mixed
    question_types: List[str] = ["choice"], # 题型
    bloom_levels: List[str] = None,         # 认知层级过滤
    require_media: bool = False,            # 是否需要图文题
):
    """
    基于知识图谱生成题目
    """

# ========== 测评 API ==========
@router.post("/evaluate/start-adaptive")
async def start_adaptive_test(
    subject_id: str,
    user_id: str,
    max_questions: int = 20,
    target_concepts: List[str] = None,
):
    """
    启动自适应测评
    """

@router.post("/evaluate/submit")
async def submit_answer(
    session_id: str,
    question_id: str,
    user_answer: str,
    time_spent: int,
):
    """
    提交答案，返回即时反馈 + 下题推荐
    """

# ========== 讲解 API ==========
@router.post("/tutor/explain")
async def explain_answer(
    question_id: str,
    user_id: str,
    user_answer: str,
    depth: str = "auto",  # L1/L2/L3/L4/auto
):
    """
    生成图谱化的答案讲解
    """

# ========== 能力画像 API ==========
@router.get("/user/{user_id}/profile/{subject_id}")
async def get_knowledge_profile(user_id: str, subject_id: str):
    """
    获取用户知识能力画像
    """
```

### 7.3 核心模块实现优先级

| 优先级 | 模块 | 工作量 | 依赖 |
|:---|:---|:---|:---|
| P0 | Concept Retriever + Subgraph Builder | 3天 | 现有图谱 schema |
| P0 | Context Assembler (Graph-to-Text) | 2天 | P0 |
| P0 | 题目溯源数据结构 + 接口 | 2天 | P0 |
| P1 | Quiz Agent 图谱化改造 | 3天 | P0 |
| P1 | 题目库 schema + CRUD | 2天 | — |
| P1 | UserKnowledgeState 状态管理 | 3天 | 题目库 |
| P2 | Coach Agent 自适应测评 | 4天 | P1 |
| P2 | 能力画像生成 | 2天 | P1 |
| P2 | Tutor Agent 图谱讲解 | 3天 | P0 + P1 |
| P3 | IRT 难度校准 | 3天 | 积累足够答题数据 |
| P3 | 前端能力画像可视化 | 3天 | P2 |

---

## 八、参考论文与技术来源

| 论文/资料 | 年份 | 贡献点 | 本方案应用 |
|:---|:---|:---|:---|
| **KAQG: Knowledge-Graph-Enhanced RAG for Difficulty-Controlled Question Generation** (Chen et al., arXiv:2505.07618) | 2025 | IRT + Bloom + KG + 多Agent RAG 整合框架；多图谱隔离；PageRank 概念权重；难度控制 | 整体架构参考；IRT 难度校准；多 Agent 协作模式 |
| **Graph Retrieval-Augmented Generation: A Survey** (ACM Computing Surveys) | 2025 | GraphRAG 全面综述；图拓扑增强检索；子图构建方法 | 图谱感知 RAG 设计；子图构建策略 |
| **Retrieval-Augmented Generation for Educational Application** (ScienceDirect) | 2025 | RAG 在教育场景的系统综述；51项研究综合分析；教育内容生成与评估 | 教育场景需求分析；出题/测评/讲解的功能定义 |
| **Knowledge Graph Prompting for Multi-Document Question Answering** (AAAI 2024) | 2024 | KG 增强多文档问答；动态图遍历检索 | 概念检索器设计；跨 chunk 上下文组装 |
| **G-Retriever: Retrieval-Augmented Generation for Textual Graph Understanding** (NeurIPS 2024) | 2024 | 文本图理解与问答的 RAG 方法；图结构编码 | 子图编码为 LLM 上下文 |
| **Self-RAG** (NeurIPS Workshop 2023) | 2023 | 自反思检索生成；检索决策的自适应性 | Quiz Agent 的检索决策优化 |
| **北京市教育领域人工智能应用实施导引** | 2025 | 政策层面定义智能出题/组卷/答疑的能力要求 | 功能需求对齐；知识图谱关联评测的合理性验证 |
| **人工智能赋能基础教育应用蓝皮书** (北师大) | 2025 | 智能出题应聚焦核心素养培育、认知轨迹、复杂问题解析 | 出题策略设计；认知层级映射 |

---

## 九、遗留问题与后续讨论点

1. **IRT 参数估计**：需要积累多少答题记录才能进行可靠的 IRT 参数估计？（建议 ≥100 人次/题）
2. **概念难度标注**：CanonicalConcept 的初始 difficulty_score 如何设定？（可用描述文本复杂度 + 图中心性启发式）
3. **多学科通用性**：UserKnowledgeState 是否跨学科共享？（建议按学科隔离）
4. **实时性 vs 准确性**：自适应测评的选题算法需要实时图计算，是否需要预计算概念中心性？
5. **LLM 幻觉控制**：Graph-to-Text 的上下文长度限制如何平衡信息量与 token 消耗？
6. **Top-N 种子概念选择**：当前 `resolve()` 只取模糊匹配 Top-1，应支持返回 Top-N 让用户/前端选择（LA-040-P0-QUIZ-IMPROV，详见遗留问题追踪）

---

## 附录：P0-QUIZ 最终设计实现（2026-07-18 验证通过）

> 记录 P0-QUIZ 从设计到最终实现的完整修复链路，供后续参考。

### 修复链路（7 轮迭代）

| 轮次 | 日期 | 问题 | 修复 |
|------|------|------|------|
| 1 | 2026-07-16 | P0-INT 设计未落地 | 实现 Coordinator 集成、QuizAgent 使用 ContextAssembler、CoachAgent 使用 IRTEstimator、UserKnowledgeState SQLite 持久化、消息总线 |
| 2 | 2026-07-17 | KuzuDB 文件锁定 | 全局 `_graph_store_cache`，每个学科共享一个 GraphStore 实例 |
| 3 | 2026-07-17 | API 端点绕过 Coordinator | `/api/quiz` 和 `/api/evaluate/start` 走 Coordinator + 共享 GraphStore |
| 4 | 2026-07-17 | QuizAgent 未订阅消息总线 | `_subscribe_to_message_bus` → `on_ability_updated` + `on_weak_area_detected` |
| 5 | 2026-07-17 | TutorAgent 未接入 P0 | `handle()` 接受 `graph_context` 参数，`_handle_with_graph_context` 使用图谱上下文 |
| 6 | 2026-07-18 | `QuizRequest` 缺少 `user_id` | 添加 `user_id: Optional[str] = None` 到 `QuizRequest` / `EvaluateStartRequest` |
| 7 | 2026-07-18 | 主题提取失败 | `_extract_topic_from_query` 使用正则：`on/about/关于 {topic}` 和 `evaluate my {topic} level` |
| 8 | 2026-07-18 | `resolve()` 抛异常 | 改为返回空列表 + PageRank Top-5 兜底 |
| 9 | 2026-07-18 | 概念匹配过于严格 | `_match_fuzzy` 双向包含 + case-insensitive Python 回退 |
| 10 | 2026-07-18 | `vector_store` 未传入 | Coordinator 传入 `HybridRetriever` 使 embedding 语义检索可用 |

### 最终架构

```
前端出题请求 → POST /api/quiz
  → QuizRequest (topic, subject, count, user_id)
  → backend_api.generate_quiz
    → get_graph_store(subject) → 共享 GraphStore
    → Coordinator.handle(query, user_id)
      → IntentRouter: "quiz" 意图
      → P0-INT-1: 使用图谱教育模块
        → _extract_topic_from_query(query) → "rag 技术"
        → ConceptRetriever.resolve(["rag 技术"])
          → 策略1: 精确匹配 → 失败
          → 策略2: _match_fuzzy (双向包含 + case-insensitive)
            → Cypher: name CONTAINS 'rag 技术' OR 'rag 技术' CONTAINS name → 0 结果
            → Python 回退: 'rag 技术'.lower() contains 'rag' → 匹配 'RAG'
          → 返回 1 个种子概念
        → SubgraphBuilder.build(seed_concepts, max_depth=2, max_nodes=15)
          → 从 "RAG" 扩展 1-hop 邻居
          → 返回子图 (11 节点, 10 边)
        → ContextAssembler.assemble(subgraph, budget=2000 tokens)
          → 返回 910 tokens 的图谱上下文
      → QuizAgent.handle(query, graph_context=graph_context)
        → P0-INT-2: 使用 P0 图谱上下文出题
        → 图谱上下文概念: ['RAG', 'RAG好处', ... '生成器模块']
        → 生成基于图谱结构的 5 道题目
      → MessageBus.publish(quiz_generated)
        → CoachAgent 订阅 quiz 主题，加入待评测队列
    → QuizResponse (questions, ...)
```

### 关键接口定义

```python
# ConceptRetriever.resolve
# 输入: 概念名称列表
# 输出: 匹配的概念节点列表（策略：精确 → 模糊 → 别名 → Embedding → PageRank Top-5 兜底）

# _match_fuzzy (双向包含 + case-insensitive)
# 1. Cypher 查询: c.name CONTAINS '{name}' OR '{name}' CONTAINS c.name
# 2. 如果 Cypher 返回 0，Python 回退: c.name.lower() in name.lower() or name.lower() in c.name.lower()
# 3. 如果仍无匹配，尝试 word-by-word: 查询词中的每个单词被概念名包含

# Coordinator._extract_topic_from_query
# 模式1: re.search(r'(?:on|about|关于)\s+(.+?)', query)
# 模式2: re.search(r'evaluate\s+my\s+(.+?)\s+level', query)
# 模式3: 停用词过滤 + 数字去除
```

### 验证日志示例

```
[Coordinator] P0-INT-1: 使用图谱教育模块为 quiz 意图组装上下文
[Coordinator] 提取主题: rag 技术
[ConceptRetriever._match_fuzzy] Case-sensitive Cypher returned 0 nodes
[ConceptRetriever._match_fuzzy] Case-insensitive match: 'rag 技术' <-> 'RAG'
[Coordinator] 解析到 1 个种子概念
[Coordinator] 构建子图: 11 节点, 10 边
[Coordinator] 组装上下文: 910 tokens
[QuizAgent] P0-INT-2: 使用 P0 图谱上下文出题
```

---

*文档结束 — 等待进一步讨论和细化*
