# LA-CONFIG-001: 用户可配置参数系统设计方案

> 版本: 1.0
> 日期: 2026-07-21
> 关联: LA-044 对话上下文、LA-040 Agent 系统

---

## 一、设计背景

当前 LearnAnything 系统中有大量硬编码参数，分布在各模块的构造函数和常量中：

```python
# 对话上下文
SESSION_TIMEOUT_MINUTES = 30
MAX_HISTORY_TURNS = 20
to_prompt_context(max_turns=5, max_chars=800)

# LLM 调用
temperature=0.3, max_tokens=800

# 图谱检索
max_depth=2, max_nodes=15, top_k=5
ContextBudget(max_tokens=2000, max_nodes=15)

# 语义连接
embedding_threshold=0.72, llm_threshold=0.80
```

这些参数直接影响用户体验和系统行为，但用户无法调整。

---

## 二、可配置参数清单

### 2.1 对话上下文模块 (dialog_context.py)

| 参数名 | 当前值 | 类型 | 说明 | 用户可见性 |
|:---|:---|:---|:---|:---|
| `session_timeout_minutes` | 30 | int | 会话超时时间(分钟) | 🟡 高级 |
| `max_history_turns` | 20 | int | 单会话最大保留轮次 | 🟡 高级 |
| `prompt_max_turns` | 5 | int | Prompt 中注入的最近轮次 | 🔴 普通 |
| `prompt_max_chars` | 800 | int | 历史文本字符阈值，超则触发摘要 | 🔴 普通 |
| `summary_max_tokens` | 300 | int | LLM 摘要的最大 token 数 | 🟡 高级 |
| `summary_temperature` | 0.3 | float | LLM 摘要的温度参数 | 🟢 隐藏 |

### 2.2 LLM 调用模块 (llm_client.py)

| 参数名 | 当前值 | 类型 | 说明 | 用户可见性 |
|:---|:---|:---|:---|:---|
| `default_temperature` | 0.3 | float | 默认温度参数 | 🔴 普通 |
| `default_max_tokens` | 800 | int | 默认最大返回 token 数 | 🔴 普通 |
| `complete_temperature` | 0.1 | float | complete 接口温度 | 🟢 隐藏 |
| `complete_max_tokens` | 1200 | int | complete 接口最大 token | 🟢 隐藏 |
| `timeout` | 60 | int | LLM 请求超时(秒) | 🟡 高级 |
| `max_retries` | 2 | int | 失败重试次数 | 🟡 高级 |

### 2.3 图谱教育模块 (graph_education/)

| 参数名 | 当前值 | 类型 | 说明 | 用户可见性 |
|:---|:---|:---|:---|:---|
| `retriever_top_k` | 5 | int | Embedding 检索返回数量 | 🔴 普通 |
| `subgraph_max_depth` | 2 | int | 子图构建最大深度 | 🔴 普通 |
| `subgraph_max_nodes` | 15 | int | 子图最大节点数 | 🔴 普通 |
| `context_budget_tokens` | 2000 | int | 上下文组装 token 预算 | 🔴 普通 |
| `context_budget_nodes` | 15 | int | 上下文组装节点预算 | 🟡 高级 |
| `depth_l1_tokens` | 1500 | int | L1 深度预算(节点) | 🟢 隐藏 |
| `depth_l1_nodes` | 5 | int | L1 深度预算(节点数) | 🟢 隐藏 |
| `depth_l2_tokens` | 2500 | int | L2 深度预算 | 🟢 隐藏 |
| `depth_l2_nodes` | 12 | int | L2 节点预算 | 🟢 隐藏 |

### 2.4 语义连接模块 (semantic_linker.py)

| 参数名 | 当前值 | 类型 | 说明 | 用户可见性 |
|:---|:---|:---|:---|:---|
| `embedding_threshold` | 0.72 | float | Embedding 相似度阈值 | 🟡 高级 |
| `llm_threshold` | 0.80 | float | LLM 判断置信度阈值 | 🟡 高级 |
| `edge_confidence_default` | 0.5 | float | Gap 边置信度折扣基准 | 🟢 隐藏 |
| `edge_confidence_discount` | 0.9 | float | Gap 边置信度折扣系数 | 🟢 隐藏 |

### 2.5 Agent 模块

#### TutorAgent

| 参数名 | 当前值 | 类型 | 说明 | 用户可见性 |
|:---|:---|:---|:---|:---|
| `top_k` | 5 | int | 检索返回概念数 | 🔴 普通 |
| `explanation_depth` | "adaptive" | enum | 讲解深度(auto/初级/中级/高级) | 🔴 普通 |
| `include_media` | true | bool | 是否包含图片/公式 | 🔴 普通 |
| `include_sources` | true | bool | 是否包含引用来源 | 🔴 普通 |

#### QuizAgent

| 参数名 | 当前值 | 类型 | 说明 | 用户可见性 |
|:---|:---|:---|:---|:---|
| `default_question_count` | 5 | int | 默认出题数量 | 🔴 普通 |
| `default_question_score` | 20 | int | 单题满分 | 🟡 高级 |
| `fill_blank_threshold_100` | 0.8 | float | 填空题全对匹配度阈值 | 🟢 隐藏 |
| `fill_blank_threshold_50` | 0.5 | float | 填空题半对匹配度阈值 | 🟢 隐藏 |

#### CoachAgent

| 参数名 | 当前值 | 类型 | 说明 | 用户可见性 |
|:---|:---|:---|:---|:---|
| `irt_a` | 1.0 | float | IRT 区分度参数 | 🟢 隐藏 |
| `irt_b` | 0.0 | float | IRT 难度参数 | 🟢 隐藏 |
| `irt_c` | 0.25 | float | IRT 猜测参数 | 🟢 隐藏 |

### 2.6 文档处理模块

| 参数名 | 当前值 | 类型 | 说明 | 用户可见性 |
|:---|:---|:---|:---|:---|
| `chunk_max_size` | 3000 | int | 分块最大字符数 | 🟡 高级 |
| `chunk_min_size` | 100 | int | 分块最小字符数 | 🟡 高级 |
| `chunk_overlap` | 200 | int | 分块重叠字符数 | 🟡 高级 |
| `semantic_chunk_size` | 1500 | int | 语义分块大小 | 🟡 高级 |

### 2.7 向量存储模块

| 参数名 | 当前值 | 类型 | 说明 | 用户可见性 |
|:---|:---|:---|:---|:---|
| `vector_query_n_results` | 10 | int | 向量查询返回数量 | 🟡 高级 |
| `embedding_dim` | 1024 | int | Embedding 维度 | 🟢 隐藏 |

---

## 三、配置架构设计

### 3.1 三层配置体系

```
┌─────────────────────────────────────────┐
│  L3: 系统默认 (代码硬编码)                │
│  - 所有参数的 fallback 值                │
│  - 升级时新增参数的默认值                 │
├─────────────────────────────────────────┤
│  L2: 用户全局配置 (SQLite/JSON)           │
│  - 用户级别的偏好设置                     │
│  - 跨会话共享                           │
│  - 前端 Settings 页面可修改               │
├─────────────────────────────────────────┤
│  L1: 会话级配置 (SQLite dialog_sessions)  │
│  - 单个会话的临时覆盖                     │
│  - @命令 或 UI 快捷调整                   │
│  - 会话结束后可选择是否保存为全局          │
└─────────────────────────────────────────┘
```

### 3.2 配置优先级

```
会话级配置 (L1) > 用户全局配置 (L2) > 系统默认 (L3)

示例:
- 用户在 Settings 设置 prompt_max_turns = 3 (L2)
- 某次会话中通过 @设置 临时改为 10 (L1)
- 新会话默认使用 L2 的值 3
- 如果 L1 和 L2 都不存在，使用 L3 的默认值 5
```

### 3.3 数据结构

```typescript
// 用户全局配置
interface UserGlobalSettings {
  user_id: string;
  updated_at: string;
  
  // 对话上下文
  dialog: {
    prompt_max_turns: number;      // 默认 5
    prompt_max_chars: number;      // 默认 800
    session_timeout_minutes: number; // 默认 30
  };
  
  // LLM 参数
  llm: {
    temperature: number;           // 默认 0.3
    max_tokens: number;            // 默认 800
    timeout: number;               // 默认 60
  };
  
  // 图谱检索
  graph: {
    retriever_top_k: number;       // 默认 5
    subgraph_max_depth: number;    // 默认 2
    subgraph_max_nodes: number;    // 默认 15
    context_budget_tokens: number; // 默认 2000
  };
  
  // Agent 行为
  agents: {
    tutor: {
      explanation_depth: "adaptive" | "beginner" | "intermediate" | "advanced";
      include_media: boolean;
      include_sources: boolean;
    };
    quiz: {
      default_count: number;
      default_score: number;
    };
  };
  
  // 前端 UI
  ui: {
    theme: "dark" | "light" | "auto";
    font_size: "small" | "medium" | "large";
    sidebar_collapsed: boolean;
    chat_width_percent: number;    // 默认 35
  };
}

// 会话级配置覆盖
interface SessionOverrideSettings {
  session_id: string;
  overrides: Partial<UserGlobalSettings>;
  is_temporary: boolean;  // true = 会话结束不保存
}
```

---

## 四、前后端接口设计

### 4.1 后端 API

```
# 获取用户全局配置
GET /api/settings
Response: UserGlobalSettings

# 更新用户全局配置（支持部分更新）
PATCH /api/settings
Body: { "dialog": { "prompt_max_turns": 3 } }
Response: { success: true, updated: ["dialog.prompt_max_turns"] }

# 获取会话级配置覆盖
GET /api/dialog/sessions/{session_id}/settings
Response: SessionOverrideSettings

# 设置会话级配置覆盖
PATCH /api/dialog/sessions/{session_id}/settings
Body: { "llm": { "temperature": 0.5 } }
Response: { success: true }

# 重置会话级配置（恢复全局默认值）
DELETE /api/dialog/sessions/{session_id}/settings
Response: { success: true }

# 获取参数说明和允许范围
GET /api/settings/schema
Response: {
  "dialog.prompt_max_turns": {
    type: "integer",
    default: 5,
    min: 1,
    max: 20,
    description: "Prompt 中注入的最近对话轮次",
    visibility: "normal"  // normal / advanced / hidden
  },
  ...
}
```

### 4.2 前端 Settings 页面

```
┌─────────────────────────────────────┐
│ ⚙️ 设置                              │
├─────────────────────────────────────┤
│                                     │
│ 📋 对话上下文                        │
│   历史注入轮次    [5]  (1-20)       │
│   摘要触发阈值    [800] 字符        │
│   会话超时时间    [30] 分钟         │
│                                     │
│ 🤖 LLM 参数                          │
│   温度参数        [0.30] (0-2)      │
│   最大返回长度    [800] tokens      │
│   请求超时        [60] 秒           │
│                                     │
│ 🧠 知识图谱                          │
│   检索返回数量    [5]               │
│   子图最大深度    [2]               │
│   子图最大节点    [15]              │
│                                     │
│ 📝 Agent 行为                        │
│   讲解深度        [自适应 ▼]        │
│   包含媒体资源    [✓]               │
│   显示引用来源    [✓]               │
│                                     │
│ 🎨 界面                              │
│   主题            [深色 ▼]          │
│   字号            [中 ▼]            │
│                                     │
│ [恢复默认]  [保存]                   │
│                                     │
└─────────────────────────────────────┘
```

---

## 五、实现路径

### 阶段 1: 配置存储层（0.5天）

1. **新建 `core/settings_store.py`**
   - `SettingsStore` 类：管理 L2/L3 配置读写
   - SQLite 表：`user_settings` (key-value JSON)
   - 配置合并逻辑：L2 覆盖 L3，L1 覆盖 L2

2. **改造各模块**
   - 将硬编码常量改为从 `SettingsStore` 读取
   - 保留参数默认值作为 L3 fallback

### 阶段 2: 后端 API（0.5天）

1. **新增 `/api/settings` 相关接口**
2. **配置 Schema 定义**
   - 每个参数的类型/范围/描述/可见性

### 阶段 3: 前端 Settings 页面（1天）

1. **新建 `SettingsView.vue`**
   - 按模块分组展示配置项
   - 根据可见性过滤（普通/高级/隐藏）
   - 数值输入框带范围验证
2. **连接后端 API**
   - 加载/保存配置
   - 实时生效（部分配置需刷新页面）

### 阶段 4: 会话级配置（0.5天）

1. **@设置 命令**
   - `@设置 历史轮次=3`
   - `@设置 讲解深度=初级`
2. **临时覆盖提示**
   - 会话顶部显示"当前配置已临时修改"
   - 提供"保存为全局默认"按钮

---

## 六、与现有系统的兼容性

| 场景 | 处理方案 |
|:---|:---|
| 升级新增参数 | 自动使用 L3 默认值，用户无感知 |
| 用户配置损坏 | 自动重置该参数为默认值，记录日志 |
| 会话级配置冲突 | L1 优先级最高，会话结束后自动清除 |
| 前端版本滞后 | 后端返回完整配置，前端只展示认识的字段 |

---

## 七、参数统计

| 模块 | 可配置参数数量 | 普通可见 | 高级可见 | 隐藏 |
|:---|:---:|:---:|:---:|:---:|
| 对话上下文 | 6 | 2 | 2 | 2 |
| LLM 调用 | 6 | 2 | 2 | 2 |
| 图谱教育 | 8 | 3 | 1 | 4 |
| 语义连接 | 4 | 0 | 2 | 2 |
| TutorAgent | 4 | 4 | 0 | 0 |
| QuizAgent | 4 | 1 | 1 | 2 |
| CoachAgent | 3 | 0 | 0 | 3 |
| 文档处理 | 4 | 0 | 4 | 0 |
| 向量存储 | 2 | 0 | 1 | 1 |
| UI | 4 | 4 | 0 | 0 |
| **总计** | **45** | **16** | **13** | **16** |

---

*文档结束 — 待讨论确认后进入实现阶段*
