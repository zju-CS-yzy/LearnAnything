# LearnAnything 设计文档

> 版本: 1.0  
> 创建日期: 2026-07-05  
> 项目路径: `D:\MyCS\AI\Project\LearnAnything\`  
> 定位: AI驱动的通用知识学习系统，支持任意学科的RAG知识库+知识图谱+Agent协作

---

## 目录

1. [项目简要说明](#1-项目简要说明)
2. [目标效果](#2-目标效果)
3. [知识图谱构建思想](#3-知识图谱构建思想)
4. [数据模型](#4-数据模型)
5. [技术栈与架构](#5-技术栈与架构)
6. [各模块实现方式](#6-各模块实现方式)
7. [数据流](#7-数据流)
8. [前端架构](#8-前端架构)
9. [部署与打包](#9-部署与打包)
10. [已知问题与限制](#10-已知问题与限制)

---

## 1. 项目简要说明

### 1.1 背景

LearnAnything 是一个**通用知识学习系统**，从 IWork（AI大模型求职学习系统）重构而来。核心目标是让任意学科的材料（PDF、文本、图片）经过AI处理后，生成结构化的知识图谱，辅助用户高效学习。

### 1.2 核心能力

| 能力 | 说明 |
|:---|:---|
| 多格式导入 | 支持文本、Markdown、PDF（文字型/扫描件）、图片（OCR） |
| 智能分块 | 标题分块 + 语义分块，支持学科专用分块策略 |
| 混合检索 | BM25 + 向量检索 + RRF融合 + Cross-Encoder重排序 |
| 知识图谱 | 双层图谱：文档层（Chunk树）+ 概念层（语义概念网络） |
| 多Agent协作 | Tutor（讲解）、Quiz（出题）、Coach（评测）、Coordinator（协调） |
| 多范式提取 | 理论归纳 / 工程分解 / 层级归纳 三种概念提取范式 |
| 可视化 | 树形知识图谱 + 卡片化节点 + 交互式浏览 |

### 1.3 与 IWork 的区别

| 维度 | IWork | LearnAnything |
|:---|:---|:---|
| 目标用户 | 求职者 | 任意学习者 |
| 学科范围 | 固定（大模型/后端/算法） | 插件式，任意学科 |
| 文档输入 | 主要是文本 | 多格式（PDF/图片/OCR） |
| 检索 | 纯向量 | 混合检索（BM25 + 向量） |
| 图谱 | 无 | 双层知识图谱 |
| 前端 | 命令行 | Vue3 + FastAPI + 桌面应用 |

---

## 2. 目标效果

### 2.1 用户使用流程

```
导入材料 → 自动分块 → 构建文档树 → 概念提取 → 去重连接 → 可视化图谱 → 学习/问答
```

### 2.2 可视化目标

#### 文档层（Chunk Tree）
- **树形结构**：根节点（文档）→ 章节 → 段落 → 知识点
- **布局原则**：
  1. 单向的树，根节点在最左侧
  2. 同层节点在横向位置上并列
  3. 叶节点（无子节点）在最右侧，上下间隔相同
  4. 有子节点的节点，纵向位置位于所有下层节点的中部
  5. 不同树共享子节点时，复制子节点到各自的树中
- **效果参考**：类似 Visio 灵感触发图，同层上下并列不重叠

#### 概念层（Concept Network）
- **工程分解范式**：需求节点 → SOLUTION → 技术节点 → DEPENDS_ON → 子需求节点
- **卡片化显示**：每个概念显示为UML风格卡片（标题+类型+描述）
- **层次方向**：从左到右（需求→技术→子需求）

### 2.3 学科管理目标

- 任意学科独立知识库
- 导入文件自动统计（原始资料数、知识片段数）
- 学科配置自动生成（关键词、分块策略、题型偏好）

---

## 3. 知识图谱构建思想

### 3.1 双层图谱架构

```
┌─────────────────────────────────────────────────────┐
│                  概念层（Concept Layer）              │
│  ┌──────────┐      SOLUTION       ┌──────────┐   │
│  │ 需求概念  │ ─────────────────────→│ 技术概念  │   │
│  │(req)     │                      │(tech)    │   │
│  └──────────┘                      └──────────┘   │
│       │                                  │          │
│       │ DEPENDS_ON                       │         │
│       ▼                                  ▼          │
│  ┌──────────┐                      ┌──────────┐   │
│  │ 子需求   │                      │ 子技术   │   │
│  └──────────┘                      └──────────┘   │
│  [Phase 2 生成：LLM提取 + 去重 + 语义连接]           │
├─────────────────────────────────────────────────────┤
│                  文档层（Document Layer）              │
│  ┌──────────┐   ADJACENT_TO   ┌──────────┐         │
│  │ Chunk 1  │ ───────────────→│ Chunk 2  │         │
│  │(文档A-1) │                  │(文档A-2) │         │
│  └──────────┘                  └──────────┘         │
│       │                                              │
│       │ BELONGS_TO（同heading_path层级）              │
│       ▼                                              │
│  ┌──────────┐                                       │
│  │ Chunk 3  │                                       │
│  └──────────┘                                       │
│  [Phase 1 生成：导入时自动构建]                        │
└─────────────────────────────────────────────────────┘
```

### 3.2 概念提取范式

| 范式 | 适用场景 | 提取逻辑 | 边类型 |
|:---|:---|:---|:---|
| **理论归纳** | 理论型材料（论文/教材） | 提取内在逻辑链（事实→概念→方法→评价） | 层级关系 |
| **工程分解** | 技术型材料（需求文档/设计） | 需求→技术→子需求→子技术 | SOLUTION + DEPENDS_ON |
| **层级归纳** | 通用知识（百科/综述） | 认知层次分类（基础→进阶→应用） | 层级关系 |

### 3.3 去重与连接

- **概念去重**：基于 embedding 相似度（阈值 0.85），合并相似概念
- **语义连接**：基于 parent_hint + LLM 二次确认，构建概念间关系
- **质量评估**：五维度评估（稳定性25%、覆盖度20%、忠实度20%、多样性15%、连接覆盖率20%）

---

## 4. 数据模型

### 4.1 节点类型

#### Chunk 节点（文档层）

```cypher
(:Chunk {
  chunk_id: string,        // 唯一标识（文件hash+序号）
  text: string,            // 文本内容
  heading_path: string,    // 标题路径（如 "第1章 > 1.1节"）
  source: string,          // 来源文件名
  page_number: int,       // 页码
  chunk_type: string,     // 类型：parent / child / markdown
})
```

#### Concept 节点（概念层）

```cypher
(:Concept {
  id: string,              // 唯一标识（UUID）
  name: string,            // 概念名称
  concept_type: string,    // 类型：requirement / technology / sub_requirement / sub_technology / concept
  description: string,     // 描述
  parent_hint: string,     // 父概念提示（用于去重后重建连接）
  source_chunks: [string], // 来源 chunk ID 列表
})
```

### 4.2 边类型

| 边类型 | 方向 | 含义 | 生成阶段 |
|:---|:---|:---|:---|
| **ADJACENT_TO** | Chunk → Chunk | 相邻 chunk（文档顺序） | Phase 1（导入时） |
| **BELONGS_TO** | Chunk → Chunk | 同 heading_path 层级关系 | Phase 1（导入时） |
| **SOLUTION** | Concept → Concept | 需求 → 技术（解决方案） | Phase 2.5（语义连接） |
| **DEPENDS_ON** | Concept → Concept | 技术 → 子需求（实现依赖） | Phase 2.5（语义连接） |
| **REQUIRES** | Concept → Concept | 通用依赖关系 | Phase 2.5（语义连接） |

### 4.3 学科元数据

```python
Subject {
  id: str                    # 学科标识（如 "ai_llm"）
  name: str                  # 显示名称
  description: str           # 描述
  keywords: [str]           # 关键词（用于自动识别）
  created_at: datetime       # 创建时间
  document_count: int        # 知识片段总数（chunks）
  raw_files_count: int       # 原始文件数
}
```

---

## 5. 技术栈与架构

### 5.1 整体架构

```
┌────────────────────────────────────────────────────────────┐
│                        前端层（Vue3）                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ 知识图谱  │ │ 学习对话  │ │ 出题评测  │ │ 导入管理  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│                      Vite + Cytoscape.js                     │
├────────────────────────────────────────────────────────────┤
│                        API层（FastAPI）                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ 文档导入  │ │ 知识检索  │ │ 图谱构建  │ │ 问答对话  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
├────────────────────────────────────────────────────────────┤
│                        Agent层                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │Coordinator│ │ TutorAgent│ │ QuizAgent│ │ CoachAgent│     │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
├────────────────────────────────────────────────────────────┤
│                        核心引擎层                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │文档处理   │ │ 向量检索  │ │ 图数据库  │ │ LLM调用  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  PyMuPDF / PaddleOCR / ChromaDB / KùzuDB / DeepSeek API    │
├────────────────────────────────────────────────────────────┤
│                        数据层                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │向量数据库 │ │ 图数据库  │ │ 监控数据库│ │ 学科配置  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  ChromaDB      KùzuDB       SQLite        JSON + SQLite   │
└────────────────────────────────────────────────────────────┘
```

### 5.2 技术栈明细

| 层级 | 组件 | 技术 | 版本 |
|:---|:---|:---|:---|
| 前端 | 框架 | Vue 3 + Vite | 3.4+ |
| 前端 | 图谱渲染 | Cytoscape.js + cytoscape-dagre | 3.26+ |
| 前端 | UI组件 | 原生CSS（未使用组件库） | — |
| 后端 | API框架 | FastAPI | 0.110+ |
| 后端 | 进程管理 | Uvicorn | 0.27+ |
| 核心 | 文档处理 | PyMuPDF + PaddleOCR | — |
| 核心 | 向量检索 | ChromaDB + BM25 + RRF | 0.4+ |
| 核心 | Embedding | 智谱AI Embedding API | 2048维 |
| 核心 | 图数据库 | KùzuDB | 0.4+ |
| 核心 | LLM | DeepSeek API (Chat) + Zhipu API | — |
| 数据 | 学科配置 | SQLite + JSON | — |
| 数据 | 监控 | SQLite | — |
| 打包 | 桌面应用 | PyInstaller + PyQt5 | 6.0+ |

---

## 6. 各模块实现方式

### 6.1 文档处理层（`core/document_processor.py`）

```python
# 处理流程
process_file(path) → 格式检测 → 内容提取 → 分块 → 返回 chunks

# 支持格式
- .txt / .md: 直接读取，标题分块
- .pdf（文字型）: PyMuPDF 提取文字 + 页面类型检测
- .pdf（扫描件）: 逐页渲染为图片 → PaddleOCR 识别
- .png/.jpg: PaddleOCR 提取文字

# 分块策略
- 标题分块：基于 heading_path 层级结构
- 语义分块：基于段落语义完整性
- 学科专用分块：由学科配置驱动（如化学公式特殊处理）
```

### 6.2 向量检索层（`core/`）

```python
# 索引构建（导入时）
chunks → Embedding（智谱AI API）→ ChromaDB 存储

# 查询流程（运行时）
query → 查询重写 → BM25检索 + 向量检索 → RRF融合 → Cross-Encoder重排序 → TopK返回

# 核心组件
- VectorStore: ChromaDB 封装，支持多集合（按学科隔离）
- HybridRetriever: BM25 + 向量检索 + RRF
- Reranker: Cross-Encoder 交叉编码器重排序
- QueryRewriter: LLM 驱动的查询扩展重写
```

### 6.3 图数据库层（`core/graph_store.py`）

```python
# 双层存储（KùzuDB）
Chunk 层: (:Chunk)-[:ADJACENT_TO|:BELONGS_TO]->(:Chunk)
Concept 层: (:Concept)-[:SOLUTION|:DEPENDS_ON|:REQUIRES]->(:Concept)

# 关键操作
- init_schema(): 初始化 schema（Chunk + Concept + 边类型）
- add_chunk_nodes(chunks): 批量写入 chunk 节点
- build_adjacent_relations(): 构建相邻关系（按文档顺序）
- build_belongs_to_relations(): 构建层级关系（同 heading_path）
- extract_concepts(chunk_id, paradigm): 基于范式提取概念
- build_semantic_links(): 构建概念间语义连接
- dedupe_concepts(): 基于 embedding 相似度去重
```

### 6.4 概念提取层（`core/semantic_extractor.py`）

```python
# 三种范式
extract(chunk_text, paradigm="engineering"):
  # 理论归纳：提取内在逻辑链
  # 工程分解：提取需求→技术关系
  # 层级归纳：提取认知层次
  → 返回 {concepts: [{name, type, description, parent_hint}], relations: [{source, target, type}]}

# 去重器（`core/concept_deduper.py`）
dedupe(concepts):
  # 计算 embedding 相似度矩阵
  # 合并相似度 > 0.85 的概念
  # 返回 canonical_concepts + merge_map
```

### 6.5 语义连接层（`core/semantic_linker.py`）

```python
# 连接构建流程
build_links(canonical_concepts, chunks):
  # 1. 基于 parent_hint 构建初始连接
  # 2. 基于 embedding 相似度补充连接
  # 3. LLM 二次确认连接合理性
  # 4. 写入 KùzuDB（SOLUTION / DEPENDS_ON / REQUIRES）
```

### 6.6 Agent 层（`agents/`）

```python
# Coordinator（协调器）
# 职责：意图路由 + Agent 分发 + 监控贯穿

# TutorAgent（讲解）
# 输入：用户问题 + 检索结果
# 输出：结构化讲解（概念定义 + 示例 + 关联）

# QuizAgent（出题）
# 输入：学科配置 + 知识点
# 输出：动态生成的选择题/填空题

# CoachAgent（评测）
# 输入：用户答案 + 标准答案
# 输出：评分 + 能力评估报告
```

### 6.7 API 层（`app/backend_api.py`）

| 端点 | 方法 | 功能 |
|:---|:---|:---|
| `/api/health` | GET | 健康检查 |
| `/api/subjects` | GET/POST | 学科列表/创建 |
| `/api/import/text` | POST | 文本导入 |
| `/api/import/file` | POST | 文件导入（PDF/图片等） |
| `/api/knowledge-graph/{subject}/nodes` | GET | Chunk 节点列表 |
| `/api/knowledge-graph/{subject}/edges` | GET | Chunk 边列表 |
| `/api/knowledge-graph/{subject}/concepts` | GET | Concept 节点列表 |
| `/api/knowledge-graph/{subject}/concept-links` | GET | Concept 边列表 |
| `/api/knowledge-graph/{subject}/build` | POST | 构建概念层（Phase 2） |
| `/api/ask` | POST | 问答对话 |
| `/api/quiz` | POST | 出题 |
| `/api/evaluate` | POST | 评测 |

---

## 7. 数据流

### 7.1 导入流程（Phase 1）

```
用户上传文件
    │
    ▼
┌──────────────────┐
│ DocumentProcessor │ 格式检测 → 内容提取
└──────────────────┘
    │
    ▼
┌──────────────────┐
│   Chunking       │ 分块（标题分块 + 语义分块）
└──────────────────┘
    │
    ├──────────────┬──────────────┐
    ▼              ▼              ▼
┌────────┐  ┌────────────┐  ┌────────────┐
│VectorStore│  │ GraphStore │  │ SubjectManager│
│ChromaDB │  │  KùzuDB    │  │  SQLite    │
│(embedding)│  │ (chunk节点)│  │ (导入记录) │
└────────┘  └────────────┘  └────────────┘
    │              │              │
    │              ▼              │
    │         ┌────────────┐      │
    │         │ build_adjacent │  │
    │         │ build_belongs_to│ │
    │         └────────────┘      │
    │              │              │
    ▼              ▼              ▼
  向量索引      Chunk 树形结构   统计信息更新
```

### 7.2 概念提取流程（Phase 2）

```
用户选择范式（理论归纳/工程分解/层级归纳）
    │
    ▼
┌──────────────────┐
│ SemanticExtractor│ 遍历每个 chunk，LLM 提取概念
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ ConceptDeduper   │ 基于 embedding 相似度去重
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ SemanticLinker   │ 构建概念间连接（SOLUTION/DEPENDS_ON）
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  GraphStore      │ 写入 KùzuDB（Concept 节点 + 语义边）
└──────────────────┘
```

### 7.3 查询流程（运行时）

```
用户问题
    │
    ▼
┌──────────────────┐
│ QueryRewriter    │ 查询重写/扩展
└──────────────────┘
    │
    ├──────────────┬──────────────┐
    ▼              ▼              ▼
┌────────┐  ┌────────────┐  ┌────────────┐
│ BM25   │  │ VectorSearch│  │ KnowledgeGraph│
│ 检索   │  │ 向量检索    │  │ 图谱检索（预留）│
└────────┘  └────────────┘  └────────────┘
    │              │              │
    └──────────────┴──────────────┘
                   │
                   ▼
            ┌────────────┐
            │ RRF融合     │
            │ k=60        │
            └────────────┘
                   │
                   ▼
            ┌────────────┐
            │ Reranker   │ Cross-Encoder 重排序
            └────────────┘
                   │
                   ▼
            ┌────────────┐
            │ LLM        │ 生成回答（DeepSeek API）
            │ (context)  │
            └────────────┘
                   │
                   ▼
              用户看到回答
```

---

## 8. 前端架构

### 8.1 技术栈

- **框架**: Vue 3（Composition API）+ Vite
- **图谱渲染**: Cytoscape.js（自定义树形布局，不使用 dagre）
- **HTTP**: 原生 fetch（无 Axios）
- **状态管理**: 原生响应式（ref/reactive），无 Pinia/Vuex

### 8.2 页面结构

```
App.vue
├── 侧边栏（学科切换 + 功能导航）
│   ├── 导入材料
│   ├── 知识库
│   ├── 学习图谱
│   └── 对话学习
│
├── 主内容区
│   ├── GraphView.vue（知识图谱）
│   │   ├── 工具栏（搜索/筛选/布局）
│   │   ├── 图谱画布（Cytoscape.js）
│   │   ├── 节点详情面板（右侧抽屉）
│   │   └── 构建配置覆盖层（范式选择）
│   │
│   ├── ChatView.vue（对话学习）
│   ├── QuizView.vue（出题评测）
│   └── ImportView.vue（导入管理）
│
└── 状态栏（节点数/边数/学科信息）
```

### 8.3 图谱布局算法

**自定义树形布局**（`runLayout()` 函数）：

```javascript
// 核心逻辑：后序遍历分配位置
// 1. 找到所有根节点（入度为0）
// 2. 复制共享子节点到各自的树
// 3. 自底向上计算子树高度（叶节点数）
// 4. 父节点 y = 所有子节点 y 范围的中点
// 5. 叶节点间隔相同（nodeGap = 60px）
// 6. 层间距固定（layerWidth = 250px）
// 7. 多棵树之间留间隙（treeGap = 120px）
```

### 8.4 节点样式

| 节点类型 | 形状 | 颜色 | 尺寸 | 标签 |
|:---|:---|:---|:---|:---|
| Chunk | 椭圆 | `#3498db` | 28×28 | 标题（前30字符） |
| 副本 | 椭圆（虚线边框） | `#e74c3c` | 28×28 | 标题 |
| Concept（需求） | 圆角矩形 | `#e74c3c` | 160×60 | 卡片标签（标题+类型+描述） |
| Concept（技术） | 圆角矩形 | `#3498db` | 160×60 | 卡片标签 |
| Concept（通用） | 圆角矩形 | `#2ecc71` | 160×60 | 卡片标签 |

---

## 9. 部署与打包

### 9.1 开发模式

```bash
# 后端
python -m app.backend_api

# 前端（dev server）
cd web-vue && npm run dev
```

### 9.2 生产模式

```bash
# 前端构建（输出到 web/dist/）
cd web-vue && npm run build

# 后端启动（静态文件服务）
python -m app.backend_api
```

### 9.3 桌面应用打包（PyInstaller）

```bash
# 打包为单文件 exe
python build.py
# 输出：dist/LearnAnything.exe
```

### 9.4 数据目录结构

```
~/.learnanything/
├── subjects.db              # 学科元数据（SQLite）
├── quiz_bank.db             # 题库
├── sessions.db              # 聊天会话
└── knowledge_base/
    ├── <subject_id>/
    │   ├── raw/             # 原始文件
    │   ├── visual/          # 可视化数据
    │   └── meta.json        # 学科配置
    ├── vector_db/           # ChromaDB 数据
    ├── graph_db/            # KùzuDB 数据
    └── cache/               # 缓存（BM25索引、查询缓存等）
```

---

## 10. 已知问题与限制

### 10.1 高优先级（影响核心功能）

| # | 问题 | 影响 | 状态 |
|:---|:---|:---|:---:|
| LA-020 | 贝塞尔曲线端点不精确 | 概念层边渲染效果 | 🟡 |
| LA-021 | 树形布局共享子节点处理 | 文档层布局 | ✅ |
| LA-024 | PowerShell 执行策略限制 | 构建脚本无法执行 | 🟡 |
| — | 导入后未自动写入 KùzuDB | 新学科图谱为空 | ✅ |
| — | `raw_files_count` 统计未更新 | 导入统计显示为0 | ✅ |
| — | 前端样式错误（height: 'label'）| 图谱不显示 | ✅ |

### 10.2 中优先级（影响体验）

| # | 问题 | 影响 |
|:---|:---|:---|
| — | 后端进程在 exec 环境不稳定 | 后台服务管理 |
| — | 概念层 zoom 范围过大 | 节点显示不清晰 |
| — | 缺少设计文档 | 上下文丢失风险 |
| LA-001 | HeadhunterAgent 未接入职位数据源 | 职位推荐不可用 |

### 10.3 技术限制

| 限制 | 说明 | 缓解方案 |
|:---|:---|:---|
| KùzuDB 并发支持 | Python 客户端在 async/多线程下不稳定 | 使用 threading.Lock 保护 |
| 智谱AI Embedding API | 需要联网，有调用限额 | 缓存 embedding 结果 |
| DeepSeek API 延迟 | 概念提取（Phase 2）耗时较长 | 异步处理 + 进度反馈 |
| PyInstaller 打包 | 前端资源需要内嵌 | 静态文件复制到 _MEIPASS |
| 前端无组件库 | 所有 UI 手写，维护成本高 | 考虑引入 Element Plus |

---

## 附录

### A. 术语表

| 术语 | 含义 |
|:---|:---|
| **Chunk** | 文档分块后的文本片段，知识库的基本单元 |
| **Concept** | 从 Chunk 中提取的语义概念，知识图谱的节点 |
| **Phase 1** | 文档导入阶段：分块 → 向量化 → 构建 Chunk 树 |
| **Phase 2** | 概念提取阶段：LLM提取 → 去重 → 语义连接 |
| **范式** | 概念提取的策略：理论归纳 / 工程分解 / 层级归纳 |
| **SOLUTION** | 需求 → 技术的解决关系边 |
| **DEPENDS_ON** | 技术 → 子需求的实现依赖边 |
| **RRF** | Reciprocal Rank Fusion，检索结果融合算法 |
| **MMR** | Maximal Marginal Relevance，多样性重排算法 |

### B. 文件索引

| 文件 | 说明 |
|:---|:---|
| `config/settings.py` | 全局配置 |
| `core/document_processor.py` | 文档处理 |
| `core/vector_store.py` | 向量数据库封装 |
| `core/graph_store.py` | KùzuDB 图数据库封装 |
| `core/semantic_extractor.py` | 概念提取（LLM） |
| `core/concept_deduper.py` | 概念去重 |
| `core/semantic_linker.py` | 语义连接构建 |
| `agents/coordinator.py` | Agent 协调器 |
| `app/backend_api.py` | FastAPI 后端 |
| `web-vue/src/components/GraphView.vue` | 知识图谱可视化 |
| `docs/leftover-problem.md` | 遗留问题跟踪 |
| `docs/PROJECT_STATUS.md` | 项目状态汇报 |

---

---

## 11. 扩展性设计

### 11.1 新学科接入

#### 自动接入流程

```
用户导入材料
    │
    ▼
┌──────────────────┐
│ SubjectAnalyzer  │ 自动分析材料内容
│ (LLM + 统计)     │ 提取关键词、识别学科类型
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ 自动生成配置     │ 生成 <subject_id>.json
│                  │ 含分块策略、题型偏好、示例问题
└──────────────────┘
    │
    ▼
  新学科可用
```

#### 学科配置模板（`subjects/<subject_id>.json`）

```json
{
  "id": "chemistry",
  "name": "化学",
  "keywords": ["化学键", "分子", "反应", "元素"],
  "chunking": {
    "strategy": "heading_semantic",
    "formula_handling": "preserve",
    "special_sections": ["实验步骤", "化学方程式"]
  },
  "quiz": {
    "preferred_types": ["multiple_choice", "fill_blank"],
    "difficulty_distribution": [0.3, 0.5, 0.2]
  },
  "extraction_paradigm": "theoretical"
}
```

#### 学科隔离机制

| 层级 | 隔离方式 | 说明 |
|:---|:---|:---|
| 向量数据库 | 按学科分集合 | `VectorStore("<subject>_v1")` 独立集合 |
| 图数据库 | 按学科分实例 | `GraphStore("<subject>_v1")` 独立 KùzuDB |
| 原始文件 | 按学科分文件夹 | `knowledge_base/<subject_id>/raw/` |
| 缓存 | 按学科分索引 | `bm25_<subject>_v1.pkl` |
| 监控 | 按学科分表 | 同一张 SQLite 表，subject_id 字段区分 |

### 11.2 新 Agent 开发

#### Agent 接口规范

```python
class BaseAgent(ABC):
    """所有 Agent 必须实现的接口"""
    
    @abstractmethod
    def can_handle(self, intent: str) -> bool:
        """判断是否能处理该意图"""
        pass
    
    @abstractmethod
    async def process(self, query: str, context: dict) -> dict:
        """处理请求，返回结构化结果"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称"""
        pass
```

#### 注册新 Agent

```python
# 在 agents/coordinator.py 中注册
from agents.new_agent import NewAgent

AGENT_REGISTRY = [
    TutorAgent(),
    QuizAgent(),
    CoachAgent(),
    NewAgent(),  # 新增 Agent
]
```

#### 意图路由扩展

```python
# 在 coordinator.py 中添加新的意图匹配规则
INTENT_PATTERNS = {
    "tutor": ["讲解", "解释", "什么是", "为什么"],
    "quiz": ["出题", "测试", "quiz", "题目"],
    "coach": ["评测", "评估", "能力", "分数"],
    "new": ["新关键词1", "新关键词2"],  # 新增
}
```

### 11.3 前端插件机制

#### 视图组件扩展

```javascript
// 新增视图页面：在 views/ 目录下创建 NewView.vue
// 在 App.vue 的侧边栏导航中添加菜单项
const menuItems = [
  { name: '知识图谱', component: GraphView, icon: 'graph' },
  { name: '对话学习', component: ChatView, icon: 'chat' },
  { name: '出题评测', component: QuizView, icon: 'quiz' },
  { name: '新功能', component: NewView, icon: 'new' },  // 新增
]
```

#### 图谱渲染扩展

```javascript
// 在 GraphView.vue 的 style 配置中添加新节点/边样式
const newNodeStyle = {
  selector: 'node[type="new_type"]',
  style: {
    'background-color': '#9b59b6',
    'shape': 'hexagon',
  }
}
```

### 11.4 后端 API 扩展

```python
# 在 app/backend_api.py 中添加新端点
@app.post("/api/new-feature")
async def new_feature(request: NewRequest):
    """新功能端点"""
    return {"result": "ok"}
```

### 11.5 扩展性评估

| 扩展方向 | 当前状态 | 难度 | 建议 |
|:---|:---|:---:|:---|
| 新学科 | 自动分析+手动微调 | 低 | 已支持，只需导入材料 |
| 新 Agent | 需实现接口+注册 | 中 | 遵循 BaseAgent 规范 |
| 新前端视图 | 新增 Vue 组件 | 低 | 遵循现有组件结构 |
| 新节点/边类型 | 修改 KùzuDB schema | 中 | 需重新初始化 schema |
| 新数据源 | 实现 DocumentProcessor 子类 | 中 | 继承 BaseProcessor |
| 新 Embedding | 修改 ApiEmbeddingClient | 低 | 仅替换 API 调用 |

---

## 12. 测试策略

### 12.1 测试金字塔

```
        ┌─────────┐
        │ E2E测试 │  < 5%（关键用户流程）
        │(浏览器) │
       ┌┴─────────┴┐
       │ 集成测试   │  ~15%（API + 数据库 + 外部服务）
       │(TestClient)│
      ┌┴─────────────┴┐
      │   单元测试      │  ~80%（核心算法、工具函数）
      │  (pytest)       │
      └─────────────────┘
```

### 12.2 单元测试（`tests/`）

#### 已覆盖模块

| 模块 | 测试文件 | 覆盖率 | 说明 |
|:---|:---|:---:|:---|
| DocumentProcessor | `test_document_processor.py` | ~60% | 文本/Markdown/PDF 处理 |
| SubjectAnalyzer | `test_subject_analyzer.py` | ~50% | 学科配置生成 |
| VectorStore | ❌ | 0% | 未测试 |
| GraphStore | ❌ | 0% | 未测试 |
| SemanticExtractor | ❌ | 0% | 未测试 |
| ConceptDeduper | ❌ | 0% | 未测试 |
| SemanticLinker | ❌ | 0% | 未测试 |
| Agents | ❌ | 0% | 未测试 |
| API | ❌ | 0% | 未测试 |

#### 待补充测试清单

```python
# tests/test_graph_store.py
class TestGraphStore:
    """KùzuDB 操作测试"""
    
    def test_init_schema(self):
        """Schema 初始化后应包含 Chunk 和 Concept 节点"""
        pass
    
    def test_add_chunk_nodes(self):
        """添加 chunk 后应能查询到"""
        pass
    
    def test_build_adjacent_relations(self):
        """相邻关系应按文档顺序建立"""
        pass
    
    def test_thread_safety(self):
        """多线程并发操作不应崩溃"""
        pass

# tests/test_semantic_extractor.py
class TestSemanticExtractor:
    """概念提取测试"""
    
    def test_extract_requirements(self):
        """工程分解范式应提取需求节点"""
        pass
    
    def test_extract_technologies(self):
        """工程分解范式应提取技术节点"""
        pass

# tests/test_concept_deduper.py
class TestConceptDeduper:
    """概念去重测试"""
    
    def test_merge_similar(self):
        """相似度 > 0.85 的概念应合并"""
        pass
    
    def test_keep_distinct(self):
        """相似度 < 0.5 的概念应保留独立"""
        pass
```

### 12.3 集成测试

#### API 端点测试（FastAPI TestClient）

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from app.backend_api import app

client = TestClient(app)

class TestImportAPI:
    def test_import_text(self):
        response = client.post("/api/import/text", json={
            "subject": "test",
            "text": "测试内容",
            "source_name": "test.txt"
        })
        assert response.status_code == 200
        assert response.json()["chunks_added"] > 0
    
    def test_import_pdf(self):
        # 上传 PDF 文件
        pass
    
    def test_graph_nodes_after_import(self):
        # 导入后应能查询到节点
        pass

class TestGraphAPI:
    def test_list_nodes(self):
        response = client.get("/api/knowledge-graph/test/nodes")
        assert response.status_code == 200
        assert "nodes" in response.json()
    
    def test_list_edges(self):
        response = client.get("/api/knowledge-graph/test/edges")
        assert response.status_code == 200
        assert "edges" in response.json()
    
    def test_build_concepts(self):
        response = client.post("/api/knowledge-graph/test/build", json={
            "paradigm": "engineering"
        })
        assert response.status_code == 200
```

#### 数据流测试

```python
class TestDataFlow:
    """端到端数据流测试"""
    
    def test_full_pipeline(self):
        """完整流程：导入 → 分块 → 向量化 → 建图 → 提取概念 → 去重 → 连接"""
        # 1. 导入测试材料
        # 2. 验证 Chunk 节点存在
        # 3. 验证向量索引存在
        # 4. 运行概念提取
        # 5. 验证 Concept 节点存在
        # 6. 验证语义边存在
        pass
```

### 12.4 E2E 测试

#### 关键用户流程

| 流程 | 步骤 | 验证点 |
|:---|:---|:---|
| **导入材料** | 选择文件 → 上传 → 等待处理 → 查看图谱 | 节点数 > 0，边数 > 0 |
| **查看图谱** | 打开图谱页 → 等待渲染 → 缩放/拖拽 | 节点可见，不重叠，可交互 |
| **提取概念** | 选择范式 → 点击提取 → 等待完成 → 查看结果 | Concept 节点出现，有语义边 |
| **问答对话** | 输入问题 → 等待回答 → 查看来源 | 回答有内容，显示引用来源 |
| **出题评测** | 选择题型 → 生成题目 → 作答 → 查看评分 | 题目生成成功，评分合理 |

### 12.5 测试环境配置

```bash
# 测试专用配置（config/settings.py 中读取环境变量）
export LEARNANYTHING_ENV=test

# 测试环境特点：
# - 使用内存数据库（不写入文件系统）
# - LLM 调用使用 mock（不消耗 API 配额）
# - 使用小数据集（快速执行）
```

### 12.6 持续集成（CI）建议

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: pip install -r requirements-test.txt
      - run: pytest tests/ --cov=core --cov=agents --cov=app
      - run: npm run build  # 前端构建检查
```

---

## 13. 数据迁移

### 13.1 Schema 版本管理

#### 当前 Schema 版本

```python
# core/graph_store.py
SCHEMA_VERSION = "1.0"  # 当前版本

# Schema 变更历史：
# v1.0 (2026-07-05): 初始版本
#   - 节点: Chunk(chunk_id, text, heading_path, source, page_number, chunk_type)
#   - 节点: Concept(id, name, concept_type, description, parent_hint, source_chunks)
#   - 边: ADJACENT_TO, BELONGS_TO, SOLUTION, DEPENDS_ON, REQUIRES
```

#### Schema 升级流程

```python
def migrate_schema(from_version: str, to_version: str):
    """
    Schema 升级函数
    
    示例：v1.0 → v1.1（添加 Concept 的 confidence 字段）
    """
    if from_version == "1.0" and to_version == "1.1":
        # 1. 备份数据
        # 2. 添加新属性
        # 3. 更新版本号
        pass
```

### 13.2 备份与恢复

#### 备份策略

| 数据类型 | 备份方式 | 频率 | 保留策略 |
|:---|:---|:---|:---|
| 向量数据库 | ChromaDB 导出 | 每日 | 保留7天 |
| 图数据库 | KùzuDB 文件复制 | 每日 | 保留7天 |
| 学科配置 | SQLite 导出 | 每次变更 | 保留全部 |
| 原始文件 | 文件系统备份 | 每次导入 | 永久保留 |
| 监控数据 | SQLite 导出 | 每周 | 保留30天 |

#### 备份脚本

```python
# scripts/backup.py
def backup_subject(subject_id: str, backup_dir: str):
    """备份单个学科的全部数据"""
    
    # 1. 备份向量数据库
    shutil.copytree(
        f"knowledge_base/vector_db/{subject_id}_v1.db",
        f"{backup_dir}/vector_db/{subject_id}_v1.db"
    )
    
    # 2. 备份图数据库
    shutil.copytree(
        f"knowledge_base/graph_db/{subject_id}_v1_graph",
        f"{backup_dir}/graph_db/{subject_id}_v1_graph"
    )
    
    # 3. 备份原始文件
    shutil.copytree(
        f"knowledge_base/{subject_id}/raw",
        f"{backup_dir}/raw/{subject_id}"
    )
    
    # 4. 备份学科配置
    shutil.copy(
        f"subjects/{subject_id}.json",
        f"{backup_dir}/config/{subject_id}.json"
    )
```

#### 恢复流程

```python
def restore_subject(subject_id: str, backup_dir: str):
    """从备份恢复单个学科"""
    # 1. 停止相关服务
    # 2. 恢复向量数据库
    # 3. 恢复图数据库
    # 4. 恢复原始文件
    # 5. 验证数据完整性
    # 6. 重启服务
```

### 13.3 学科数据迁移

#### 学科间迁移

```python
# 将学科 A 的数据复制到学科 B（用于分支/克隆）
def clone_subject(from_id: str, to_id: str):
    """克隆学科（复制全部数据，不共享）"""
    # 1. 复制向量数据库
    # 2. 复制图数据库
    # 3. 复制原始文件
    # 4. 修改配置中的 subject_id
    # 5. 注册新学科
```

#### 跨版本迁移

```python
# 系统升级时，将旧版本数据迁移到新版本格式
def migrate_subject_data(subject_id: str, old_version: str):
    """跨版本数据迁移"""
    
    if old_version == "0.9":
        # v0.9 → v1.0 的变更：
        # - Chunk 节点新增 chunk_type 字段
        # - Concept 节点新增 source_chunks 字段
        
        # 1. 读取旧数据
        # 2. 转换格式
        # 3. 写入新格式
        # 4. 验证
        pass
```

### 13.4 数据导出/导入

#### 标准导出格式

```json
{
  "version": "1.0",
  "subject": {
    "id": "ai_llm",
    "name": "AI大模型",
    "config": { ... }
  },
  "chunks": [
    {
      "id": "chunk_001",
      "text": "...",
      "heading_path": "第1章 > 1.1节",
      "source": "doc.pdf",
      "page_number": 1
    }
  ],
  "concepts": [
    {
      "id": "concept_001",
      "name": "Transformer",
      "type": "technology",
      "description": "..."
    }
  ],
  "relations": [
    {
      "source": "concept_001",
      "target": "concept_002",
      "type": "SOLUTION"
    }
  ]
}
```

#### 导出/导入接口

```python
# API 端点
@app.post("/api/subjects/{subject}/export")
def export_subject(subject: str, format: str = "json"):
    """导出学科数据"""
    pass

@app.post("/api/subjects/{subject}/import")
def import_subject_data(subject: str, file: UploadFile):
    """导入学科数据（从标准格式）"""
    pass
```

### 13.5 数据清理

```python
# 定期清理任务
def cleanup_old_data(days: int = 30):
    """清理过期数据"""
    # 1. 清理过期监控日志
    # 2. 清理过期查询缓存
    # 3. 清理已删除学科的残留数据
    # 4. 注意：不删除原始文件！
```

### 13.6 灾难恢复检查清单

```markdown
## 灾难恢复步骤

### 场景：数据库损坏
1. [ ] 停止所有写入操作
2. [ ] 从备份恢复向量数据库
3. [ ] 从备份恢复图数据库
4. [ ] 验证数据完整性（对比原始文件）
5. [ ] 重启服务

### 场景：误删除学科
1. [ ] 停止服务（防止写入冲突）
2. [ ] 从备份恢复学科数据
3. [ ] 重新注册学科（更新 subjects.db）
4. [ ] 重启服务

### 场景：Schema 不兼容升级
1. [ ] 备份全部数据
2. [ ] 运行迁移脚本
3. [ ] 验证迁移结果
4. [ ] 更新 SCHEMA_VERSION
5. [ ] 清理旧格式数据
```

---

*本文档是 LearnAnything 项目的权威设计参考，任何数据模型或架构变更都应同步更新此文档。*
