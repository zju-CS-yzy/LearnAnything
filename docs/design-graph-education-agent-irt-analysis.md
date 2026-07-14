# LA-040-1: IRT 工作原理与实时图计算需求分析

> 2026-07-14 讨论记录  
> 关联: LA-040 图谱教育 Agent 方案

---

## 一、IRT（项目反应理论）工作原理

### 1.1 核心思想

IRT（Item Response Theory）用**概率模型**描述考生能力和题目特性之间的关系。

与经典测量理论（CTT，即传统"得分/总分"）的区别：

| 维度 | CTT（经典理论） | IRT（项目反应理论） |
|:---|:---|:---|
| 难度定义 | 这道题的平均得分率 | 能力值 θ=b 时，答对概率恰好 50% |
| 能力测量 | 依赖于具体试卷 | 与试卷无关，不同试卷可比 |
| 题目参数 | 没有独立参数 | 每道题有难度(b)、区分度(a)、猜测度(c) |
| 自适应能力 | 弱 | 强——可以精确选择"最匹配"下一题 |
| 适用场景 | 常规考试 | 标准化考试（SAT、GRE、高考自适应卷） |

### 1.2 核心参数

IRT 用 **3 个参数** 描述一道题：

#### ① 难度参数（b）
- **定义**：ICC 曲线上答对概率 = 50% 时对应的能力值
- **范围**：通常 -3 ~ +3（logit 尺度）
- **含义**：b=0 表示中等难度；b=1.5 表示很难；只有 θ=1.5 的考生才有 50% 概率做对
- **与我们的映射**：CanonicalConcept 的 `difficulty_score` 可以映射到 b 参数

#### ② 区分度参数（a）
- **定义**：ICC 曲线在 b 点处的**斜率**（陡峭程度）
- **范围**：通常 0 ~ 3
- **含义**：a 越大，曲线越陡。意味着在 b 点附近，能力微小提升 → 答对概率大幅提升。题目能很好区分"刚好会"和"刚好不会"的人
- **高区分度题目的价值**：筛出真正的能力边界
- **与我们的映射**：可以基于选项设计质量（干扰项与正确项的语义距离）来估计 a

#### ③ 猜测度参数（c）
- **定义**：能力极低时（θ→-∞），纯靠猜答对的概率
- **范围**：0 ~ 1
- **含义**：4 选 1 选择题，c 理论值 ≈ 0.25；判断题 c ≈ 0.5
- **与我们的映射**：选择题直接取 0.25；填空题/问答题 c=0

### 1.3 项目特征曲线（ICC）

```
答对概率 P
    1.0 │                              ╱────
       │                          ╱───
    0.8 │                      ╱───
       │                  ╱───
    0.6 │              ╱───
       │          ╱───
    0.4 │      ╱───                    ← c（猜测度）
       │  ╱───
    0.2 │─
       │
    0.0 └──────────────────────────────→ 能力 θ
         -3    -2    -1     0     1     2     3
                        ↑
                        b（难度）—— 50%概率点

    曲线斜率 = a（区分度）
```

**三参数模型（3PL）公式**：
```
P(θ) = c + (1-c) / (1 + exp[-a(θ - b)])
```

- θ：考生能力（估计值，-3~+3）
- a、b、c：题目参数（已校准）
- P(θ)：该能力水平的考生答对此题的概率

### 1.4 在自适应测评中的应用

IRT 的核心价值是**能回答两个问题**：

1. **给定考生能力 θ，某题的信息量是多少？**
   ```
   I(θ) = a² * P(θ) * (1-P(θ)) / (1-c)²
   ```
   - 当 θ ≈ b 时，信息量最大（题目最能"精准测量"这个能力水平的考生）
   - **自适应选题**：选 I(θ) 最大的题，花最少的题最精准地定位能力

2. **答完若干题后，考生的能力 θ 估计值是多少？**
   - 用最大似然估计（MLE）或贝叶斯估计，根据答题序列反推 θ

### 1.5 对我们的意义

| 能力 | 当前做法 | IRT 升级后 |
|:---|:---|:---|
| 难度定义 | 基于描述文本长度 + 图中心性启发式 | 基于历史答题数据校准出 b 参数 |
| 自适应选题 | 简单过滤（难度±0.2 范围） | I(θ) 最大化，每道题都是"最优信息" |
| 能力估计 | 正确率 | θ 值，与试卷无关的可比度量 |
| 题目质量评估 | 无 | 低 a 值的题自动标记"区分度差，需优化" |

### 1.6 校准所需数据量

IRT 参数估计需要**足够多的答题数据**才能收敛。经验法则：

- **Rasch 模型（1PL，只估计 b）**：≥ 50 人作答/题，或 ≥ 20 题 × 50 人 = 1000 条记录
- **2PL（a+b）**：≥ 100 人/题 或 ≥ 200 题 × 100 人
- **3PL（a+b+c）**：≥ 200 人/题（c 最难估计）

**我们的策略**：
```
阶段1（无数据）：用启发式 b（基于概念图中心性 + 描述复杂度）
阶段2（少量数据，50-100人/题）：用 Rasch 模型校准 b，固定 a=1.0
阶段3（足够数据，200+人/题）：用 2PL 校准 a 和 b
阶段4（长期运营）：用 3PL 全面校准，题目自动质量评估
```

---

## 二、实时图计算需求分析

### 2.1 需要实时图计算的场景

| 场景 | 触发时机 | 计算的图 | 实时性要求 | 计算复杂度 |
|:---|:---|:---|:---|:---|
| **自适应选题** | 用户答完一题后立即选下一题 | 知识状态子图 + 题目-概念关联图 | 高（<500ms） | 中等 |
| **能力画像更新** | 答完一题后更新 | 用户状态图 + CanonicalConcept 图 | 高（<200ms） | 低 |
| **知识传播** | 答对/答错后沿图传播 | DEPENDS_ON / SOLUTION 边 | 高（<100ms） | 低 |
| **出题子图构建** | 用户请求出题时 | CanonicalConcept + 语义连接 | 中（<2s） | 中等 |
| **讲解子图构建** | 用户答错后请求讲解 | 题目关联概念 + 2-hop 邻居 | 中（<2s） | 中等 |
| **覆盖度检测** | 生成试卷时 | 全图概念节点 + 用户状态 | 低（离线） | 高 |
| **中心性预计算** | 概念更新时 | 全图 | 低（离线/增量） | 高 |

### 2.2 实时计算的具体节点和边

#### 场景 A：自适应选题（最高频、最实时）

```
输入: user_id, subject_id

实时计算的节点:
  ├─ UserKnowledgeState 节点（该用户在该学科的所有状态）
  │   └─ 属性: mastery_level, confidence, last_tested
  │
  ├─ CanonicalConcept 节点（该学科的概念）
  │   └─ 属性: concept_type, difficulty_score (初始b)
  │
  └─ Question 节点（候选题目池）
      └─ 属性: difficulty_score, primary_concepts, usage_count

实时计算的边:
  ├─ User → HAS_STATE → UserKnowledgeState（1:N）
  ├─ Question → TESTS_CONCEPT → CanonicalConcept（M:N）
  ├─ CanonicalConcept → SOLUTION → CanonicalConcept（知识依赖）
  └─ CanonicalConcept → DEPENDS_ON → CanonicalConcept（知识依赖）

计算过程:
  1. 读取用户状态子图（~50-200 个状态节点）
  2. 计算每个概念的信息增益 = (1-confidence) × centrality
  3. 找到目标概念 → 查询关联的候选题目
  4. 计算每道题的 IRT 信息量 I(θ)
  5. 返回 I(θ) 最大的题
```

#### 场景 B：能力画像更新（高频、实时）

```
输入: user_id, question_id, is_correct

实时计算的节点:
  ├─ UserKnowledgeState（该用户在该题关联概念上的状态）
  └─ CanonicalConcept（关联概念）

实时计算的边:
  ├─ CanonicalConcept → DEPENDS_ON → CanonicalConcept（前置知识传播）
  └─ CanonicalConcept → SOLUTION → CanonicalConcept（应用能力传播）

计算过程:
  1. 更新直接关联概念的 mastery_level（IRT 更新）
  2. 沿 DEPENDS_ON 反向传播（答对 → 前置知识+0.05）
  3. 沿 SOLUTION 正向传播（答错 → 应用概念 confidence×0.9）
  4. 更新 streak、test_count 等
```

#### 场景 C：出题子图构建（中频）

```
输入: target_concepts, difficulty, count

实时计算的节点:
  ├─ CanonicalConcept（目标概念）
  ├─ CanonicalConcept（1-hop 邻居）
  ├─ ExtractedConcept（DERIVED_FROM 来源）
  └─ Chunk（HAS_CONCEPT 来源）

实时计算的边:
  ├─ CanonicalConcept → SOLUTION → CanonicalConcept
  ├─ CanonicalConcept → DEPENDS_ON → CanonicalConcept
  ├─ ExtractedConcept → DERIVED_FROM → CanonicalConcept
  └─ Chunk → HAS_CONCEPT → ExtractedConcept

计算过程:
  1. 种子概念匹配
  2. 2-hop BFS 扩展
  3. 子图拓扑分析（路径、环、中心性）
  4. 按题型规则选择子图模式
  5. 组装为 Graph-to-Text 上下文
```

### 2.3 数据来源

| 数据类型 | 来源 | 存储位置 | 更新频率 |
|:---|:---|:---|:---|
| CanonicalConcept 节点 | 概念提取 + 去重 | KùzuDB L3 层 | 构建图谱时（低频） |
| 语义连接边 | LLM 提取 + 规则 | KùzuDB L4 层 | 构建图谱时（低频） |
| UserKnowledgeState | 答题过程动态生成 | KùzuDB / SQLite | 每次答题（高频） |
| Question 节点 | Quiz Agent 生成 + 人工审核 | KùzuDB / 关系数据库 | 出题时（中频） |
| 题目-概念关联 | 出题时自动标注 | Question 表的 JSON 字段 | 出题时（中频） |
| 图中心性/权重 | PageRank 预计算 | 缓存表 / Redis | 图谱更新后（低频） |

### 2.4 实时性策略建议

#### 策略 1：预计算 + 缓存（解决高频场景）

```python
# 预计算：图谱更新后批量计算
page_rank = compute_pagerank(canonical_graph)
betweenness = compute_betweenness(canonical_graph)

# 存入缓存
for concept_id, score in page_rank.items():
    cache.set(f"pr:{concept_id}", score, ttl=86400)

# 实时查询：自适应选题时直接从缓存读取
concept_centrality = cache.get(f"pr:{concept_id}")  # O(1)
```

#### 策略 2：用户状态子图缓存（解决高频场景）

```python
# 用户登录时，将其在该学科的知识状态子图加载到内存
user_state_graph = load_user_subgraph(user_id, subject_id)

# 答题过程中只在内存中更新，批量写回数据库
# 每 N 题或每 M 分钟同步一次到持久化存储
```

#### 策略 3：实时计算 vs 离线计算的分界

| 计算类型 | 策略 | 说明 |
|:---|:---|:---|
| 图中心性（PageRank/Betweenness） | **离线预计算** | 图谱更新后重新计算，结果缓存 |
| 概念难度（b 参数） | **离线校准** | 积累足够数据后用 EM 算法批量估计 |
| 用户能力（θ） | **实时估算** | 用简单公式（如 Elo 更新）快速近似 |
| 知识传播 | **实时** | 沿边简单传播，O(1)~O(degree) |
| 信息量计算（I(θ)） | **实时** | 基于预计算的 b 和实时估计的 θ，O(1) |
| 子图构建 | **实时** | 小规模 BFS（2-hop，限制 20 节点），O(100) |
| 全图覆盖度检测 | **离线** | 生成试卷时检查，不阻塞用户交互 |

#### 策略 4：分层存储

```
热数据（高频访问）          温数据（中频访问）          冷数据（低频访问）
├─ 用户当前状态子图          ├─ 用户历史答题记录          ├─ 全图概念节点
├─ 缓存的图中心性            ├─ 题目库                    ├─ Chunk 文本内容
├─ 预计算的题目信息           ├─ 概念别名/描述             ├─ ExtractedConcept
│                            │                            └─ 媒体文件
│
存储: Redis/Memory           存储: KùzuDB/SQLite          存储: KùzuDB/文件系统
TTL: 会话级/分钟级           更新: 准实时                 更新: 构建时
```

---

## 三、UserKnowledgeState 分学科隔离

**确认：按学科隔离。**

理由：
1. 不同学科的概念空间完全不同（"注意力机制"在 Transformer 中 vs 心理学中）
2. 用户在不同学科的能力水平通常不相关（物理好不代表英语好）
3. 能力画像需要学科内可比，跨学科比较无意义

实现方式：

```cypher
// UserKnowledgeState 的复合键
state_id = f"{user_id}#{subject_id}#{canonical_id}"

// 查询某用户在某学科的状态
MATCH (u:User {user_id: "user_001"})-[:HAS_STATE]->(s:UserKnowledgeState)
WHERE s.subject_id = "transformer"
RETURN s
```

---

## 四、以参考试卷为基准的上下文平衡策略

### 4.1 核心思路

以真实标准化考试（高考、考研、考公）为**物理基准**，确定：
1. **题量**：一张试卷能承载多少道题？
2. **信息密度**：每道题需要多少知识关联？
3. **难度分布**：简单:中等:困难的比例？
4. **考试时间**：考生答题节奏如何？
5. **LLM 上下文限制**：对应到多少 token 的图谱信息？

### 4.2 参考数据

#### 高考（以全国新课标 I 卷数学为例）

| 维度 | 数据 |
|:---|:---|
| 总题量 | 22 题（8 选择 + 4 多选 + 4 填空 + 6 解答） |
| 考试时间 | 120 分钟 |
| 平均时间/题 | 选择/填空 2-3 分钟；解答 10-15 分钟 |
| 难度分布 | 简单 60% + 中等 25% + 困难 15% |
| 每题信息关联 | 选择题通常 1-2 个知识点；解答题 3-5 个知识点 |
| 试卷总信息 | 约 3000-5000 汉字（题干+选项） |
| 考生阅读量 | 约 5000-8000 字/小时 |

#### 考研（以数学一为例）

| 维度 | 数据 |
|:---|:---|
| 总题量 | 22 题（10 选择 + 6 填空 + 6 解答） |
| 考试时间 | 180 分钟 |
| 难度分布 | 基础 50% + 综合 35% + 高难 15% |
| 每题信息关联 | 选择题 2-3 知识点；解答题 4-6 知识点（跨章节） |
| 试卷总信息 | 约 4000-6000 汉字 |
| 考生阅读量 | 约 3000-5000 字/小时（计算量大，阅读时间被压缩） |

#### 考公（以行测为例）

| 维度 | 数据 |
|:---|:---|
| 总题量 | 130-135 题（常识 20 + 言语 40 + 数量 15 + 判断 40 + 资料 20） |
| 考试时间 | 120 分钟 |
| 平均时间/题 | ~53 秒/题（极端时间压力） |
| 难度分布 | 模块间差异大，整体约 4:3:3 |
| 每题信息关联 | 常识/言语 1 知识点；资料分析 3-5 知识点（图表+计算） |
| 试卷总信息 | 约 8000-10000 汉字（题量大） |

### 4.3 映射到 LLM 上下文

**核心假设**：LLM 生成一道题时，"图谱信息"相当于考生需要调用的"知识储备"。

| 考试类型 | 人类考生知识储备 | 对应 LLM 上下文 | 图谱信息策略 |
|:---|:---|:---|:---|
| 高考 | 3年学习 + 教材 + 笔记 | 中等（~2k-3k tokens） | 单概念 + 1-hop 邻居 |
| 考研 | 4年本科 + 系统复习 | 较大（~3k-5k tokens） | 单概念 + 2-hop 子图 |
| 考公行测 | 广泛知识 + 技巧训练 | 分散（多模块，各 1k） | 多独立概念，低关联 |

**具体策略**：

```python
CONTEXT_BUDGET = {
    "easy": {        # 简单题 → 类似高考选择题
        "max_tokens": 1500,      # ~500 中文字
        "subgraph_depth": 1,     # 1-hop 邻居
        "max_nodes": 5,          # 中心 + 4 邻居
        "concept_chain": False,  # 不需要依赖链
    },
    "medium": {      # 中等题 → 类似高考解答题
        "max_tokens": 2500,      # ~800 中文字
        "subgraph_depth": 2,     # 2-hop 邻居
        "max_nodes": 12,         # 小局部子图
        "concept_chain": True,   # 包含依赖链
    },
    "hard": {        # 困难题 → 类似考研综合题
        "max_tokens": 4000,      # ~1300 中文字
        "subgraph_depth": 2,     # 2-hop
        "max_nodes": 20,         # 较大子图
        "concept_chain": True,   # 完整依赖链
        "multi_path": True,      # 多条路径
    }
}
```

### 4.4 用户上传试卷后的校准

用户上传真实试卷（如考研真题 PDF）后，系统：

1. **解析试卷结构**：MinerU 提取题目 → 识别题型、数量、难度分布
2. **建立试卷模板**：
   ```json
   {
     "exam_name": "2025考研数学一",
     "total_questions": 22,
     "time_limit": 180,
     "difficulty_ratio": {"easy": 0.5, "medium": 0.35, "hard": 0.15},
     "question_patterns": [
       {"type": "choice", "count": 10, "time_per_q": 3, "context_tokens": 1500},
       {"type": "fill_blank", "count": 6, "time_per_q": 5, "context_tokens": 1500},
       {"type": "essay", "count": 6, "time_per_q": 20, "context_tokens": 3000}
     ]
   }
   ```
3. **动态调整出题策略**：
   - 题量对齐试卷模板
   - 难度分布对齐试卷模板
   - 每题的 context_tokens 对齐同类题型
   - 考试时间用于模拟考试模式（倒计时）

4. **用户自定义目标**：
   - 用户说"我想达到考研水平" → 使用考研模板参数
   - 用户说"我只想巩固基础" → 使用高考模板，但难度偏向简单
   - 用户上传自己的试卷 → 解析为该用户的专属模板

### 4.5 上下文与图谱信息量的平衡公式

```python
def balance_context(subgraph, template, question_type):
    """
    基于试卷模板动态调整图谱信息量
    """
    # 基础预算
    base_tokens = template["question_patterns"].find(q => q.type == question_type)["context_tokens"]
    
    # 图谱信息预算 = 总预算 - 固定开销（prompt框架、题目元数据）
    graph_budget = base_tokens - 800  # 预留 800 tokens 给 prompt 框架
    
    # 根据子图节点数动态精简
    nodes = subgraph.nodes()
    if len(nodes) > 20:
        # 子图过大，优先保留：目标概念 + 直接依赖 + 最高中心性邻居
        nodes = prioritize_nodes(nodes, keep=20)
    
    # 文本化后的 token 估算
    estimated_tokens = estimate_tokens(subgraph_to_text(nodes))
    
    if estimated_tokens > graph_budget:
        # 超过预算，逐层裁剪描述文本
        for node in nodes:
            if node.description_tokens > 100:
                node.description = truncate(node.description, 100)
        
        # 仍超预算，减少节点
        while estimated_tokens > graph_budget and len(nodes) > 5:
            nodes.remove(least_important_node(nodes))
            estimated_tokens = estimate_tokens(subgraph_to_text(nodes))
    
    return nodes
```

---

## 五、总结与下一步讨论

| 议题 | 结论 | 待决策 |
|:---|:---|:---|
| IRT | 分阶段实施：Rasch → 2PL → 3PL | 阶段 1 的启发式 b 参数公式是否需现在确定？ |
| 学科隔离 | ✅ 确认按学科隔离 | — |
| 实时图计算 | 高频场景用预计算+缓存；低频场景允许实时 | 缓存技术选型（Redis？内存？） |
| 上下文平衡 | 以参考试卷为基准，动态调整 | 是否需要先实现"试卷模板解析"模块？ |

**建议下一步**：
1. 先确定 P0 模块（Concept Retriever + Subgraph Builder + Context Assembler）的接口契约
2. 同时设计"试卷模板"数据结构和解析流程（支持用户上传试卷校准）
3. 用户回到电脑前验证 P19 修复后，优先启动 P0 开发

---

*记录时间：2026-07-14 11:52*
