# LearnAnything

> 基于双层知识图谱的通用知识学习系统

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3-green)](https://vuejs.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**LearnAnything** 是一个面向通用知识学习的端到端 RAG（检索增强生成）系统。它将任意学科的文档（PDF、Markdown、图片等）转化为结构化的双层知识图谱（文档层 + 概念层），并基于图谱实现智能出题、自适应测评、溯源讲解的完整学习闭环。

---

## ✨ 核心功能

### 1. 双层知识图谱构建

- **文档层（Chunk Tree）**：将导入的文档按标题层级、自然段落自动分块，构建原文溯源树
- **概念层（Concept Network）**：通过 LLM 提取语义概念，经去重、连接后形成规范概念图谱
- **多范式提取**：支持「理论归纳」「工程分解」「层级归纳」三种概念提取范式，适配不同材料类型
- **图片语义理解**：集成 VLM（视觉语言模型），自动为图片生成描述并提取概念

### 2. 知识图谱可视化

- **文档树视图**：章节 → 段落 → 知识点的层级树，支持原文溯源
- **概念图谱视图**：UML 风格卡片节点，DAG 布局 + 副本处理，清晰展示概念间语义关系
- **悬浮预览**：鼠标悬停显示原文摘要、图片缩略图
- **交互探索**：点击节点查看详情、搜索过滤、视图切换

### 3. 智能学习 Agent

- **TutorAgent（讲解）**：基于概念关联网络提供溯源讲解，从"点"到"面"构建理解
- **QuizAgent（出题）**：基于概念子图动态生成题目，覆盖度高、关联度强
- **CoachAgent（测评）**：IRT 自适应测评，定位薄弱知识点，生成能力画像
- **多 Agent 群聊**：Trae 式分栏群聊界面，支持 `@Agent` 指令与跨 Agent 协作

### 4. 混合检索

- **四层检索策略**：精确匹配 → 模糊匹配 → 别名匹配 → Embedding 回退
- **RRF 融合**：BM25 稀疏检索 + 向量检索融合排序
- **Cross-Encoder 重排序**：提升检索精度

### 5. 评测结果可视化

- **能力条形图**：各概念掌握度可视化，支持排序/筛选/对比
- **评测报告概览**：正确率、能力值、薄弱点一目了然
- **进步曲线**：追踪学习进度（开发中）
- **错题本**：答错题目归类，支持标记已掌握（开发中）

---

## 🚀 快速开始

### 方式一：压缩包部署（推荐）

> 无需安装 Python/Node，下载解压即可运行

1. **下载压缩包**
   - 从 [Releases](https://github.com/zju-CS-yzy/LearnAnything/releases) 页面下载 `LearnAnything-vX.X.X.zip`

2. **解压到任意目录**
   ```
   LearnAnything-v1.0.0/
   └── LearnAnything/
       ├── LearnAnything.exe      ← 双击运行
       ├── _internal/             ← Python 运行时 + 依赖
       ├── web/                   ← 前端文件
       ├── config/                ← 配置文件目录
       ├── knowledge_base/        ← 知识库目录
       └── tools/                 ← 工具目录
           └── mineru/
               └── mineru-open-api.exe  ← PDF 解析工具
   ```

3. **首次启动配置**
   - 双击 `LearnAnything.exe`，自动打开浏览器
   - 首次启动会弹出配置向导，按功能模块配置 API：
     - 💬 **语言处理**（LLM）：DeepSeek / OpenAI / 硅基流动
     - 👁️ **视觉处理**（VLM）：智谱AI / OpenAI
     - 📊 **文本向量化**（Embedding）：智谱AI / OpenAI
     - 📄 **PDF 解析**（MinerU）：需要到 [mineru.net](https://mineru.net/apiManage/token) 申请免费 Token

4. **开始使用**
   - 导入材料 → 构建图谱 → 学习/问答

### 方式二：源码部署

> 适合开发者或需要自定义的用户

**前置要求**
- Python 3.10+
- Node.js 18+

**安装步骤**
```bash
# 1. 克隆仓库
git clone https://github.com/zju-CS-yzy/LearnAnything.git
cd LearnAnything

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 构建前端（如需要）
cd web-vue
npm install
npm run build
cd ..

# 4. 启动后端
python -m app.backend_api

# 5. 访问 http://localhost:5000
```

---

## 📖 使用指南

### 导入学习材料

1. 在侧边栏选择「导入管理」
2. 上传 PDF、Markdown、TXT 或图片文件
3. 系统自动完成：文档解析 → 分块 → 向量化 → 构建文档树

### 构建概念图谱

1. 切换到「学习图谱」视图
2. 点击「构建概念层」
3. 选择提取范式（理论归纳 / 工程分解 / 层级归纳）
4. 等待 LLM 提取概念 → 去重 → 语义连接

### 智能问答

1. 在「对话学习」中输入问题
2. 使用 `@tutor` 获取讲解、`@quiz` 生成题目、`@evaluate` 进行测评
3. 点击节点「分享到群聊」可将图谱元素发送到对话中

### 能力评测

1. 使用 `@evaluate` 或切换到「评测」视图
2. 完成自适应测评题目
3. 查看评测报告：概览面板 + 能力条形图

---

## 🏗️ 项目架构

```
┌────────────────────────────────────────────────────────────┐
│                        前端层（Vue3 + Vite）                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ 知识图谱  │ │ 对话学习  │ │ 出题评测  │ │ 导入管理  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
├────────────────────────────────────────────────────────────┤
│                        API层（FastAPI）                     │
│  文档导入 / 知识检索 / 图谱构建 / 问答对话 / 配置向导         │
├────────────────────────────────────────────────────────────┤
│                        Agent层                              │
│  Coordinator → TutorAgent / QuizAgent / CoachAgent         │
├────────────────────────────────────────────────────────────┤
│                        核心引擎层                            │
│  文档处理 / 向量检索 / 图数据库 / LLM调用 / VLM调用          │
├────────────────────────────────────────────────────────────┤
│                        数据层                                │
│  ChromaDB（向量）/ KùzuDB（图）/ SQLite（状态）              │
└────────────────────────────────────────────────────────────┘
```

### 双层知识图谱

```
┌─────────────────────────────────────────────────────┐
│                  概念层（Concept Layer）              │
│  ┌──────────┐      SOLUTION       ┌──────────┐   │
│  │ 需求概念  │ ─────────────────────→│ 技术概念  │   │
│  └──────────┘                      └──────────┘   │
│       │                                  │          │
│       │ DEPENDS_ON                       │         │
│       ▼                                  ▼          │
│  ┌──────────┐                      ┌──────────┐   │
│  │ 子需求   │                      │ 子技术   │   │
│  └──────────┘                      └──────────┘   │
├─────────────────────────────────────────────────────┤
│                  文档层（Document Layer）              │
│  ┌──────────┐   ADJACENT_TO   ┌──────────┐         │
│  │ Chunk 1  │ ───────────────→│ Chunk 2  │         │
│  └──────────┘                  └──────────┘         │
│       │                                              │
│       │ BELONGS_TO（同heading_path层级）              │
│       ▼                                              │
│  ┌──────────┐                                       │
│  │ Chunk 3  │                                       │
│  └──────────┘                                       │
└─────────────────────────────────────────────────────┘
```

---

## 🛠️ 技术栈

| 层级 | 组件 | 技术 |
|:---|:---|:---|
| 前端 | 框架 | Vue 3 + Vite |
| 前端 | 图谱渲染 | Cytoscape.js + dagre |
| 前端 | 图表 | ECharts |
| 后端 | API 框架 | FastAPI |
| 核心 | 文档解析 | PyMuPDF + MinerU CLI + PaddleOCR |
| 核心 | 图片理解 | VLM (GLM-4V / GPT-4o) |
| 核心 | 向量检索 | ChromaDB + BM25 + RRF |
| 核心 | 图数据库 | KùzuDB |
| 核心 | Embedding | 智谱AI / OpenAI |
| 核心 | LLM | DeepSeek / OpenAI / 硅基流动 |
| 打包 | 桌面应用 | PyInstaller |

---

## 📚 文档索引

| 文档 | 说明 |
|:---|:---|
| [docs/DESIGN.md](docs/DESIGN.md) | 总体设计文档 |
| [docs/DEPLOY.md](docs/DEPLOY.md) | 部署指南 |
| [docs/PROJECT_PAPER.md](docs/PROJECT_PAPER.md) | 工程论文 |
| [docs/data-model-v2.md](docs/data-model-v2.md) | 四层数据模型设计 |
| [docs/design-evaluation-visualization.md](docs/design-evaluation-visualization.md) | 评测结果可视化设计 |
| [docs/design-dialog-context.md](docs/design-dialog-context.md) | 多轮对话上下文设计 |
| [docs/design-trae-multiagent-chat.md](docs/design-trae-multiagent-chat.md) | 多 Agent 群聊架构设计 |
| [docs/leftover-problem.md](docs/leftover-problem.md) | 遗留问题跟踪 |

---

## 🤝 贡献指南

欢迎提交 Issue 和 PR！

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/xxx`
3. 提交更改：`git commit -am 'Add xxx'`
4. 推送分支：`git push origin feature/xxx`
5. 创建 Pull Request

---

## 📄 许可证

[MIT License](LICENSE)

---

> 本项目由 AI 辅助开发，持续迭代中。如有问题，欢迎提交 Issue 或 Discussions。
