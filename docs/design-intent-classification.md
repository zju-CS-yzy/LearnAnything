# 意图分类设计文档：从关键词匹配到混合智能分类

> 版本: v0.1
> 日期: 2026-07-18
> 文件: `core/intent_router.py` 重构方案

## 1. 当前问题分析

### 1.1 关键词匹配的问题

```python
# 当前实现：简单包含匹配
if "出题" in query: return "quiz"
if "找工作" in query: return "job"
```

| 问题 | 示例 | 错误结果 | 正确结果 |
|------|------|---------|---------|
| **否定不被识别** | "不要给我出题" | quiz | concept |
| **反问误判** | "这道题怎么做？" | quiz（"道题"匹配） | concept |
| **复合意图被截断** | "先出题再评测" | quiz（只匹配第一个） | [quiz, evaluate] |
| **语义相近但关键词不同** | "我想考考自己" | concept（无匹配） | quiz |
| **无置信度分层** | 任何匹配都是 1.0，无匹配就是 0.0 | 无中间态 | 应该有 0.3-0.9 的渐变 |
| **上下文无关** | 连续问"继续" | concept | 继承上次意图 |

## 2. 设计方案：混合意图分类（规则 + LLM 辅助）

### 2.1 架构概览

```
用户查询
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│                CompositeIntentRouter (混合路由器)             │
│                                                              │
│  步骤 1: 预处理                                              │
│    ├── 否定检测 (NegationDetector)                          │
│    ├── 指代消解 (AnaphoraResolver) — 复用对话上下文模块       │
│    └── 多意图分割 (MultiIntentSplitter) — 可选               │
│                                                              │
│  步骤 2: 规则分类 (RuleClassifier) — 快速路径               │
│    ├── 精确关键词匹配（加权）                               │
│    ├── 否定反转（"不要出题"→概念讲解）                       │
│    └── 输出: {intent, confidence, is_high_confidence}       │
│                                                              │
│  步骤 3: 判断是否需要 LLM 辅助                               │
│    ├── confidence >= 0.8 → 直接返回规则结果                 │
│    ├── confidence < 0.3 → 直接进入 LLM 分类               │
│    └── 0.3 <= confidence < 0.8 → 规则为主，LLM 验证        │
│                                                              │
│  步骤 4: LLM 意图分类 (LLMIntentClassifier) — 慢路径        │
│    ├── 轻量 prompt（只输出意图 + 置信度，不生成完整回答）    │
│    ├── 多意图检测（输出意图列表）                            │
│    └── 与规则结果融合（加权平均）                            │
│                                                              │
│  步骤 5: 后处理                                              │
│    ├── 多意图排序（按优先级 + 用户上下文）                   │
│    ├── 意图转换（如 evaluate 后自动建议 quiz）                │
│    └── 输出最终意图 + 备选意图列表                           │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

#### 2.2.1 规则分类器（RuleClassifier）—— 保留并增强

```python
class RuleClassifier:
    """增强版规则分类器：关键词匹配 + 否定检测 + 权重评分"""
    
    INTENT_PATTERNS = {
        "quiz": {
            "strong": ["给我出题", "生成题目", "来道题", "出几题", "quiz me"],  # 权重 1.0
            "medium": ["出题", "题目", "面试题", "练习题", "测试题", "考我", "测一下"],  # 权重 0.7
            "weak": ["题", "考", "测", "test", "exam"],  # 权重 0.3
        },
        "job": {
            "strong": ["推荐职位", "找工作", "求职", "推荐工作"],
            "medium": ["职位", "招聘", "岗位", "JD", "简历", "内推"],
            "weak": ["工作", "job", "career"],
        },
        "evaluate": {
            "strong": ["评测我", "评估我", "测水平", "测能力", "我水平怎么样"],
            "medium": ["评测", "评估", "评分", "测一下我", "我懂多少"],
            "weak": ["打分", "评价", "level", "score"],
        },
        "concept": {
            "strong": ["是什么", "讲解", "解释", "介绍一下", "详细说明"],
            "medium": ["什么是", "怎么理解", "原理", "概念"],
            "weak": [],
        },
    }
    
    NEGATION_PATTERNS = [
        "不要", "别", "不需要", "不想", "不用", "不",
        "别再", "别再给我", "不要给我", "不需要",
        "no ", "don't ", "don't need", "not ",
    ]
    
    def classify(self, query: str) -> IntentResult:
        """返回意图 + 置信度 + 匹配详情"""
        query_lower = query.lower().strip()
        
        # 1. 否定检测
        has_negation = any(neg in query_lower for neg in self.NEGATION_PATTERNS)
        
        scores = {}
        for intent, patterns in self.INTENT_PATTERNS.items():
            score = 0.0
            matched_keywords = []
            
            for level, weight in [("strong", 1.0), ("medium", 0.7), ("weak", 0.3)]:
                for kw in patterns.get(level, []):
                    if kw.lower() in query_lower:
                        score += weight
                        matched_keywords.append((kw, weight))
            
            scores[intent] = {
                "score": min(score, 1.5),  # 封顶 1.5，多个强匹配可叠加
                "matched": matched_keywords,
            }
        
        # 2. 选择最高分意图
        best_intent = max(scores, key=lambda k: scores[k]["score"])
        best_score = scores[best_intent]["score"]
        
        # 3. 否定反转：如果检测到否定，且原意图不是 concept，大幅降低置信度或反转
        if has_negation and best_intent != "concept":
            # 检查否定是否修饰该意图关键词
            negation_applies = self._negation_modifies(query_lower, best_intent, scores[best_intent]["matched"])
            if negation_applies:
                return IntentResult(
                    intent="concept",
                    confidence=0.6,  # 否定后不是高置信度，但偏向概念讲解
                    rule_confidence=best_score * 0.3,  # 原意图残差置信度
                    is_negated=True,
                    original_intent=best_intent,
                    reason=f"否定修饰原意图'{best_intent}'，回退到概念讲解",
                )
        
        # 4. 计算标准化置信度
        if best_score >= 1.0:
            confidence = 0.9 + min(best_score - 1.0, 0.1)  # 1.0+ → 0.9-1.0
        elif best_score >= 0.7:
            confidence = 0.7 + (best_score - 0.7) * 0.67  # 0.7-1.0 → 0.7-0.9
        elif best_score > 0:
            confidence = 0.3 + best_score * 0.57  # 0.0-0.7 → 0.3-0.7
        else:
            confidence = 0.0
        
        is_high_conf = confidence >= 0.8
        
        return IntentResult(
            intent=best_intent,
            confidence=confidence,
            rule_confidence=confidence,
            is_negated=False,
            matched_keywords=scores[best_intent]["matched"],
            is_high_confidence=is_high_conf,
            reason=f"规则匹配: {scores[best_intent]['matched']}",
        )
    
    def _negation_modifies(self, query: str, intent: str, matched_keywords: List[Tuple[str, float]]) -> bool:
        """检查否定词是否修饰该意图关键词"""
        negation_words = ["不要", "别", "不需要", "不想", "不用", "别再", "no ", "don't ", "not "]
        
        for kw, _ in matched_keywords:
            # 找到关键词在 query 中的位置
            pos = query.find(kw.lower())
            if pos == -1:
                continue
            # 检查关键词前 5-20 个字符内是否有否定词
            prefix = query[max(0, pos-20):pos]
            if any(neg in prefix for neg in negation_words):
                return True
        
        return False
```

#### 2.2.2 LLM 意图分类器（LLMIntentClassifier）—— 轻量调用

```python
class LLMIntentClassifier:
    """基于 LLM 的意图分类器（轻量 prompt，只输出意图判断）"""
    
    SYSTEM_PROMPT = """你是一个意图分类助手。你的任务是将用户查询分类为以下意图之一：

可用意图：
- concept: 概念讲解（用户询问"什么是XXX"、"XXX的原理"、"讲解XXX"、"这道题怎么做"）
- quiz: 出题（用户要求"给我出题"、"来道题"、"测试我"、"考考我"）
- evaluate: 能力评测（用户要求"评测我"、"评估我水平"、"我学得怎么样"）
- job: 职位推荐（用户要求"推荐工作"、"找工作"、"职位推荐"）

规则：
1. 用户询问某概念的定义、原理、用法、区别 → concept
2. 用户要求生成题目或测试 → quiz
3. 用户要求评估自己的知识水平 → evaluate
4. 用户要求推荐工作或职位 → job
5. 用户说"不要XXX"、"别XXX"、"不需要XXX" → 先判断原意图，再标记为否定，最终输出 concept
6. 一个查询可能包含多个意图，用逗号分隔输出

输出格式（严格 JSON，无 markdown）：
{"intents": ["concept"], "confidence": 0.95, "reason": "用户询问概念定义"}
或
{"intents": ["quiz", "evaluate"], "confidence": 0.85, "reason": "先出题再评测"}
"""

    def __init__(self, llm_client=None):
        self._llm = llm_client
    
    def classify(self, query: str) -> LLMIntentResult:
        """调用 LLM 进行意图分类"""
        if not self._llm or not self._llm.available:
            return LLMIntentResult(intents=["concept"], confidence=0.0, reason="LLM不可用")
        
        try:
            result = self._llm.chat_json(
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"请分类以下查询：\n\n{query}"},
                ],
                temperature=0.0,  # 确定性输出
                max_tokens=200,  # 极短输出，节省 token
            )
            
            intents = result.get("intents", ["concept"])
            confidence = result.get("confidence", 0.5)
            reason = result.get("reason", "")
            
            # 过滤无效意图
            valid_intents = [i for i in intents if i in ("concept", "quiz", "evaluate", "job")]
            if not valid_intents:
                valid_intents = ["concept"]
            
            return LLMIntentResult(
                intents=valid_intents,
                confidence=confidence,
                reason=reason,
            )
        except Exception as e:
            print(f"[LLMIntentClassifier] 分类失败: {e}")
            return LLMIntentResult(intents=["concept"], confidence=0.0, reason=f"错误: {e}")
```

#### 2.2.3 混合路由器（CompositeIntentRouter）—— 主入口

```python
class CompositeIntentRouter:
    """混合意图路由器：规则为主，LLM 为辅，置信度驱动"""
    
    CONFIDENCE_HIGH = 0.8    # 规则高置信度，直接返回，不调用 LLM
    CONFIDENCE_LOW = 0.3   # 规则低置信度，必须调用 LLM 辅助
    
    def __init__(self, rule_classifier=None, llm_classifier=None):
        self._rule = rule_classifier or RuleClassifier()
        self._llm = llm_classifier
        self._history = []  # 意图历史，用于上下文推断
    
    def route(self, query: str, enabled_intents: List[str] = None, dialog_context=None) -> RouteResult:
        """
        主路由方法。
        
        流程：
        1. 预处理（否定检测、多意图分割）
        2. 规则分类
        3. 根据置信度决定是否调用 LLM
        4. 融合结果
        5. 后处理（过滤 disabled intents、上下文推断）
        """
        enabled = enabled_intents or ["concept", "quiz", "evaluate", "job"]
        
        # 1. 规则分类
        rule_result = self._rule.classify(query)
        
        # 2. 高置信度快速路径
        if rule_result.is_high_confidence and not rule_result.is_negated:
            # 如果规则很确定，且不是否定，直接返回
            final_intent = self._filter_enabled(rule_result.intent, enabled)
            return RouteResult(
                primary_intent=final_intent,
                all_intents=[final_intent],
                confidence=rule_result.confidence,
                method="rule_high_conf",
                rule_result=rule_result,
                llm_result=None,
                reason=rule_result.reason,
            )
        
        # 3. 中低置信度：调用 LLM 辅助
        llm_result = None
        if self._llm:
            llm_result = self._llm.classify(query)
        
        # 4. 融合规则 + LLM 结果
        fused = self._fuse(rule_result, llm_result)
        
        # 5. 过滤 disabled intents
        final_intents = [self._filter_enabled(i, enabled) for i in fused.intents]
        final_intents = [i for i in final_intents if i]  # 去除 None
        
        if not final_intents:
            final_intents = ["concept"]
        
        # 6. 上下文推断（如果意图是 concept，但对话上下文是 quiz，可能是"继续"）
        if dialog_context and final_intents[0] == "concept":
            inferred = self._infer_from_context(query, dialog_context)
            if inferred:
                final_intents.insert(0, inferred)
        
        # 7. 记录历史
        self._history.append({
            "query": query,
            "intents": final_intents,
            "rule": rule_result.to_dict(),
            "llm": llm_result.to_dict() if llm_result else None,
        })
        
        return RouteResult(
            primary_intent=final_intents[0],
            all_intents=final_intents,
            confidence=fused.confidence,
            method="fused" if llm_result else "rule_low_conf",
            rule_result=rule_result,
            llm_result=llm_result,
            reason=fused.reason,
        )
    
    def _fuse(self, rule_result: IntentResult, llm_result: LLMIntentResult) -> FusedResult:
        """融合规则结果和 LLM 结果"""
        if not llm_result or llm_result.confidence == 0:
            # LLM 不可用，纯规则
            return FusedResult(
                intents=[rule_result.intent],
                confidence=rule_result.confidence,
                reason=rule_result.reason,
            )
        
        # 规则意图和 LLM 主意图一致 → 高置信度
        if rule_result.intent == llm_result.intents[0]:
            confidence = max(rule_result.confidence, llm_result.confidence)
            confidence = min(confidence + 0.1, 1.0)  # 一致性加成
            return FusedResult(
                intents=llm_result.intents,  # 保留 LLM 的多意图
                confidence=confidence,
                reason=f"规则({rule_result.intent})与LLM一致，置信度提升",
            )
        
        # 不一致：如果 LLM 置信度明显高于规则，信任 LLM
        if llm_result.confidence > rule_result.confidence + 0.3:
            return FusedResult(
                intents=llm_result.intents,
                confidence=llm_result.confidence * 0.9,  # 稍有保留
                reason=f"LLM置信度({llm_result.confidence})显著高于规则({rule_result.confidence})，优先LLM",
            )
        
        # 否则：信任规则，但降低置信度
        return FusedResult(
            intents=[rule_result.intent],
            confidence=rule_result.confidence * 0.8,
            reason=f"规则与LLM不一致({rule_result.intent} vs {llm_result.intents[0]})，以规则为主但置信度降低",
        )
    
    def _filter_enabled(self, intent: str, enabled: List[str]) -> Optional[str]:
        """过滤 disabled intent，回退到 concept"""
        if intent in enabled:
            return intent
        fallback = INTENT_META.get(intent, {}).get("fallback", "concept")
        if fallback in enabled:
            return fallback
        return "concept" if "concept" in enabled else None
    
    def _infer_from_context(self, query: str, dialog_context) -> Optional[str]:
        """基于对话上下文推断意图（处理'继续'、'下一题'等）"""
        context_phrases = ["继续", "再来", "下一题", "下一道", "接着", "还有", "more", "next"]
        if any(p in query for p in context_phrases):
            # 从对话历史中获取上次意图
            last_intent = dialog_context.get("last_intent") if dialog_context else None
            return last_intent
        return None
```

## 3. 与现有系统的集成

### 3.1 修改 `Coordinator`

```python
class Coordinator:
    def __init__(self, ...):
        # 替换旧的 IntentRouter
        self._intent_router = CompositeIntentRouter(
            rule_classifier=RuleClassifier(),
            llm_classifier=LLMIntentClassifier(self._get_llm()) if self._get_llm() else None,
        )
    
    def handle(self, query, ...):
        # 获取对话上下文（如果有多轮对话模块）
        dialog_context = self._get_dialog_context(session_id)
        
        # 调用新的混合路由
        route_result = self._intent_router.route(
            query, 
            enabled_intents=self.enabled_intents,
            dialog_context=dialog_context,
        )
        
        # 支持多意图：逐个执行，或只执行主意图
        primary_intent = route_result.primary_intent
        
        # 记录意图详情到监控
        monitor.log_stage(
            query_id=query_id,
            stage_name="intent_route",
            metrics={
                "primary_intent": primary_intent,
                "all_intents": route_result.all_intents,
                "confidence": route_result.confidence,
                "method": route_result.method,
                "rule_matched": route_result.rule_result.matched_keywords if route_result.rule_result else None,
                "llm_intents": route_result.llm_result.intents if route_result.llm_result else None,
            },
        )
        
        # 如果有多意图，可以提示用户选择
        if len(route_result.all_intents) > 1:
            print(f"[Coordinator] 检测到多意图: {route_result.all_intents}，执行主意图: {primary_intent}")
        
        # ... 原有 Agent 分发逻辑
```

### 3.2 修改 `AskResponse` 暴露意图详情

```python
class AskResponse(BaseModel):
    question: str
    answer: str
    intent: Dict[str, Any]  # 扩展：包含 confidence, method, all_intents 等
    agent: str
    duration_ms: float
    query_id: str
    media: Optional[List[Dict]] = None
```

## 4. Token 成本估算

| 路径 | 输入 token | 输出 token | 调用 LLM | 成本 |
|------|-----------|-----------|---------|------|
| **规则高置信度** | 0 | 0 | ❌ 否 | 0 |
| **规则中置信度 + LLM 验证** | ~200 | ~50 | ✅ 是 | ~0.001 元 |
| **规则低置信度 + LLM 分类** | ~200 | ~50 | ✅ 是 | ~0.001 元 |
| **纯 LLM（规则完全无匹配）** | ~200 | ~50 | ✅ 是 | ~0.001 元 |

**结论**：80% 的查询走规则高置信度路径（不调用 LLM），20% 调用 LLM（单次成本约 0.001 元）。

## 5. 实现优先级

| 优先级 | 功能 | 工作量 | 效果 |
|--------|------|--------|------|
| **P1** | 增强规则分类器（加权关键词 + 否定检测） | 2-3 小时 | 解决 70% 的误判问题 |
| **P2** | LLM 辅助分类器 | 2-3 小时 | 解决语义相近、复合意图 |
| **P2** | 混合融合逻辑 | 1-2 小时 | 规则+LLM 协同 |
| **P3** | 上下文推断（"继续"） | 1 小时 | 需要对话上下文模块 |
| **P3** | 多意图支持与用户选择 | 2-3 小时 | 前端需增加意图选择 UI |

## 6. 测试用例

| 查询 | 旧规则 | 新规则 | 新混合（+LLM） | 期望 |
|------|--------|--------|---------------|------|
| "给我出几道 RAG 的题" | quiz(1.0) | quiz(0.95) | quiz(0.98) | ✅ quiz |
| "不要给我出题" | quiz(1.0) | concept(0.6) | concept(0.75) | ✅ concept |
| "这道题怎么做" | quiz(0.0) | concept(0.85) | concept(0.9) | ✅ concept |
| "先出题再评测我" | quiz(1.0) | quiz(0.95) | [quiz, evaluate] | ✅ 多意图 |
| "我想考考自己" | concept(0.0) | concept(0.0) | quiz(0.85) | ✅ quiz |
| "继续" | concept(0.0) | concept(0.0) | 继承上次 | ✅ 上下文 |
| "RAG 是什么" | concept(0.0) | concept(0.9) | concept(0.95) | ✅ concept |
| "推荐工作" | job(1.0) | job(0.95) | job(0.98) | ✅ job |

---

*文档结束 — 确认后可直接进入代码实现*
