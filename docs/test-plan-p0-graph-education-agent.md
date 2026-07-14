# LA-040-P0-TEST: 图谱教育 Agent P0 模块测试计划文档

> 版本: 1.0  
> 创建日期: 2026-07-14  
> 关联: LA-040-P0 详细设计文档  
> 目标: 确保 P0 各模块可测试、可定位、可回归

---

## 一、测试策略总览

### 1.1 测试金字塔

```
                    ┌─────────┐
                    │  E2E   │  ← 端到端：完整出题→答题→评分→讲解流程
                    │  (5%)  │     工具: Playwright + API 测试
                    ├─────────┤
                    │ 集成测试│  ← 模块间数据链路: Retriever → Builder → Assembler
                    │ (25%)  │     工具: pytest + TestClient + 内存 KùzuDB
                    ├─────────┤
                    │ 单元测试│  ← 单个模块: ConceptRetriever, SubgraphBuilder, 
                    │ (70%)  │     IRT更新, ContextAssembler, GroupManager
                    │        │     工具: pytest + mock + fixture
                    └─────────┘
```

### 1.2 可定位性设计原则

| 原则 | 实现方式 |
|:---|:---|
| **每个请求有唯一追踪 ID** | `trace_id = uuid.uuid4().hex[:16]`，贯穿全链路 |
| **每个模块有独立日志** | `logger = logging.getLogger("la.p0.concept_retriever")` |
| **关键决策点记录日志** | "选择目标概念: X (原因: 覆盖度最低)" |
| **错误码分级** | `LA-0401xxx` 格式，前 4 位模块标识，后 4 位错误类型 |
| **测试断言包含上下文** | 失败时输出 `input → expected → actual → diff` |
| **数据库状态可快照** | 测试前后 dump 为 JSON，diff 可见变更 |

### 1.3 错误码体系

```
LA-0401000: 通用错误
LA-0401001: 参数缺失
LA-0401002: 参数类型错误
LA-0401003: 权限不足

LA-0402000: Concept Retriever 错误
LA-0402001: 概念名称解析失败（未找到匹配概念）
LA-0402002: 概念扩展超时（图查询超过 max_nodes）
LA-0402003: Embedding 检索失败
LA-0402004: 学科不存在

LA-0403000: Subgraph Builder 错误
LA-0403001: 种子概念为空
LA-0403002: 子图节点数超过上限
LA-0403003: 路径构建失败（两点间无路径）
LA-0403004: 子图序列化失败

LA-0404000: Context Assembler 错误
LA-0404001: Token 预算不足（即使裁剪后仍超预算）
LA-0404002: 子图包含无描述节点
LA-0404003: 上下文组装失败（缺失关键概念）

LA-0405000: IRT 估计器错误
LA-0405001: 校准数据不足（<50 条）
LA-0405002: 参数估计发散（数值溢出）
LA-0405003: 猜测度 c 超出合理范围（>0.5）

LA-0406000: Group Manager 错误
LA-0406001: 题目组不存在
LA-0406002: 题目组状态冲突（已提交不可重复提交）
LA-0406003: 答题记录不匹配（题数不一致）
LA-0406004: 后台处理超时

LA-0407000: 数据存储错误
LA-0407001: KùzuDB 连接失败
LA-0407002: SQLite 写入失败
LA-0407003: 缓存读取失败
LA-0407004: 溯源信息缺失
```

---

## 二、单元测试计划

### 2.1 Concept Retriever 测试

**测试文件**: `tests/p0/test_concept_retriever.py`

#### TC-CR-001: 名称精确匹配
```python
def test_resolve_exact_match(self, retriever, mock_db):
    """
    输入: ["注意力机制"]
    预期: 返回 canonical_id 为 "concept_canonical_attention" 的 ConceptNode
    断言: result[0].canonical_id == "concept_canonical_attention"
    """
```

#### TC-CR-002: 名称模糊匹配（别名匹配）
```python
def test_resolve_alias_match(self, retriever, mock_db):
    """
    输入: ["Self-Attention"]
    预期: 匹配到别名为 "Self-Attention" 的概念 "自注意力机制"
    断言: result[0].name == "自注意力机制"
    """
```

#### TC-CR-003: 名称无匹配（Embedding 回退）
```python
def test_resolve_no_match_fallback_embedding(self, retriever, mock_db, mock_vector):
    """
    输入: ["一种特殊的注意力计算方法"]  # 无直接匹配
    预期: Embedding 语义检索返回 top_k=3 的相似概念
    断言: len(result) == 3 and all(r.similarity_score > 0.6 for r in result)
    """
```

#### TC-CR-004: 概念扩展（1-hop）
```python
def test_expand_one_hop(self, retriever, mock_db):
    """
    输入: 种子概念 "多头注意力"，hop=1
    预期: 返回通过 SOLUTION/DEPENDS_ON 连接的直接邻居
    断言: "缩放点积注意力" in [r.name for r in result]
           and len(result) <= 20
    """
```

#### TC-CR-005: 概念扩展（限制 max_nodes）
```python
def test_expand_respects_max_nodes(self, retriever, mock_db):
    """
    输入: 种子概念，hop=2，max_nodes=5
    预期: 即使 2-hop 有更多节点，也只返回 5 个
    断言: len(result) == 5
    """
```

#### TC-CR-006: 选择薄弱概念（有历史数据）
```python
def test_select_weak_concepts_with_history(self, retriever, mock_db):
    """
    前提: 用户已有知识状态，"位置编码" mastery=0.2，"注意力机制" mastery=0.8
    输入: user_id, subject_id, n=2
    预期: 返回 mastery 最低的 2 个概念
    断言: result[0].name == "位置编码" and result[0].mastery_level == 0.2
    """
```

#### TC-CR-007: 选择薄弱概念（无历史数据）
```python
def test_select_weak_concepts_no_history(self, retriever, mock_db):
    """
    前提: 用户无任何答题记录
    输入: user_id, subject_id, n=3
    预期: 返回 PageRank 最低的 3 个概念（边缘概念通常更难）
    断言: len(result) == 3 and all(r.pagerank_score < 0.1 for r in result)
    """
```

#### TC-CR-008: 概念统计信息（中心性）
```python
def test_get_concept_stats(self, retriever, mock_db):
    """
    输入: canonical_id="concept_canonical_attention"
    预期: 返回 in_degree, out_degree, pagerank_score
    断言: stats.in_degree >= 0 and stats.out_degree >= 0
           and 0 <= stats.pagerank_score <= 1
    """
```

#### TC-CR-ERR-001: 学科不存在
```python
def test_resolve_subject_not_found(self, retriever):
    """
    输入: subject_id="nonexistent_subject"
    预期: 抛出 LA0402004 错误
    断言: exc_info.value.code == "LA-0402004"
    """
```

#### TC-CR-ERR-002: 概念名称解析失败
```python
def test_resolve_all_concepts_not_found(self, retriever, mock_db):
    """
    输入: ["完全不存在的概念名称"]
    预期: 抛出 LA0402001 错误
    断言: exc_info.value.code == "LA-0402002"
           and "未找到匹配概念" in str(exc_info.value)
    """
```

---

### 2.2 Subgraph Builder 测试

**测试文件**: `tests/p0/test_subgraph_builder.py`

#### TC-SB-001: 构建星型子图
```python
def test_build_star(self, builder, mock_db):
    """
    输入: 中心概念 "多头注意力"，include_derived=True
    预期: 返回中心 + 1-hop 邻居 + DERIVED_FROM 来源
    断言: "多头注意力" in [n.name for n in subgraph.nodes]
           and len(subgraph.nodes) <= 1 + max_degree
    """
```

#### TC-SB-002: 构建链型子图
```python
def test_build_chain(self, builder, mock_db):
    """
    输入: start="多头注意力", end="注意力机制"
    预期: 返回两点间最短路径上的所有概念
    断言: subgraph.nodes[0].name == "多头注意力"
           and subgraph.nodes[-1].name == "注意力机制"
           and len(subgraph.edges) == len(subgraph.nodes) - 1
    """
```

#### TC-SB-003: 构建树型子图（BFS）
```python
def test_build_tree(self, builder, mock_db):
    """
    输入: root="Transformer", max_depth=2
    预期: BFS 展开 2 层
    断言: max(node.depth for node in subgraph.nodes) == 2
    """
```

#### TC-SB-004: 子图节点数上限
```python
def test_build_respects_max_nodes(self, builder, mock_db):
    """
    输入: 种子概念（高连接度），max_nodes=10
    预期: 无论图多大，只返回 10 个节点
    断言: len(subgraph.nodes) == 10
    """
```

#### TC-SB-005: 为题型构建专用子图（选择题）
```python
def test_build_for_pattern_choice(self, builder, mock_db):
    """
    输入: target="多头注意力", pattern=choice_single（depth=1, max_nodes=5）
    预期: 返回适合单选题的精简子图
    断言: len(subgraph.nodes) <= 5
           and all(n.description for n in subgraph.nodes)  # 有描述
    """
```

#### TC-SB-006: 为题型构建专用子图（解答题）
```python
def test_build_for_pattern_essay(self, builder, mock_db):
    """
    输入: target="多头注意力", pattern=essay（depth=2, max_nodes=15）
    预期: 返回包含概念链的完整子图
    断言: len(subgraph.nodes) <= 15
           and any(e.type == "DEPENDS_ON" for e in subgraph.edges)
    """
```

#### TC-SB-007: 子图序列化与重建
```python
def test_snapshot_roundtrip(self, builder, mock_db):
    """
    输入: 任意子图
    预期: to_snapshot → from_snapshot 后子图等价
    断言: original.nodes == restored.nodes
           and original.edges == restored.edges
    """
```

#### TC-SB-ERR-001: 种子概念为空
```python
def test_build_empty_seed(self, builder):
    """
    输入: seed_concepts=[]
    预期: 抛出 LA0403001 错误
    断言: exc_info.value.code == "LA-0403001"
    """
```

#### TC-SB-ERR-002: 两点间无路径
```python
def test_build_chain_no_path(self, builder, mock_db):
    """
    输入: start="多头注意力", end="完全无关的概念"
    预期: 抛出 LA0403003 错误
    断言: exc_info.value.code == "LA-0403003"
    """
```

---

### 2.3 Context Assembler 测试

**测试文件**: `tests/p0/test_context_assembler.py`

#### TC-CA-001: 组装出题上下文（预算内）
```python
def test_assemble_within_budget(self, assembler, sample_subgraph):
    """
    输入: 10 节点子图，budget=1500 tokens
    预期: 组装后上下文在预算内
    断言: context.token_count <= 1500
           and "目标知识点" in context.text
           and "来源文档" in context.text
    """
```

#### TC-CA-002: 组装出题上下文（超预算裁剪）
```python
def test_assemble_trim_to_budget(self, assembler, large_subgraph):
    """
    输入: 50 节点子图，budget=1500 tokens（必然超预算）
    预期: 自动裁剪到预算内，优先保留中心节点
    断言: context.token_count <= 1500
           and "中心概念" in context.text  # 中心节点保留
    """
```

#### TC-CA-003: 组装包含依赖链的上下文
```python
def test_assemble_with_prerequisites(self, assembler, chain_subgraph):
    """
    输入: 链型子图（A → B → C），include_prerequisites=True
    预期: 上下文包含完整依赖链
    断言: "前置知识" in context.text
           and "A" in context.text and "B" in context.text and "C" in context.text
    """
```

#### TC-CA-004: 组装讲解上下文（L2 链讲解）
```python
def test_assemble_explanation_l2(self, assembler, subgraph, user_states):
    """
    输入: 用户答错题，depth="L2"
    预期: 包含概念链、用户状态、原文依据
    断言: "知识定位" in context.text
           and "用户掌握度" in context.text
           and "原文依据" in context.text
    """
```

#### TC-CA-005: 组装讲解上下文（L3 面讲解）
```python
def test_assemble_explanation_l3(self, assembler, tree_subgraph, user_states):
    """
    输入: 用户多次答错，depth="L3"
    预期: 包含完整局部子图、薄弱知识网络
    断言: "知识网络" in context.text
           and "薄弱点" in context.text
    """
```

#### TC-CA-006: 描述截断
```python
def test_trim_description(self, assembler, subgraph_with_long_desc):
    """
    输入: 概念描述 > 500 字，budget 紧张
    预期: 描述被截断到 max_description_length
    断言: all(len(n.description) <= 200 for n in trimmed.nodes)
    """
```

#### TC-CA-ERR-001: 预算严重不足（即使裁剪后仍超预算）
```python
def test_assemble_budget_insufficient(self, assembler, subgraph):
    """
    输入: 子图，budget=100 tokens（prompt 开销 800 已超）
    预期: 抛出 LA0404001 错误
    断言: exc_info.value.code == "LA-0404001"
    """
```

---

### 2.4 IRT 估计器测试

**测试文件**: `tests/p0/test_irt_estimator.py`

#### TC-IRT-001: 启发式难度估计（中心概念）
```python
def test_estimate_b_central_concept(self, estimator):
    """
    输入: 中心概念（PageRank=0.3, 邻居=8, 描述=300字）
    预期: b 值较低（概念基础，难度低）
    计算: b = 0.3*(1-0.3) + 0.3*min(8/10,1) + 0.2*min(300/500,1) = 0.21+0.24+0.12 = 0.57
    断言: 0.4 <= b <= 0.7
    """
```

#### TC-IRT-002: 启发式难度估计（边缘概念）
```python
def test_estimate_b_edge_concept(self, estimator):
    """
    输入: 边缘概念（PageRank=0.02, 邻居=2, 描述=50字）
    预期: b 值较高（概念边缘，难度高）
    断言: b > 0.8
    """
```

#### TC-IRT-003: 信息量计算（θ = b 时最大）
```python
def test_information_max_at_theta_equals_b(self, estimator):
    """
    输入: a=1.5, b=0.0, c=0.25
    预期: θ=0.0 时信息量最大
    断言: I(0.0) > I(-1.0) and I(0.0) > I(1.0)
    """
```

#### TC-IRT-004: 能力更新（答对）
```python
def test_update_theta_correct(self, estimator):
    """
    输入: θ=0.0, is_correct=True, b=0.0, a=1.0, c=0.25
    预期: θ 上升（因为 P(0.0) = 0.625，答对说明能力 >= 估计）
    断言: theta_new > 0.0
    """
```

#### TC-IRT-005: 能力更新（答错）
```python
def test_update_theta_incorrect(self, estimator):
    """
    输入: θ=0.0, is_correct=False, b=0.0, a=1.0, c=0.25
    预期: θ 下降
    断言: theta_new < 0.0
    """
```

#### TC-IRT-006: 能力更新边界（θ 不超出 [-3, 3]）
```python
def test_update_theta_clipped(self, estimator):
    """
    输入: θ=2.9, is_correct=True, b=2.9
    预期: θ 被裁剪到 3.0，不超出范围
    断言: theta_new == 3.0
    """
```

#### TC-IRT-007: Rasch 校准（50 条记录）
```python
def test_calibrate_rasch_sufficient(self, estimator):
    """
    输入: 50 条答题记录（混合对错）
    预期: 成功估计 b 参数
    断言: b_estimated is not None and -3 <= b_estimated <= 3
    """
```

#### TC-IRT-ERR-001: Rasch 校准数据不足
```python
def test_calibrate_rasch_insufficient(self, estimator):
    """
    输入: 30 条记录（<50）
    预期: 抛出 LA0405001 错误
    断言: exc_info.value.code == "LA-0405001"
    """
```

---

### 2.5 Group Manager 测试

**测试文件**: `tests/p0/test_group_manager.py`

#### TC-GM-001: 创建题目组（指定模板）
```python
def test_create_group_with_template(self, manager, mock_quiz_agent):
    """
    输入: template_id="quick_practice", subject_id="transformer"
    预期: 返回 QuestionGroup，包含 5 道题
    断言: group.total_questions == 5
           and group.status == GroupStatus.GENERATED
           and all(q.irt_params.b is not None for q in group.questions)
    """
```

#### TC-GM-002: 创建题目组（指定目标概念）
```python
def test_create_group_with_target_concepts(self, manager, mock_quiz_agent):
    """
    输入: target_concepts=["concept_canonical_attention"]
    预期: 所有题目都关联该概念
    断言: all("concept_canonical_attention" in q.knowledge_trace.primary_concepts
               for q in group.questions)
    """
```

#### TC-GM-003: 提交整组（正常流程）
```python
def test_submit_group_success(self, manager, sample_group):
    """
    前提: group 状态为 IN_PROGRESS，用户已答完所有题
    输入: 5 个答案，其中 3 对 2 错
    预期: 返回即时得分，后台异步处理
    断言: result.score == 0.6
           and group.status == GroupStatus.SUBMITTED
    """
```

#### TC-GM-004: 提交后能力画像更新
```python
def test_profile_updated_after_grading(self, manager, sample_group, mock_db):
    """
    前提: 提交后等待后台处理完成
    预期: 用户知识状态更新
    断言: state = load_state(user_id, subject_id, "concept_canonical_attention")
           state.test_count > 0
           state.theta != 0.0  # 能力值已更新
    """
```

#### TC-GM-005: 提交后知识传播（答对前置）
```python
def test_knowledge_propagation_correct(self, manager, sample_group, mock_db):
    """
    前提: 用户答对"多头注意力"（依赖"缩放点积注意力"）
    预期: 前置知识"缩放点积注意力"掌握度 +0.05
    断言: prereq_state.mastery_level == original_mastery + 0.05
    """
```

#### TC-GM-006: 提交后知识传播（答错应用）
```python
def test_knowledge_propagation_incorrect(self, manager, sample_group, mock_db):
    """
    前提: 用户答错"多头注意力"（SOLUTION 指向"Transformer编码器"）
    预期: 应用概念"Transformer编码器"置信度 ×0.9
    断言: app_state.confidence == original_confidence * 0.9
    """
```

#### TC-GM-007: 获取组结果（评分后）
```python
def test_get_group_result_graded(self, manager, graded_group):
    """
    前提: 组已评分
    预期: 返回完整结果，包含得分、薄弱概念、推荐
    断言: result.score is not None
           and len(result.weak_concepts) >= 0
           and len(result.recommended_next) >= 0
    """
```

#### TC-GM-ERR-001: 重复提交
```python
def test_submit_already_submitted(self, manager, submitted_group):
    """
    前提: 组已提交
    输入: 再次提交
    预期: 抛出 LA0406002 错误
    断言: exc_info.value.code == "LA-0406002"
    """
```

#### TC-GM-ERR-002: 答案数量不匹配
```python
def test_submit_answer_count_mismatch(self, manager, sample_group):
    """
    前提: 组有 5 题
    输入: 只提交 3 个答案
    预期: 抛出 LA0406003 错误
    断言: exc_info.value.code == "LA-0406003"
    """
```

---

## 三、集成测试计划

### 3.1 数据链路测试

**测试文件**: `tests/p0/integration/test_data_pipeline.py`

#### TC-INT-001: 完整出题链路（Concept → Subgraph → Context → Question）
```python
def test_full_question_generation_pipeline(self, test_client, mock_db):
    """
    流程: 用户请求出题 → ConceptRetriever 解析概念 → SubgraphBuilder 构建子图
          → ContextAssembler 组装 → LLM 生成 → 存储题目
    断言: 最终题目有 question_id
           and 题目有 knowledge_trace（primary_concepts 非空）
           and 题目有 irt_params（b 已估计）
           and 溯源信息已存储（trace 可查询）
    """
```

#### TC-INT-002: 完整答题链路（Submit → Record → State Update → Profile）
```python
def test_full_submission_pipeline(self, test_client, mock_db, sample_group):
    """
    流程: 提交答案 → 创建记录 → 更新状态 → 图传播 → 生成画像
    断言: answer_records 表有 N 条记录
           and user_knowledge_state 表有更新
           and 用户画像 JSON 已生成
    """
```

#### TC-INT-003: 讲解链路（Question → Trace → Subgraph → Explanation）
```python
def test_full_explanation_pipeline(self, test_client, mock_db, graded_group):
    """
    流程: 用户请求讲解 → 加载题目 → 加载溯源 → 重建子图 → 组装上下文 → LLM 生成
    断言: 返回的 explanation 包含 "核心错因"
           and explanation 包含 "知识定位"
           and explanation 包含 "原文依据"
    """
```

#### TC-INT-004: 跨模块数据一致性
```python
def test_cross_module_data_consistency(self, test_client, mock_db):
    """
    流程: 生成题目 → 检查 KùzuDB Question 节点与 SQLite question_traces 记录
    断言: KùzuDB 中 question.irt_b == SQLite 中 trace 的 difficulty_score
           and KùzuDB 中 question.primary_concepts 与 trace 一致
    """
```

### 3.2 边界条件测试

#### TC-INT-BOUND-001: 空图谱（学科无任何概念）
```python
def test_empty_knowledge_graph(self, test_client):
    """
    前提: 学科刚刚创建，无导入文档
    输入: 请求出题
    预期: 返回友好提示，不崩溃
    断言: response.status_code == 200
           and "暂无知识点" in response.json()["message"]
    """
```

#### TC-INT-BOUND-002: 单概念图谱（只有 1 个概念）
```python
def test_single_concept_graph(self, test_client, mock_db):
    """
    前提: 学科只有 1 个概念，无语义连接
    输入: 请求生成 5 题
    预期: 生成 5 题（围绕同一概念的不同角度）
    断言: len(questions) == 5
           and all(q.primary_concepts == ["唯一概念"] for q in questions)
    """
```

#### TC-INT-BOUND-003: 大规模图谱（1000+ 概念）
```python
def test_large_graph_performance(self, test_client, mock_db):
    """
    前提: 学科有 1000+ 概念，5000+ 连接
    输入: 请求出题（5 题）
    预期: 生成时间 < 5 秒
    断言: elapsed_time < 5.0
    """
```

### 3.3 缓存一致性测试

#### TC-INT-CACHE-001: 图中心性缓存命中
```python
def test_centrality_cache_hit(self, test_client, mock_cache):
    """
    前提: PageRank 已预计算并缓存
    输入: 两次查询同一概念的中心性
    预期: 第二次命中缓存，不访问 KùzuDB
    断言: first_query.db_calls > 0 and second_query.db_calls == 0
    """
```

#### TC-INT-CACHE-002: 用户状态缓存更新后读取
```python
def test_user_state_cache_invalidation(self, test_client, mock_cache):
    """
    流程: 查询状态 → 答题更新 → 再次查询
    预期: 更新后读取到最新值
    断言: state_after.test_count == state_before.test_count + 1
    """
```

---

## 四、性能测试计划

### 4.1 响应时间基准

| 操作 | P0 目标 | 测试方法 | 通过标准 |
|:---|:---|:---|:---|
| 概念检索（名称匹配） | < 50ms | 100 次请求，测量平均/95th | 平均 < 50ms，95th < 100ms |
| 概念检索（Embedding） | < 200ms | 同上 | 平均 < 200ms |
| 子图构建（<20 节点） | < 100ms | 同上 | 平均 < 100ms |
| 上下文组装 | < 50ms | 同上 | 平均 < 50ms |
| 生成题目组（5 题） | < 3s | 端到端计时 | 总时间 < 3s（含 LLM 调用） |
| 提交整组（即时评分） | < 100ms | 同上 | 返回得分 < 100ms |
| 后台处理（5 题） | < 5s | 异步任务计时 | 状态更新完成 < 5s |
| 讲解请求（加载溯源） | < 200ms | 同上 | 组装上下文 < 200ms |

### 4.2 负载测试

```python
def test_concurrent_group_generation(self, test_client):
    """
    场景: 10 个用户同时请求生成题目组
    预期: 所有请求成功，无明显延迟
    断言: all(r.status_code == 200 for r in responses)
           and max(response_time) < 10.0
    """

def test_concurrent_submissions(self, test_client):
    """
    场景: 50 个用户同时提交答题组
    预期: 所有提交成功，数据库写入无冲突
    断言: all(r.status_code == 200 for r in responses)
           and no_database_errors
    """
```

### 4.3 内存测试

```python
def test_memory_leak_free(self, test_client):
    """
    场景: 连续生成 100 个题目组，观察内存增长
    预期: 内存无持续增长（排除缓存泄漏）
    断言: memory_growth < 50MB
    """
```

---

## 五、可定位性测试

### 5.1 日志追踪测试

```python
def test_trace_id_propagation(self, test_client, caplog):
    """
    流程: 发送请求（带 X-Trace-ID: abc123）→ 检查各模块日志
    预期: 所有日志行包含 trace_id="abc123"
    断言: all("trace_id=abc123" in record.message for record in caplog.records)
    """

def test_error_log_contains_context(self, test_client, caplog):
    """
    流程: 触发一个错误（如概念解析失败）
    预期: 错误日志包含输入参数、错误码、建议操作
    断言: "LA-0402001" in error_log
           and "输入概念" in error_log
           and "建议: 检查概念名称或尝试语义搜索" in error_log
    """
```

### 5.2 数据库状态快照测试

```python
def test_database_snapshot_on_failure(self, test_client, mock_db):
    """
    流程: 测试失败时，dump 数据库状态为 JSON
    预期: 可 diff 测试前后的状态变化
    断言: os.path.exists("test_failures/test_name_before.json")
           and os.path.exists("test_failures/test_name_after.json")
    """
```

### 5.3 错误码测试

```python
def test_all_error_codes_documented(self):
    """
    流程: 检查所有抛出的错误码在文档中都有定义
    预期: 无未定义错误码
    断言: all(code in ERROR_CODE_REGISTRY for code in used_codes)
    """
```

---

## 六、测试环境配置

### 6.1 测试数据库

```python
# conftest.py - 测试配置

@pytest.fixture
def test_kuzu_db():
    """内存 KùzuDB 实例，每次测试后重置"""
    db = KuzuDB.create_in_memory()
    yield db
    db.close()
    # 注意：内存数据库关闭后自动清理

@pytest.fixture
def test_sqlite_db():
    """内存 SQLite 实例，支持事务回滚"""
    db = sqlite3.connect(":memory:")
    init_schema(db)
    yield db
    db.close()

@pytest.fixture
def test_cache():
    """内存缓存，模拟 Redis"""
    cache = InMemoryCache()
    yield cache
    cache.clear()
```

### 6.2 Mock 策略

```python
# LLM Mock：避免实际调用，返回固定响应
class MockLLM:
    def generate_question(self, context, pattern, target):
        return Question(
            question_text=f"关于 {target.name} 的题目",
            options={"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
            correct_answer="B",
            explanation="这是解析...",
        )

# KùzuDB Mock：使用预定义的图数据
@pytest.fixture
def sample_graph():
    """返回预定义的 10 概念图"""
    return load_graph_from_json("tests/fixtures/sample_graph_10.json")
```

### 6.3 测试数据（Fixture）

```python
# tests/fixtures/sample_graph_10.json
{
  "concepts": [
    {"id": "c1", "name": "注意力机制", "type": "concept", 
     "description": "...", "aliases": ["Attention"], "pagerank": 0.3},
    {"id": "c2", "name": "缩放点积注意力", "type": "sub_technology", ...},
    {"id": "c3", "name": "多头注意力", "type": "technology", ...},
    {"id": "c4", "name": "Transformer", "type": "technology", ...},
    {"id": "c5", "name": "自注意力", "type": "concept", ...}
  ],
  "edges": [
    {"source": "c3", "target": "c2", "type": "DEPENDS_ON"},
    {"source": "c3", "target": "c1", "type": "SOLUTION"},
    {"source": "c4", "target": "c3", "type": "SOLUTION"}
  ]
}
```

---

## 七、回归测试计划

### 7.1 每次提交前运行

```bash
# 快速检查（< 1 分钟）
pytest tests/p0/unit -x --tb=short

# 完整检查（< 5 分钟）
pytest tests/p0 -v --tb=short

# 性能检查（按需）
pytest tests/p0/performance -v
```

### 7.2 每次发布前运行

```bash
# 全量测试
pytest tests/ -v --tb=long --cov=agents --cov-report=html

# 性能基准
pytest tests/p0/performance -v --benchmark-only

# 端到端测试（需完整环境）
pytest tests/e2e -v --headed  # Playwright 浏览器测试
```

---

## 八、测试文档维护

| 事件 | 动作 |
|:---|:---|
| 新增模块 | 新增对应测试文件，更新本计划 |
| 修改接口 | 更新对应测试用例，确保覆盖变更 |
| 发现 Bug | 先写复现测试，再修复代码，测试通过后再提交 |
| 性能退化 | 新增性能基准测试，记录基线数据 |
| 错误码变更 | 同步更新 ERROR_CODE_REGISTRY 和测试断言 |

---

*测试计划文档结束 — 等待 P0 开发启动后迭代*
