# LearnAnything 项目进展汇报与遗留问题

> 创建日期：2026-06-23
> 项目路径：`D:\MyCS\AI\Project\LearnAnything`
> 项目定位：基于 IWork 重构的通用知识学习 RAG 系统，支持任意学科

---

## 一、项目架构概览

```
LearnAnything/
├── config/          # 配置层（学科配置 + 全局设置）
├── core/            # 核心引擎（文档处理、检索、缓存、监控）
├── agents/          # Agent 层（协调器 + 各职能 Agent）
├── subjects/        # 学科扩展（插件式）
├── interfaces/      # 用户接口（CLI / Web）
├── app/             # 桌面应用 + API 后端
├── knowledge_base/  # 知识库数据（运行时生成）
├── tests/           # 测试
└── web/             # 前端页面
```

---

## 二、已完成模块（✅）

### 2.1 文档处理层（core/document_processor.py）

| 能力 | 状态 | 说明 |
|:---|:---:|:---|
| 文本/Markdown | ✅ | 直接读取，标题分块 |
| PDF（文字型） | ✅ | PyMuPDF 提取文字 + 页面类型检测 |
| PDF（扫描件） | ✅ | 逐页渲染为图片 → PaddleOCR 识别 |
| 图片（png/jpg） | ✅ | PaddleOCR 提取文字 |
| 公式识别 | ⚠️ | pix2tex 框架接入，但实际公式区域提取标记为"后续处理" |
| 批量处理 | ✅ | process_batch 支持多文件 + 自动学科分析 |

### 2.2 检索层（core/）

| 模块 | 状态 | 说明 |
|:---|:---:|:---|
| VectorStore | ✅ | ChromaDB 封装，支持多集合管理 |
| EmbeddingManager | ✅ | ONNX MiniLM（384维），本地运行 |
| HybridRetriever | ✅ | BM25 + 向量检索 + RRF 融合（k=60） |
| Reranker | ✅ | Cross-Encoder 重排序 |
| MMR | ✅ | 多样性重排（lambda=0.7） |
| QueryRewriter | ✅ | 查询扩展重写 |
| QueryCache | ✅ | 本地缓存（TTL=24h, max=10000条） |

### 2.3 生成与评测层（core/）

| 模块 | 状态 | 说明 |
|:---|:---:|:---|
| LLMClient | ✅ | DeepSeek API 接入，支持 chat/stream/json |
| HallucinationDetector | ✅ | 基于 Embedding 相似度 + 关键词覆盖检测 |
| Evaluator | ✅ | LLM-as-judge（6维度评分）+ 规则回退 |
| SubjectAnalyzer | ✅ | 自动分析材料生成学科配置（JSON） |

### 2.4 Agent 层（agents/）

| Agent | 状态 | 说明 |
|:---|:---:|:---|
| Coordinator | ✅ | 意图路由 + Agent 分发 + 监控贯穿 |
| TutorAgent | ✅ | 概念讲解，基于检索内容生成回答 |
| QuizAgent | ✅ | 动态出题，支持学科配置驱动的题型选择 |
| CoachAgent | ✅ | 能力评测，两步流程（出题→评分） |
| HeadhunterAgent | ⏳ | **占位实现**，仅有关键词解析，未接入数据源 |

### 2.5 API 与接口层（app/ + interfaces/）

| 组件 | 状态 | 说明 |
|:---|:---:|:---|
| FastAPI 后端 | ✅ | 完整 REST API（health/ask/quiz/evaluate/import/subjects） |
| CLI 接口 | ✅ | `python -m interfaces.cli` 支持 import/ask |
| 桌面应用 | ✅ | PyQt5 + QWebEngineView，含启动画面 + 后端生命周期管理 |
| PyInstaller 打包 | ✅ | 已生成 `LearnAnything.exe`（dist/ 目录） |

### 2.6 基础设施

| 模块 | 状态 | 说明 |
|:---|:---:|:---|
| 监控（Monitoring） | ✅ | SQLite 存储查询日志，含阶段耗时统计 |
| 意图路由 | ✅ | 基于关键词匹配的简单路由 |
| 分块器 | ✅ | 标题分块 + 语义分块，支持学科专用分块 |
| 全局配置 | ✅ | `config/settings.py` 集中管理所有参数 |

---

## 三、遗留问题（⏳）

### 🔴 高优先级

| # | 问题 | 影响 | 下一步 |
|:---|:---|:---|:---|
| LA-001 | **HeadhunterAgent 未接入职位数据源** | 职位推荐功能不可用 | 需接入招聘 API 或爬虫；或暂时移出核心功能 |
| LA-002 | **前端 UI 缺失** | 桌面应用 WebView 只能显示测试页 | 需要设计并实现实际前端（Vue/React 或 PyQt5 原生界面） |
| LA-003 | **学科配置单一** | 只有 generic.json，化学/公务员考试等学科未配置 | 导入实际学科材料，运行 SubjectAnalyzer 生成配置 |
| LA-004 | **公式 OCR 未完整实现** | PDF 中公式密集型页面仅标记，未实际提取 LaTeX | 实现页面→图片→pix2tex→LaTeX 的完整流程 |

### 🟡 中优先级

| # | 问题 | 影响 | 下一步 |
|:---|:---|:---|:---|
| LA-005 | 评测会话内存存储 | 服务重启后评测进度丢失 | 迁移到 SQLite/Redis 持久化 |
| LA-006 | 用户认证缺失 | 无多用户支持，评测数据无隔离 | 添加 JWT 认证 + 用户系统 |
| LA-007 | 流式输出 API 不完整 | `/api/ask` 可能未完全支持 SSE 流式 | 验证并实现流式响应 |
| LA-008 | 混合检索首次加载延迟 | BM25 索引需预加载，首次查询慢 | 添加索引预热机制或后台加载 |

### 🟢 低优先级

| # | 问题 | 影响 | 下一步 |
|:---|:---|:---|:---|
| LA-009 | 测试覆盖率低 | 仅 test_document_processor.py + test_subject_analyzer.py | 补充 agents/ core/ API 层的单元测试 |
| LA-010 | 知识库可视化缺失 | 无法查看已导入的 chunk 列表 | 添加 `/api/knowledge-base/{subject}/chunks` 接口 |
| LA-011 | 监控数据未暴露 | 查询统计仅存储在 SQLite，无 API 查看 | 添加 `/api/monitoring/stats` 接口 |
| LA-012 | CORS 配置过于宽松 | `allow_origins=["*"]` 存在安全风险 | 生产环境限制为实际域名 |

---

## 四、快速验证步骤

```bash
cd D:\MyCS\AI\Project\LearnAnything

# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key（方式二选一）
# 方式A：编辑配置文件（推荐，不用每次设置环境变量）
copy config\api_keys.ini.example config\api_keys.ini
# 然后用编辑器打开 config\api_keys.ini，填入你的实际密钥

# 方式B：设置环境变量
set ZHIPU_API_KEY=your_zhipu_key
set DEEPSEEK_API_KEY=your_deepseek_key

# 3. 启动后端
python -m app.backend_api

# 4. 测试 API
curl http://127.0.0.1:5000/api/health

# 5. 导入测试材料（注意：需先删除旧知识库重建）
python -m interfaces.cli import --subject generic --path ./knowledge_base/test_chemistry.txt

# 6. 提问测试
python -m interfaces.cli ask --subject generic "什么是化学键？"
```

# 6. 提问测试
python -m interfaces.cli ask --subject generic "什么是化学键？"
```

---

## 五、与 IWork 项目的对比

| 维度 | IWork | LearnAnything |
|:---|:---|:---|
| 目标 | AI大模型求职学习 | 通用知识学习 |
| 学科 | 固定（大模型/后端/算法） | 插件式，任意学科 |
| 文档输入 | 主要是文本 | 多格式（PDF/图片/OCR/公式） |
| 检索 | 纯向量 | 混合检索（BM25 + 向量） |
| Agent | 4个固定 | 可扩展 Coordinator 架构 |
| 前端 | 命令行 | 桌面应用 + WebView |
| 打包 | 无 | PyInstaller 单文件 exe |

---

## 六、下一步建议

**如果今天开始推进，建议优先级：**

1. **确认核心使用场景**：这个系统目前主要给谁用？（个人学习/教学辅助/企业培训）—— 这决定前端 UI 的设计方向
2. **解决 LA-001（HeadhunterAgent）**：如果职位推荐不是核心功能，建议暂时移出或标记为实验性功能
3. **解决 LA-002（前端 UI）**：这是用户直接感知的部分，决定产品的完成度
4. **解决 LA-003（学科配置）**：导入 1~2 个实际学科材料，验证端到端流程

---

*本汇报基于代码审查整理，未运行实际测试。如需验证具体功能，可执行上述"快速验证步骤"。*

---

## 七、2026-06-24 变更记录：Embedding 方案迁移至智谱AI API

### 变更原因
PyInstaller 打包环境下本地 embedding 模型（onnxruntime / sentence-transformers）存在 DLL 初始化失败和依赖链遗漏问题，无法生成可用的单文件 exe。

### 变更内容

| 文件 | 变更 |
|:---|:---|
| `core/embedding.py` | 重写为 `ApiEmbeddingClient`（智谱AI Embedding API）+ `HashEmbeddingFunction`（离线降级） |
| `config/settings.py` | 新增 `ZHIPU_API_KEY`、`ZHIPU_EMBEDDING_BASE_URL`、`ZHIPU_EMBEDDING_MODEL` 配置；`DEFAULT_EMBEDDING_DIM` 从 384 改为 **2048**；新增 `_load_api_keys()` 自动从配置文件读取 |
| `config/api_keys.ini` (+ `.example`) | 新增 API Key 配置文件，支持智谱 + DeepSeek 双 key 管理 |
| `.gitignore` | 新增，忽略 `config/api_keys.ini` 防止密钥泄露 |
| `requirements.txt` | 移除 `torch`、`sentence-transformers` |
| `app.spec` | 移除所有 torch/transformers/sentence_transformers 收集代码；将 `tqdm` 移出 excludes |
| `main.py` | 移除 `SENTENCE_TRANSFORMERS_HOME`、`HF_HOME`、`TRANSFORMERS_CACHE`、`CUDA_VISIBLE_DEVICES` 环境变量 |
| `core/vector_store.py` | 默认 `embedding_dim` 改为 `DEFAULT_EMBEDDING_DIM` (2048) |
| `core/reranker.py` | 无需修改（CrossEncoder 的 try/except 已自动处理缺失） |

### API Key 配置方式（优先级从高到低）

```
1. 环境变量（ZHIPU_API_KEY, DEEPSEEK_API_KEY）
2. config/api_keys.ini 配置文件
3. 空字符串（降级模式）
```

配置步骤：
```bash
cd D:\MyCS\AI\Project\LearnAnything
copy config\api_keys.ini.example config\api_keys.ini
# 编辑 config\api_keys.ini，填入实际密钥
```

> `api_keys.ini` 已被 `.gitignore` 忽略，不会误提交到版本控制。

### 环境变量要求（如不适用配置文件）

```bash
# 必须设置
set ZHIPU_API_KEY=your_zhipu_api_key_here
set DEEPSEEK_API_KEY=your_deepseek_api_key_here

# 可选（默认已配置）
set ZHIPU_EMBEDDING_BASE_URL=https://open.bigmodel.cn/api/paas/v4
set ZHIPU_EMBEDDING_MODEL=embedding-3
```

### ⚠️ 知识库重建提醒

**embedding 维度从 384 变为 2048，旧知识库不兼容。**

重建步骤：
```bash
# 1. 删除旧向量数据库
rmdir /s /q D:\MyCS\AI\Project\LearnAnything\knowledge_base\vector_db

# 2. 重新导入文档
python -m interfaces.cli import --subject generic --path ./knowledge_base/test_chemistry.txt
```

### 智谱AI Embedding-3 模型信息

| 属性 | 值 |
|:---|:---|
| 模型 | `embedding-3` |
| 默认维度 | 2048（可自定义 256-2048） |
| 上下文窗口 | 8K tokens |
| 价格 | 0.5 元 / 百万 tokens |
| API 文档 | https://docs.bigmodel.cn/cn/guide/models/embedding/embedding-3 |

---

## 八、2026-06-24 调试记录：PyInstaller 打包问题（历史归档）

### 调试背景

运行时出题功能报错，报错信息为后端 500 错误（前端解析 JSON 失败）。开始定位打包环境问题。

### 调试过程

| 步骤 | 操作 | 结果 |
|:---|:---|:---|
| 1 | 分析错误码 1114（onnxruntime.dll 初始化失败） | 定位到 PyInstaller + VC++ Runtime 冲突 |
| 2 | 增加 `main.py` DLL 诊断代码（~150行） | 确认 `onnxruntime.dll` 的 `DllMain` 在 PyInstaller 环境下始终失败 |
| 3 | 增加 `core/embedding.py` 降级方案（HashEmbedding） | 系统可在 onnxruntime 失败时回退运行，但搜索质量下降 |
| 4 | 尝试将 `onnxruntime` 替换为 `sentence-transformers` | 修改 `core/embedding.py`、`config/settings.py`、`requirements.txt`、`app.spec`、`main.py` |
| 5 | 重新打包（PyInstaller） | 打包耗时约 15-20 分钟 |
| 6 | 运行打包后的 exe | **新错误：`No module named 'tqdm'`** |
| 7 | 增加 `tqdm` 和 `chromadb.telemetry` 到 `hiddenimports` | 重新打包 |
| 8 | 再次运行 | **仍报错：`No module named 'tqdm'`** 和 **`No module named 'chromadb.api.rust'`** |

### 调试结论

1. **onnxruntime 方案**：PyInstaller 环境下 `DllMain` 初始化失败（错误码 1114），无法修复
2. **sentence-transformers 方案**：PyInstaller 打包链中存在深层依赖遗漏问题，短期内难以逐个修复
3. **最终方案**：改用智谱AI Embedding API（远程调用），彻底移除本地模型依赖

---

## 九、2026-06-27 变更记录：Parent-Child 双层分块 + Embedding 评估体系

### 变更内容

| 文件 | 变更 |
|:---|:---|
| `core/chunking.py` | **重写** ParentChildChunker：新增 `chunk_document(pages)` 方法（先全局分 Child、再按页码聚合 Parent）；修复 `merge_sections_to_chunks` 跨章节边界检测；`parse_page_sections` 新增 heading_level 字段 |
| `core/document_processor.py` | `_process_pdf` 重写为使用 `chunk_document` 全局分块；`_process_text_file` 适配新接口；`_ocr_pdf_pages` / `_process_formula_pages` 更新为 `Tuple[str, Dict]` 输出格式 |
| `core/vector_store.py` | `get_by_parent_id` + `query_with_parent_context` 支持 `parent_ids`（多 Parent 关联） |
| `tests/test_embedding_quality.py` | 三层评估脚本 |

### 设计决策

1. **Parent-Child 双层分块（先 Child 后 Parent）**：
   - **问题**：传统"先按页分 Parent，再按页内分 Child"会导致跨页段落被切断
   - **解决方案**：先收集所有页面文本 -> 全局解析 section -> 全局分 Child chunk（跨页段落保持完整）-> 按页码标记聚合 Parent chunk
   - **页码标记**：`<!--PAGE:N-->` 插入在每页文本之间，Child 分块后解析标记确定来源页码
   - **跨页 Child**：一个段落跨两页时，`page_numbers=[1,2]`，`parent_ids=[parent_page_1, parent_page_2]`

2. **跨章节边界强制分块**：
   - `merge_sections_to_chunks` 中遇到 `heading` 类型立即 break
   - 确保章节之间不会跨边界合并

3. **真实文档验证**：
   - 15 个 summary.md（欧格玛知识库）全部导入
   - 113 chunks（15 Parent + 98 Child）
   - 6 个真实查询全部精准命中正确文档

---

## 十、当前代码状态（2026-06-27 双层分块后）

| 文件 | 状态 | 说明 |
|:---|:---:|:---|
| `core/chunking.py` | 已更新 | ParentChildChunker + chunk_document（全局分块） |
| `core/document_processor.py` | 已更新 | PDF/文本文件使用 chunk_document 全局分块 |
| `core/vector_store.py` | 已更新 | query_with_parent_context 支持多 Parent 关联 |
| `tests/test_embedding_quality.py` | 已创建 | 三层评估脚本 |
| `knowledge_base/vector_db/ai_llm_v2.db` | 已重建 | 15 个文档，113 chunks |

### 检索验证结果（真实文档）

| 查询 | 命中文档 | 相似度 | 结果 |
|:---|:---|:---:|:---:|
| Transformer的注意力机制是什么 | KNOW-202601-004 深度解析Transformer | 0.6247 | 精准命中 |
| RAG检索增强生成原理 | KNOW-202606-009 RAG基础原理与实现 | 0.6572 | 精准命中 |
| 如何设计优秀的提示词 | KNOW-202601-002 优秀提示词设计技巧 | 0.5774 | 精准命中 |
| 大模型的底层运行机制 | KNOW-202601-003 大模型底层运行机制 | 0.5949 | 精准命中 |
| Qwen2.5-VL安装步骤 | KNOW-202605-002 Qwen2.5-VL-7B本地安装指南 | 0.5500 | 精准命中 |
| LangChain的核心组件 | KNOW-202606-010 LangChain框架与组件 | 0.7095 | 精准命中 |

---

## 遗留问题（更新至 LA-017）

### 高优先级

| # | 问题 | 影响 | 下一步 |
|:---|:---|:---|:---|
| LA-001 | **HeadhunterAgent 未接入职位数据源** | 职位推荐功能不可用 | 需接入招聘 API 或爬虫；或暂时移出核心功能 |
| LA-002 | **前端 UI 缺失** | 桌面应用 WebView 只能显示测试页 | 需要设计并实现实际前端 |
| LA-003 | **学科配置单一** | 只有 generic.json | 导入实际学科材料，运行 SubjectAnalyzer |
| LA-004 | **公式 OCR 未完整实现** | pix2tex 框架接入但公式区域提取未实现 | 实现页面->图片->pix2tex->LaTeX 完整流程 |
| LA-016 | **知识库需重建（embedding 维度变更）** | 旧 384 维知识库与新的 2048 维 embedding 不兼容 | 已完成（ai_llm_v2） |
| LA-017 | **PDF 图片/表格/流程图提取** | 当前仅标记类型，未实际提取结构信息 | 实现 VLM API 描述（表格->Markdown，流程图->文本） |

### 中优先级

| # | 问题 | 影响 | 下一步 |
|:---|:---|:---|:---|
| LA-005 | 评测会话内存存储 | 服务重启后评测进度丢失 | 迁移到 SQLite/Redis 持久化 |
| LA-006 | 用户认证缺失 | 无多用户支持 | 添加 JWT 认证 + 用户系统 |
| LA-007 | 流式输出 API 不完整 | `/api/ask` SSE 流式可能未完全实现 | 验证并实现流式响应 |
| LA-008 | 混合检索首次加载延迟 | BM25 索引需预加载 | 添加索引预热机制 |

### 低优先级

| # | 问题 | 影响 | 下一步 |
|:---|:---|:---|:---|
| LA-009 | 测试覆盖率低 | 仅 2 个测试文件 | 补充单元测试 |
| LA-010 | 知识库可视化缺失 | 无法查看 chunk 列表 | 添加 `/api/knowledge-base/{subject}/chunks` 接口 |
| LA-011 | 监控数据未暴露 | 查询统计仅 SQLite | 添加 `/api/monitoring/stats` 接口 |
| LA-012 | CORS 配置过于宽松 | `allow_origins=["*"]` | 生产环境限制为实际域名 |

---

## 十一、开发目标路径 v1.0（2026-06-28 制定）

> 由开发者制定，经树状图评估盲点。执行顺序按优先级排列，每个阶段需完成前序方可进入下一阶段。

### 阶段1：前端 UI 优化

**目标**：替换简陋的 WebView 测试页，实现可用的桌面应用界面

**范围**：
- 设计主界面布局（导航栏、知识库侧边栏、对话区、检索结果展示）
- 实现问答交互界面（支持流式输出、引用溯源展示）
- 实现文档导入界面（拖拽上传、进度展示、学科选择）
- 实现评测/测验界面（题目展示、答题、即时反馈）
- 适配桌面应用窗口（PyQt5 WebView 或 原生 PyQt5 界面）

**关键技术决策**（待确认）：
- 技术栈：Vue.js/React + PyQt5 WebView？还是纯 PyQt5 原生界面？
- 是否需要本地前端构建（npm/node.js）？还是纯静态 HTML+JS？
- 与后端的通信方式：HTTP API（已存在）/ WebSocket（实时推送）？

**关联遗留问题**：LA-002

**阻塞后序**：阶段3（知识库可视化）、阶段5（Agent动态调整）的UI展示

---

### 阶段2：PDF 文档处理能力完善

**目标**：实现完整的 PDF 多模态提取（文字 + 公式 + 图片/表格/流程图）

**范围**：
- 文字型 PDF：已完成（PyMuPDF + Parent-Child 分块）
- 扫描件 PDF：已完成（PaddleOCR + 图片渲染）
- 公式区域：⚠️ 标记但未提取 → 实现页面→图片→pix2tex→LaTeX 完整流程
- 图片/表格/流程图：❌ 仅标记类型 → 实现 VLM API 描述提取（表格→Markdown，流程图→文本描述，图片→内容摘要）

**关键技术决策**（待确认）：
- VLM 选择：使用智谱 GLM-4V 还是其他多模态模型？
- 表格提取：VLM 生成 Markdown 表格？还是专用库（如 camelot/tabula）？
- 成本预估：VLM API 调用成本（每页可能 1~2 次调用）

**关联遗留问题**：LA-004（公式）、LA-017（图片/表格/流程图）

**阻塞后序**：阶段3（知识库可视化需完整文档数据）、阶段6（端到端测试）

---

### 阶段3：知识库可视化（思维导图）

**目标**：根据 chunk 之间的逻辑关联生成用户可查看、可编辑、可热重载的思维导图

**范围**：
- 后端：分析 chunk 间语义关联（embedding 相似度 + 关键词重叠 + 章节层级），生成图结构数据
- 后端 API：提供 `/api/knowledge-base/{subject}/graph` 接口，返回节点（chunk）和边（关联）
- 前端：思维导图渲染（D3.js / ECharts / Cytoscape.js）
- 前端：用户可拖拽编辑节点位置、手动添加/删除关联边、编辑节点内容（热重载回后端）
- 热重载：用户编辑后实时保存到向量库（或 SQLite 缓存），下次检索时生效

**关键技术决策**（待确认）：
- 关联算法：纯 embedding 相似度？还是结合 LLM 提取 chunk 间的逻辑关系？
- 编辑持久化：编辑后修改向量库 metadata？还是独立存储"用户自定义图谱"？
- 热重载范围：仅影响可视化？还是影响检索排序？
- 前端库选择：D3.js（灵活但复杂）/ ECharts（中文友好）/ Cytoscape.js（图布局专业）？

**关联遗留问题**：LA-010（知识库可视化缺失）→ 升级为高级可视化

**阻塞后序**：阶段6（端到端测试需要完整的知识库体验）

---

### 阶段4：工程优化

**目标**：提升系统稳定性、性能、用户体验

**范围**：
- 会话持久化：评测会话从内存迁移到 SQLite（LA-005）
- 用户系统：多用户支持（SQLite 存储用户表，评测数据隔离）→ LA-006 降级为简单本地用户（无需 JWT）
- 流式输出：验证 `/api/ask` SSE 流式响应，前端适配流式展示（LA-007）
- 索引预热：后台线程预加载 BM25 索引，减少首次查询延迟（LA-008）
- 监控 API：暴露查询统计接口（LA-011）
- CORS 配置：生产环境限制域名（LA-012）

**关键技术决策**（待确认）：
- 用户系统：本地 SQLite（单用户）还是简单多用户（无密码，仅用户名区分）？
- 流式输出：前端 WebView 如何接收 SSE？是否需要 WebSocket 替代？

**关联遗留问题**：LA-005~LA-012

**阻塞后序**：阶段6（端到端测试需要稳定系统）

---

### 阶段5：Agent 动态调整 + 简单用户画像

**目标**：首次启动通过问答确认用户倾向，动态激活/隐藏 Agent

**范围**：
- 首次启动流程：弹出问卷（3~5 个问题）→ 判断用户倾向
- 倾向分类：求职（激活 HeadhunterAgent）/ 准备考试（激活 QuizAgent + 强化评测）/ 独立学习（激活 TutorAgent）/ 项目解析（强化文档处理 + 知识库可视化）
- Agent 动态注册：Coordinator 根据倾向动态注册 Agent，隐藏不相关 Agent 的 UI 入口
- 用户画像存储：SQLite 存储用户倾向配置，后续启动直接加载
- HeadhunterAgent 处理：求职倾向时激活（但 LA-001 数据源问题仍待解决）

**关键技术决策**（待确认）：
- 倾向判断：规则匹配（关键词）还是 LLM 分类？
- HeadhunterAgent：如果用户选求职倾向，但职位数据源未接入（LA-001），如何处理？（降级提示/推荐外部链接/标记为实验性）
- 动态 Agent 注册：运行时热插拔？还是启动时静态配置？

**关联遗留问题**：LA-001（HeadhunterAgent 数据源）→ 阶段5 需决定如何处理

**阻塞后序**：无（这是最后一个功能阶段）

---

### 阶段6：端到端测试 + 开源推广

**目标**：导入实际学科材料，验证全流程，开源收集反馈

**范围**：
- 选择 1~2 个实际学科（如"前端开发"、"公务员考试"、"医学知识"）
- 导入真实材料（PDF/网页/笔记），运行 SubjectAnalyzer 生成学科配置
- 端到端测试：导入 → 提问 → 评测 → 可视化 → 反馈
- 开源准备：README 完善、LICENSE 选择、GitHub 仓库整理、截图/录屏展示
- 推广：GitHub 发布、社交平台分享、收集用户反馈
- 反馈驱动迭代：根据用户反馈调整功能优先级

**关联遗留问题**：LA-003（学科配置）→ 阶段6 解决

---

## 十二、目标路径盲点评估（树状图评估）

### 已识别的潜在盲点

#### 盲点1：前端技术栈选择对后续阶段的深远影响 ⚠️

**问题**：阶段1（UI）的技术栈选择会直接影响阶段3（思维导图）和阶段4（流式输出）的实现方式。

- 如果选择 **Vue/React + WebView**：
  - 优势：前端生态丰富，思维导图库（D3/ECharts/Cytoscape）成熟，流式输出通过 SSE 简单实现
  - 劣势：需要 Node.js 构建环境，PyInstaller 打包时可能需要额外处理前端资源
  - 对阶段3的影响：思维导图可直接用 npm 库，开发效率高
  - 对阶段5的影响：动态 Agent 注册通过前端路由控制即可
  
- 如果选择 **纯 PyQt5 原生界面**：
  - 优势：无需 Node.js，打包简单，与后端 Python 通信直接
  - 劣势：思维导图需用 Python 图可视化库（如 PyQtGraph、NetworkX），UI 美观度和交互体验可能不如 Web 前端
  - 对阶段3的影响：可能需要自己实现图渲染，或嵌入 WebView 做思维导图部分（混合方案）

**建议**：推荐 **Vue3 + Vite + PyQt5 WebView** 方案。思维导图用 ECharts/Cytoscape，打包时将前端构建产物（dist/）嵌入 PyInstaller。这样既有现代前端生态，又能打包为单文件 exe。

**决策待确认**：开发者需要确认前端技术栈偏好。

---

#### 盲点2：知识库可视化（思维导图）的"关联算法"复杂度 ⚠️⚠️

**问题**：阶段3 的目标"根据 chunk 之间的逻辑关联对知识库形成思维导图"比看起来更复杂。

- **简单方案**：纯 embedding 相似度（cosine）> 阈值 → 建立边。实现快，但关联可能过于表面（两个 chunk 都提到"Transformer"，但一个是架构描述，一个是应用案例，不应直接关联）。
- **中等方案**：embedding + 关键词重叠 + 章节层级。需要定义"关联类型"（父子关系、引用关系、对比关系、补充关系），不同关系用不同边样式。
- **高级方案**：LLM 分析每对 chunk 的逻辑关系。准确但成本高（N chunks = N²/2 次 LLM 调用，且需要持久化缓存）。

**建议**：
- 阶段3 先实现**简单方案**（embedding + 章节层级）作为 MVP
- 用户编辑功能（手动添加/删除边）可以补偿算法的不完美
- 后续迭代中加入 LLM 分析作为"增强模式"（可选开启）

**决策待确认**：
- 是否接受"简单方案 + 用户编辑补偿"的 MVP 策略？
- 关联边是否需要区分类型（父子/引用/对比）？还是统一无向边？
- 热重载的"重载"范围：仅影响可视化布局？还是用户编辑的关联会影响检索排序？

---

#### 盲点3：VLM 成本与文档处理吞吐量 ⚠️

**问题**：阶段2（PDF 完善）中 VLM 调用（图片/表格/流程图提取）的成本可能被低估。

- 假设一本 200 页的教材，每页有 1 张图片或表格，需要 200 次 VLM 调用
- 智谱 GLM-4V 价格：约 0.05 元/次（估算）→ 一本教材 10 元
- 如果用户批量导入 10 本教材 → 100 元处理成本
- 处理时间：每页 VLM 调用 ~1~3 秒 → 200 页需要 5~10 分钟（串行）

**建议**：
- 实现异步处理队列：文档导入后后台处理，前端显示进度条
- 提供"跳过 VLM 提取"选项：用户可选择只提取文字，不处理图片/表格（快速导入）
- 缓存 VLM 结果：同一文档重复导入时复用缓存
- 批量处理优化：并发调用 VLM API（但需注意 API 速率限制）

**决策待确认**：
- 是否接受 VLM 处理成本？还是有预算上限？
- 是否需要"跳过 VLM"的快速导入模式？

---

#### 盲点4：HeadhunterAgent 的阶段性处理 ⚠️

**问题**：阶段5（Agent 动态调整）中，如果用户选择"求职"倾向，但 HeadhunterAgent 数据源未接入（LA-001），会导致用户体验断层。

**建议**：
- 阶段5 实现时，HeadhunterAgent 暂时标记为**"实验性功能"**
- 用户选择"求职"倾向时，系统提示："职位推荐功能正在开发中，当前仅提供学习辅导功能"
- 或者：阶段5 实现时先**不激活 HeadhunterAgent**，仅做 UI 层面的倾向收集和 Agent 框架准备，等 LA-001 解决后再真正接入
- 阶段6（开源推广）后，根据用户反馈决定是否投入开发 HeadhunterAgent

**决策待确认**：
- HeadhunterAgent 在阶段5 是标记为实验性/降级，还是完全不暴露？

---

#### 盲点5：用户画像与隐私 ⚠️

**问题**：阶段5 的用户画像（倾向问答）涉及用户数据存储。

- 当前系统无用户认证（LA-006），如果用户画像存在本地 SQLite，同一台电脑的多用户共享数据
- 开源后，用户可能关心隐私（问答内容是否上传）

**建议**：
- 阶段4 中简单实现多用户（仅用户名区分，无密码，本地 SQLite）
- 用户画像和评测数据完全本地存储，不上传云端
- 开源 README 中明确隐私政策（数据本地存储，不上传）

**决策待确认**：
- 阶段4 是否实现简单多用户（用户名区分）？还是单用户即可？

---

#### 盲点6：开源准备的技术债务 ⚠️

**问题**：阶段6（开源推广）需要清理代码、完善文档、处理密钥安全。

- 当前代码中有 `API.txt` 明文存储密钥？（需要确认是否已清理）
- `.gitignore` 已配置忽略 `config/api_keys.ini`，但需确认是否有其他密钥泄露风险
- 开源 LICENSE：MIT / Apache 2.0 / GPL？
- 文档：需要完善 README（安装、配置、使用）、贡献指南、截图/录屏

**建议**：
- 阶段6 前进行一次"密钥审计"：检查所有代码文件中是否有硬编码密钥
- 选择 MIT LICENSE（宽松，适合推广）
- 录制 3~5 分钟使用演示视频（GIF 或视频）

---

### 总结：盲点与建议决策汇总

| # | 盲点 | 风险等级 | 建议决策 | 需要开发者确认？ |
|:---|:---|:---:|:---|:---:|
| 1 | 前端技术栈选择 | ⚠️ 中 | Vue3 + Vite + PyQt5 WebView | ✅ 是 |
| 2 | 思维导图关联算法 | ⚠️⚠️ 高 | 简单方案（embedding+章节）MVP + 用户编辑补偿 | ✅ 是 |
| 3 | VLM 成本与吞吐量 | ⚠️ 中 | 异步队列 + 可选跳过 VLM + 缓存 | ✅ 是 |
| 4 | HeadhunterAgent 处理 | ⚠️ 中 | 阶段5 标记为实验性/降级，不真正接入 | ✅ 是 |
| 5 | 用户画像与隐私 | ⚠️ 低 | 简单多用户（用户名区分），数据本地存储 | ✅ 是 |
| 6 | 开源准备的技术债务 | ⚠️ 低 | 阶段6 前密钥审计 + MIT LICENSE + 演示视频 | ❌ 可自行处理 |

---

## 十三、2026-06-28 工作记录

### 今日完成（2026-06-28 上午/下午）

| # | 任务 | 状态 |
|:---|:---|:---:|
| 1 | **前端 UI 重构** — Vue3 + Vite 侧边栏+主对话布局 | ✅ 完成 |
| 2 | **暗色主题** — 参考 Kimi 桌面版配色方案 | ✅ 完成 |
| 3 | **5 个功能视图** — 智能对话/出题/评测/导入/知识库 | ✅ 完成 |
| 4 | **API 封装层** — useApi.js 统一后端通信 | ✅ 完成 |
| 5 | **PyInstaller 打包修复** — 解决 WebView 缓存问题 | ✅ 完成 |
| 6 | **backend_api.py 静态文件路径** — 优先加载 web/dist | ✅ 完成 |
| 7 | **LA-018 修复** — QuizAgent 重写为 LLM 驱动出题 | ✅ 完成 |
| 8 | **LA-019 修复** — SSE 流式接口避免重复 LLM 调用 | ✅ 完成 |
| 9 | **知识库重建** — generic_v1 替换为 ai_llm_v2（113 文档） | ✅ 完成 |
| 10 | **评测评分 Bug 修复** — 前端提交字母 + 后端容错标准化 | ✅ 完成 |
| 11 | **题库持久化机制** — SQLite 题库 + 保存/抽题/混合模式 | ✅ 完成 |
| 12 | **学科管理系统** — 学科 CRUD、自动识别、知识库隔离 | ✅ 完成 |
| 13 | **历史会话机制** — localStorage 持久化 + Sidebar 会话列表 | ✅ 完成 |

### 关键决策（已确认）

| # | 决策 | 方案 |
|:---|:---|:---|
| 1 | 前端技术栈 | Vue3 + Vite + PyQt5 WebView |
| 2 | 思维导图关联算法 | 简单方案（embedding+章节）MVP + 用户编辑补偿 |
| 3 | VLM 处理模式 | 异步队列 + 可选"跳过 VLM"快速导入 |
| 4 | HeadhunterAgent | 阶段5 标记实验性/降级，不真正接入 |
| 5 | 用户系统 | 简单多用户（用户名区分），数据本地存储 |
| 6 | 学科管理 | SQLite 学科表 + 用户数据目录持久化 + jieba 关键词自动识别 |

### 关键决策（已确认）

| # | 决策 | 方案 |
|:---|:---|:---|
| 1 | 前端技术栈 | Vue3 + Vite + PyQt5 WebView |
| 2 | 思维导图关联算法 | 简单方案（embedding+章节）MVP + 用户编辑补偿 |
| 3 | VLM 处理模式 | 异步队列 + 可选"跳过 VLM"快速导入 |
| 4 | HeadhunterAgent | 阶段5 标记实验性/降级，不真正接入 |
| 5 | 用户系统 | 简单多用户（用户名区分），数据本地存储 |

### 新发现的问题（今日暴露）

| # | 问题 | 优先级 | 描述 |
|:---|:---|:---:|:---|
| LA-018 | **出题/评测题目质量差** | 🔴 高 | **已修复** — QuizAgent 重写为 LLM 驱动生成，Prompt 要求选项必须是完整有意义的句子，添加验证层过滤碎片选项。LLM 不可用时回退到改进的规则方法 | 2026-06-28 |
| LA-019 | **SSE 流式输出重复调用 LLM** | 🔴 高 | **已修复** — `/api/ask/stream` 改为直接使用 coordinator.handle() 结果分段发送，避免 TutorAgent 被调用两次。按段落/句子切分模拟打字机效果 | 2026-06-28 |
| LA-020 | **历史会话机制缺失** | 🟡 中 | **已修复** — localStorage 持久化，Sidebar 显示真实历史会话列表，点击加载历史消息 | 2026-06-28 |
| LA-021 | **学科分类功能未实现** | 🟡 中 | **已修复** — 全局学科状态管理，侧边栏学科选择器，支持创建/切换学科，各视图自动使用当前学科 | 2026-06-28 |
| LA-022 | **题库-知识库关联可视化** | 🟡 中 | 题目已支持 source_entry_id 关联知识条目，但知识库可视化时未展示相关题目 |

### 技术债务记录

- `main.py` 和 `app/desktop_app.py` 存在重复代码（两个桌面应用入口），需要统一
- `web/` 根目录已清理旧文件，仅保留 `dist/` 和 `lib/`
- PyInstaller 打包时需确保进程完全关闭，否则文件被占用导致打包失败

---

*最后更新：2026-06-28*

---

## 十四、2026-06-29 变更记录：LA-023 修复 + 知识库可视化架构确立

### LA-023 修复：前端展示知识片段层级问题

**问题**：向量库同时存储 Parent（15个，整页级）和 Child（98个，段落级）chunks，前端 API 未过滤，展示的是混合内容。

**修复**：
| 文件 | 修改 |
|:---|:---|
| `core/vector_store.py` | `list_all()` / `count()` 增加 `where` 过滤参数；修复 `json_extract` 比较值格式 |
| `app/backend_api.py` | `/chunks` 接口默认过滤 `type=parent`，只返回 child 层 |
| `web-vue/.../KnowledgeBaseView.vue` | 统计展示改为"知识片段/来源页数/原始资料"；新增"上下文路径"列 |

---

## 十五、知识库可视化（思维导图）专项设计

### 15.1 技术栈决策（2026-06-29）

| 决策项 | 选定方案 | 原因 |
|:---|:---|:---|
| 图数据库 | **KùzuDB**（嵌入式） | 零配置、进程内运行、Windows原生、PyInstaller兼容；Cypher查询能力等同于Neo4j |
| 舍弃方案 | Neo4j | 需要Java运行时+独立服务，与单文件exe桌面应用冲突 |
| LLM | DeepSeek API | 已有配置，成本低 |
| 概念提取 | **全局跨chunk联合提取** | 避免概念重复，保证同一概念只有一个节点 |
| 前端可视化 | 待选（Cytoscape.js vs D3.js） | 见15.4节 |

### 15.2 Chunk间关系构建思路（开发者原创）

> **理论来源**：《技术的本质》+ 概念空间向量模型
>
> **核心思想**：意义的本质是概念空间中的向量。每个chunk代表一个意义向量，将其分解为子意义向量后，通过共享概念维度建立联系。

#### 15.2.1 联系的定义

- **直接联系**：两个意义向量存在相同的概念维分向量
  - 例：`[黑色的球]`和`[白色的球]`通过`[球]`建立直接联系
- **间接联系**：两个意义向量A和B无直接联系，但存在C同时与A和B建立直接联系
  - 例：`[黑色]`和`[球]`通过`[黑色的球]`建立间接联系

#### 15.2.2 分解范式

参考《技术的本质》的技术组合理论，chunk分解采用递归树状结构：

**技术类文档**：
```
需求（为什么需要）
  └─ 子需求分解（产生什么子需求）
      └─ 子技术解决（用什么技术满足）
          └─ 原理支撑（基于什么物理现象）
```

**知识类文档**：
```
定义
  └─ 规律
      └─ 应用
          └─ 扩展
```

每个chunk在知识库整体结构中具有唯一位置，内部通过四个方向分解，最终形成**分形且递归的树形结构**。

#### 15.2.3 图模型设计（KùzuDB）

```cypher
-- 节点类型
Chunk(chunk_id, text, heading_path, source, page_number, chunk_type)
Concept(concept_id, name, concept_type, source_chunk)
Principle(principle_id, name, description)

-- 结构层关系（确定性，零成本）
BELONGS_TO(Chunk → Chunk)      -- 同heading_path层级
HAS_PARENT(Chunk → Chunk)      -- parent-child引用
ADJACENT_TO(Chunk → Chunk)     -- 相邻/同源

-- 语义层关系（LLM提取）
DEFINES(Chunk → Concept)       -- 定义关系
HAS_LAW(Chunk → Concept)       -- 规律关系
APPLIES_TO(Chunk → Concept)    -- 应用关系
EXTENDS(Chunk → Concept)       -- 扩展关系
REQUIRES(Concept → Concept)    -- 需求/依赖
IMPLEMENTS(Concept → Concept)  -- 实现关系
PREREQUISITE(Concept → Concept)-- 先修关系

-- 用户层关系（交互式）
USER_DEFINED(Chunk → Chunk)    -- 用户自定义
QUESTION_ABOUT(Chunk → Chunk)  -- 关联题库
```

### 15.3 实现阶段规划

| 阶段 | 内容 | 输入 | 输出 |
|:---|:---|:---|:---|
| **Phase 1** | 结构层构建 | SQLite向量库chunk数据 | KùzuDB文档结构树 |
| **Phase 2** | 语义层构建 | chunk文本 + DeepSeek LLM | 概念节点 + 语义关系边 |
| **Phase 3** | 用户层交互 | 用户操作 | 自定义边 + 可视化思维导图 |

### 15.4 前端可视化库对比（待选）

| 特性 | Cytoscape.js | D3.js |
|:---|:---|:---|
| **定位** | 专业图/网络可视化库 | 通用数据可视化框架 |
| **上手难度** | 低，API专为图设计 | 高，需手写力导向算法 |
| **布局算法** | 内置15+种（力导向、环形、网格、分层等） | 需自行实现或引入插件 |
| **交互能力** | 拖拽、缩放、框选、聚类、手势原生支持 | 需手动绑定事件 |
| **性能** | 针对大规模图优化（1000+节点流畅） | 依赖实现质量 |
| **样式控制** | 节点/边样式集中配置 | 完全自由（CSS+SVG） |
| **社区生态** | 图分析专用，文档清晰 | 生态巨大，但图相关示例分散 |
| **适用场景** | 知识图谱、社交网络、流程图 | 自定义交互、复杂动画 |

**推荐**：Cytoscape.js（与知识图谱场景高度匹配，开发效率高）

### 15.5 当前状态

- KùzuDB 已安装（v0.11.3），功能验证通过
- 测试数据来源：IWork/yuque_download/pdfs/（53个PDF，AI/大模型/后端技术主题）
- Phase 1 实现中...

---

## 十六、2026-06-29 详细进展记录

### 16.1 已完成工作

| 序号 | 工作项 | 状态 | 说明 |
|:---|:---|:---:|:---|
| 1 | LA-023 修复 | ✅ 完成 | 前端展示 parent 层而非 child 层。后端 API 增加 where 过滤，前端统计展示修正 |
| 2 | 技术栈决策 | ✅ 确认 | KùzuDB（嵌入式图数据库）替代 Neo4j，适配桌面应用单文件部署 |
| 3 | chunk 关系构建思路归档 | ✅ 完成 | 基于《技术的本质》的递归树状分解思路，已存入 15.2 节 |
| 4 | Phase 1 结构层实现 | ✅ 完成 | KùzuDB Schema + GraphBuilder + 4个图谱 API + 前端 GraphView |
| 5 | 测试数据导入 | ✅ 完成 | IWork PDF 导入 9/20 成功，142 chunks，构建图谱 142 节点/19 层级边/131 相邻边 |
| 6 | 前端主题切换 | ✅ 完成 | 暗色/亮色主题一键切换，localStorage 持久化，平滑过渡动画 |
| 7 | 前端字号调节 | ✅ 完成 | 小/中/大 三档字号（14px/16px/18px），全局响应式 |
| 8 | 知识图谱前端 bug 修复 | ✅ 完成 | isLoading 未定义、wheelSensitivity 警告、Failed to load nodes 均已修复 |
| 9 | 内容预览 + 节点标题 | ✅ 完成 | 后端返回 text 字段，前端智能提取 Markdown 标题/heading_path 作为节点标签 |
| 10 | 去除 parent 节点显示 | ✅ 完成 | 图谱只显示 child 节点（蓝色圆形），parent 节点已过滤 |

### 16.2 新增文件

| 文件 | 功能 |
|:---|:---|
| `core/graph_store.py` | KùzuDB 图数据库封装（Schema/CRUD/统计/子图查询） |
| `core/graph_builder.py` | Phase 1 结构层构建器（向量库 → 图数据库） |
| `composables/useTheme.js` | 全局主题状态管理（主题切换 + 字号调节 + localStorage） |
| `scripts/import_test_pdfs.py` | 批量导入 IWork PDF 测试数据脚本 |
| `web-vue/src/components/GraphView.vue` | Cytoscape.js 知识图谱可视化组件 |

### 16.3 新增 API 接口

| 接口 | 方法 | 说明 |
|:---|:---:|:---|
| `/api/knowledge-graph/{subject}/build` | POST | 构建/重建图谱（113 chunks → 113 节点，9 层级边，112 相邻边） |
| `/api/knowledge-graph/{subject}/stats` | GET | 图谱统计（节点数、各类边数） |
| `/api/knowledge-graph/{subject}/subgraph/{chunk_id}` | GET | 以指定 chunk 为中心的子图（用于可视化） |
| `/api/knowledge-graph/{subject}/nodes` | GET | 所有 child Chunk 节点列表（全局浏览，过滤 parent） |
| `/api/knowledge-graph/{subject}/edges` | GET | child 节点之间的边列表（BELONGS_TO + ADJACENT_TO） |

### 16.4 前端 GraphView 功能

| 功能 | 状态 |
|:---|:---:|
| 力导向图布局（cose 算法） | ✅ |
| 节点渲染（蓝色圆形，Markdown 标题命名） | ✅ |
| 边渲染（BELONGS_TO=蓝色实线，ADJACENT_TO=灰色虚线） | ✅ |
| 点击选中 → 右侧内容预览面板 | ✅ |
| 双击展开子树 | ✅ |
| 搜索节点 | ✅ |
| 聚焦/适应窗口/重置布局 | ✅ |
| 邻居高亮 | ✅ |
| 一键重新构建图谱 | ✅ |

### 16.5 新增关键决策

| # | 决策 | 方案 | 决策时间 |
|:---|:---|:---|:---:|
| 7 | 图数据库 | **KùzuDB**（嵌入式，Cypher，PyInstaller 兼容） | 2026-06-29 |
| 8 | 前端可视化库 | **Cytoscape.js**（专业图布局，开发效率高） | 2026-06-29 |
| 9 | 概念提取模式 | **全局跨 chunk 联合提取**（去重，避免概念重复） | 2026-06-29 |
| 10 | LLM 用于语义层 | **DeepSeek API**（已有配置，成本低） | 2026-06-29 |
| 11 | 主题系统 | 暗色/亮色双主题 + 三档字号（S/M/L）+ localStorage 持久化 | 2026-06-29 |

### 16.6 遗留问题更新

| # | 问题 | 优先级 | 状态 | 备注 |
|:---|:---|:---:|:---:|:---|
| LA-001 | HeadhunterAgent 未接入职位数据源 | 🔴 高 | ⏳ | 阶段5 标记实验性 |
| LA-003 | 学科配置单一 | ⏳ 中 | ⏳ | 已支持多学科，但配置模板有限 |
| LA-004 | 公式 OCR 未完整实现 | ⏳ 中 | ⏳ | 需 paddleocr 或 Mathpix |
| LA-005 | 评测会话内存存储 → SQLite 持久化 | 🟡 中 | ⏳ | |
| LA-006 | 用户认证缺失 | 🟡 中 | ⏳ | |
| LA-007 | SSE 流式输出重复调用 LLM | 🟡 中 | ✅ 已修复 | LA-019 |
| LA-008 | 混合检索首次加载延迟 | 🟡 中 | ⏳ | |
| LA-009 | 测试覆盖率低 | 🟢 低 | ⏳ | |
| LA-010 | 知识库可视化缺失 | 🟢 低 | **✅ Phase 1 完成** | Phase 2 语义层待开始 |
| LA-011 | 监控数据未暴露 | 🟢 低 | ⏳ | |
| LA-012 | CORS 配置过于宽松 | 🟢 低 | ⏳ | |
| LA-017 | PDF 图片/表格/流程图 VLM 提取 | 🔴 高 | ⏳ | 部分 PDF 因扫描件无法解析 |
| LA-022 | 题库-知识库关联可视化 | 🟡 中 | ⏳ | 题目已支持 source_entry_id |
| LA-023 | 前端展示知识片段层级 | 🔴 高 | ✅ 已修复 | 2026-06-29 |
| **LA-020** | **贝塞尔曲线端点** | 🔴 高 | **🔴 未解决** | **Cytoscape.js 的 bezier/unbundled-bezier 不支持精确连接点控制（如 Visio 的连接点系统）。端点仍由 Cytoscape 自动计算，无法固定在"右边界中点→左边界中点"** |
| **LA-021** | **纵向连线（多根树共享子节点）** | 🔴 高 | **🔴 未解决** | **多棵树的根节点共享同一个子节点时，布局算法无法正确分配位置。尝试自底向上布局引入 maxDepth 未定义 bug，回退后仍有问题** |
| **LA-024** | **构建脚本执行** | 🟡 中 | **🟡 待验证** | **用户反馈 `scripts/build.ps1` 无法直接执行（PowerShell 执行策略限制），需使用 `powershell -ExecutionPolicy Bypass -File`** |
| LA-023 | 前端展示知识片段层级 | 🔴 高 | ✅ 已修复 | 2026-06-29 |

### 16.7 技术债务更新

- `main.py` 和 `app/desktop_app.py` 存在重复代码（两个桌面应用入口），需要统一
- `web/` 根目录已清理旧文件，仅保留 `dist/` 和 `lib/`
- PyInstaller 打包时需确保进程完全关闭，否则文件被占用导致打包失败
- KùzuDB 图数据库目录（`knowledge_base/graph_db/`）已创建，但需要在打包时包含

### 16.8 下一步计划（Phase 2：语义层）

1. **LLM 驱动的概念提取**：对每个 chunk 提取核心概念，建立 DEFINES/HAS_LAW/APPLIES_TO/EXTENDS 关系
2. **需求链提取**：技术文档中提取需求→子需求→子技术的层级关系（REQUIRES/IMPLEMENTS）
3. **全局去重**：同一概念在不同 chunk 中重复出现时，合并为单一 Concept 节点
4. **先修关系**：基于概念依赖建立 PREREQUISITE 边（用于学习路径推荐）
5. **社区发现**：使用 Louvain 算法识别知识社区，生成社区摘要

---

*最后更新：2026-06-29*

---

## 十七、2026-07-01 变更记录：范式选择 UI + 多范式提示词优化

### 17.1 范式选择前端 UI

| 功能 | 状态 | 说明 |
|:---|:---:|:---|
| 图谱生成配置覆盖层 | ✅ | GraphView.vue 新增非弹窗选项面板 |
| 范式选择（3种） | ✅ | 卡片式单选，带描述 |
| 分解粒度滑块 | ✅ | 粗/中/细，实验性预留 |
| 附加选项 | ✅ | 语义层构建、去重、强制重建开关 |
| 评估参数权重 | ⚠️ | 折叠面板预留，未实际可配置 |
| 后端 build API 扩展 | ✅ | 支持 paradigm/force_rebuild/with_semantic |

### 17.2 多范式提示词优化

| 范式 | 优化前问题 | 优化后效果 |
|:---|:---|:---|
| 理论归纳 | 标签稳定 | 增加"内在逻辑链"指令，定义/规律/应用/扩展分类更精确 |
| 工程分解 | 缺少需求类型 | 强制识别"需求→技术"链条，成功提取 requirement 概念 |
| 层级归纳 | 类型单一（全是 concept） | 明确四种认知层次，fact/concept/method/evaluation 全部出现 |

### 17.3 范式对比测试结果

测试 chunk: 86b43f7c10f0bc74（Transformer 架构发展）

| 范式 | 概念数 | 类型分布 | 独有概念 | Jaccard（vs 理论归纳） |
|:---|:---:|:---|:---:|:---:|
| 理论归纳 | 6 | definition(2), law(1), extension(2), application(1) | 0 | — |
| 工程分解 | 8 | technology(2), sub_technology(4), requirement(2) | 突破RNN顺序处理瓶颈 | 0.75 |
| 层级归纳 | 7 | fact(2), concept(1), method(2), evaluation(2) | Decoder-only架构, Encoder-only架构 | 0.44 |

**结论**：三种范式差异化显著，每种视角提取出了其他范式看不到的概念。

### 17.4 新增文件

| 文件 | 功能 |
|:---|:---|
| `scripts/test_paradigm_comparison.py` | 自动化范式对比测试脚本 |
| `scripts/paradigm_comparison_report.json` | 测试报告 JSON |

### 17.5 遗留问题更新

| # | 问题 | 优先级 | 状态 | 备注 |
|:---|:---|:---:|:---:|:---|
| LA-002 | 前端 UI 缺失 | 🔴 高 | **部分完成** | 范式选择 UI 已实现，分解粒度预留 |
| — | 连接覆盖率未接入批量提取 | 🟡 中 | ⏳ | Phase 2 后续 |
| — | 评估参数权重未实际可配置 | 🟡 中 | ⏳ | 预留面板 |

---

*最后更新：2026-07-01*

