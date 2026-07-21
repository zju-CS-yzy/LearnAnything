# LA-UI-001: Trae 式多 Agent 群聊架构设计方案

> 版本: 1.0
> 日期: 2026-07-21
> 状态: 设计阶段
> 关联: design-dialog-context.md, design-agent-memory-collaboration.md

---

## 一、设计目标

将 LearnAnything 从"功能视图切换"模式升级为"Trae 式分栏群聊"模式：

- **右侧 ChatView**：多 Agent 群聊入口，用户与 Tutor/Quiz/Coach 等 Agent 直接对话
- **左侧功能视图**：知识图谱、出题、评测、文档树等专业功能区
- **双向互动**：左侧元素可分享到右侧群聊，右侧 Agent 可驱动左侧视图变化

---

## 二、核心架构

### 2.1 布局设计

```
┌─────────────────────────────────────────────────────────────────────┐
│  Sidebar (窄边栏)    │  主内容区 (左侧 65%)     │  ChatView (右侧 35%) │
│                      │                          │                      │
│  📚 学科选择          │  ┌──────────────────┐   │  ┌────────────────┐  │
│  📊 知识图谱          │  │  GraphView       │   │  │ 群聊标题栏      │  │
│  📝 出题             │  │  或              │   │  │ Tutor | Quiz   │  │
│  📊 评测             │  │  QuizView        │   │  │ Coach | ...    │  │
│  📁 文档树           │  │  或              │   │  ├────────────────┤  │
│  💬 智能问答         │  │  EvaluateView    │   │  │ 消息列表        │  │
│                      │  │  或              │   │  │ 👤 用户: ...   │  │
│                      │  │  KnowledgeBase   │   │  │ 🎓 Tutor: ...  │  │
│                      │  └──────────────────┘   │  │ 📝 Quiz: ...   │  │
│                      │                          │  │ 📊 Coach: ...  │  │
│                      │                          │  ├────────────────┤  │
│                      │                          │  │ 输入框          │  │
│                      │                          │  │ [发送]         │  │
│                      │                          │  └────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 角色定义

| 角色 | 身份 | 职责 | 触发方式 |
|:---|:---|:---|:---|
| **用户** | 👤 | 发起需求、回答问题、分享元素 | 自然输入 |
| **TutorAgent** | 🎓 | 讲解知识、回答问题、解析概念 | `@tutor` 或默认 |
| **QuizAgent** | 📝 | 出题、解析题目、保存到题库 | `@quiz` |
| **CoachAgent** | 📊 | 能力评测、画像分析、学习建议 | `@evaluate` |
| **Coordinator** | 🎮 | 路由、协调、状态管理 | 后台自动 |

### 2.3 消息类型体系

```typescript
// 基础消息接口
interface BaseMessage {
  id: string;
  sender: 'user' | 'agent' | 'system';
  agent_name?: string;  // sender='agent' 时使用
  timestamp: number;
  session_id: string;
}

// 文本消息
interface TextMessage extends BaseMessage {
  type: 'text';
  content: string;  // Markdown 格式
  sources?: SourceRef[];  // LA-047 引用来源
}

// 卡片消息：左侧功能视图的元素分享到群聊
interface CardMessage extends BaseMessage {
  type: 'card';
  card_type: 'concept' | 'question' | 'quiz_result' | 'graph_node';
  title: string;
  data: any;  // 原始数据
  preview: string;  // 预览文本
  actions: CardAction[];  // 可操作按钮
}

// 命令消息：Agent 驱动左侧视图变化
interface CommandMessage extends BaseMessage {
  type: 'command';
  command: 'navigate' | 'highlight' | 'open_modal' | 'update_data';
  target: string;  // 目标视图 ID
  payload: any;
}

// 系统消息：状态变更、错误提示
interface SystemMessage extends BaseMessage {
  type: 'system';
  level: 'info' | 'warning' | 'error';
  content: string;
}
```

---

## 三、交互协议

### 3.1 用户 → Agent（右侧输入）

```
用户输入: "@quiz 给我出5道RAG相关的题目"
    ↓
ChatView 解析 @quiz → 设置目标 Agent = QuizAgent
    ↓
发送给后端: {query, agent_target: 'quiz', session_id}
    ↓
Coordinator 路由到 QuizAgent
    ↓
QuizAgent 生成题目 → 返回 CardMessage (type='card', card_type='question')
    ↓
ChatView 渲染题目卡片（可展开、可选择、可保存）
```

### 3.2 Agent → 左侧视图（命令驱动）

```
用户输入: "帮我找到知识图谱中关于 Transformer 的部分"
    ↓
TutorAgent 处理 → 返回 CommandMessage
    ↓
{
  type: 'command',
  command: 'navigate',
  target: 'graph',
  payload: {
    action: 'focus_node',
    node_id: 'concept_transformer',
    highlight: true
  }
}
    ↓
左侧 GraphView 接收命令 → 聚焦到 Transformer 节点 → 高亮显示
```

### 3.3 左侧 → 右侧分享（元素分享）

```
用户在 GraphView 中右键点击 "RAG架构" 节点
    ↓
选择 "分享到群聊"
    ↓
生成 CardMessage:
{
  type: 'card',
  card_type: 'concept',
  title: 'RAG架构',
  data: {node_id, name, description, type},
  preview: '检索增强生成(RAG)是将外部知识检索与...',
  actions: [
    {label: '详细解释', action: 'ask_tutor'},
    {label: '相关题目', action: 'ask_quiz'},
    {label: '能力评测', action: 'ask_evaluate'}
  ]
}
    ↓
发送到右侧 ChatView → 显示概念卡片
    ↓
用户点击 "详细解释" → 自动发送 "@tutor 请解释 RAG架构"
```

### 3.4 评测流程（跨 Agent 协作）

```
用户: "@evaluate 评测一下我对 RAG 的掌握"
    ↓
CoachAgent 生成评测题目（内部调用 QuizAgent）
    ↓
返回 CommandMessage: {command: 'open_modal', target: 'evaluate', payload: {questions}}
    ↓
左侧弹出评测弹窗（或切换到 EvaluateView）
    ↓
用户答题完成 → 结果自动分享到群聊
    ↓
CoachAgent 分析结果 → 生成能力画像卡片
    ↓
用户: "我的薄弱点在哪里？"
    ↓
TutorAgent 读取评测结果 → 针对性讲解
```

---

## 四、状态管理

### 4.1 全局状态

```typescript
interface AppState {
  // 左侧
  currentView: 'chat' | 'graph' | 'quiz' | 'evaluate' | 'knowledge_base' | 'import';
  activeSubject: string;
  
  // 右侧
  chatSession: {
    session_id: string;
    messages: Message[];
    currentAgent: string;  // 默认 'tutor'
    topic: string;
  };
  
  // 跨栏共享
  sharedContext: {
    selectedConcept: Concept | null;
    quizResult: QuizResult | null;
    evaluateResult: EvaluateResult | null;
  };
}
```

### 4.2 事件总线（跨组件通信）

```typescript
// 左侧 → 右侧
EventBus.emit('share-to-chat', cardMessage);
EventBus.emit('agent-response', textMessage);

// 右侧 → 左侧
EventBus.emit('navigate-view', {view, payload});
EventBus.emit('highlight-element', {view, elementId});
EventBus.emit('open-modal', {modal, data});
```

---

## 五、API 设计

### 5.1 多 Agent 群聊接口

```
POST /api/chat/send
{
  "session_id": "...",
  "user_id": "anonymous",
  "content": "@quiz 出3道题",
  "agent_target": "quiz",  // 可选，由前端解析 @ 命令
  "shared_context": {      // 当前共享上下文
    "selected_concept": "...",
    "current_view": "graph"
  }
}

Response (SSE stream):
event: meta
data: {agent: "QuizAgent", current_topic: "RAG", ...}

event: chunk  
data: {type: "text", content: "好的，为您生成3道RAG题目："}

event: chunk
data: {type: "card", card_type: "question", title: "第1题", ...}

event: command
data: {command: "navigate", target: "quiz", payload: {...}}

event: done
data: {}
```

### 5.2 分享接口

```
POST /api/chat/share
{
  "session_id": "...",
  "card_type": "concept",
  "title": "RAG架构",
  "data": {...},
  "source_view": "graph"
}
```

---

## 六、实现路径

### 阶段 1: 布局重构（2-3天）

1. **主布局组件改造**
   - 新建 `AppLayout.vue`：三栏布局（Sidebar + Main + Chat）
   - Main 区域支持视图切换（Graph/Quiz/Evaluate/KnowledgeBase）
   - Chat 区域常驻右侧，可折叠

2. **ChatView 升级**
   - 消息列表支持多种消息类型（text/card/command/system）
   - 输入框支持 @命令自动补全
   - Agent 标签栏（Tutor/Quiz/Coach）切换

3. **全局事件总线**
   - 实现 `EventBus` 跨组件通信
   - 定义标准事件类型

### 阶段 2: 多 Agent 接入（2-3天）

1. **后端 API 改造**
   - `POST /api/chat/send` 统一入口
   - Coordinator 支持 `agent_target` 参数
   - SSE 支持多种事件类型（text/card/command）

2. **Agent 标准化输出**
   - QuizAgent 返回 `CardMessage(type='card', card_type='question')`
   - CoachAgent 返回 `CardMessage(type='card', card_type='quiz_result')`
   - TutorAgent 返回 `TextMessage` + 可选 `CommandMessage`

3. **命令执行器**
   - 前端 `CommandExecutor` 解析 command 消息
   - 驱动左侧视图导航/高亮/弹窗

### 阶段 3: 双向互动（2-3天）

1. **左侧分享功能**
   - GraphView 节点右键菜单：分享到群聊
   - QuizView 题目卡片：分享到群聊
   - EvaluateView 结果：分享到群聊

2. **卡片渲染组件**
   - `ConceptCard.vue`：概念卡片（含解释/出题/评测按钮）
   - `QuestionCard.vue`：题目卡片（可交互作答）
   - `ResultCard.vue`：评测结果卡片

3. **上下文传递**
   - 分享时携带完整数据
   - Agent 可读取 shared_context 生成个性化回复

### 阶段 4: 对话上下文增强（1-2天）

1. **多 Agent 会话隔离**
   - 同一 session 中不同 Agent 的对话历史独立存储
   - `@quiz` 和 `@tutor` 的上下文不互相污染

2. **话题链增强**
   - 跨 Agent 话题追踪（用户在 Tutor 聊 RAG → @quiz 出题仍知是 RAG）
   - 左侧视图操作自动更新当前话题

---

## 七、与现有文档的整合

### 7.1 与多轮对话设计文档的整合

| 原设计 | 新方案调整 |
|:---|:---|
| `DialogContextManager` 管理单一会话 | 扩展为支持多 Agent 子会话（每个 Agent 独立历史） |
| `current_topic` 全局 | 细化为 `view_topic`（左侧视图话题）+ `chat_topic`（群聊话题） |
| `resolve_references` 仅文本 | 扩展为支持解析 @命令和卡片引用 |
| `dialog_topics` 表 | 增加 `agent_name` 字段，记录各 Agent 的话题分布 |

### 7.2 与多 Agent 协作设计的整合

| 原设计 | 新方案调整 |
|:---|:---|
| L1/L2/L3 记忆分层 | 增加 L0: 界面状态层（共享上下文） |
| MessageBus 事件 | 增加 UI 事件类型（`navigate`, `highlight`, `share`） |
| Coordinator 路由 | 增加 `@命令` 解析和 `agent_target` 处理 |
| 标准化输出 | 增加 `CardMessage` 和 `CommandMessage` 格式 |

---

## 八、完成度评估

### ✅ 已完成（可直接复用）

| 模块 | 完成内容 |
|:---|:---|
| **DialogContextManager** | 会话管理、消息存储、话题追踪、指代解析 |
| **Coordinator** | Agent 路由、意图分类、P0 图谱上下文组装 |
| **TutorAgent** | 图谱上下文回答、媒体引用、引用来源 |
| **QuizAgent** | 多题型出题、题库保存 |
| **CoachAgent** | IRT 评分、能力画像 |
| **前端视图** | GraphView、QuizView、EvaluateView、KnowledgeBaseView |
| **后端 API** | `/api/ask`, `/api/quiz/generate`, `/api/evaluate` |
| **事件系统** | 基础 `window.dispatchEvent`（可升级为 EventBus） |

### 🔄 部分完成（需改造）

| 模块 | 现状 | 需改造 |
|:---|:---|:---|
| **ChatView** | 只有文本消息 | 支持 card/command 消息、@命令、Agent 标签 |
| **Sidebar** | 导航菜单 | 精简为纯学科/视图切换，去掉历史会话 |
| **API 路由** | 各 Agent 独立端点 | 统一为 `/api/chat/send` |
| **消息格式** | 纯文本 | 标准化为 Message 类型体系 |

### ❌ 待实现

| 模块 | 工作量 | 优先级 |
|:---|:---|:---|
| **AppLayout.vue** | 1天 | 🔴 高 |
| **EventBus** | 0.5天 | 🔴 高 |
| **@命令解析** | 0.5天 | 🔴 高 |
| **Card 渲染组件** | 1天 | 🟡 中 |
| **分享功能（左→右）** | 1天 | 🟡 中 |
| **CommandExecutor** | 1天 | 🟡 中 |
| **多 Agent 子会话** | 1天 | 🟢 低 |
| **跨 Agent 话题同步** | 0.5天 | 🟢 低 |

---

## 九、风险评估

| 风险 | 影响 | 缓解措施 |
|:---|:---|:---|
| 布局重构影响现有功能 | 高 | 分阶段重构，先新建布局再迁移视图 |
| SSE 多事件类型兼容 | 中 | 保持 `event: chunk` 为主，新增 `event: card/command` |
| 移动端适配困难 | 中 | 右侧 Chat 在移动端变为底部浮动按钮+全屏弹窗 |
| Agent 上下文污染 | 中 | 各 Agent 独立子会话，共享 topic 但不共享 history |

---

*文档结束 — 待讨论确认后进入实现阶段*
