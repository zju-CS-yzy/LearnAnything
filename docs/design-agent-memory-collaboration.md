# LA-040-P0-MEM: 多 Agent 记忆与协作架构设计文档

> 版本: 1.0  
> 创建日期: 2026-07-14  
> 关联: LA-040-P0 图谱教育 Agent 系统  
> 参考论文: G-Memory (2024), A-MEM (2025), Mem0 (2025), MetaGPT (2024), Chain-of-Agents (NeurIPS 2024), MA-RAG (2025)

---

## 一、设计背景

### 1.1 现有 Agent 体系

LearnAnything P0 已构建 5 个核心 Agent：

| Agent | 职责 | 输入 | 输出 |
|:---|:---|:---|:---|
| **Quiz Agent** | 出题 | 模板 + 目标概念 | 题目组（QuestionGroup） |
| **Coach Agent** | 测评与画像 | 整组答题记录 | 能力画像 + 推荐 |
| **Tutor Agent** | 讲解 | 错题 + 用户状态 | 知识网络讲解 |
| **Concept Retriever** | 概念检索 | 名称/语义查询 | CanonicalConcept 列表 |
| **Subgraph Builder** | 子图构建 | 种子概念 + 模式 | 局部子图 |

### 1.2 需要解决的核心问题

| 问题 | 影响 | 解决方案方向 |
|:---|:---|:---|
| Agent 间数据孤岛 | 每个 Agent 独立查询数据库，重复检索 | **共享记忆空间** |
| 用户状态不一致 | Coach 更新的掌握度，Quiz 看不到 | **全局状态同步** |
| 多轮对话断裂 | 上一轮的子图上下文下一轮丢失 | **对话历史记忆** |
| Agent 能力边界模糊 | Quiz 和 Coach 都涉及难度估计 | **角色分工协议** |
| 冷启动效率低 | 新用户无历史时各 Agent 独立探索 | **集体经验复用** |

---

## 二、参考论文核心思想

### 2.1 G-Memory: Hierarchical Memory for Multi-Agent Systems (2024)

**核心贡献**：为每个 Agent 设计分层记忆结构

```
┌─────────────────────────────────────────┐
│  L3: Collective Memory (集体记忆)         │
│  - 共享知识图谱、用户画像、全局统计数据      │
│  - 所有 Agent 可读，Coordinator 可写       │
├─────────────────────────────────────────┤
│  L2: Team Memory (团队记忆)               │
│  - 同场景 Agent 间的共享上下文              │
│  - 如 Quiz + Coach 共享 IRT 参数          │
├─────────────────────────────────────────┤
│  L1: Individual Memory (个体记忆)         │
│  - 每个 Agent 的私有工作记忆                │
│  - 如 Tutor 的讲解策略偏好                  │
└─────────────────────────────────────────┘
```

**对本系统的启发**：
- 知识图谱（L3 集体记忆）作为所有 Agent 的共同知识底座
- IRT 参数和用户状态（L2 团队记忆）在 Quiz/Coach/Tutor 间共享
- 每个 Agent 的 prompt 模板和策略偏好（L1 个体记忆）独立维护

### 2.2 A-MEM: Agentic Memory for LLM Agents (2025)

**核心贡献**：Agent 主动管理自己的记忆

```python
class AgenticMemory:
    """
    Agent 主动决定：
    1. 何时读取记忆（记忆检索策略）
    2. 何时写入记忆（记忆更新策略）
    3. 记忆重要性排序（记忆优先级）
    """
    
    def retrieve(self, query, strategy="relevance"):
        #  relevance / recency / importance / hybrid
        pass
    
    def update(self, new_info, importance_score):
        #  根据重要性决定是否写入，是否替换旧记忆
        pass
    
    def reflect(self):
        #  定期反思：合并相似记忆，删除低价值记忆
        pass
```

**对本系统的启发**：
- Coach Agent 应该主动决定何时更新用户画像（不是所有答题都触发完整画像重算）
- Tutor Agent 应该根据用户历史错误模式，主动检索最相关的知识子图

### 2.3 Mem0: Scalable Long-Term Memory (2025)

**核心贡献**：分层记忆存储架构

```
┌─────────────────────────────────────────┐
│  Vector DB (语义检索层)                   │
│  - 用户对话历史 Embedding 检索             │
├─────────────────────────────────────────┤
│  Graph DB (关系推理层)                    │
│  - 实体关系、知识依赖                      │
├─────────────────────────────────────────┤
│  Key-Value Store (快速访问层)             │
│  - 用户偏好、高频查询缓存                  │
└─────────────────────────────────────────┘
```

**对本系统的启发**：
- 知识图谱（Graph DB）已存在 → 用于概念关系和推理
- 需要补充 Vector DB → 用于对话历史和语义检索
- 需要补充 KV Store → 用于用户状态高频访问

### 2.4 MetaGPT: Multi-Agent Collaborative Framework (2024)

**核心贡献**：角色分工 + 标准化输出 + 共享消息池

```python
class MetaGPT:
    """
    核心机制：
    1. 角色定义：ProductManager, Architect, Engineer, QA
    2. 标准化输出：每个角色产出特定格式的文档
    3. 消息池：所有角色共享一个消息队列，订阅感兴趣的消息
    """
    
    def run(self, idea):
        # PM 产出 PRD → 写入消息池
        # Architect 订阅 PRD → 产出设计文档 → 写入消息池
        # Engineer 订阅设计文档 → 产出代码 → 写入消息池
        # QA 订阅代码 → 产出测试报告
        pass
```

**对本系统的启发**：
- 为每个 Agent 定义标准化输出格式（如 QuestionGroup, KnowledgeProfile）
- 建立 Agent 间消息总线（Message Bus），Agent 订阅相关事件

### 2.5 Chain-of-Agents (NeurIPS 2024)

**核心贡献**：长文本多 Agent 协作链

```
Worker 1 → Worker 2 → Worker 3 → ... → Manager
   ↑          ↑          ↑              ↑
 处理片段1   处理片段2   处理片段3      整合所有输出
```

**对本系统的启发**：
- 出题流程可以是链式：Retriever → Builder → Assembler → LLM
- 每个环节产出标准化中间结果，下一环节接力处理

### 2.6 MA-RAG: Multi-Agent RAG via Collaborative Chain-of-Thought (2025)

**核心贡献**：多 Agent 协作式 RAG，每个 Agent 负责不同检索策略

```python
class MARAG:
    """
    多个 Agent 各自用不同策略检索：
    - Agent A: 关键词检索
    - Agent B: 语义检索  
    - Agent C: 图遍历检索
    
    然后投票/融合，生成最终答案
    """
```

**对本系统的启发**：
- Concept Retriever 可以扩展为多策略：名称匹配 + Embedding + 别名
- 结果融合机制（投票 / 加权 / 去重）

---

## 三、LearnAnything 多 Agent 记忆与协作架构

### 3.1 总体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                           用户交互层                                  │
│                    （出题 / 答题 / 查看讲解 / 查看画像）                │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Agent 协调器 (Coordinator)                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   │
│  │   Router   │  │  Context   │  │  Session   │  │  Event     │   │
│  │   路由     │  │  Manager   │  │  Manager   │  │  Publisher │   │
│  │            │  │  上下文管理 │  │  会话管理  │  │  事件发布  │   │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘   │
└────────┼───────────────┼───────────────┼───────────────┼──────────┘
         │               │               │               │
         ▼               ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         共享记忆空间 (Shared Memory)                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │  L3: 集体记忆     │  │  L2: 团队记忆     │  │  L1: 个体记忆     │   │
│  │  Knowledge Graph │  │  User States     │  │  Agent Prompts   │   │
│  │  Global Stats    │  │  IRT Params      │  │  Strategy Pref   │   │
│  │  Shared Context  │  │  Session History │  │  Private Cache   │   │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
         │               │               │               │
         ▼               ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Agent 执行层                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────────┐   │
│  │  Quiz    │  │  Coach   │  │  Tutor   │  │  Retriever/Builder │   │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  (工具 Agent)      │   │
│  │          │  │          │  │          │  │                    │   │
│  │ 产出:    │  │ 产出:    │  │ 产出:    │  │ 产出:              │   │
│  │ Question │  │ Profile  │  │ Explanation│ │ Subgraph/Context   │   │
│  └──────────┘  └──────────┘  └──────────┘  └────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 三层记忆空间

#### L3: 集体记忆（Collective Memory）

**存储内容**：

| 数据类型 | 存储位置 | 读写权限 | 更新频率 |
|:---|:---|:---|:---|
| 知识图谱（4 层架构） | KùzuDB | 所有 Agent 只读 | 构建时 |
| 全局概念统计（PageRank, 中心性） | Redis/JSON | 所有 Agent 只读 | 图谱更新后 |
| 试卷模板库 | 内存 Dict | 所有 Agent 只读 | 启动时加载 |
| 跨学科通用规则 | 配置文件 | 所有 Agent 只读 | 手动更新 |

**访问接口**：
```python
class CollectiveMemory:
    """集体记忆接口：所有 Agent 共享的只读知识底座"""
    
    def get_concept(self, canonical_id: str) -> ConceptNode:
        """获取规范概念"""
        pass
    
    def get_subgraph(self, seed_concepts: List[str], depth: int) -> Subgraph:
        """获取局部子图"""
        pass
    
    def get_centrality(self, canonical_id: str) -> float:
        """获取图中心性"""
        pass
    
    def get_template(self, template_id: str) -> ExamTemplate:
        """获取试卷模板"""
        pass
```

#### L2: 团队记忆（Team Memory）

**存储内容**：

| 数据类型 | 存储位置 | 读写权限 | 生命周期 |
|:---|:---|:---|:---|
| 用户知识状态（UserKnowledgeState） | SQLite/Redis | Quiz 读, Coach 写 | 会话级 |
| IRT 参数（题目难度、区分度） | SQLite | Quiz 写, Coach 读 | 长期 |
| 答题记录（AnswerRecord） | SQLite | Coach 写, Tutor 读 | 长期 |
| 能力画像（KnowledgeProfile） | SQLite/JSON | Coach 写, UI 读 | 长期 |
| 会话历史（SessionHistory） | SQLite | 所有 Agent 读写 | 会话级 |

**访问接口**：
```python
class TeamMemory:
    """团队记忆接口：同场景 Agent 间的共享状态"""
    
    # 用户状态
    def get_user_state(self, user_id, subject_id, concept_id) -> UserKnowledgeState:
        pass
    
    def update_user_state(self, state: UserKnowledgeState) -> None:
        pass
    
    # IRT 参数
    def get_irt_params(self, question_id: str) -> IRTParams:
        pass
    
    def update_irt_params(self, question_id: str, params: IRTParams) -> None:
        pass
    
    # 会话历史
    def get_session_history(self, session_id: str) -> List[Dict]:
        """获取当前会话的历史交互"""
        pass
    
    def append_session(self, session_id: str, event: Dict) -> None:
        """追加会话事件"""
        pass
```

#### L1: 个体记忆（Individual Memory）

**存储内容**：

| Agent | 个体记忆内容 | 存储位置 |
|:---|:---|:---|
| **Quiz Agent** | 出题策略偏好、历史出题模式 | 内存 |
| **Coach Agent** | 评分策略、画像生成策略 | 内存 |
| **Tutor Agent** | 讲解深度偏好、用户反馈历史 | 内存 |
| **Concept Retriever** | Embedding 缓存、检索策略参数 | 内存/Redis |
| **Context Assembler** | Token 预算使用模式、截断策略 | 内存 |

**访问接口**：
```python
class IndividualMemory:
    """个体记忆接口：每个 Agent 的私有工作记忆"""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.working_memory = {}  # 当前任务上下文
        self.strategy_cache = {}  # 策略偏好
    
    def get_strategy(self, task_type: str) -> Dict:
        """获取该 Agent 对某类任务的策略偏好"""
        pass
    
    def update_strategy(self, task_type: str, feedback: Dict) -> None:
        """根据反馈更新策略"""
        pass
```

### 3.3 Agent 间协作协议

#### 3.3.1 事件驱动的消息总线

```python
class AgentEventBus:
    """
    Agent 间事件总线
    
    事件类型：
    - question_generated: Quiz 生成题目后发布
    - answer_submitted: 用户提交答案后发布
    - state_updated: Coach 更新用户状态后发布
    - profile_generated: Coach 生成画像后发布
    - explanation_requested: 用户请求讲解后发布
    """
    
    def publish(self, event_type: str, payload: Dict) -> None:
        """发布事件"""
        pass
    
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """订阅事件"""
        pass
```

**事件流示例**：

```
用户: "生成一组 Transformer 练习题"
    ↓
[Event] user_request → {type: "generate_quiz", user_id: "u1", subject: "transformer"}
    ↓
Quiz Agent 订阅 → 调用 ConceptRetriever + SubgraphBuilder → 生成 QuestionGroup
    ↓
[Event] question_generated → {group_id: "qg_xxx", questions: [...]}
    ↓
用户答题完成，点击提交
    ↓
[Event] answer_submitted → {group_id: "qg_xxx", answers: [...]}
    ↓
Coach Agent 订阅 → 批量评分 + IRT 更新 + 知识传播
    ↓
[Event] state_updated → {user_id: "u1", updated_concepts: [...]}
[Event] profile_generated → {user_id: "u1", profile: {...}}
    ↓
用户: "这题为什么错了？"
    ↓
[Event] explanation_requested → {question_id: "q_xxx", user_answer: "C"}
    ↓
Tutor Agent 订阅 → 加载 QuestionTrace + UserStates → 生成讲解
    ↓
[Event] explanation_generated → {question_id: "q_xxx", explanation: "..."}
```

#### 3.3.2 Agent 间数据流

```python
# Quiz Agent → Coach Agent 的数据传递
question_group = quiz_agent.create_group(...)
# Quiz Agent 将 IRT 参数和知识追踪写入 Team Memory
team_memory.save_question_metadata(question_group)

# 用户提交后
result = coach_agent.process_submission(group_id, answers)
# Coach Agent 读取 Quiz Agent 写入的 IRT 参数
irt_params = team_memory.get_irt_params(question_id)
# Coach Agent 更新用户状态后写入 Team Memory
team_memory.update_user_state(new_state)

# Tutor Agent 讲解时
explanation = tutor_agent.explain(question_id, user_answer)
# Tutor Agent 读取 Coach Agent 更新的用户状态
user_states = team_memory.get_user_states(user_id, subject_id)
# Tutor Agent 读取 Quiz Agent 写入的题目溯源
trace = team_memory.get_question_trace(question_id)
```

### 3.4 Coordinator（协调器）

Coordinator 是 Agent 协作的中央调度器：

```python
class AgentCoordinator:
    """
    Agent 协调器：管理 Agent 生命周期和任务调度
    """
    
    def __init__(self):
        self.agents = {}
        self.event_bus = AgentEventBus()
        self.collective_memory = CollectiveMemory()
        self.team_memory = TeamMemory()
    
    def register_agent(self, agent_id: str, agent: BaseAgent):
        """注册 Agent"""
        self.agents[agent_id] = agent
        # 为 Agent 注入共享记忆
        agent.collective_memory = self.collective_memory
        agent.team_memory = self.team_memory
        agent.individual_memory = IndividualMemory(agent_id)
    
    def dispatch(self, user_request: Dict) -> Dict:
        """
        调度用户请求到合适的 Agent
        
        路由规则：
        - "出题" → Quiz Agent
        - "提交" → Coach Agent
        - "讲解" → Tutor Agent
        - "画像" → Coach Agent
        """
        intent = self._parse_intent(user_request)
        
        routing = {
            "generate_quiz": "quiz_agent",
            "submit_answers": "coach_agent",
            "explain": "tutor_agent",
            "get_profile": "coach_agent",
        }
        
        agent_id = routing.get(intent)
        if not agent_id:
            raise ValueError(f"未知意图: {intent}")
        
        agent = self.agents[agent_id]
        return agent.handle(user_request)
    
    def _parse_intent(self, request: Dict) -> str:
        """解析用户意图"""
        pass
```

---

## 四、实现路线图

### 4.1 P0 阶段（当前）：内存级共享

```python
# P0 实现：所有 Agent 共享同一个内存缓存
shared_cache = MockCache()  # 或 Redis

# 每个 Agent 通过共享缓存读写 Team Memory
group_manager = GroupManager(
    retriever=retriever,
    builder=builder,
    assembler=assembler,
    irt=irt,
    cache=shared_cache,  # ← 共享缓存
)

# 后续 Tutor Agent 通过同一个缓存读取用户状态
tutor = TutorAgent(cache=shared_cache)
user_states = tutor.load_states(user_id, subject_id)
```

### 4.2 P1 阶段：SQLite 持久化

```python
# P1 实现：SQLite 数据库替代内存缓存
import sqlite3

team_db = sqlite3.connect("team_memory.db")

# UserKnowledgeState 表
# AnswerRecord 表
# QuestionTrace 表
# KnowledgeProfile 表

# Agent 通过 ORM 或 DAO 访问
group_manager = GroupManager(db=team_db, cache=redis_cache)
```

### 4.3 P2 阶段：事件总线 + 异步处理

```python
# P2 实现：引入消息队列（如 Redis Pub/Sub 或 RabbitMQ）
from redis import Redis

event_bus = Redis()

# Coach Agent 订阅答题事件
def on_answer_submitted(event):
    group_manager.process_submission(event.group_id, event.answers)

event_bus.subscribe("answer_submitted", on_answer_submitted)

# Quiz Agent 发布题目生成事件
event_bus.publish("question_generated", {
    "group_id": group.group_id,
    "question_count": len(group.questions),
})
```

### 4.4 P3 阶段：完整多 Agent 框架

```python
# P3 实现：引入 MetaGPT 或 AutoGen 式框架
from autogen import AssistantAgent, UserProxyAgent

quiz_agent = AssistantAgent(
    name="quiz_agent",
    system_message="你是出题专家...",
    llm_config={...}
)

coach_agent = AssistantAgent(
    name="coach_agent",
    system_message="你是测评专家...",
    llm_config={...}
)

# Agent 间自动协商
chat = autogen.GroupChat(
    agents=[quiz_agent, coach_agent, tutor_agent],
    messages=[],
    max_round=10
)
```

---

## 五、与现有 P0 代码的对接

### 5.1 当前已实现（P0）

```
GroupManager
├── ConceptRetriever (共享 graph_store)
├── SubgraphBuilder (共享 graph_store)
├── ContextAssembler (可选 graph_store)
├── IRTEstimator (独立)
└── cache (共享内存缓存)
```

### 5.2 下一步改造（P1）

1. **提取 CollectiveMemory 接口**：将 graph_store 包装为 CollectiveMemory
2. **提取 TeamMemory 接口**：将 cache 升级为 SQLite + Redis 混合存储
3. **添加 EventBus**：用 Python 内置的 `queue.Queue` 或 `asyncio.Queue` 实现
4. **添加 Coordinator**：简单的路由调度器

---

## 六、关键设计决策

| 决策 | 选择 | 理由 |
|:---|:---|:---|
| 记忆分层 | L3/L2/L1 三层 | 参考 G-Memory 和 Mem0，职责清晰 |
| 状态同步 | 读写分离 + 事件通知 | Coach 写状态，Quiz/Tutor 读状态，避免竞争 |
| 存储选型 | P0 内存 → P1 SQLite → P2 Redis | 渐进式升级，不阻塞当前开发 |
| Agent 通信 | 共享缓存（P0）→ 消息总线（P2） | 先验证逻辑，再优化性能 |
| 用户画像 | Coach Agent 负责生成，其他 Agent 只读 | 单一写入者，避免数据不一致 |
| 题目溯源 | Quiz Agent 生成时写入，Tutor Agent 讲解时读取 | 一次写入，多次读取 |

---

## 七、待讨论问题

1. **Agent 数量扩展**：未来是否引入更多 Agent（如 ContentParser Agent、FeedbackCollector Agent）？
2. **记忆淘汰策略**：L2 团队记忆中的答题记录是否需要定期归档？
3. **跨用户学习**：能否从其他用户的数据中提炼共性规律（如某概念普遍薄弱）？
4. **Agent 冲突解决**：如果 Quiz Agent 和 Coach Agent 对难度估计不一致，听谁的？

---

*文档结束 — 等待进一步讨论和实现*
