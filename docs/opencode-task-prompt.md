# 任务：P0-INT-1/2/3 Agent 集成 P0 模块

## 项目上下文
- 项目名称: LearnAnything
- 项目路径: D:\MyCS\AI\Project\LearnAnything
- 技术栈: Python 3.10, FastAPI, KùzuDB, Vue 3

## 背景
P0 核心模块已存在（core/graph_education/），但上层 Agent（Coordinator、QuizAgent、CoachAgent）未调用它们。需要完成集成，使 P0 模块从"死代码"变为可用。

## 参考文件（请先读取）
1. `core/graph_education/__init__.py` — 导出所有 P0 模块
2. `core/graph_education/types.py` — 数据类型：ConceptNode, Subgraph, GraphContext, ContextBudget, IRTParams, UserKnowledgeState, AnswerRecord
3. `core/graph_education/concept_retriever.py` — ConceptRetriever.resolve(concept_names), .expand(seed_concepts)
4. `core/graph_education/subgraph_builder.py` — SubgraphBuilder.build(seed_concepts, mode, max_depth, max_nodes)
5. `core/graph_education/context_assembler.py` — ContextAssembler.assemble(subgraph, budget), .assemble_explanation(subgraph, user_states)
6. `core/graph_education/irt_estimator.py` — IRTEstimator.estimate_b_heuristic(concept), .update_ability(theta, records), .calibrate_rasch(question_id, records)
7. `agents/coordinator.py` — 当前只路由到旧 Agent，未导入 P0 模块
8. `agents/quiz_agent.py` — 当前直接检索 chunks 拼接 prompt，未使用 ContextAssembler
9. `agents/coach_agent.py` — 当前使用简单规则评分，未使用 IRTEstimator

## 任务 1: P0-INT-1 Coordinator 集成 P0 模块

修改 `agents/coordinator.py`：

1. 导入 P0 模块和 GraphStore：
   ```python
   from core.graph_store import GraphStore
   from core.graph_education import (
       ConceptRetriever, SubgraphBuilder, ContextAssembler, ContextBudget,
       IRTEstimator, UserKnowledgeState
   )
   ```

2. 修改 `__init__`：
   - 添加 `self._graph_store = GraphStore(f"{collection_name}")`（延迟初始化，避免立即连接数据库）
   - 添加 `self._retriever = None`, `self._builder = None`, `self._assembler = None`, `self._irt = None`

3. 修改 `handle` 方法：
   - 对于 "quiz" 意图（已存在），在调用 `QuizAgent` 前增加 P0 流程：
     ```python
     # P0-INT-1: 使用图谱教育模块组装出题上下文
     try:
         graph_store = self._get_graph_store()
         retriever = self._get_retriever(graph_store)
         
         # 提取主题（简单实现：使用 query 作为概念名）
         topic = self._extract_topic_from_query(query)
         seed_concepts = retriever.resolve([topic])
         
         if seed_concepts:
             builder = self._get_builder(graph_store)
             subgraph = builder.build(seed_concepts, mode="auto", max_depth=2, max_nodes=15)
             
             assembler = self._get_assembler()
             budget = ContextBudget(max_tokens=2000, max_nodes=15)
             graph_context = assembler.assemble(subgraph, budget=budget)
             
             # 将组装后的上下文传递给 QuizAgent
             agent_result = agent.handle(query, filters=filters, graph_context=graph_context)
         else:
             # 回退：无匹配概念时仍使用旧方式
             agent_result = agent.handle(query, filters=filters)
     except Exception as e:
         print(f"[Coordinator] P0 模块调用失败，回退到旧模式: {e}")
         agent_result = agent.handle(query, filters=filters)
     ```
   
   - 对于 "evaluate" 意图，在 `CoachAgent` 调用后增加 IRT 能力估计：
     ```python
     # P0-INT-1: 使用 IRT 估计用户能力
     try:
         irt = self._get_irt()
         # 从答题记录中提取概念答题记录，更新 IRT 能力估计
         # （详见任务 3）
     except Exception as e:
         print(f"[Coordinator] IRT 能力估计失败: {e}")
     ```

4. 添加辅助方法：
   - `_get_graph_store()` — 延迟初始化 GraphStore
   - `_get_retriever(graph_store)` — 延迟初始化 ConceptRetriever
   - `_get_builder(graph_store)` — 延迟初始化 SubgraphBuilder
   - `_get_assembler()` — 延迟初始化 ContextAssembler
   - `_get_irt()` — 延迟初始化 IRTEstimator
   - `_extract_topic_from_query(query)` — 简单提取主题（使用 query 去除常见词后的第一个名词短语）

## 任务 2: P0-INT-2 QuizAgent 使用 ContextAssembler

修改 `agents/quiz_agent.py`：

1. 导入 GraphContext：
   ```python
   from core.graph_education import GraphContext
   ```

2. 修改 `handle` 方法签名：
   ```python
   def handle(self, query: str, n_questions: int = 5, filters=None, graph_context: Optional[GraphContext] = None) -> Dict[str, Any]:
   ```

3. 在 `handle` 方法中，如果 `graph_context` 存在，使用 P0 流程生成题目：
   ```python
   if graph_context and graph_context.text:
       # P0-INT-2: 使用 ContextAssembler 组装的上下文出题
       print(f"[QuizAgent] 使用 P0 图谱上下文出题，token={graph_context.token_count}")
       quiz_result = self._generate_questions_with_context(query, n_questions, graph_context)
   else:
       # 回退：旧方式直接检索 chunks
       print(f"[QuizAgent] 回退到旧方式出题（无图谱上下文）")
       quiz_result = self._generate_questions_old(query, n_questions, filters)
   ```

4. 添加新方法 `_generate_questions_with_context`：
   - 使用 `graph_context.text` 替代原始 chunks 作为 LLM prompt 的上下文部分
   - 保留原有 `QUIZ_GENERATION_PROMPT` 框架，但将 `chunks_text` 替换为 `graph_context.text`
   - 记录概念来源信息：`graph_context.subgraph.nodes` 中的概念名列表
   - 返回的 questions 中增加 `knowledge_trace` 字段，包含题目关联的概念列表

5. 将原来的 `handle` 中的出题逻辑提取为 `_generate_questions_old` 方法（保留旧逻辑不变，作为回退）

## 任务 3: P0-INT-3 CoachAgent 使用 IRTEstimator

修改 `agents/coach_agent.py`：

1. 导入 IRT 类型：
   ```python
   from core.graph_education import IRTEstimator, IRTParams, UserKnowledgeState, AnswerRecord
   ```

2. 修改 `__init__`：
   - 添加 `self._irt_estimator = None`

3. 添加 `_get_irt_estimator()` 方法：
   ```python
   def _get_irt_estimator(self) -> IRTEstimator:
       if self._irt_estimator is None:
           self._irt_estimator = IRTEstimator(calibration_stage=1)
       return self._irt_estimator
   ```

4. 修改 `evaluate` 方法：
   - 在现有评分逻辑之后，增加 IRT 能力估计：
     ```python
     # P0-INT-3: IRT 能力估计
     try:
         irt = self._get_irt_estimator()
         
         # 构建答题记录（AnswerRecord）列表
         answer_records = []
         for detail in details:
             record = AnswerRecord(
                 question_id=str(detail["id"]),
                 user_answer=detail["user_answer"],
                 correct_answer=detail["correct_answer"],
                 is_correct=detail["is_correct"],
                 score=detail["score"],
                 max_score=detail["max_score"],
                 response_time=30,  # 默认 30 秒，前端可传实际用时
                 primary_concepts=[detail.get("topic", "")],  # 题目关联的概念
             )
             answer_records.append(record)
         
         # 估计用户能力（theta）
         theta = 0.0  # 初始能力
         for record in answer_records:
             theta = irt.update_ability(theta, [record])
         
         # 为每个概念估计难度
         concept_difficulties = {}
         for detail in details:
             topic = detail.get("topic", "")
             if topic:
                 # 使用启发式难度估计（阶段 1）
                 concept_difficulties[topic] = irt.estimate_b_heuristic(
                     # 创建临时 ConceptNode 用于估计
                     type('ConceptNode', (), {
                         'pagerank_score': 0.5,
                         'in_degree': 2, 'out_degree': 2,
                         'description': detail.get("question", ""),
                         'concept_type': 'concept'
                     })()
                 )
         
         print(f"[CoachAgent] IRT 能力估计: theta={theta:.2f}")
         
         # 将 IRT 结果添加到报告
         report["irt"] = {
             "theta": round(theta, 2),
             "level": self._theta_to_level(theta),
             "concept_difficulties": concept_difficulties,
         }
     except Exception as e:
         print(f"[CoachAgent] IRT 估计失败: {e}")
         report["irt"] = {"error": str(e)}
     ```

5. 添加 `_theta_to_level` 方法：
   ```python
   def _theta_to_level(self, theta: float) -> str:
       """将 IRT theta 转换为等级"""
       if theta < -1.5: return "入门"
       elif theta < -0.5: return "初级"
       elif theta < 0.5: return "中级"
       elif theta < 1.5: return "高级"
       return "专家"
   ```

## 约束条件
- 所有修改必须保持向后兼容：旧调用方式（不传 graph_context）仍然正常工作
- 如果 P0 模块调用失败（如概念未找到、数据库连接失败），必须回退到旧方式并打印警告
- 逐行注释新添加的代码
- 保持原有代码风格
- 确保 `python -m pytest tests/p0/` 仍然通过（不破坏现有测试）

## 验收标准
- [ ] `coordinator.py` 可以导入并初始化 P0 模块（延迟加载）
- [ ] `coordinator.py` 的 `quiz` 意图分支调用 P0 模块流程（ConceptRetriever → SubgraphBuilder → ContextAssembler → QuizAgent）
- [ ] `quiz_agent.py` 的 `handle` 方法接受 `graph_context` 参数
- [ ] `quiz_agent.py` 在 `graph_context` 存在时使用 P0 上下文出题，否则回退旧方式
- [ ] `coach_agent.py` 的 `evaluate` 方法在评分后调用 IRT 能力估计
- [ ] `coach_agent.py` 返回的报告包含 `irt` 字段（theta, level, concept_difficulties）
- [ ] 所有修改的文件不破坏现有 pytest 测试
- [ ] 代码中添加适当的 console print 以便前端测试时观察调用流程
