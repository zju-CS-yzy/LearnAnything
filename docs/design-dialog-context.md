# 多轮对话上下文机制设计方案

> 版本: v0.1
> 日期: 2026-07-18
> 状态: 设计阶段（待讨论后实现）

## 1. 设计目标

让 LearnAnything 的三个核心 Agent（TutorAgent / QuizAgent / CoachAgent）支持**多轮对话上下文**，实现：
- 用户连续提问时，Agent 能记住之前的对话内容
- 对话上下文跨会话持久化（重启后仍可用）
- 与现有 Agent 集体记忆 L1 层（`UserStateStore` / `MessageBus`）无缝连接
- 参考 OpenClaw 自身的上下文管理架构（`MEMORY.md` / `memory/*.md` / 会话历史）

## 2. 核心问题分析

### 当前状态（无对话上下文）

```
用户: "RAG 是什么？"
  -> TutorAgent.handle("RAG 是什么？")  # 独立查询，无历史
  -> 返回 RAG 定义

用户: "它和 GraphRAG 有什么区别？"
  -> TutorAgent.handle("它和 GraphRAG 有什么区别？")  # "它" 指代不明！
  -> 需要用户明确说 "RAG 和 GraphRAG 的区别"
```

### 期望状态（有对话上下文）

```
用户: "RAG 是什么？"
  -> TutorAgent.handle("RAG 是什么？", context=DialogContext)
  -> 返回 RAG 定义
  -> 系统记录: 当前话题="RAG"

用户: "它和 GraphRAG 有什么区别？"
  -> TutorAgent.handle("它和 GraphRAG 有什么区别？", context=DialogContext)
  -> 系统解析 "它" -> 指代 "RAG"（通过上下文解析）
  -> 返回 RAG vs GraphRAG 对比
```

## 3. 参考架构：OpenClaw 上下文管理

OpenClaw 自身的上下文管理机制（本项目可借鉴）：

| 层级 | 作用 | 持久化 | 生命周期 |
|------|------|--------|----------|
| **会话历史** | 当前对话的完整消息记录 | `memory/YYYY-MM-DD.md` | 按日归档 |
| **长期记忆** | 跨会话的 curated 知识 | `MEMORY.md` | 永久 |
| **用户画像** | 用户偏好、习惯、背景 | `USER.md` | 永久 |
| **技能状态** | 工具配置、环境信息 | `TOOLS.md` | 永久 |
| **心跳状态** | 周期性检查点 | `HEARTBEAT.md` | 按需 |

**借鉴点**：
1. **分层存储**：短期上下文（当前对话）vs 长期记忆（跨会话知识状态）
2. **文件持久化**：`memory/*.md` 按日归档，类似我们的 `UserStateStore` SQLite 持久化
3. **上下文注入**：每次对话前读取相关记忆文件，注入到 prompt

## 4. 设计方案

### 4.1 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                     对话上下文管理器                         │
│                    (DialogContextManager)                     │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ 短期上下文    │  │ 长期记忆     │  │ 消息总线事件       │  │
│  │ SessionMemory │  │ UserMemory   │  │ MessageBus Events  │  │
│  │ (SQLite)      │  │ (SQLite)     │  │                    │  │
│  └──────────────┘  └──────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
   │ TutorAgent   │    │ QuizAgent   │    │ CoachAgent   │
   │ handle(query,│    │ handle(query,│   │ handle(query,│
   │  context=ctx)│    │  context=ctx)│   │  context=ctx)│
   └─────────────┘    └─────────────┘    └─────────────┘
```

### 4.2 数据模型

#### 表 1: `dialog_sessions`（对话会话）

```sql
CREATE TABLE dialog_sessions (
    session_id TEXT PRIMARY KEY,        -- 会话唯一标识 (UUID)
    user_id TEXT NOT NULL,              -- 用户标识（匿名或登录用户）
    subject TEXT,                       -- 当前学科
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_agent TEXT,                    -- 最后交互的 Agent
    current_topic TEXT,                 -- 当前话题（提取的关键词）
    status TEXT DEFAULT 'active',       -- active / closed / expired
    context_summary TEXT                -- 对话摘要（由 LLM 生成）
);
```

#### 表 2: `dialog_messages`（对话消息）

```sql
CREATE TABLE dialog_messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,       -- 轮次编号（1, 2, 3...）
    role TEXT NOT NULL,                 -- 'user' / 'agent' / 'system'
    agent_name TEXT,                    -- Agent 名称（role=agent 时）
    content TEXT NOT NULL,              -- 消息内容（文本或 JSON）
    intent TEXT,                        -- 意图分类（concept/quiz/evaluate/job）
    metadata TEXT,                      -- JSON：{topic, theta, weak_areas, ...}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES dialog_sessions(session_id)
);

CREATE INDEX idx_messages_session ON dialog_messages(session_id, turn_number);
```

#### 表 3: `dialog_topics`（话题追踪）

```sql
CREATE TABLE dialog_topics (
    topic_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,           -- 话题名称
    first_turn INTEGER,                 -- 首次出现轮次
    last_turn INTEGER,                  -- 最后出现轮次
    mention_count INTEGER DEFAULT 1,    -- 提及次数
    canonical_concept_ids TEXT,         -- 关联的 CanonicalConcept IDs（逗号分隔）
    FOREIGN KEY (session_id) REFERENCES dialog_sessions(session_id)
);
```

### 4.3 对话上下文对象（`DialogContext`）

```python
@dataclass
class DialogContext:
    """传递在 Agent 之间的对话上下文对象"""
    session_id: str
    user_id: str
    turn_number: int                    # 当前轮次
    history: List[Dict[str, Any]]      # 最近 N 轮消息（role, content, agent_name）
    current_topic: str                  # 当前话题
    topic_chain: List[str]             # 话题链（历史话题列表）
    user_theta: float                  # 当前 IRT 能力值
    weak_areas: List[str]              # 当前薄弱领域
    subject: str                       # 当前学科
    
    # 指代解析结果
    resolved_references: Dict[str, str]  # {"它": "RAG", "这个方法": "向量检索"}
    
    def to_prompt_context(self, max_turns: int = 5) -> str:
        """转换为 LLM prompt 中的上下文文本"""
        lines = ["【对话上下文】"]
        for msg in self.history[-max_turns:]:
            role_label = "用户" if msg["role"] == "user" else msg.get("agent_name", "系统")
            content = msg["content"][:200]  # 截断
            lines.append(f"{role_label}: {content}")
        if self.current_topic:
            lines.append(f"\n当前话题: {self.current_topic}")
        return "\n".join(lines)
    
    def add_message(self, role: str, content: str, agent_name: str = None, metadata: Dict = None):
        """添加新消息到历史（同时持久化到 SQLite）"""
        self.history.append({
            "role": role,
            "content": content,
            "agent_name": agent_name,
            "metadata": metadata or {},
        })
        self.turn_number += 1
```

### 4.4 与现有组件的集成

#### 与 Agent 集体记忆 L1 层的连接

```
现有 L1 层（UserStateStore）:
  UserKnowledgeState ── 存储在 SQLite ── 跨会话持久化
  字段: user_id, subject_id, canonical_id, mastery_level, theta, test_count, streak

新增对话层（DialogContextManager）:
  DialogSession ── 存储在 SQLite ── 跨会话持久化
  DialogMessage ── 存储在 SQLite ── 跨会话持久化
  DialogTopic ── 存储在 SQLite ── 跨会话持久化

连接点:
  1. DialogContext.user_theta  <-- 读取 UserKnowledgeState.theta
  2. DialogContext.weak_areas  <-- 查询 UserKnowledgeState.streak > 2 的记录
  3. 对话结束时：DialogContext 生成摘要 --> 写入 UserKnowledgeState.notes（扩展字段）
```

#### 与消息总线的集成

```python
# DialogContextManager 订阅消息总线事件
class DialogContextManager:
    def __init__(self, message_bus: MessageBus, user_state_store: UserStateStore):
        self._bus = message_bus
        self._state_store = user_state_store
        self._db = sqlite3.connect("dialog_context.db")
        self._init_tables()
        
        # 订阅关键事件
        self._bus.subscribe("user_state", "DialogContextManager", self.on_ability_updated)
        self._bus.subscribe("weak_area", "DialogContextManager", self.on_weak_area_detected)
        self._bus.subscribe("quiz", "DialogContextManager", self.on_quiz_generated)
    
    def on_ability_updated(self, msg):
        """能力更新时，更新当前会话的 user_theta"""
        session = self._get_active_session(msg.payload.get("user_id"))
        if session:
            session.user_theta = msg.payload.get("theta", 0.0)
            self._update_session(session)
    
    def on_weak_area_detected(self, msg):
        """薄弱领域检测时，更新当前会话的 weak_areas"""
        session = self._get_active_session(msg.payload.get("user_id"))
        if session:
            concept = msg.payload.get("concept")
            if concept and concept not in session.weak_areas:
                session.weak_areas.append(concept)
                self._update_session(session)
```

### 4.5 指代解析（Anaphora Resolution）

用户查询中的指代词（"它"、"这个方法"、"刚才说的"）需要通过上下文解析为具体实体。

```python
class ReferenceResolver:
    """基于对话历史的指代解析器"""
    
    PRONOUNS = {"它", "他", "她", "这", "那", "这个", "那个", "这种方法", "刚才说的"}
    
    def resolve(self, query: str, context: DialogContext) -> str:
        """解析查询中的指代词，返回替换后的完整查询"""
        resolved = query
        
        # 1. 代词解析（"它" -> 当前话题）
        if self._has_pronoun(query) and context.current_topic:
            resolved = query.replace("它", context.current_topic)
            resolved = query.replace("这个方法", context.current_topic)
        
        # 2. 省略主语解析（"和 GraphRAG 有什么区别？" -> "RAG 和 GraphRAG 有什么区别？"）
        if self._is_ellipsis(query) and context.current_topic:
            resolved = f"{context.current_topic} {query}"
        
        # 3. 话题切换检测（"换个话题，讲下 Embedding"）
        if self._is_topic_switch(query):
            context.current_topic = self._extract_new_topic(query)
        
        return resolved
    
    def _has_pronoun(self, query: str) -> bool:
        return any(p in query for p in self.PRONOUNS)
    
    def _is_ellipsis(self, query: str) -> bool:
        # 查询以介词/连词开头，缺少主语
        return bool(re.match(r'^(和|与|跟|同|跟|以及|还有|另外|那么|那|然后)', query.strip()))
    
    def _is_topic_switch(self, query: str) -> bool:
        switch_keywords = {"换个话题", "换个", "另外", "再讲一下", "再说说", "还有"}
        return any(kw in query for kw in switch_keywords)
```

### 4.6 Prompt 注入策略

将对话上下文注入 LLM prompt 的策略：

```python
def build_prompt_with_context(
    base_prompt: str,
    query: str,
    context: DialogContext,
    max_history_turns: int = 3,
    max_context_tokens: int = 1000,
) -> str:
    """构建带上下文的 prompt"""
    
    # 1. 指代解析后的查询
    resolved_query = ReferenceResolver().resolve(query, context)
    
    # 2. 生成对话历史文本（最近 N 轮）
    history_text = context.to_prompt_context(max_turns=max_history_turns)
    
    # 3. 注入到 prompt
    prompt_parts = [
        base_prompt,
        "",
        "【对话历史】",
        history_text,
        "",
        f"当前用户查询: {resolved_query}",
    ]
    
    # 4. 如果上下文太长，使用 LLM 生成摘要替代完整历史
    full_prompt = "\n".join(prompt_parts)
    if estimate_tokens(full_prompt) > max_context_tokens:
        summary = context.to_summary()  # LLM 生成的对话摘要
        prompt_parts = [
            base_prompt,
            "",
            "【对话摘要】",
            summary,
            "",
            f"当前用户查询: {resolved_query}",
        ]
    
    return "\n".join(prompt_parts)
```

### 4.7 会话生命周期管理

```python
class SessionLifecycleManager:
    """管理对话会话的生命周期"""
    
    SESSION_TIMEOUT_MINUTES = 30  # 30 分钟无活动视为超时
    MAX_HISTORY_TURNS = 20       # 单会话最大保留轮次
    
    def get_or_create_session(self, user_id: str, subject: str = None) -> DialogSession:
        """获取活跃会话或创建新会话"""
        # 1. 查找最近活跃会话
        session = self._find_active_session(user_id, subject)
        
        # 2. 检查是否超时
        if session and self._is_expired(session):
            self._close_session(session)
            session = None
        
        # 3. 创建新会话
        if not session:
            session = DialogSession(
                session_id=str(uuid.uuid4()),
                user_id=user_id,
                subject=subject,
                current_topic=None,
                user_theta=0.0,
                weak_areas=[],
            )
            self._save_session(session)
        
        return session
    
    def _is_expired(self, session: DialogSession) -> bool:
        """检查会话是否超时"""
        elapsed = (datetime.now() - session.updated_at).total_seconds()
        return elapsed > self.SESSION_TIMEOUT_MINUTES * 60
```

## 5. 实现路径（分阶段）

### 阶段 1: 基础设施（1-2 天）

1. **创建 `DialogContextManager`** 类
   - 文件: `core/dialog_context.py`
   - 包含: `DialogSession`, `DialogMessage`, `DialogTopic` 数据模型
   - SQLite 表创建 + CRUD 操作

2. **扩展 `BaseAgent`**
   - 修改 `handle(self, query: str, **kwargs)` → `handle(self, query: str, context: DialogContext = None, **kwargs)`
   - 每个 Agent 在生成回答时，如果提供了 `context`，将对话历史注入 prompt

3. **修改 `Coordinator.handle()`**
   - 从 `kwargs` 中提取 `session_id`
   - 调用 `DialogContextManager.get_or_create_session(user_id, subject)`
   - 将 `context` 传递给目标 Agent
   - 收到 Agent 结果后，保存用户消息和 Agent 回复到 `dialog_messages`

### 阶段 2: 指代解析与话题追踪（1-2 天）

1. **实现 `ReferenceResolver`**
   - 基于规则的指代解析（代词、省略主语、话题切换）
   - 可扩展为 LLM-based 解析（更准确但成本更高）

2. **实现话题追踪**
   - 从每轮对话中提取话题关键词
   - 更新 `dialog_topics` 表
   - 话题链用于 Agent 的上下文切换提示

### 阶段 3: 与现有系统深度集成（1-2 天）

1. **连接 `UserStateStore`**
   - `DialogContext.user_theta` 自动同步 `UserKnowledgeState.theta`
   - 对话结束时，生成对话摘要写入 `UserKnowledgeState.notes`

2. **连接 `MessageBus`**
   - `DialogContextManager` 订阅 `user_state` / `weak_area` / `quiz` 事件
   - 事件触发时更新当前会话的上下文状态

3. **Agent 个性化 Prompt**
   - TutorAgent: 根据 `user_theta` 调整讲解深度（初级用通俗语言，高级用专业术语）
   - QuizAgent: 根据 `weak_areas` 和 `current_topic` 出题
   - CoachAgent: 根据对话历史中的错误模式调整评分权重

### 阶段 4: 前端支持（2-3 天）

1. **会话列表页面**
   - 展示历史会话列表（时间、学科、最后话题、轮数）
   - 可点击继续对话

2. **对话界面增强**
   - 显示当前话题标签
   - 显示"上下文已继承"提示
   - 支持"新会话"按钮（显式重置上下文）

3. **持久化验证**
   - 重启后端后验证对话历史是否正确加载
   - 跨会话验证 `user_theta` 和 `weak_areas` 的连续性

## 6. 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 存储介质 | SQLite（与 `UserStateStore` 同库） | 统一持久化，简化运维 |
| 上下文注入方式 | Prompt 文本注入（而非向量检索） | 简单、可解释、适合当前规模 |
| 指代解析 | 规则为主 + LLM 可选 | 规则覆盖 80% 场景，LLM 用于复杂歧义 |
| 会话超时 | 30 分钟 | 平衡用户体验与资源占用 |
| 历史保留 | 最近 20 轮 / 1000 tokens | 避免 prompt 过长，超出 LLM 上下文 |
| 话题提取 | 从 LLM 回答中提取关键概念 | 复用现有 `ConceptExtractor` 能力 |

## 7. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 指代解析错误 | 中等 | 规则 + 可配置开关；用户可手动重置会话 |
| 上下文过长导致 LLM 性能下降 | 高 | 摘要机制 + Token 限制 + 截断策略 |
| 跨会话数据不一致 | 低 | 事务写入 SQLite；定期数据校验 |
| 前端状态与后端不同步 | 中 | 每次对话后前端拉取完整历史 |
| 敏感信息泄露 | 低 | 对话内容仅本地存储，不上传 |

## 8. 与遗留问题的关联

| 遗留问题 | 关联方式 |
|----------|----------|
| `LA-040-P1-QUIZ-TYPES`（多题型） | 对话上下文影响 QuizAgent 出题：同一话题下连续出题时，避免重复考察相同知识点 |
| `LA-040-P1-VIS`（评测可视化） | 对话历史可作为评测数据的补充来源（对话中的错误回答） |
| `P0-INT-6`（消息总线） | DialogContextManager 订阅消息总线，接收 Agent 事件更新上下文 |
| `P0-INT-4`（UserStateStore） | 对话结束时的摘要写入 UserKnowledgeState，实现跨会话记忆 |
| `LA-OPT-P2-001`（混合查询） | 对话上下文中的 `current_topic` 可作为图查询的默认种子概念 |

---

*文档结束 — 待讨论确认后进入实现阶段*
