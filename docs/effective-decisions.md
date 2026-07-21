# LearnAnything 项目有效决策记录

## 决策 1: 多分解范式支持（2026-06-30）

**状态**: ✅ 已实施

**决策内容**: 不再使用单一的理论归纳范式，改为支持 3 种内置范式：
- 理论归纳（定义→规律→应用→扩展）
- 工程分解（需求→技术→子需求→子技术）
- 层级归纳（事实→概念→方法→评价）

**决策原因**: 单一范式不适用于所有文本类型。用户以"多GPU并行训练流程"被误标为"规律"为例，指出技术文本更适合需求-技术分解范式。

**技术实现**: `core/semantic_extractor.py` 中定义 `PARADIGMS` 字典，通过 `paradigm` 参数切换。

**遗留**: 前端缺少范式选择 UI。

---

## 决策 2: 语义质量评估五维度（2026-06-30）

**状态**: ✅ 已实施

**决策内容**: 综合质量分数 = 0.25×稳定性 + 0.20×覆盖度 + 0.20×忠实度 + 0.15×多样性 + 0.20×连接覆盖率

**参考来源**:
- OpenReview LLM-judge 框架（多 LLM 评审评估概念质量）
- ACL 2025 "MoC: Mixtures of Text Chunking Learners"（Chunk Stickiness / 连接覆盖率）
- Terminology Extraction 评估框架（覆盖度、忠实度）

**技术实现**: `core/semantic_quality_evaluator.py`

**遗留**: 连接覆盖率未接入批量提取流程（需要 chunk 列表计算）。

---

## 决策 3: 模糊概念过滤规则（2026-06-30）

**状态**: ✅ 已实施

**决策内容**: 自动过滤长度 ≤4 且以模糊词（聚合/嵌入/优化/集成/整合/微调/完善/完整/整体）结尾或开头的概念名称。

**决策原因**: LLM 常生成"完整聚合""微调嵌入"等脱离上下文、没头没尾的概念。

**技术实现**: `SemanticExtractor._is_vague_concept()`

**遗留**: 规则可能不够全面，需要更多案例扩展。

---

## 决策 4: 连接覆盖率计算方法（2026-06-30）

**状态**: ✅ 算法实现，待接入流程

**决策内容**:
- 相邻 chunk 的概念集合计算 Jaccard 相似度
- 阈值 0.3，超过视为存在逻辑连接
- 覆盖率 = 度数 ≥2 的 chunk 数 / 总 chunk 数
- 弱连接：相邻但 Jaccard < 0.3

**参考来源**: ACL 2025 "MoC: Mixtures of Text Chunking Learners"

**技术实现**: `SemanticQualityEvaluator.evaluate_linkage()`

**遗留**: 未在 `extract_all_concepts()` 中自动调用。

---

## 决策 5: 全局概念表导出（2026-06-30）

**状态**: ✅ 已实施

**决策内容**: 去重后的概念表自动导出为 CSV，路径 `knowledge_base/{subject}_concepts.csv`。

**表字段**: ID, 概念名称, 别名列表, 别名数量, 概念类型, 关系类型, 来源 chunk 数

**技术实现**: `ConceptDeduper.export_table()`

---

*记录时间: 2026-07-01 01:30*

---

## 决策 6: Trae 式多 Agent 群聊架构（2026-07-21 16:44）

**状态**: 📋 设计方案完成，待实现

**决策内容**: 将 LearnAnything 从"功能视图切换"模式升级为"Trae 式分栏群聊"模式：
- 右侧 ChatView：多 Agent 群聊入口（Tutor/Quiz/Coach），支持 @命令
- 左侧功能视图：知识图谱、出题、评测等专业功能区
- 双向互动：左侧元素可分享到右侧群聊，右侧 Agent 可驱动左侧视图变化

**参考来源**: Trae AI 编程助手的分栏设计模式

**设计文档**: `docs/design-trae-multiagent-chat.md`

**实现阶段**: 
1. 布局重构（AppLayout.vue 三栏 + EventBus）
2. 多 Agent 接入（统一 `/api/chat/send` + Agent 标准化输出）
3. 双向互动（左侧分享 + Card 渲染 + 上下文传递）
4. 对话增强（多 Agent 子会话 + 跨 Agent 话题同步）

**决策原因**: 当前功能视图切换割裂用户体验，统一群聊入口更符合 AI 助手直觉。

**前置条件**: 需先完成基础设施（Agent 个性化、UserStateStore 同步）

---

## 决策 7: 对话上下文摘要机制（2026-07-21 12:12）

**状态**: ✅ 已实施

**决策内容**: 当对话历史超过 800 字符时，自动使用 LLM 生成摘要替代完整历史注入 Prompt。

**技术实现**: `DialogContext.to_summary()` — 使用 LLM 生成 200 字以内摘要，按 `session_id + turn_number` 缓存

**配置参数**:
- `prompt_max_turns`: 5（Prompt 中注入的最近轮次）
- `prompt_max_chars`: 800（历史文本字符阈值，超则触发摘要）
- `summary_max_tokens`: 300（LLM 摘要的最大 token 数）

**验证**: 连续对话 8+ 轮后自动切换为摘要模式

---

## 决策 8: 用户可配置参数系统（2026-07-21 20:27）

**状态**: 📋 设计方案完成，待实现

**决策内容**: 系统 45 个硬编码参数开放为三层配置体系（系统默认 L3 → 用户全局 L2 → 会话级 L1）。

**关键参数**（普通用户可见）:
- `prompt_max_turns`: Prompt 中记住几轮对话
- `temperature`: LLM 回答的创造性
- `retriever_top_k`: 检索返回几个概念
- `explanation_depth`: 讲解深度（自适应/初级/中级/高级）
- `include_media`: 是否显示图片/公式
- `include_sources`: 是否显示引用来源

**设计文档**: `docs/design-user-configurable-settings.md`

**实现路径**: `core/settings_store.py` + `/api/settings` API + 前端 Settings 页面

---

*记录时间: 2026-07-22 00:30*
