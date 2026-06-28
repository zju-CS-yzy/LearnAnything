# LearnAnything - 通用知识学习 RAG 系统

基于 IWork 项目重构的通用知识学习系统，支持任意学科。

## 架构设计

```
LearnAnything/
├── config/          # 配置层（学科配置 + 全局设置）
├── core/            # 核心引擎（文档处理、检索、缓存、监控）
├── agents/          # Agent 层（协调器 + 各职能 Agent）
├── subjects/        # 学科扩展（插件式，化学/公务员考试/...）
├── interfaces/      # 用户接口（CLI / Web）
├── knowledge_base/  # 知识库数据（运行时生成）
└── tests/           # 测试
```

## 核心能力

1. **多格式输入**：文本、Markdown、PDF（文字型/扫描件）、图片、手写笔记、公式、图表
2. **自动知识分块**：标题分块 + 语义分块 + 学科专用分块
3. **智能检索**：混合检索（BM25 + 向量）+ Rerank + MMR 多样性
4. **多 Agent 协作**：讲解/出题/评测/职位推荐（可扩展）
5. **学科扩展**：插件式学科配置（题型、评分标准、知识层级）

## 快速开始

```bash
pip install -r requirements.txt

# 导入知识材料
python -m interfaces.cli import --subject chemistry --path ./materials/

# 查询
python -m interfaces.cli ask --subject chemistry "解释化学键"
```

## 学科配置

学科配置位于 `config/subjects/`，每个学科一个 JSON 文件：
- `chemistry.json`：高中化学（题型：选择题、填空题、方程式配平、实验设计）
- `civil_service.json`：公务员考试（题型：行测、申论）
- `generic.json`：通用配置（默认）
