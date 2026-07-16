# LA-040-P0: 图谱教育 Agent P0 模块详细设计文档

> 版本: 1.0  
> 创建日期: 2026-07-14  
> 关联: LA-040 总体方案、LA-040-1 IRT与实时计算分析  
> 覆盖模块: Concept Retriever、Subgraph Builder、Context Assembler、题目溯源、按组选题

---

## 一、设计决策总览

### 1.1 关键决策

| 决策项 | 决策内容 | 理由 |
|:---|:---|:---|
| **按组选题** | 用户以"组"为单位答题，提交整组后统一处理 | 大幅降低实时性要求，允许后台批量图计算 |
| **IRT 冷启动** | 阶段 1 使用启发式难度（Rasch 模型），固定 a=1.0, c=0.25 | 无需积累数据即可启动，数据达标后自动升级 |
| **学科隔离** | UserKnowledgeState 按 `user_id + subject_id` 复合键隔离 | 不同学科能力不相关，画像需学科内可比 |
| **图中心性预计算** | PageRank / Betweenness 在图谱构建后离线计算，结果缓存 | 消除实时图计算的最大开销项 |
| **上下文预算** | 以参考试卷（高考/考研/考公）为物理基准确定 token 预算 | 避免 LLM 幻觉，贴合真实考试信息密度 |

### 1.2 按组选题 vs 逐题实时对比

| 维度 | 逐题实时（原方案） | 按组选题（本方案） |
|:---|:---|:---|
| 交互模式 | 答一题→立即反馈→选下一题 | 选一组题→逐题作答→提交整组→统一反馈 |
| 实时性要求 | 每题 <500ms（自适应选题） | 组内选题可预生成，提交后处理 <3s 即可 |
| 图计算触发 | 每题后触发 | 每组提交后统一触发，可批量/异步 |
| 用户体验 | 类似自适应考试（如 GRE） | 类似常规练习（如章节测试） |
| 实现复杂度 | 高（实时 IRT + 实时图传播） | 中（批量 IRT + 批量图传播） |
| 适用场景 | 诊断测评、自适应考试 | 日常练习、章节测试、复习巩固 |

**决策：P0 阶段先实现按组选题，支持自适应能力画像但非实时。逐题实时模式作为 P2 扩展。**

---

## 二、数据结构设计

### 2.1 试卷模板（ExamTemplate）

```python
@dataclass
class ExamTemplate:
    """
    试卷模板：以真实考试为基准，定义一组题的结构参数
    """
    template_id: str              # 唯一标识，如 "gaokao_math_2025"
    name: str                     # 显示名称，如 "2025年高考数学（新课标I卷）"
    exam_type: str                # 考试类型: gaokao / kaoyan / gongkao / custom
    subject_id: str               # 关联学科
    
    # 时间结构
    total_time_minutes: int       # 总考试时间（分钟）
    
    # 题目结构（每种题型一个配置）
    question_patterns: List[QuestionPattern]
    
    # 难度分布（0-1 概率，总和为 1）
    difficulty_distribution: Dict[str, float]  # {"easy": 0.5, "medium": 0.35, "hard": 0.15}
    
    # 认知层级分布（Bloom）
    bloom_distribution: Dict[str, float]       # {"remember": 0.1, "understand": 0.3, ...}
    
    # LLM 上下文预算（按难度）
    context_budget: Dict[str, ContextBudget]   # 见下文 ContextBudget
    
    # 元数据
    source_exam: Optional[str]     # 来源真实考试名称（如用户上传的试卷）
    is_user_uploaded: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def total_questions(self) -> int:
        return sum(p.count for p in self.question_patterns)


@dataclass
class QuestionPattern:
    """题型配置"""
    pattern_id: str               # 如 "choice_single", "fill_blank", "essay"
    name: str                     # 如 "单项选择题"
    count: int                    # 该题型在试卷中的数量
    time_per_question: int        # 建议每题时间（秒）
    points_per_question: float    # 每题分值
    
    # 图谱上下文预算
    context_budget: ContextBudget
    
    # 概念关联策略
    concept_depth: int = 1        # 子图深度: 1=单概念, 2=概念链
    max_concepts_per_question: int = 5  # 每题关联概念上限
    require_concept_chain: bool = False  # 是否需要完整依赖链


@dataclass
class ContextBudget:
    """LLM 上下文预算"""
    max_tokens: int               # 总 token 预算
    prompt_overhead: int = 800    # 预留 prompt 框架开销
    
    @property
    def graph_tokens(self) -> int:
        return self.max_tokens - self.prompt_overhead
    
    max_nodes: int = 10           # 子图节点数上限
    max_description_length: int = 200  # 每个概念描述截断长度
```

**内置模板（P0 支持）**：

```python
BUILTIN_TEMPLATES = {
    "gaokao_math": ExamTemplate(
        template_id="gaokao_math",
        name="高考数学（新课标I卷）",
        exam_type="gaokao",
        subject_id="*",  # 任意数学相关学科
        total_time_minutes=120,
        question_patterns=[
            QuestionPattern(
                pattern_id="choice_single", name="单项选择题", count=8,
                time_per_question=180, points_per_question=5,
                context_budget=ContextBudget(max_tokens=1500, max_nodes=5),
                concept_depth=1, max_concepts_per_question=3
            ),
            QuestionPattern(
                pattern_id="choice_multi", name="多项选择题", count=4,
                time_per_question=240, points_per_question=5,
                context_budget=ContextBudget(max_tokens=1800, max_nodes=8),
                concept_depth=2, require_concept_chain=True
            ),
            QuestionPattern(
                pattern_id="fill_blank", name="填空题", count=4,
                time_per_question=180, points_per_question=5,
                context_budget=ContextBudget(max_tokens=1500, max_nodes=5),
                concept_depth=1
            ),
            QuestionPattern(
                pattern_id="essay", name="解答题", count=6,
                time_per_question=900, points_per_question=12,
                context_budget=ContextBudget(max_tokens=3000, max_nodes=15),
                concept_depth=2, require_concept_chain=True
            ),
        ],
        difficulty_distribution={"easy": 0.6, "medium": 0.25, "hard": 0.15},
        bloom_distribution={
            "remember": 0.1, "understand": 0.3, "apply": 0.35,
            "analyze": 0.15, "evaluate": 0.05, "create": 0.05
        },
    ),
    
    "kaoyan_math": ExamTemplate(
        template_id="kaoyan_math",
        name="考研数学（数学一）",
        exam_type="kaoyan",
        subject_id="*",
        total_time_minutes=180,
        question_patterns=[
            QuestionPattern(
                pattern_id="choice_single", name="单项选择题", count=10,
                time_per_question=180, points_per_question=5,
                context_budget=ContextBudget(max_tokens=1800, max_nodes=8),
                concept_depth=2, max_concepts_per_question=5
            ),
            QuestionPattern(
                pattern_id="fill_blank", name="填空题", count=6,
                time_per_question=300, points_per_question=5,
                context_budget=ContextBudget(max_tokens=1800, max_nodes=8),
                concept_depth=2
            ),
            QuestionPattern(
                pattern_id="essay", name="解答题", count=6,
                time_per_question=1200, points_per_question=12,
                context_budget=ContextBudget(max_tokens=4000, max_nodes=20),
                concept_depth=2, require_concept_chain=True
            ),
        ],
        difficulty_distribution={"easy": 0.45, "medium": 0.35, "hard": 0.20},
        bloom_distribution={
            "remember": 0.05, "understand": 0.25, "apply": 0.35,
            "analyze": 0.25, "evaluate": 0.05, "create": 0.05
        },
    ),
    
    "quick_practice": ExamTemplate(
        template_id="quick_practice",
        name="快速练习（自定义）",
        exam_type="custom",
        subject_id="*",
        total_time_minutes=15,
        question_patterns=[
            QuestionPattern(
                pattern_id="choice_single", name="单选题", count=5,
                time_per_question=120, points_per_question=1,
                context_budget=ContextBudget(max_tokens=1500, max_nodes=5),
                concept_depth=1
            ),
        ],
        difficulty_distribution={"easy": 0.4, "medium": 0.4, "hard": 0.2},
        bloom_distribution={"understand": 0.4, "apply": 0.4, "analyze": 0.2},
    ),
}
```

### 2.2 题目组（QuestionGroup）—— 核心数据结构

```python
@dataclass
class QuestionGroup:
    """
    题目组：按组选题的核心容器
    一组题在生成时确定，用户作答过程中内容不变
    """
    group_id: str                 # 唯一标识，如 "qg_{uuid}"
    user_id: str
    subject_id: str
    template_id: str              # 使用的试卷模板
    
    # 组状态
    status: GroupStatus = GroupStatus.GENERATED  # generated / in_progress / submitted / graded
    
    # 题目列表（生成时确定，顺序即答题顺序）
    questions: List[Question] = field(default_factory=list)
    
    # 目标概念（生成时确定，用于组题和后续画像）
    target_concepts: List[str] = field(default_factory=list)  # canonical_id 列表
    
    # 元数据
    generated_at: datetime = field(default_factory=datetime.now)
    submitted_at: Optional[datetime] = None
    graded_at: Optional[datetime] = None
    
    # 难度分布（实际生成后的统计）
    actual_difficulty_distribution: Optional[Dict[str, int]] = None
    
    @property
    def total_questions(self) -> int:
        return len(self.questions)
    
    @property
    def is_completed(self) -> bool:
        return self.status in (GroupStatus.SUBMITTED, GroupStatus.GRADED)


class GroupStatus(Enum):
    GENERATED = "generated"       # 已生成，等待用户开始
    IN_PROGRESS = "in_progress"   # 用户正在作答
    SUBMITTED = "submitted"       # 已提交，等待评分/画像更新
    GRADED = "graded"             # 已评分，画像已更新


@dataclass
class Question:
    """
    题目：精简后的核心结构，溯源信息独立存储
    """
    question_id: str              # 唯一标识
    group_id: str                 # 所属组
    sequence: int                 # 组内序号（1-based）
    
    # 内容
    question_type: str            # choice_single / choice_multi / fill_blank / essay
    question_text: str              # 题干
    options: Optional[Dict[str, str]] = None  # {"A": "...", "B": "..."}
    correct_answer: str           # 正确答案（如 "B" 或自由文本）
    explanation: str = ""         # 答案解析（生成时产生）
    
    # 知识追踪（精简版，完整溯源见 QuestionTrace）
    knowledge_trace: KnowledgeTrace = field(default_factory=KnowledgeTrace)
    
    # IRT 参数（生成时确定，后续可校准）
    irt_params: IRTParams = field(default_factory=IRTParams)
    
    # 用户作答（答题后填充）
    user_answer: Optional[str] = None
    is_correct: Optional[bool] = None
    time_spent: Optional[int] = None  # 秒
    answered_at: Optional[datetime] = None


@dataclass
class KnowledgeTrace:
    """知识追踪：题目与概念的关联"""
    primary_concepts: List[str] = field(default_factory=list)      # 主要考察概念
    secondary_concepts: List[str] = field(default_factory=list)    # 次要关联概念
    concept_chain: List[str] = field(default_factory=list)         # 概念依赖链（如 ["A", "B", "C"]）
    bloom_level: str = "understand"   # remember / understand / apply / analyze / evaluate / create
    difficulty_score: float = 0.5     # 0-1，启发式难度
    difficulty_label: str = "中等"     # 简单 / 中等 / 困难


@dataclass
class IRTParams:
    """IRT 参数：分阶段校准"""
    a: float = 1.0                  # 区分度（阶段1固定为1.0，阶段2校准）
    b: float = 0.0                  # 难度（阶段1启发式，阶段2校准）
    c: float = 0.25                 # 猜测度（选择题固定0.25，填空/问答题0.0）
    
    calibration_stage: int = 1      # 1=Rasch(只估b), 2=2PL, 3=3PL
    calibration_samples: int = 0    # 已用于校准的答题记录数
    
    @property
    def is_calibrated(self) -> bool:
        if self.calibration_stage == 1:
            return self.calibration_samples >= 50  # Rasch 至少50条
        elif self.calibration_stage == 2:
            return self.calibration_samples >= 100
        return self.calibration_samples >= 200
```

### 2.3 题目溯源（QuestionTrace）

溯源信息独立存储，避免重复加载大 JSON：

```python
@dataclass
class QuestionTrace:
    """
    题目全链路溯源：Question → CanonicalConcept → ExtractedConcept → Chunk → Document
    独立存储，按需加载
    """
    trace_id: str                 # 与 question_id 相同
    question_id: str
    
    # L3 层溯源
    canonical_sources: List[CanonicalSource] = field(default_factory=list)
    
    # 图谱子图（序列化存储，用于讲解时重建）
    subgraph_snapshot: Optional[SubgraphSnapshot] = None
    
    # 生成时的原始上下文（压缩存储）
    generation_context: str = ""   # Graph-to-Text 的原始文本，用于调试和复现
    
    # 生成元数据
    paradigm: str = "theory"        # 生成时使用的范式
    llm_model: str = ""             # 生成使用的模型
    generation_timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CanonicalSource:
    """单个概念的多层溯源"""
    canonical_id: str
    canonical_name: str
    concept_type: str
    
    # L2: 原始概念来源
    extracted_sources: List[ExtractedSource] = field(default_factory=list)
    
    # L3 属性
    description: str = ""
    aliases: List[str] = field(default_factory=list)
    
    # 图谱位置
    pagerank_score: float = 0.0
    in_degree: int = 0
    out_degree: int = 0


@dataclass
class ExtractedSource:
    """L2 原始概念 → L1 Chunk 溯源"""
    extracted_id: str
    extract_role: str              # DEFINES / HAS_LAW / APPLIES_TO / EXTENDS
    
    # L1: Chunk 来源
    source_chunks: List[ChunkSource] = field(default_factory=list)


@dataclass
class ChunkSource:
    """L1 Chunk 溯源"""
    chunk_id: str
    source: str                    # 文件名
    heading_path: str
    page_number: int
    text_snippet: str = ""         # 原文摘录（前200字）
    media_refs: List[MediaRef] = field(default_factory=list)


@dataclass
class MediaRef:
    media_type: str                # image / formula / table
    path: str
    thumbnail_path: Optional[str] = None
    description: str = ""
```

### 2.4 用户知识状态（UserKnowledgeState）

```python
@dataclass
class UserKnowledgeState:
    """
    用户知识状态：按学科隔离，按组更新
    """
    state_id: str                 # 复合键: f"{user_id}#{subject_id}#{canonical_id}"
    user_id: str
    subject_id: str
    canonical_id: str
    canonical_name: str
    
    # 掌握状态
    mastery_level: float = 0.0     # 0.0-1.0
    confidence: float = 0.5        # 0.0-1.0，掌握度估计的置信度
    
    # 答题统计
    test_count: int = 0
    correct_count: int = 0
    streak: int = 0               # 连续正确次数（正数=连续对，负数=连续错）
    
    # IRT 能力估计（该概念上的局部能力）
    theta: float = 0.0             # 能力估计值（logit 尺度，-3~+3）
    theta_se: float = 1.0          # 标准误
    
    # 时间戳
    last_tested: Optional[datetime] = None
    first_tested: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.now)
    
    # 元数据
    source_of_latest_update: str = ""  # 记录最后一次更新的来源（如 group_id）
```

### 2.5 答题记录（AnswerRecord）

```python
@dataclass
class AnswerRecord:
    """
    答题记录：用于 IRT 校准和能力画像
    """
    record_id: str
    user_id: str
    subject_id: str
    group_id: str
    question_id: str
    sequence: int                 # 组内序号
    
    # 作答内容
    user_answer: str
    correct_answer: str
    is_correct: bool
    
    # 时间
    time_spent: int               # 秒
    answered_at: datetime
    
    # 关联概念（用于知识传播分析）
    primary_concepts: List[str] = field(default_factory=list)
    
    # IRT 相关（提交时计算）
    theta_before: float = 0.0     # 答题前能力估计
    theta_after: float = 0.0      # 答题后能力估计
    item_information: float = 0.0  # 该题的信息量 I(θ)
```

### 2.6 数据库 Schema 扩展（KùzuDB + SQLite）

**KùzuDB 扩展（图谱层）**：

```cypher
// ========== 题目节点（精简） ==========
CREATE NODE TABLE Question (
    question_id STRING PRIMARY KEY,
    subject_id STRING,
    question_type STRING,
    difficulty_score FLOAT,
    bloom_level STRING,
    primary_concepts STRING,      // JSON 数组
    irt_b FLOAT,                  // 难度参数
    irt_a FLOAT,                  // 区分度参数
    irt_c FLOAT,                  // 猜测度参数
    calibration_stage INT64,
    created_at TIMESTAMP
)

// ========== 题目组节点 ==========
CREATE NODE TABLE QuestionGroup (
    group_id STRING PRIMARY KEY,
    user_id STRING,
    subject_id STRING,
    template_id STRING,
    status STRING,
    total_questions INT64,
    generated_at TIMESTAMP,
    submitted_at TIMESTAMP
)

// ========== 用户知识状态节点 ==========
CREATE NODE TABLE UserKnowledgeState (
    state_id STRING PRIMARY KEY,
    user_id STRING,
    subject_id STRING,
    canonical_id STRING,
    mastery_level FLOAT,
    confidence FLOAT,
    theta FLOAT,
    test_count INT64,
    streak INT64,
    last_tested TIMESTAMP
)

// ========== 关系表 ==========
CREATE REL TABLE CONTAINS (
    FROM QuestionGroup TO Question,
    ONE_MANY
)

CREATE REL TABLE TESTS_CONCEPT (
    FROM Question TO CanonicalConcept,
    MANY_MANY
)

CREATE REL TABLE HAS_STATE (
    FROM User TO UserKnowledgeState,
    ONE_MANY
)
```

**SQLite 存储（非图谱数据，高频读写）**：

```sql
-- 答题记录表（高频写入，适合关系型）
CREATE TABLE answer_records (
    record_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    sequence INTEGER,
    user_answer TEXT,
    correct_answer TEXT,
    is_correct INTEGER,  -- 0/1
    time_spent INTEGER,
    answered_at TIMESTAMP,
    theta_before FLOAT,
    theta_after FLOAT,
    item_information FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 题目溯源表（大 JSON，按需查询）
CREATE TABLE question_traces (
    trace_id TEXT PRIMARY KEY,  -- = question_id
    question_id TEXT NOT NULL,
    trace_json TEXT,             -- 完整溯源 JSON
    generation_context TEXT,     -- 生成上下文（压缩）
    created_at TIMESTAMP
);

-- 索引
CREATE INDEX idx_answer_user_subject ON answer_records(user_id, subject_id);
CREATE INDEX idx_answer_group ON answer_records(group_id);
CREATE INDEX idx_answer_question ON answer_records(question_id);
```

---

## 三、Agent 与知识图谱交互数据链路

### 3.1 数据链路总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                          用户请求层                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                   │
│  │ 生成题目组   │  │ 提交题目组   │  │ 请求讲解     │                   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                   │
└─────────┼────────────────┼────────────────┼───────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Agent 编排层                                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                   │
│  │ Quiz Agent │  │ Coach Agent│  │ Tutor Agent│                   │
│  │  (出题)     │  │  (测评/画像) │  │  (讲解)     │                   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                   │
└─────────┼────────────────┼────────────────┼───────────────────────┘
          │                │                │
          │   ┌────────────┴────────────┐  │
          │   │                           │  │
          ▼   ▼                           ▼  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        P0 核心模块层                                │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   │
│  │ Concept    │  │ Subgraph   │  │ Context    │  │ Question   │   │
│  │ Retriever  │  │ Builder    │  │ Assembler  │  │ Trace Store│   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
└─────────┼────────────────┼────────────────┼────────────────┼───────────┘
          │                │                │                │
          │   ┌────────────┴────────────┐   │                │
          │   │          KùzuDB          │   │                │
          │   │  ┌────────────────────┐ │   │                │
          │   │  │ L1: Chunk          │ │   │                │
          │   │  │ L2: ExtractedConcept│ │   │                │
          │   │  │ L3: CanonicalConcept│ │   │                │
          │   │  │ L4: 语义连接         │ │   │                │
          │   │  └────────────────────┘ │   │                │
          │   └─────────────────────────┘   │                │
          │                │                │                │
          │   ┌────────────┴────────────┐   │                │
          │   │        SQLite / Redis    │   │                │
          │   │  ┌────────────────────┐ │   │                │
          │   │  │ AnswerRecord       │ │   │                │
          │   │  │ QuestionTrace      │ │   │                │
          │   │  │ UserKnowledgeState │ │   │                │
          │   │  └────────────────────┘ │   │                │
          │   └─────────────────────────┘   │                │
          │                                 │                │
          │   ┌────────────┴────────────┐   │                │
          │   │        Cache 层          │   │                │
          │   │  ┌────────────────────┐ │   │                │
          │   │  │ 图中心性缓存        │ │   │                │
          │   │  │ 用户状态子图缓存    │ │   │                │
          │   │  │ 题目信息缓存        │ │   │                │
          │   │  └────────────────────┘ │   │                │
          │   └─────────────────────────┘   │                │
          │                                 │                │
          ▼                                 ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          LLM 服务层                                  │
│                     (OpenAI / Claude / Kimi)                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 链路 1：Quiz Agent → 生成题目组

```python
# 时序图（简化）

# 步骤 1: 用户选择模板 + 目标概念
user_request = {
    "template_id": "gaokao_math",
    "subject_id": "transformer",
    "target_concepts": ["concept_canonical_attention"],  # 可选，未指定则自动选择
    "count": 10,  # 覆盖模板数量，或自定义
}

# 步骤 2: Quiz Agent 调用 Concept Retriever
# ─────────────────────────────────────────
retriever = ConceptRetriever(kuzu_db, vector_store)
if target_concepts:
    seed_concepts = retriever.resolve(target_concepts)  # 名称 → canonical_id
else:
    # 自动选择：从用户薄弱概念中采样
    seed_concepts = retriever.select_weak_concepts(user_id, subject_id, n=3)

# 扩展相关概念（1-hop 邻居）
related_concepts = retriever.expand(seed_concepts, hop=1, max_nodes=20)
# 返回: List[ConceptNode] with pagerank, degree, aliases, description

# 步骤 3: Quiz Agent 调用 Subgraph Builder
# ─────────────────────────────────────────
builder = SubgraphBuilder(kuzu_db)
subgraph = builder.build(
    seed_concepts=seed_concepts,
    related_concepts=related_concepts,
    mode="auto",  # 根据题型自动选择 star/chain/tree
    max_depth=2,
    max_nodes=20,
)
# 返回: Subgraph (nodes: List[CanonicalConcept], edges: List[SemanticEdge])

# 步骤 4: Quiz Agent 按模板生成每道题
# ─────────────────────────────────────────
group = QuestionGroup(...)
for pattern in template.question_patterns:
    for i in range(pattern.count):
        # 选择目标概念（考虑覆盖度，避免重复）
        target = select_target_concept(subgraph, used_concepts, pattern)
        
        # 构建题型专用子图
        question_subgraph = builder.build_for_pattern(target, pattern)
        
        # Context Assembler 组装上下文
        assembler = ContextAssembler()
        context = assembler.assemble(
            subgraph=question_subgraph,
            budget=pattern.context_budget,
            include_prerequisites=pattern.require_concept_chain,
        )
        
        # LLM 生成题目
        question = llm.generate_question(context, pattern, target)
        
        # 构建溯源
        trace = QuestionTraceBuilder().build(question, question_subgraph, context)
        
        # 存储
        question.knowledge_trace = extract_knowledge_trace(trace)
        question.irt_params = estimate_irt_params(question, trace)  # 启发式 b
        store_question(question, trace)
        
        group.questions.append(question)

# 步骤 5: 返回题目组给用户
return group
```

### 3.3 链路 2：Coach Agent → 按组处理提交

```python
# 时序图（简化）

# 步骤 1: 用户提交整组答案
submission = {
    "group_id": "qg_xxx",
    "answers": [
        {"question_id": "q_001", "user_answer": "B", "time_spent": 120},
        {"question_id": "q_002", "user_answer": "A", "time_spent": 180},
        ...
    ]
}

# 步骤 2: 前端验证 + 即时评分（无需图计算）
for ans in submission.answers:
    question = load_question(ans.question_id)
    ans.is_correct = (ans.user_answer == question.correct_answer)
    # 前端直接显示对错，无需等待后端

# 步骤 3: 批量提交到 Coach Agent（后台处理）
# ─────────────────────────────────────────
coach = CoachAgent(kuzu_db, sqlite_db)

# 3.1 批量创建答题记录
records = []
for ans in submission.answers:
    record = AnswerRecord(
        user_answer=ans.user_answer,
        is_correct=ans.is_correct,
        time_spent=ans.time_spent,
        ...
    )
    records.append(record)

# 3.2 批量更新用户知识状态（按组触发，非实时）
for record in records:
    # 获取当前状态
    state = load_user_state(user_id, subject_id, record.primary_concepts)
    
    # IRT 更新（Rasch 模型简化版）
    # θ_new = θ_old + learning_rate * (is_correct - P(θ_old))
    # P(θ) = 1 / (1 + exp[-(θ - b)])
    p = sigmoid(state.theta - record.irt_b)
    state.theta += 0.3 * (record.is_correct - p)  # 学习率 0.3
    state.theta = clip(state.theta, -3.0, 3.0)
    
    # 更新统计
    state.test_count += 1
    state.correct_count += record.is_correct
    state.streak = state.streak + 1 if record.is_correct else max(-5, state.streak - 1)
    
    # 掌握度映射（θ → 0-1）
    state.mastery_level = sigmoid(state.theta)  # 映射到 0-1
    state.confidence = min(1.0, state.test_count / 10)  # 10次后置信度满
    
    # 3.3 沿图传播（批量）
    if record.is_correct:
        # 答对：前置知识掌握度 +0.05（沿 DEPENDS_ON 反向）
        prerequisites = graph.get_predecessors(record.primary_concepts, "DEPENDS_ON")
        for prereq in prerequisites:
            prereq_state = load_or_create_state(user_id, subject_id, prereq)
            prereq_state.mastery_level = min(1.0, prereq_state.mastery_level + 0.05)
    else:
        # 答错：应用概念置信度降低（沿 SOLUTION 正向）
        applications = graph.get_successors(record.primary_concepts, "SOLUTION")
        for app in applications:
            app_state = load_or_create_state(user_id, subject_id, app)
            app_state.confidence *= 0.9
    
    save_state(state)

# 3.4 批量 IRT 校准（异步任务，非阻塞）
# 检查每道题是否达到校准阈值
for record in records:
    question = load_question(record.question_id)
    if not question.irt_params.is_calibrated:
        # 异步触发校准任务
        schedule_irt_calibration(question.question_id)

# 3.5 生成能力画像报告
profile = generate_profile(user_id, subject_id)

# 步骤 4: 返回结果（可异步）
return {
    "group_score": sum(r.is_correct for r in records) / len(records),
    "correct_count": sum(r.is_correct for r in records),
    "weak_concepts": profile.weak_concepts,
    "recommended_next": profile.recommended_groups,
}
```

### 3.4 链路 3：Tutor Agent → 图谱化讲解

```python
# 时序图（简化）

# 步骤 1: 用户请求讲解某题
explain_request = {
    "question_id": "q_001",
    "user_answer": "C",  # 用户答错的选项
    "depth": "auto",     # L1/L2/L3/L4/auto
}

# 步骤 2: Tutor Agent 加载题目溯源
question = load_question(question_id)
trace = load_trace(question_id)

# 步骤 3: 确定讲解深度
if explain_request.depth == "auto":
    if question.is_correct:
        depth = "L1"  # 简要确认
    elif len(question.knowledge_trace.concept_chain) > 2:
        depth = "L3"  # 综合题 → 面讲解
    elif get_error_count(user_id, question.primary_concepts[0]) > 2:
        depth = "L3"  # 重复错误 → 面讲解
    else:
        depth = "L2"  # 默认链讲解

# 步骤 4: 重建或加载子图
if trace.subgraph_snapshot:
    subgraph = SubgraphBuilder.from_snapshot(trace.subgraph_snapshot)
else:
    # 重建子图（从概念 ID 重新查询）
    subgraph = SubgraphBuilder(kuzu_db).build(
        seed_concepts=question.knowledge_trace.primary_concepts,
        depth=2,
    )

# 步骤 5: 加载用户知识状态（用于个性化讲解）
user_states = {}
for concept_id in subgraph.nodes:
    state = load_user_state(user_id, subject_id, concept_id)
    user_states[concept_id] = state

# 步骤 6: Context Assembler 组装讲解上下文
context = ContextAssembler().assemble_explanation(
    subgraph=subgraph,
    user_states=user_states,
    source_trace=trace,
    question=question,
    user_answer=explain_request.user_answer,
    depth=depth,
)

# 步骤 7: LLM 生成讲解
explanation = llm.generate_explanation(context)

return explanation
```

---

## 四、P0 核心模块接口设计

### 4.1 Concept Retriever（概念检索器）

```python
class ConceptRetriever:
    """
    将用户查询/出题需求映射到 CanonicalConcept 节点
    """
    
    def __init__(self, kuzu_db: KuzuDB, vector_store: VectorStore, 
                 cache: Optional[Cache] = None):
        self.db = kuzu_db
        self.vector_store = vector_store
        self.cache = cache or InMemoryCache()
    
    # ───── 核心接口 ─────
    
    def resolve(self, concept_names: List[str], subject_id: str) -> List[ConceptNode]:
        """
        将概念名称列表解析为 CanonicalConcept 节点
        策略：名称精确匹配 → 模糊匹配 → Embedding 语义检索
        """
        pass
    
    def expand(self, seed_concepts: List[ConceptNode], 
               hop: int = 1, 
               edge_types: List[str] = None,
               max_nodes: int = 20) -> List[ConceptNode]:
        """
        从种子概念沿图扩展，获取相关概念
        """
        pass
    
    def select_weak_concepts(self, user_id: str, subject_id: str, 
                             n: int = 5) -> List[ConceptNode]:
        """
        选择用户掌握度最低的 n 个概念（用于靶向出题）
        """
        pass
    
    def select_by_coverage(self, subject_id: str, 
                           existing_questions: List[Question],
                           n: int = 5) -> List[ConceptNode]:
        """
        选择覆盖度最低的 n 个概念（用于全面检测）
        """
        pass
    
    # ───── 辅助接口 ─────
    
    def search_by_embedding(self, query: str, top_k: int = 5) -> List[ConceptNode]:
        """Embedding 语义检索"""
        pass
    
    def get_concept_stats(self, canonical_id: str) -> ConceptStats:
        """获取概念统计信息（度中心性、PageRank、历史正确率等）"""
        pass
```

### 4.2 Subgraph Builder（子图构建器）

```python
class SubgraphBuilder:
    """
    围绕目标概念构建用于出题/讲解的局部子图
    """
    
    def __init__(self, kuzu_db: KuzuDB, 
                 centrality_cache: Optional[Dict] = None):
        self.db = kuzu_db
        self.centrality_cache = centrality_cache or {}
    
    # ───── 核心接口 ─────
    
    def build(self, 
              seed_concepts: List[ConceptNode],
              related_concepts: Optional[List[ConceptNode]] = None,
              mode: str = "auto",  # auto / star / chain / tree
              max_depth: int = 2,
              max_nodes: int = 20) -> Subgraph:
        """
        构建通用子图
        """
        pass
    
    def build_for_pattern(self, 
                          target_concept: ConceptNode,
                          pattern: QuestionPattern) -> Subgraph:
        """
        根据题型构建专用子图
        """
        pass
    
    def build_for_explanation(self,
                              question: Question,
                              depth: str = "L2") -> Subgraph:
        """
        为讲解构建子图
        """
        pass
    
    # ───── 子图模式 ─────
    
    def build_star(self, center: ConceptNode, 
                   include_derived: bool = True) -> Subgraph:
        """星型子图：中心 + 1-hop 邻居"""
        pass
    
    def build_chain(self, start: ConceptNode, end: ConceptNode) -> Subgraph:
        """链型子图：两点间最短路径"""
        pass
    
    def build_tree(self, root: ConceptNode, 
                   max_depth: int = 3) -> Subgraph:
        """树型子图：BFS 展开"""
        pass
    
    # ───── 序列化 ─────
    
    def to_snapshot(self, subgraph: Subgraph) -> SubgraphSnapshot:
        """序列化子图用于存储"""
        pass
    
    def from_snapshot(self, snapshot: SubgraphSnapshot) -> Subgraph:
        """从快照重建子图"""
        pass
```

### 4.3 Context Assembler（上下文组装器）

```python
class ContextAssembler:
    """
    将图谱子图组装为 LLM 可理解的结构化上下文
    """
    
    def __init__(self, tokenizer: Optional[Tokenizer] = None):
        self.tokenizer = tokenizer or SimpleTokenizer()
    
    # ───── 核心接口 ─────
    
    def assemble(self,
                 subgraph: Subgraph,
                 budget: ContextBudget,
                 include_prerequisites: bool = False,
                 include_media: bool = True) -> GraphContext:
        """
        组装出题上下文
        """
        pass
    
    def assemble_explanation(self,
                             subgraph: Subgraph,
                             user_states: Dict[str, UserKnowledgeState],
                             source_trace: QuestionTrace,
                             question: Question,
                             user_answer: str,
                             depth: str = "L2") -> GraphContext:
        """
        组讲解上下文
        """
        pass
    
    # ───── 预算控制 ─────
    
    def trim_to_budget(self, 
                       subgraph: Subgraph, 
                       budget: ContextBudget) -> Subgraph:
        """
        将子图裁剪到 token 预算内
        策略：保留中心节点 → 截断描述 → 删除低中心性节点
        """
        pass
    
    def estimate_tokens(self, text: str) -> int:
        """估算文本 token 数"""
        pass
```

### 4.4 IRT 估计器（分阶段）

```python
class IRTEstimator:
    """
    IRT 参数估计：分阶段从启发式到数据驱动
    """
    
    def __init__(self, stage: int = 1):
        self.stage = stage
    
    def estimate_b_heuristic(self, concept: ConceptNode) -> float:
        """
        阶段 1: 启发式难度估计
        公式: b = 0.3 * (1 - centrality) + 0.3 * min(neighbors/10, 1) + 
                    0.2 * min(description_len/500, 1) + 0.2 * historical_difficulty
        """
        pass
    
    def estimate_a_heuristic(self, question: Question, 
                             distractor_quality: float) -> float:
        """
        阶段 2: 基于干扰项质量估计区分度
        """
        pass
    
    def calibrate_rasch(self, question_id: str, 
                        records: List[AnswerRecord]) -> float:
        """
        阶段 1 校准: 固定 a=1.0, c=0.25，仅估计 b
        使用最大似然估计或贝叶斯估计
        """
        pass
    
    def calibrate_2pl(self, question_id: str,
                      records: List[AnswerRecord]) -> Tuple[float, float]:
        """
        阶段 2 校准: 估计 a 和 b
        """
        pass
    
    def compute_information(self, theta: float, 
                           a: float, b: float, c: float) -> float:
        """
        计算题目信息量 I(θ)
        I(θ) = a² × P(θ) × (1-P(θ)) / (1-c)²
        """
        p = c + (1-c) / (1 + math.exp(-a * (theta - b)))
        return (a ** 2) * p * (1 - p) / ((1 - c) ** 2)
    
    def update_theta(self, theta: float, is_correct: bool, 
                     a: float, b: float, c: float,
                     learning_rate: float = 0.3) -> float:
        """
        更新能力估计（简化 Elo 式更新）
        """
        p = c + (1-c) / (1 + math.exp(-a * (theta - b)))
        return theta + learning_rate * (is_correct - p)
```

### 4.5 按组管理器（GroupManager）

```python
class GroupManager:
    """
    题目组生命周期管理：生成 → 答题 → 提交 → 评分 → 画像更新
    """
    
    def __init__(self, quiz_agent: QuizAgent, coach_agent: CoachAgent,
                 db: SQLiteDB, cache: Cache):
        self.quiz_agent = quiz_agent
        self.coach_agent = coach_agent
        self.db = db
        self.cache = cache
    
    def create_group(self, user_id: str, subject_id: str,
                     template_id: str,
                     target_concepts: Optional[List[str]] = None) -> QuestionGroup:
        """生成新题目组"""
        pass
    
    def get_group(self, group_id: str) -> QuestionGroup:
        """加载题目组（缓存优先）"""
        pass
    
    def submit_group(self, group_id: str, 
                   answers: List[UserAnswer]) -> GroupResult:
        """
        提交整组答案，触发后台处理
        返回即时结果（得分），后台异步更新画像
        """
        pass
    
    def get_group_result(self, group_id: str) -> GroupResult:
        """获取组的完整评分和画像结果"""
        pass
    
    def get_next_recommendation(self, user_id: str, subject_id: str) -> str:
        """推荐下一组题目（基于能力画像）"""
        pass
```

---

## 五、按组选题：详细流程

### 5.1 状态机

```
                    ┌─────────┐
                    │  GENERATED  │  ← create_group() 生成完成
                    └────┬────┘
                         │ start_group()
                         ▼
                    ┌─────────┐
              ┌───→│ IN_PROGRESS │  ← 用户开始答题
              │     └────┬────┘
              │          │ answer_question() 前端缓存
              │          │ (答题过程中不触发图计算)
              │          ▼
              │     ┌─────────┐
              └───→│ IN_PROGRESS │  ← 继续答题
                    └────┬────┘
                         │ submit_group() 提交整组
                         ▼
                    ┌─────────┐
                    │ SUBMITTED  │  ← 触发后台批量处理
                    └────┬────┘
                         │ 后台: grade_batch() + update_profile()
                         ▼
                    ┌─────────┐
                    │  GRADED   │  ← 处理完成，可查看画像
                    └─────────┘
```

### 5.2 时序图

```
用户          前端          Quiz Agent    GroupManager   Coach Agent   后台任务
 │             │              │              │              │              │
 │──选模板──→│              │              │              │              │
 │             │──create_group()──→│              │              │              │
 │             │              │──ConceptRetriever──→│              │              │
 │             │              │              │──KùzuDB──→│              │              │
 │             │              │              │←─概念列表──│              │              │
 │             │              │──SubgraphBuilder──→│              │              │
 │             │              │              │──KùzuDB──→│              │              │
 │             │              │              │←─子图────│              │              │
 │             │              │──ContextAssembler──→│              │              │
 │             │              │              │←─上下文──│              │              │
 │             │              │──LLM生成──→│              │              │              │
 │             │              │              │              │              │              │
 │←─返回组───│              │              │              │              │              │
 │             │              │              │              │              │              │
 │──逐题作答─→│              │              │              │              │              │
 │             │（前端缓存，不触发后端）              │              │              │              │
 │             │              │              │              │              │              │
 │──提交整组─→│              │              │              │              │              │
 │             │──submit_group()──→│              │              │              │              │
 │             │              │              │──即时评分──→│              │              │
 │             │              │              │              │              │              │
 │←─返回得分──│              │              │              │              │              │
 │             │              │              │              │              │              │
 │             │              │              │──异步调度──→│              │              │
 │             │              │              │              │              │──批量处理──→│
 │             │              │              │              │              │              │
 │             │              │              │              │              │   ┌─IRT更新─┐
 │             │              │              │              │              │   │ 图传播  │
 │             │              │              │              │              │   │ 画像生成 │
 │             │              │              │              │              │   └────┬───┘
 │             │              │              │              │              │          │
 │             │              │              │←─完成回调──│              │              │
 │             │              │              │              │              │              │
 │──查询结果─→│              │              │              │              │              │
 │             │──get_group_result()──→│              │              │              │
 │←─返回画像──│              │              │              │              │              │
```

### 5.3 后台批量处理任务

```python
async def process_group_submission(group_id: str):
    """
    后台异步处理整组提交
    """
    group = load_group(group_id)
    records = []
    
    # 1. 批量创建答题记录
    for question in group.questions:
        record = create_answer_record(question)
        records.append(record)
    save_records(records)
    
    # 2. 批量更新知识状态（IRT 更新）
    for record in records:
        for concept_id in record.primary_concepts:
            state = load_user_state(record.user_id, record.subject_id, concept_id)
            
            # IRT 能力更新
            theta_new = irt_estimator.update_theta(
                state.theta, record.is_correct,
                record.irt_a, record.irt_b, record.irt_c
            )
            state.theta = theta_new
            state.mastery_level = sigmoid(theta_new)
            state.test_count += 1
            state.correct_count += record.is_correct
            state.streak = update_streak(state.streak, record.is_correct)
            state.confidence = min(1.0, state.test_count / 10)
            state.last_tested = now()
            state.source_of_latest_update = group_id
            
            save_state(state)
    
    # 3. 批量图传播（知识依赖推理）
    # 答对 → 前置知识 +0.05
    # 答错 → 应用概念 confidence × 0.9
    for record in records:
        if record.is_correct:
            prerequisites = graph.get_predecessors(record.primary_concepts, "DEPENDS_ON")
            for prereq in prerequisites:
                state = load_or_create_state(record.user_id, record.subject_id, prereq)
                state.mastery_level = min(1.0, state.mastery_level + 0.05)
                save_state(state)
        else:
            applications = graph.get_successors(record.primary_concepts, "SOLUTION")
            for app in applications:
                state = load_or_create_state(record.user_id, record.subject_id, app)
                state.confidence *= 0.9
                save_state(state)
    
    # 4. 检查 IRT 校准条件
    for question in group.questions:
        if not question.irt_params.is_calibrated:
            all_records = load_records_for_question(question.question_id)
            if len(all_records) >= 50:  # Rasch 阈值
                # 异步触发校准
                schedule_task(calibrate_irt_question, question.question_id)
    
    # 5. 生成能力画像
    profile = generate_knowledge_profile(
        user_id=group.user_id,
        subject_id=group.subject_id
    )
    save_profile(profile)
    
    # 6. 更新组状态
    group.status = GroupStatus.GRADED
    group.graded_at = now()
    save_group(group)
    
    # 7. 通知用户（可选：WebSocket / SSE）
    notify_user(group.user_id, {
        "type": "group_graded",
        "group_id": group_id,
        "profile_summary": profile.summary()
    })
```

---

## 六、缓存与预计算策略

### 6.1 预计算项（离线/低频）

| 预计算项 | 触发时机 | 存储 | TTL |
|:---|:---|:---|:---|
| 图中心性（PageRank） | 图谱构建/更新后 | Redis / JSON 文件 | 永久（直到下次更新） |
| 图中心性（Betweenness） | 图谱构建/更新后 | Redis / JSON 文件 | 永久 |
| 概念难度启发式 b | 概念生成/更新后 | KùzuDB Question.irt_b | 永久 |
| 学科概念覆盖度矩阵 | 图谱构建/更新后 | SQLite | 永久 |

### 6.2 缓存项（中高频）

| 缓存项 | 存储 | TTL | 失效策略 |
|:---|:---|:---|:---|
| 用户知识状态子图 | Redis Hash | 1小时 | 答题后更新 |
| 题目基本信息 | Redis String | 24小时 | 题目更新后删除 |
| 题目溯源（完整） | 文件系统 | 永久 | 题目删除后清理 |
| 试卷模板 | 内存 Dict | 永久 | 重启后重载 |
| LLM 生成结果（同参数） | 可选 | 短期 | 概念更新后失效 |

### 6.3 缓存键设计

```python
# 用户状态子图
"uks:{user_id}:{subject_id}:{canonical_id}"  ->  UserKnowledgeState JSON

# 图中心性
"pr:{subject_id}:{canonical_id}"  ->  float (PageRank)
"bw:{subject_id}:{canonical_id}"  ->  float (Betweenness)

# 题目信息
"q:{question_id}:meta"  ->  Question JSON（不含溯源）
"q:{question_id}:trace"  ->  trace_id（溯源存储在 SQLite）

# 题目组
"qg:{group_id}"  ->  QuestionGroup JSON
"qg:{group_id}:status"  ->  GroupStatus
```

---

*详细设计文档结束。等待测试计划文档编写。*


---

## 附录：P0 模块实现状态（2026-07-16 更新）

> 本附录由 OpenClaw 自动维护，每次代码更新后同步检查并更新。

### 已实现模块（代码存在 + 单元测试通过）

| 模块 | 代码文件 | 单元测试 | 提交记录 | 状态 |
|------|----------|----------|----------|------|
| **ConceptRetriever** | core/graph_education/concept_retriever.py (19KB) | 	ests/p0/test_concept_retriever.py (56 测试) |  8b11c6 | ✅ 已实现 |
| **SubgraphBuilder** | core/graph_education/subgraph_builder.py (23KB) | 	ests/p0/test_subgraph_builder.py (56 测试) |  8b11c6 | ✅ 已实现 |
| **ContextAssembler** | core/graph_education/context_assembler.py (18KB) | 	ests/p0/test_context_assembler.py (79 测试) | 81f010 | ✅ 已实现 |
| **IRTEstimator** | core/graph_education/irt_estimator.py (12KB) | 	ests/p0/test_irt_estimator.py (26 测试) | 48f33e7 | ✅ 已实现 |
| **GroupManager** | core/graph_education/group_manager.py | 	ests/p0/test_group_manager.py (15 测试) |  94b54b | ✅ 已实现 |
| **types** | core/graph_education/types.py | — | — | ✅ 已实现 |
| **__init__ 导出** | core/graph_education/__init__.py | — | — | ✅ 已导出 |

### 未集成问题（代码已存在但未被上层调用）

| 问题 | 说明 | 影响 |
|------|------|------|
| **Coordinator 未集成 P0 模块** | gents/coordinator.py 仍只使用旧版 TutorAgent/QuizAgent/CoachAgent/HeadhunterAgent，未导入 core.graph_education 的任何模块 | P0 模块无法通过 Coordinator 入口使用 |
| **QuizAgent 未使用 ContextAssembler** | gents/quiz_agent.py 仍直接检索 chunks 拼接为 LLM prompt，未调用 ContextAssembler 组装结构化上下文 | 出题上下文未按 P0 设计进行 budget 控制和子图构建 |
| **CoachAgent 未使用 IRTEstimator** | gents/coach_agent.py 的评分逻辑使用简单规则评分（对/错），未调用 IRTEstimator 进行能力估计 | 用户能力画像无 IRT 参数，无法自适应出题难度 |
| **Agent 间无消息总线** | 设计文档中的 MetaGPT 风格消息池未实现 | 各 Agent 独立工作，状态不共享 |
| **UserKnowledgeState 无持久化** | 	ypes.py 中定义了 UserKnowledgeState dataclass，但无 SQLite/Redis 持久化实现 | 用户答题历史无法保存，IRT 无法校准 |
| **图中心性预计算未集成** | SubgraphBuilder 有 centrality_cache 参数，但无预计算脚本 | 每次构建子图需实时计算中心性 |

### 遗留任务

| 编号 | 任务 | 优先级 | 依赖 |
|------|------|--------|------|
| **P0-INT-1** | 修改 Coordinator 集成 P0 模块（ConceptRetriever → SubgraphBuilder → ContextAssembler → IRTEstimator） | P0 | — |
| **P0-INT-2** | 修改 QuizAgent 使用 ContextAssembler 组装出题上下文（替代直接 chunks 拼接） | P0 | P0-INT-1 |
| **P0-INT-3** | 修改 CoachAgent 使用 IRTEstimator 进行能力估计（替代简单规则评分） | P0 | P0-INT-1 |
| **P0-INT-4** | 实现 UserKnowledgeState SQLite 持久化 | P1 | — |
| **P0-INT-5** | 实现图中心性预计算脚本（PageRank / Betweenness） | P1 | — |
| **P0-INT-6** | 实现 Agent 间消息总线（事件订阅/发布） | P2 | P0-INT-4 |

---

_更新记录：2026-07-16 由 OpenClaw 检查代码库后更新，确认 5 个 P0 核心模块已实现但未被上层 Agent 调用。_



---

## 附录更新：P0-INT 集成状态（2026-07-16 20:00）

### P0-INT 1-3 已完成

| 编号 | 任务 | 状态 | 实现文件 | 验证脚本 |
|------|------|------|----------|----------|
| P0-INT-1 | Coordinator 集成 P0 模块 | ✅ 已完成 | gents/coordinator.py | scripts/test_p0_integration.py |
| P0-INT-2 | QuizAgent 使用 ContextAssembler | ✅ 已完成 | gents/quiz_agent.py | scripts/test_p0_integration.py |
| P0-INT-3 | CoachAgent 使用 IRTEstimator | ✅ 已完成 | gents/coach_agent.py | scripts/test_p0_integration.py |

### 实现详情

**P0-INT-1（Coordinator）**:
- handle() 的 quiz 分支：ConceptRetriever.resolve → SubgraphBuilder.build → ContextAssembler.assemble → QuizAgent(graph_context)
- handle() 的 evaluate 分支：评分后附加 irt_theta 字段
- 所有 P0 模块延迟初始化，调用失败自动回退旧方式
- 关键 console print（便于前端观察）：
  - [Coordinator] P0-INT-1: 使用图谱教育模块为 quiz 意图组装上下文
  - [Coordinator] 解析到 N 个种子概念
  - [Coordinator] 构建子图: N 节点, M 边
  - [Coordinator] 组装上下文: T tokens
  - [Coordinator] IRT 能力估计结果: theta=XX.XX

**P0-INT-2（QuizAgent）**:
- handle() 接受 graph_context: Optional[GraphContext] 参数
- 当 graph_context 存在时，使用 _generate_questions_with_context() 出题
- 返回的题目包含 knowledge_trace 字段
- 关键 console print：
  - [QuizAgent] P0-INT-2: 使用 P0 图谱上下文出题，token=T
  - [QuizAgent] 图谱上下文概念: [概念1, ...]
  - [QuizAgent] 回退到旧方式出题（无图谱上下文）（回退时）

**P0-INT-3（CoachAgent）**:
- evaluate() 评分后调用 IRTEstimator 估计能力
- 报告新增 irt 字段：	heta, level, concept_difficulties
- 新增 _theta_to_level() 方法：theta → 入门/初级/中级/高级/专家
- 关键 console print：
  - [CoachAgent] P0-INT-3: 开始 IRT 能力估计
  - [CoachAgent] IRT 能力估计: theta=XX.XX

### 向后兼容

所有修改保持向后兼容：
- 不传 graph_context → 旧方式正常工作
- P0 模块调用失败 → 自动回退旧方式
- 120 个 P0 单元测试全部通过

### 遗留任务（P0-INT-4~6 仍待实现）

| 编号 | 任务 | 优先级 | 状态 |
|------|------|--------|------|
| P0-INT-4 | UserKnowledgeState SQLite 持久化 | P1 | 🔴 待实现 |
| P0-INT-5 | 图中心性预计算脚本 | P1 | 🔴 待实现 |
| P0-INT-6 | Agent 间消息总线 | P2 | 🔴 待实现 |

---

_更新记录：2026-07-16 由 OpenClaw 执行 P0-INT-1/2/3 集成并更新。_

