#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IntentClassifier (LA-UI-001 Step 1)
LLM 意图识别器 — 智能分析用户输入并分配给合适的 Agent。

核心能力：
1. @命令解析 — 提取显式指定的 Agent
2. LLM 语义识别 — 无@时自动判断意图
3. 多 Agent 任务拆分 — 复合意图分解为独立任务
4. 执行策略确定 — 串行/并行/混合

使用方式:
    from core.intent_classifier import IntentClassifier
    classifier = IntentClassifier()
    result = classifier.classify("帮我评测RAG并出3道题", context={...})
    # result.agent_tasks → [{agent: "coach", ...}, {agent: "quiz", ...}]
"""

import re
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from core.llm_client import FallbackLLMClient


# ========== 数据模型 ==========

@dataclass
class AgentTask:
    """单个 Agent 的任务分配"""
    agent: str                    # Agent 名称: tutor|quiz|coach|job
    task: str                     # 任务描述
    sub_query: str               # 分配给该 Agent 的具体查询
    priority: int = 1            # 优先级（1=最高）
    depends_on: List[str] = field(default_factory=list)  # 依赖的前置 Agent
    estimated_output: str = "text"  # 预期输出类型: text|question_card|evaluate_result_card


@dataclass
class IntentResult:
    """意图识别结果"""
    primary_intent: str          # 主意图: tutor|quiz|coach|job|mixed
    agent_tasks: List[AgentTask]  # 任务列表
    execution_mode: str = "sequential"  # sequential|parallel|mixed
    shared_topic: str = ""      # 提取的共享话题
    reasoning: str = ""         # 推理说明
    
    @classmethod
    def single_agent(cls, agent: str, query: str, reason: str = ""):
        """单 Agent 快捷构造"""
        return cls(
            primary_intent=agent,
            agent_tasks=[AgentTask(
                agent=agent,
                task=query,
                sub_query=query,
                priority=1,
                depends_on=[],
                estimated_output="text",
            )],
            execution_mode="sequential",
            shared_topic="",
            reasoning=reason or f"用户显式指定了 {agent} Agent",
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转为字典（供 API 序列化）"""
        return {
            "primary_intent": self.primary_intent,
            "execution_mode": self.execution_mode,
            "shared_topic": self.shared_topic,
            "reasoning": self.reasoning,
            "agent_tasks": [
                {
                    "agent": t.agent,
                    "task": t.task,
                    "sub_query": t.sub_query,
                    "priority": t.priority,
                    "depends_on": t.depends_on,
                    "estimated_output": t.estimated_output,
                }
                for t in self.agent_tasks
            ],
        }


# ========== 系统提示词 ==========

INTENT_CLASSIFICATION_PROMPT = """你是一个智能意图识别器，负责分析用户输入并将其分配给合适的AI Agent。

## 可用Agent
- tutor: 讲解知识、回答问题、解析概念（适合教学、解释类需求）
- quiz: 出题、解析题目、保存到题库（适合练习、测试类需求）
- coach: 能力评测、画像分析、学习建议（适合评估、诊断类需求）
- job: 求职相关（适合职业规划、面试准备类需求）

## 识别规则
1. 如果用户@了某个Agent，优先使用@指定的Agent
2. 如果没有@，根据语义自动判断最合适的Agent
3. 如果用户请求涉及多个Agent的能力，拆分为多个任务
4. 评估任务之间是否有依赖关系，确定执行顺序

## 关键词映射规则（结合语义判断，不要机械套用）
- 用户请求"对自己"进行评测/摸底（如"评测我"、"考考我"、"测测我的水平"、"摸底"）→ coach
- "评测"、"评估"、"诊断"等词若只是讨论主题中的普通名词（如"解释一下风险评估"），按知识讲解处理 → tutor
- "出题"、"来道题"、"测试一下" → quiz
- "讲解"、"解释一下"、"什么是"、"怎么理解" → tutor
- "面试"、"求职"、"职业规划" → job

注意：如果用户说"评测...并出题"，这是复合意图，应拆分为 coach + quiz，且 coach 优先（因为评测结果可用于指导出题）。

## 输出格式
必须返回严格的JSON格式，不要包含任何其他文本：
{
  "primary_intent": "tutor|quiz|coach|job|mixed",
  "agent_tasks": [
    {
      "agent": "agent名称",
      "task": "任务描述",
      "sub_query": "分配给该Agent的具体查询（从用户原始输入中提取）",
      "priority": 1,
      "depends_on": [],
      "estimated_output": "text|question_card|evaluate_result_card"
    }
  ],
  "execution_mode": "sequential|parallel|mixed",
  "shared_topic": "提取的共享话题",
  "reasoning": "思考过程（为什么这样分配）"
}

## 示例

输入: "帮我评测一下RAG，顺便出3道题"
输出:
{
  "primary_intent": "mixed",
  "agent_tasks": [
    {"agent": "coach", "task": "评测用户对RAG的掌握程度", "sub_query": "评测RAG掌握程度", "priority": 1, "depends_on": [], "estimated_output": "evaluate_result_card"},
    {"agent": "quiz", "task": "出3道RAG相关题目", "sub_query": "出3道RAG相关题目", "priority": 2, "depends_on": ["coach"], "estimated_output": "question_card"}
  ],
  "execution_mode": "sequential",
  "shared_topic": "RAG",
  "reasoning": "用户要求先评测再出题，评测结果可作为出题依据，因此串行执行"
}

输入: "解释一下Transformer，同时给我几个面试题"
输出:
{
  "primary_intent": "mixed",
  "agent_tasks": [
    {"agent": "tutor", "task": "解释Transformer概念", "sub_query": "解释Transformer", "priority": 1, "depends_on": [], "estimated_output": "text"},
    {"agent": "quiz", "task": "生成Transformer相关面试题", "sub_query": "出几道Transformer面试题", "priority": 1, "depends_on": [], "estimated_output": "question_card"}
  ],
  "execution_mode": "parallel",
  "shared_topic": "Transformer",
  "reasoning": "讲解和出题相互独立，可以并行执行"
}
"""


# ========== IntentClassifier 主类 ==========

class IntentClassifier:
    """
    LLM 意图识别器。
    
    使用方式:
        classifier = IntentClassifier()
        result = classifier.classify("出几道题", context={"current_topic": "RAG"})
        print(result.primary_intent)  # "quiz"
        print(result.agent_tasks[0].agent)  # "quiz"
    """
    
    # Agent 名称映射表（支持中文别名）
    AGENT_ALIASES = {
        # 英文
        'tutor': 'tutor', 'quiz': 'quiz', 'coach': 'coach', 'job': 'job',
        # 中文别名
        '讲解': 'tutor', '老师': 'tutor', '教师': 'tutor', '教学': 'tutor',
        '出题': 'quiz', '题目': 'quiz', '测试': 'quiz', '考试': 'quiz',
        '评测': 'coach', '评估': 'coach', '诊断': 'coach',
        '求职': 'job', '面试': 'job', '招聘': 'job', '职位': 'job',
    }
    
    # 默认 LLM 配置（使用轻量级模型降低延迟）
    DEFAULT_LLM_MODEL = "deepseek-chat"  # 可配置为 flash 模型
    DEFAULT_MAX_TOKENS = 800
    DEFAULT_TEMPERATURE = 0.1
    
    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: 可选的 LLMClient 实例。None 时自动创建 FallbackLLMClient。
        """
        if llm_client is not None:
            self._llm = llm_client
        else:
            # 使用 FallbackLLMClient 确保高可用
            self._llm = FallbackLLMClient()
        
        self._prompt_template = INTENT_CLASSIFICATION_PROMPT
        print(f"[IntentClassifier] 初始化完成，LLM={self._llm.primary.model}")
    
    # ---------- 核心方法 ----------
    
    def classify(self, query: str, context: Optional[Dict[str, Any]] = None) -> IntentResult:
        """
        对用户输入进行意图分类。
        
        Args:
            query: 用户输入文本
            context: 上下文信息（可选）
                {
                    "current_topic": str,      # 当前话题
                    "last_agent": str,         # 上一个Agent
                    "turn_count": int,         # 轮次
                    "selected_concept": str,   # 选中的概念
                }
                
        Returns:
            IntentResult: 意图识别结果
        """
        context = context or {}
        
        # 1. 提取显式@的Agent
        explicit_agents = self._extract_at_mentions(query)
        
        # 2. 如果只有一个显式Agent，快速返回（无需LLM）
        if len(explicit_agents) == 1:
            agent = explicit_agents[0]
            # 移除@前缀后的内容作为 sub_query
            sub_query = self._remove_at_mentions(query)
            return IntentResult.single_agent(
                agent=agent,
                query=sub_query or query,
                reason=f"用户显式@了 {agent} Agent",
            )
        
        # 3. 关键词强信号预处理（无显式@时）
        # 如果查询包含强信号词，在上下文中标记倾向，帮助LLM正确识别
        if not explicit_agents:
            forced_hint = self._detect_forced_intent(query)
            if forced_hint:
                context = dict(context)
                context["forced_intent_hint"] = forced_hint
                print(f"[IntentClassifier] 关键词意图检测: {forced_hint}")
        
        # 4. 如果有多个显式Agent，需要LLM进行任务拆分
        # 5. 如果没有显式Agent，需要LLM识别意图
        return self._llm_classify(query, context, explicit_agents)
    
    def classify_simple(self, query: str) -> str:
        """
        简化的意图分类，只返回Agent名称。
        
        适用于只需要知道用哪个Agent的场景（如Coordinator路由）。
        
        Returns:
            str: Agent名称（tutor|quiz|coach|job|mixed）
        """
        result = self.classify(query)
        return result.primary_intent
    
    # ---------- 私有方法 ----------
    
    def _extract_at_mentions(self, query: str) -> List[str]:
        """
        提取@提及的Agent。
        
        支持格式：
          - @tutor
          - @quiz
          - @coach
          - @讲解（中文别名）
          
        Returns:
            List[str]: 标准化后的Agent名称列表（去重，保持顺序）
        """
        # 匹配 @word 格式
        pattern = r'@(\w+)'
        mentions = re.findall(pattern, query)
        
        # 标准化映射
        standardized = []
        seen = set()
        for m in mentions:
            agent = self.AGENT_ALIASES.get(m.lower(), m.lower())
            if agent in ('tutor', 'quiz', 'coach', 'job') and agent not in seen:
                standardized.append(agent)
                seen.add(agent)
        
        return standardized
    
    def _remove_at_mentions(self, query: str) -> str:
        """移除@提及，返回清理后的查询文本"""
        # 移除所有 @word 格式的文本
        cleaned = re.sub(r'@\w+\s*', '', query)
        return cleaned.strip()
    
    def _detect_forced_intent(self, query: str) -> str:
        """
        关键词意图信号检测（INTENT-P2-1 修复版）。

        分两档，避免"解释一下风险评估"这类讲解请求被"评估"二字误判：
        - 强信号：动作明确指向"对用户本人"的评测/出题/求职，高置信，
          提示中给出明确建议；
        - 弱信号：该词可能只是讨论主题中的普通名词（如"风险评估"
          "绩效评估"），提示中仅作倾向性参考，最终由 LLM 结合语义判断。

        Returns:
            str: 意图提示文本（可多行合并），无匹配时返回空字符串
        """
        q = query.lower()
        hints = []

        def _hit(keywords):
            return next((kw for kw in keywords if kw in q), None)

        # ---- 强信号 ----

        # coach：明确指向"测我/考我"这类对用户本人的评测动作。
        # 注："考考"涵盖"考考我"，统一归 coach（不再与 quiz 表重复）。
        kw = _hit(['考考', '测测', '评测我', '评估我', '诊断我', '考我',
                   '测一下我', '摸摸底', '摸底', '我的水平', '掌握程度'])
        if kw:
            hints.append(
                f"检测到强信号词'{kw}'：用户在请求对其本人进行能力评测，"
                f"应使用 coach Agent（能力评测）")

        # quiz：明确的出题动作（含"出3道题/出几道题"这类数量词插入的变体）
        kw = _hit(['出题', '来道题', '来几道题', '测试题', '练习题'])
        if not kw and re.search(r'出[^，。,.]{0,4}道题', q):
            kw = '出…道题'
        if kw:
            hints.append(
                f"检测到强信号词'{kw}'：用户在请求出题，"
                f"应使用 quiz Agent（出题）")

        # job：明确的求职动作
        kw = _hit(['面试', '求职', '职业规划', '简历', '应聘'])
        if kw:
            hints.append(
                f"检测到强信号词'{kw}'：用户在咨询求职相关事宜，"
                f"应使用 job Agent")

        # ---- 弱信号（可能是主题名词，仅供 LLM 参考）----

        # coach 弱信号："评测/评估/诊断/测一下"常出现在讲解类问题中
        kw = _hit(['评测', '评估', '诊断', '测一下'])
        if kw:
            hints.append(
                f"检测到关键词'{kw}'：用户可能想进行能力评测（coach），"
                f"但'{kw}'也可能只是讨论主题中的普通名词（如“风险评估”）。"
                f"请判断：若用户在请求对自己进行评测/摸底，使用 coach；"
                f"若只是在询问包含该词的知识概念，按语义选择（通常为 tutor）")

        # quiz 弱信号："测试一下"（与提示词规则对齐；可能是出题也可能是评测）
        kw = _hit(['测试一下'])
        if kw:
            hints.append(
                f"检测到关键词'测试一下'：用户可能想要练习题（quiz），"
                f"也可能想评测水平（coach），请结合语义判断")

        return "\n".join(hints)
    
    def _build_prompt(self, query: str, context: Dict[str, Any], explicit_agents: List[str]) -> str:
        """构建LLM提示词"""
        # 构建上下文信息
        ctx_parts = []
        if context.get("current_topic"):
            ctx_parts.append(f"当前话题: {context['current_topic']}")
        if context.get("last_agent"):
            ctx_parts.append(f"最近Agent: {context['last_agent']}")
        if context.get("selected_concept"):
            ctx_parts.append(f"选中概念: {context['selected_concept']}")
        if context.get("turn_count"):
            ctx_parts.append(f"对话轮次: {context['turn_count']}")
        
        ctx_str = "\n".join(ctx_parts) if ctx_parts else "无额外上下文"
        
        # 显式Agent信息
        explicit_str = ""
        if explicit_agents:
            explicit_str = f"用户显式@了: {', '.join(explicit_agents)}"
        
        # LA-UI-001-FIX / INTENT-P2-1: 关键词意图提示（分强/弱档，弱档仅供 LLM 参考）
        forced_hint = context.get("forced_intent_hint", "")
        forced_str = f"\n## 关键词意图提示（请结合语义最终判断）\n{forced_hint}\n" if forced_hint else ""
        
        prompt = f"""{self._prompt_template}

## 当前上下文
{ctx_str}
{explicit_str}{forced_str}

## 用户输入
{query}

请分析用户意图并返回JSON格式结果。"""
        
        return prompt
    
    def _llm_classify(self, query: str, context: Dict[str, Any], explicit_agents: List[str]) -> IntentResult:
        """
        调用LLM进行意图分类。
        
        这是核心方法，处理以下场景：
        - 无@前缀：LLM判断意图
        - 多@前缀：LLM拆分任务
        """
        prompt = self._build_prompt(query, context, explicit_agents)
        
        try:
            # 调用LLM进行JSON输出
            response = self._llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                temperature=self.DEFAULT_TEMPERATURE,
                max_tokens=self.DEFAULT_MAX_TOKENS,
            )
            
            # 解析并验证结果
            return self._parse_response(response, query, explicit_agents)
            
        except Exception as e:
            print(f"[IntentClassifier] LLM分类失败: {e}，回退到关键词匹配")
            # LLM失败时回退到关键词匹配
            return self._fallback_classify(query, explicit_agents)
    
    def _parse_response(self, response: Dict[str, Any], query: str, explicit_agents: List[str]) -> IntentResult:
        """
        解析LLM返回的JSON响应。
        
        包含严格的字段验证和默认值处理。
        """
        try:
            primary_intent = response.get("primary_intent", "tutor")
            agent_tasks_raw = response.get("agent_tasks", [])
            execution_mode = response.get("execution_mode", "sequential")
            shared_topic = response.get("shared_topic", "")
            reasoning = response.get("reasoning", "")
            
            # LA-UI-001-FIX: 调试日志 — 打印原始LLM响应
            print(f"[IntentClassifier] LLM原始响应: primary_intent={primary_intent}, "
                  f"tasks_count={len(agent_tasks_raw)}, mode={execution_mode}")
            for i, tr in enumerate(agent_tasks_raw):
                print(f"[IntentClassifier]   task[{i}]: agent={tr.get('agent')}, "
                      f"sub_query={tr.get('sub_query', '')[:50]}, "
                      f"depends_on={tr.get('depends_on', [])}")
            
            # 验证并构建 AgentTask 列表
            agent_tasks = []
            for task_raw in agent_tasks_raw:
                agent = task_raw.get("agent", "tutor")
                # 验证agent名称合法性
                if agent not in ('tutor', 'quiz', 'coach', 'job'):
                    print(f"[IntentClassifier] 警告: 非法agent名称'{agent}'，兜底为tutor")
                    agent = 'tutor'  # 兜底
                
                task = AgentTask(
                    agent=agent,
                    task=task_raw.get("task", ""),
                    sub_query=task_raw.get("sub_query", ""),
                    priority=task_raw.get("priority", 1),
                    depends_on=task_raw.get("depends_on", []),
                    estimated_output=task_raw.get("estimated_output", "text"),
                )
                agent_tasks.append(task)
            
            # 如果没有解析到任务，创建默认任务
            if not agent_tasks:
                print(f"[IntentClassifier] 警告: LLM未返回agent_tasks，创建默认单任务")
                agent_tasks = [AgentTask(
                    agent=primary_intent if primary_intent != 'mixed' else 'tutor',
                    task=query,
                    sub_query=query,
                )]
            
            result = IntentResult(
                primary_intent=primary_intent,
                agent_tasks=agent_tasks,
                execution_mode=execution_mode,
                shared_topic=shared_topic,
                reasoning=reasoning,
            )
            
            # LA-UI-001-FIX: 调试日志 — 打印最终解析结果
            print(f"[IntentClassifier] 解析完成: primary={result.primary_intent}, "
                  f"tasks={len(result.agent_tasks)}, mode={result.execution_mode}")
            for t in result.agent_tasks:
                print(f"[IntentClassifier]   → {t.agent}: {t.sub_query[:60]} (dep={t.depends_on})")
            
            return result
            
        except Exception as e:
            print(f"[IntentClassifier] 解析响应失败: {e}，回退到关键词匹配")
            return self._fallback_classify(query, explicit_agents)
    
    def _fallback_classify(self, query: str, explicit_agents: List[str]) -> IntentResult:
        """
        回退策略：使用关键词匹配。
        
        当LLM调用失败时使用，保证系统可用性。
        """
        # 如果有显式Agent，使用第一个
        if explicit_agents:
            return IntentResult.single_agent(
                agent=explicit_agents[0],
                query=self._remove_at_mentions(query) or query,
                reason="LLM分类失败，回退到显式Agent",
            )
        
        # 否则使用 IntentRouter 的关键词匹配
        from core.intent_router import IntentRouter
        router = IntentRouter()
        intent, _ = router.classify_with_score(query)
        
        # 映射到标准Agent名
        intent_to_agent = {
            'quiz': 'quiz',
            'evaluate': 'coach',
            'job': 'job',
            'concept': 'tutor',
        }
        agent = intent_to_agent.get(intent, 'tutor')
        
        return IntentResult.single_agent(
            agent=agent,
            query=query,
            reason=f"LLM分类失败，回退到关键词匹配({intent})",
        )


# ========== 便捷函数 ==========

def classify_intent(query: str, context: Optional[Dict[str, Any]] = None) -> IntentResult:
    """
    便捷函数：快速进行意图分类。
    
    使用方式:
        result = classify_intent("出3道题")
        print(result.primary_intent)  # "quiz"
    """
    classifier = IntentClassifier()
    return classifier.classify(query, context)


# ========== 测试入口 ==========

if __name__ == "__main__":
    # 快速测试
    test_cases = [
        # 单Agent - 显式@
        ("@quiz 出3道题", {}, "quiz"),
        # 单Agent - 自动识别
        ("帮我评测一下RAG", {}, "coach"),
        # 多Agent - 复合意图
        ("评测RAG并出3道题", {}, "mixed"),
        # 多@前缀
        ("@tutor @quiz RAG是什么，出3道题", {}, "mixed"),
        # 无明确意图
        ("你好", {}, "tutor"),
    ]
    
    classifier = IntentClassifier()
    
    print("=" * 60)
    print("IntentClassifier 快速测试")
    print("=" * 60)
    
    for query, ctx, expected in test_cases:
        print(f"\n输入: {query}")
        try:
            result = classifier.classify(query, ctx)
            print(f"  primary_intent: {result.primary_intent} (期望: {expected})")
            print(f"  tasks: {len(result.agent_tasks)}")
            for t in result.agent_tasks:
                print(f"    - {t.agent}: {t.sub_query} (priority={t.priority})")
            print(f"  mode: {result.execution_mode}")
            print(f"  topic: {result.shared_topic}")
            match = "✓" if result.primary_intent == expected else "✗"
            print(f"  结果: {match}")
        except Exception as e:
            print(f"  错误: {e}")
    
    print("\n" + "=" * 60)
