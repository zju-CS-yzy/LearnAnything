"""
LA-040-P0: 图谱教育 Agent 核心数据类型

定义 ConceptNode、Subgraph、Context 等数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from datetime import datetime


class GroupStatus(Enum):
    """题目组状态机"""
    GENERATED = "generated"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    GRADED = "graded"


@dataclass
class ConceptNode:
    """概念节点：CanonicalConcept 的内存表示"""
    canonical_id: str
    name: str
    concept_type: str = "concept"
    description: str = ""
    aliases: List[str] = field(default_factory=list)
    parent_hint: str = ""
    
    # 图谱位置属性
    pagerank_score: float = 0.0
    in_degree: int = 0
    out_degree: int = 0
    
    # 溯源属性
    source_chunks: str = ""       # JSON 字符串或逗号分隔
    media_refs: List[Dict] = field(default_factory=list)
    
    # 相似度（Embedding 检索时填充）
    similarity_score: Optional[float] = None
    
    def __repr__(self) -> str:
        return f"ConceptNode({self.name}, id={self.canonical_id[:20]}...)"
    
    def __hash__(self) -> int:
        return hash(self.canonical_id)
    
    def __eq__(self, other) -> bool:
        if isinstance(other, ConceptNode):
            return self.canonical_id == other.canonical_id
        return False


@dataclass 
class SemanticEdge:
    """语义边：CanonicalConcept 之间的关系"""
    source_id: str
    target_id: str
    edge_type: str                # SOLUTION / DEPENDS_ON / HAS_DETAIL
    confidence: float = 1.0
    
    def __repr__(self) -> str:
        return f"SemanticEdge({self.source_id[:15]}... -{self.edge_type}-> {self.target_id[:15]}...)"


@dataclass
class Subgraph:
    """子图：用于出题/讲解的局部图"""
    nodes: List[ConceptNode] = field(default_factory=list)
    edges: List[SemanticEdge] = field(default_factory=list)
    
    # 元数据
    seed_concepts: List[str] = field(default_factory=list)  # 种子概念 ID
    build_mode: str = "auto"       # auto / star / chain / tree
    max_depth: int = 2
    
    @property
    def node_count(self) -> int:
        return len(self.nodes)
    
    @property
    def edge_count(self) -> int:
        return len(self.edges)
    
    @property
    def node_map(self) -> Dict[str, ConceptNode]:
        """节点 ID 到节点的快速映射"""
        return {n.canonical_id: n for n in self.nodes}
    
    def get_neighbors(self, concept_id: str, edge_types: Optional[List[str]] = None) -> List[ConceptNode]:
        """获取某节点的邻居"""
        neighbor_ids = set()
        for e in self.edges:
            if e.source_id == concept_id:
                neighbor_ids.add(e.target_id)
            elif e.target_id == concept_id:
                neighbor_ids.add(e.source_id)
        
        return [self.node_map[nid] for nid in neighbor_ids if nid in self.node_map]
    
    def get_outgoing(self, concept_id: str, edge_type: Optional[str] = None) -> List[ConceptNode]:
        """获取 outgoing 邻居（有向）"""
        neighbor_ids = []
        for e in self.edges:
            if e.source_id == concept_id:
                if edge_type is None or e.edge_type == edge_type:
                    neighbor_ids.append(e.target_id)
        return [self.node_map[nid] for nid in neighbor_ids if nid in self.node_map]
    
    def get_incoming(self, concept_id: str, edge_type: Optional[str] = None) -> List[ConceptNode]:
        """获取 incoming 邻居（有向）"""
        neighbor_ids = []
        for e in self.edges:
            if e.target_id == concept_id:
                if edge_type is None or e.edge_type == edge_type:
                    neighbor_ids.append(e.source_id)
        return [self.node_map[nid] for nid in neighbor_ids if nid in self.node_map]


@dataclass
class GraphContext:
    """Graph-to-Text 组装后的上下文"""
    text: str = ""                 # 组装后的文本
    token_count: int = 0           # 估算 token 数
    subgraph: Optional[Subgraph] = None
    
    # 分段内容（方便调试）
    sections: Dict[str, str] = field(default_factory=dict)


@dataclass
class ContextBudget:
    """LLM 上下文预算"""
    max_tokens: int = 1500
    prompt_overhead: int = 800
    
    @property
    def graph_tokens(self) -> int:
        return self.max_tokens - self.prompt_overhead
    
    max_nodes: int = 10
    max_description_length: int = 200


@dataclass
class IRTParams:
    """IRT 参数"""
    a: float = 1.0
    b: float = 0.0
    c: float = 0.25
    calibration_stage: int = 1
    calibration_samples: int = 0
    
    @property
    def is_calibrated(self) -> bool:
        if self.calibration_stage == 1:
            return self.calibration_samples >= 50
        elif self.calibration_stage == 2:
            return self.calibration_samples >= 100
        return self.calibration_samples >= 200


@dataclass
class UserKnowledgeState:
    """用户知识状态"""
    state_id: str = ""
    user_id: str = ""
    subject_id: str = ""
    canonical_id: str = ""
    canonical_name: str = ""
    
    mastery_level: float = 0.0
    confidence: float = 0.5
    theta: float = 0.0
    theta_se: float = 1.0
    
    test_count: int = 0
    correct_count: int = 0
    streak: int = 0
    
    last_tested: Optional[datetime] = None
    first_tested: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.now)
    source_of_latest_update: str = ""


@dataclass
class KnowledgeTrace:
    """知识追踪：题目与概念的关联"""
    primary_concepts: List[str] = field(default_factory=list)
    secondary_concepts: List[str] = field(default_factory=list)
    concept_chain: List[str] = field(default_factory=list)
    bloom_level: str = "understand"
    difficulty_score: float = 0.5
    difficulty_label: str = "中等"


@dataclass
class Question:
    """题目"""
    question_id: str = ""
    group_id: str = ""
    sequence: int = 0
    
    question_type: str = ""
    question_text: str = ""
    options: Optional[Dict[str, str]] = None
    correct_answer: str = ""
    explanation: str = ""
    
    knowledge_trace: KnowledgeTrace = field(default_factory=KnowledgeTrace)
    irt_params: IRTParams = field(default_factory=IRTParams)
    
    user_answer: Optional[str] = None
    is_correct: Optional[bool] = None
    time_spent: Optional[int] = None
    answered_at: Optional[datetime] = None


class GroupStatus(Enum):
    """题目组状态机"""
    GENERATED = "generated"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    GRADED = "graded"


@dataclass
class QuestionGroup:
    """题目组"""
    group_id: str = ""
    user_id: str = ""
    subject_id: str = ""
    template_id: str = ""
    
    status: GroupStatus = GroupStatus.GENERATED
    questions: List[Question] = field(default_factory=list)
    target_concepts: List[str] = field(default_factory=list)
    
    generated_at: datetime = field(default_factory=datetime.now)
    submitted_at: Optional[datetime] = None
    graded_at: Optional[datetime] = None
    
    @property
    def total_questions(self) -> int:
        return len(self.questions)
    
    @property
    def is_completed(self) -> bool:
        return self.status in (GroupStatus.SUBMITTED, GroupStatus.GRADED)


@dataclass
class QuestionPattern:
    """题型配置"""
    pattern_id: str = ""
    name: str = ""
    count: int = 0
    time_per_question: int = 180
    points_per_question: float = 1.0
    context_budget: ContextBudget = field(default_factory=lambda: ContextBudget())
    concept_depth: int = 1
    max_concepts_per_question: int = 5
    require_concept_chain: bool = False


@dataclass  
class ExamTemplate:
    """试卷模板"""
    template_id: str = ""
    name: str = ""
    exam_type: str = "custom"
    subject_id: str = ""
    total_time_minutes: int = 15
    question_patterns: List[QuestionPattern] = field(default_factory=list)
    difficulty_distribution: Dict[str, float] = field(default_factory=dict)
    bloom_distribution: Dict[str, float] = field(default_factory=dict)
    is_user_uploaded: bool = False


# ===== 内置模板定义 =====

QUICK_PRACTICE_TEMPLATE = ExamTemplate(
    template_id="quick_practice",
    name="快速练习",
    exam_type="custom",
    subject_id="*",
    total_time_minutes=15,
    question_patterns=[
        QuestionPattern(
            pattern_id="choice_single",
            name="单选题",
            count=5,
            time_per_question=120,
            points_per_question=1.0,
            context_budget=ContextBudget(max_tokens=1500, max_nodes=5),
            concept_depth=1,
        ),
    ],
    difficulty_distribution={"easy": 0.4, "medium": 0.4, "hard": 0.2},
    bloom_distribution={"understand": 0.4, "apply": 0.4, "analyze": 0.2},
)

BUILTIN_TEMPLATES = {
    "quick_practice": QUICK_PRACTICE_TEMPLATE,
}


@dataclass
class AnswerRecord:
    """
    答题记录：用于 IRT 校准和能力画像
    """
    record_id: str = ""
    user_id: str = ""
    subject_id: str = ""
    group_id: str = ""
    question_id: str = ""
    sequence: int = 0
    
    # 作答内容
    user_answer: str = ""
    correct_answer: str = ""
    is_correct: bool = False
    
    # 时间
    time_spent: int = 0  # 秒
    answered_at: Optional[Any] = None
    
    # 关联概念（用于知识传播分析）
    primary_concepts: List[str] = field(default_factory=list)
    
    # IRT 相关（提交时计算）
    theta_before: float = 0.0  # 答题前能力估计
    theta_after: float = 0.0   # 答题后能力估计
    item_information: float = 0.0  # 该题的信息量 I(θ)
