#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
协调器 (Coordinator)
统一入口：意图路由 -> Agent 分发 -> 监控贯穿 -> 结果聚合
"""

import time
import re
from typing import Dict, Any, List, Optional

from core.intent_router import IntentRouter
from core.intent_classifier import IntentClassifier, IntentResult, AgentTask
from core.monitoring import get_monitor
from core.graph_store import GraphStore
from core.graph_education import (
    ConceptRetriever, SubgraphBuilder, ContextAssembler, ContextBudget,
    IRTEstimator, UserKnowledgeState, GraphContext, AnswerRecord
)
from core.hybrid_retriever import HybridRetriever

from agents.base_agent import BaseAgent
from agents.tutor_agent import TutorAgent
from agents.quiz_agent import QuizAgent
from agents.coach_agent import CoachAgent
from agents.headhunter_agent import HeadhunterAgent
from agents.message_bus import MessageBus, Message
from core.dialog_context import DialogContextManager


class Coordinator:
    """
    多 Agent 协调器。

    使用方式:
        coordinator = Coordinator()
        result = coordinator.handle("给我出几道化学题")
    """

    def __init__(self, collection_name: str = "learnanything_v1", top_k: int = 5, enabled_intents: List[str] = None, graph_store=None, vector_store=None, user_theta: Optional[float] = None):
        self.collection_name = collection_name
        self.top_k = top_k
        self.enabled_intents = enabled_intents or ["concept", "quiz", "job", "evaluate"]
        self.user_theta = user_theta

        self._intent_router = IntentRouter()
        # LA-UI-001: 新增 LLM 意图识别器，用于无@前缀时的智能Agent选择和多Agent任务拆分
        self._intent_classifier = IntentClassifier()
        # Agent 名称映射：IntentClassifier 输出名称 -> Coordinator 内部名称
        self._agent_name_map = {
            'tutor': 'concept',
            'quiz': 'quiz',
            'coach': 'evaluate',
            'job': 'job',
        }
        # 反向映射：Coordinator 内部名称 -> IntentClassifier 输出名称
        self._agent_name_reverse = {v: k for k, v in self._agent_name_map.items()}

        self._agents: Dict[str, BaseAgent] = {}

        # P0-INT-6: create message bus
        self._message_bus = MessageBus(enable_audit=True)

        # Lazy initialization of agents (pass message_bus)
        self._agents["concept"] = TutorAgent(collection_name=collection_name, top_k=top_k, message_bus=self._message_bus, user_theta=user_theta)
        self._agents["quiz"] = QuizAgent(collection_name=collection_name, top_k=top_k, message_bus=self._message_bus)
        self._agents["evaluate"] = CoachAgent(collection_name=collection_name, top_k=top_k, message_bus=self._message_bus)
        self._agents["job"] = HeadhunterAgent(message_bus=self._message_bus)

        # P0-INT-6: set up message bus subscriptions
        self._setup_message_bus()

        # P0-INT-1: lazy initialization of P0 modules (avoid immediate database connection)
        # P0-QUIZ-fix: support external shared GraphStore instance to avoid KuzuDB repeated connections / file locking
        # LA-051: support external vector_store for permission-aware data access
        self._graph_store = graph_store
        self._vector_store = vector_store
        self._retriever = None
        self._builder = None
        self._assembler = None
        self._irt = None
        
        # 阶段 1: 延迟初始化 DialogContextManager
        self._dialog_manager = None

    def handle(self, query: str, filters: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None, session_id: Optional[str] = None, user_theta: Optional[float] = None, agent_target: Optional[str] = None) -> Dict[str, Any]:
        """
        处理用户查询的统一入口。
        阶段 1: 新增对话上下文管理（会话持久化、指代解析、历史注入）。
        LA-044-B: 话题提取、切换检测、追踪。
        LA-044-#2: 支持传入 user_theta 进行个性化讲解。
        LA-UI-001: 集成 IntentClassifier，支持 @命令解析、LLM智能识别、多Agent任务拆分。

        Args:
            agent_target: 前端解析的显式Agent目标（可选），如 "tutor" | "quiz" | "coach" | "job"

        Returns:
            {
                "question": str,
                "text": str,
                "intent": {...},
                "agent": str,
                "result": dict,
                "monitoring": {...},
                "session_id": str,
                "multi_agent": bool,      # LA-UI-001: 是否为多Agent执行
                "execution_mode": str,    # LA-UI-001: sequential | parallel | mixed
            }
        """
        start_time = time.time()
        monitor = get_monitor()
        query_id = monitor.start_query(query, user_id=user_id, session_id=session_id)

        # 阶段 1 增强: 会话管理（含跨学科切换检测）
        if self._dialog_manager is None:
            self._dialog_manager = DialogContextManager()
        actual_user_id = user_id or "default"

        # LA-044-B: 详细的函数链打印
        print(f"\n{'='*60}")
        print(f"[Coordinator] 🔗 函数链: Coordinator.handle() ENTER")
        print(f"[Coordinator] 📥 输入数据链:")
        print(f"[Coordinator]    - user_id: {actual_user_id}")
        print(f"[Coordinator]    - query: '{query[:80]}...'")
        print(f"[Coordinator]    - session_id: {session_id}")
        print(f"[Coordinator]    - user_theta: {user_theta}")
        print(f"[Coordinator]    - collection_name: {self.collection_name}")
        print(f"[Coordinator]    - filters: {filters}")
        print(f"[Coordinator]    - agent_target: {agent_target}")
        print(f"{'='*60}")

        sid, session_info = self._dialog_manager.get_or_create_session(
            user_id=actual_user_id,
            subject_id=self.collection_name,
            session_id=session_id
        )

        # 使用增强版 build_context（含全局画像 + 学科隔离）
        dialog_context = self._dialog_manager.build_context(sid)
        turn_number = dialog_context.turn_number + 1 if dialog_context else 1

        # LA-044-B: 打印当前会话状态
        print(f"\n[Coordinator] 📊 当前会话状态:")
        print(f"[Coordinator]    - session_id: {sid}")
        print(f"[Coordinator]    - turn_number: {turn_number}")
        print(f"[Coordinator]    - current_topic: {getattr(dialog_context, 'current_topic', None)}")
        print(f"[Coordinator]    - history_len: {len(getattr(dialog_context, 'history', []))}")
        print(f"[Coordinator]    - subject: {getattr(dialog_context, 'subject', None)}")

        # ==================== LA-UI-001: 意图识别（IntentClassifier）====================
        # 构建上下文信息供 IntentClassifier 使用
        classifier_context = {
            "current_topic": getattr(dialog_context, 'current_topic', None),
            "last_agent": getattr(dialog_context, 'last_agent', None),
            "turn_count": turn_number,
            "selected_concept": getattr(dialog_context, 'selected_concept', None),
        }

        # 根据是否有显式 agent_target 决定意图识别路径
        if agent_target:
            # 用户通过前端标签栏或@命令显式指定了Agent
            print(f"[Coordinator] LA-UI-001: 用户显式指定 agent_target={agent_target}")
            intent_result = IntentResult.single_agent(
                agent=agent_target,
                query=query,
                reason=f"用户显式指定了 {agent_target} Agent",
            )
        else:
            # 无显式指定，使用 IntentClassifier 进行智能识别
            print(f"[Coordinator] LA-UI-001: 调用 IntentClassifier 进行意图识别...")
            intent_result = self._intent_classifier.classify(query, context=classifier_context)
            print(f"[Coordinator] LA-UI-001: 识别结果 primary_intent={intent_result.primary_intent}, "
                  f"tasks={len(intent_result.agent_tasks)}, mode={intent_result.execution_mode}")

        # 将 IntentClassifier 的 agent 名称映射为 Coordinator 内部名称
        mapped_tasks = self._map_agent_names(intent_result.agent_tasks)
        intent_result.agent_tasks = mapped_tasks

        # 构建 intent_info（兼容旧格式）
        is_multi_agent = len(intent_result.agent_tasks) > 1
        primary_internal_agent = self._agent_name_map.get(
            intent_result.primary_intent, intent_result.primary_intent
        )
        intent_info = {
            "original": primary_internal_agent,
            "resolved": primary_internal_agent,
            "confidence": 1.0 if agent_target else 0.8,
            "fallback": False,
            "primary_intent": intent_result.primary_intent,
            "execution_mode": intent_result.execution_mode,
            "shared_topic": intent_result.shared_topic,
            "reasoning": intent_result.reasoning,
            "is_multi_agent": is_multi_agent,
            "task_count": len(intent_result.agent_tasks),
        }

        print(f"\n[Coordinator] 🎯 意图路由结果:")
        print(f"[Coordinator]    - primary_intent: {intent_result.primary_intent}")
        print(f"[Coordinator]    - resolved_agent: {primary_internal_agent}")
        print(f"[Coordinator]    - is_multi_agent: {is_multi_agent}")
        print(f"[Coordinator]    - execution_mode: {intent_result.execution_mode}")
        print(f"[Coordinator]    - task_count: {len(intent_result.agent_tasks)}")
        for t in intent_result.agent_tasks:
            print(f"[Coordinator]      - {t.agent}: {t.sub_query} (priority={t.priority}, depends_on={t.depends_on})")

        monitor.log_stage(
            query_id=query_id,
            stage_name="route",
            agent_name="coordinator",
            metrics=intent_info,
            duration_ms=0,
            input_summary=query[:100],
            output_summary=f"resolved={primary_internal_agent}, tasks={len(intent_result.agent_tasks)}, mode={intent_result.execution_mode}",
        )

        # 阶段 1: 指代解析
        resolved_query = query
        if dialog_context:
            resolved_query = self._dialog_manager.resolve_references(query, dialog_context)
            if resolved_query != query:
                print(f"[Coordinator] 阶段1: 指代解析 '{query}' -> '{resolved_query}'")

        # 阶段 1: 保存用户消息
        self._dialog_manager.save_message(
            session_id=sid,
            turn_number=turn_number,
            role="user",
            content=query,
            intent=primary_internal_agent
        )

        # LA-044-B: 话题切换检测
        is_topic_switch, switch_target = self._dialog_manager.detect_topic_switch(query)
        if is_topic_switch:
            print(f"[Coordinator] LA-044-B: 用户意图切换话题 -> '{switch_target}'")
            if switch_target:
                self._dialog_manager.update_session_topic(sid, switch_target, turn_number)
                dialog_context = self._dialog_manager.build_context(sid)

        # ==================== LA-UI-001: 多Agent执行调度 ====================
        # 根据执行模式调度Agent
        if is_multi_agent:
            print(f"[Coordinator] LA-UI-001: 多Agent执行，模式={intent_result.execution_mode}")
            if intent_result.execution_mode == "parallel":
                execution_result = self._execute_parallel(
                    intent_result, resolved_query, dialog_context, filters, user_theta, sid, turn_number
                )
            else:
                # 默认串行（sequential 或 mixed 都先按串行实现）
                execution_result = self._execute_sequential(
                    intent_result, resolved_query, dialog_context, filters, user_theta, sid, turn_number
                )
        else:
            # 单Agent，保持原有逻辑
            execution_result = self._execute_single(
                intent_result.agent_tasks[0], resolved_query, dialog_context, filters, user_theta, sid, turn_number
            )

        total_duration_ms = (time.time() - start_time) * 1000

        # 阶段 1: 保存 Agent 回复（单Agent已在 _execute_single 中保存，多Agent在各自执行方法中保存）
        agent_result = execution_result.get("result", {})

        # LA-050-C: Agent 标准化输出包装
        from agents.message_formats import wrap_agent_output
        agent_name = execution_result.get("agent", primary_internal_agent)
        standardized_result = wrap_agent_output(agent_name, agent_result, query)
        print(f"[Coordinator] LA-050-C: Agent 输出已标准化 | agent={agent_name} | content_type={standardized_result['content_type']}")

        # LA-044-B: 从 Agent 回答中提取话题并更新会话
        answer_text = agent_result.get("text", "") if isinstance(agent_result, dict) else str(agent_result)
        concept_names = []
        if isinstance(agent_result, dict) and agent_result.get("metadata"):
            concept_names = agent_result.get("metadata", {}).get("concepts", [])

        if is_topic_switch and switch_target:
            extracted_topic = switch_target
            print(f"[Coordinator] LA-044-B: 使用话题切换目标: '{extracted_topic}'")
        else:
            extracted_topic = self._dialog_manager.extract_topic(
                answer_text=answer_text,
                concept_names=concept_names,
                query=query
            )

        if extracted_topic:
            self._dialog_manager.update_session_topic(sid, extracted_topic, turn_number)

        # 阶段 1: 更新会话状态
        self._dialog_manager.update_session(sid, turn_count=turn_number)

        # 结束监控
        final_metrics = {
            "agent": agent_name,
            "resolved_intent": primary_internal_agent,
            "original_intent": primary_internal_agent,
            "fallback": False,
            "multi_agent": is_multi_agent,
            "execution_mode": intent_result.execution_mode,
        }
        monitor.end_query(query_id, final_metrics, status="completed")

        # P0-INT-1: 对 evaluate 意图，在 CoachAgent 返回后附加 IRT 能力估计
        if primary_internal_agent == "evaluate" and isinstance(agent_result, dict):
            try:
                print(f"[Coordinator] P0-INT-1: 对 evaluate 结果进行 IRT 能力估计")
                irt = self._get_irt()
                details = agent_result.get("details", agent_result.get("result", {}).get("details", []))
                if details:
                    answer_records = []
                    for detail in details:
                        record = AnswerRecord(
                            question_id=str(detail.get("id", "")),
                            user_answer=detail.get("user_answer", ""),
                            correct_answer=detail.get("correct_answer", ""),
                            is_correct=detail.get("is_correct", False),
                            score=detail.get("score", 0),
                            max_score=detail.get("max_score", 0),
                            response_time=30,
                            primary_concepts=[detail.get("topic", "")],
                        )
                        answer_records.append(record)

                    theta = 0.0
                    for record in answer_records:
                        theta = irt.update_theta(theta, record.is_correct, a=1.0, b=0.0, c=0.25)

                    print(f"[Coordinator] IRT 能力估计结果: theta={theta:.2f}")
                    agent_result["irt_theta"] = round(theta, 2)
            except Exception as e:
                print(f"[Coordinator] IRT 能力估计失败: {e}")

        # LA-044-B: 详细的函数链退出打印
        result_text = answer_text[:100] if answer_text else ""
        print(f"\n{'='*60}")
        print(f"[Coordinator] 🔗 函数链: Coordinator.handle() EXIT")
        print(f"[Coordinator] 📤 输出数据链:")
        print(f"[Coordinator]    - session_id: {sid}")
        print(f"[Coordinator]    - agent: {agent_name}")
        print(f"[Coordinator]    - intent: {primary_internal_agent}")
        print(f"[Coordinator]    - multi_agent: {is_multi_agent}")
        print(f"[Coordinator]    - answer_len: {len(answer_text)}")
        print(f"[Coordinator]    - answer_preview: '{result_text}...'")
        print(f"[Coordinator]    - duration_ms: {round(total_duration_ms, 2)}")
        print(f"[Coordinator]    - topic_chain: {self._dialog_manager.get_topic_chain(sid)[:5]}")
        print(f"{'='*60}\n")

        return {
            "question": query,
            "text": answer_text,
            "intent": intent_info,
            "agent": agent_name,
            "result": agent_result,
            "standardized": standardized_result,
            "monitoring": {
                "query_id": query_id,
                "total_duration_ms": round(total_duration_ms, 2),
            },
            "session_id": sid,
            "multi_agent": is_multi_agent,
            "execution_mode": intent_result.execution_mode,
            "agent_tasks": [
                {
                    "agent": t.agent,
                    "task": t.task,
                    "sub_query": t.sub_query,
                    "priority": t.priority,
                }
                for t in intent_result.agent_tasks
            ],
        }

    # ==================== LA-UI-001: Agent名称映射 ====================

    def _map_agent_names(self, tasks: List[AgentTask]) -> List[AgentTask]:
        """
        将 IntentClassifier 输出的 agent 名称映射为 Coordinator 内部名称。

        IntentClassifier 使用: tutor | quiz | coach | job
        Coordinator 内部使用: concept | quiz | evaluate | job
        """
        mapped = []
        for task in tasks:
            internal_name = self._agent_name_map.get(task.agent, task.agent)
            # 创建新的 AgentTask，替换 agent 字段
            mapped_task = AgentTask(
                agent=internal_name,
                task=task.task,
                sub_query=task.sub_query,
                priority=task.priority,
                depends_on=[self._agent_name_map.get(d, d) for d in task.depends_on],
                estimated_output=task.estimated_output,
            )
            mapped.append(mapped_task)
        return mapped

    # ==================== LA-UI-001: 单Agent执行（提取原有逻辑）====================

    def _execute_single(self, task: AgentTask, resolved_query: str,
                        dialog_context, filters, user_theta,
                        sid: str, turn_number: int) -> Dict[str, Any]:
        """
        执行单Agent任务，保持原有图谱上下文组装逻辑不变。

        这是 LA-UI-001 之前 handle() 方法的核心执行逻辑，
        被提取出来供单Agent和多Agent串行执行复用。
        """
        agent_name = task.agent
        agent = self._agents.get(agent_name)

        # Agent 不存在时回退到 concept
        if agent is None:
            print(f"[Coordinator] LA-UI-001: Agent '{agent_name}' 未找到，回退到 concept")
            agent_name = "concept"
            agent = self._agents["concept"]

        # 使用任务的 sub_query 作为实际查询（已从用户输入中提取）
        actual_query = task.sub_query or resolved_query

        # P0-INT-1: 对 quiz / concept / evaluate 意图使用图谱教育模块组装上下文
        if agent_name in ("quiz", "concept", "evaluate"):
            try:
                print(f"[Coordinator] P0-INT-1: 使用图谱教育模块为 {agent_name} 意图组装上下文")
                graph_store = self._get_graph_store()
                retriever = self._get_retriever(graph_store)

                # 提取主题
                topic = self._extract_topic_from_query(actual_query)
                print(f"[Coordinator] 提取主题: {topic}")
                seed_concepts = retriever.resolve([topic])

                if seed_concepts:
                    print(f"[Coordinator] 解析到 {len(seed_concepts)} 个种子概念")
                    builder = self._get_builder(graph_store)
                    subgraph = builder.build(seed_concepts, mode="auto", max_depth=2, max_nodes=15)
                    print(f"[Coordinator] 构建子图: {subgraph.node_count} 节点, {subgraph.edge_count} 边")

                    assembler = self._get_assembler()
                    budget = ContextBudget(max_tokens=2000, max_nodes=15)
                    graph_context = assembler.assemble(subgraph, budget=budget)
                    print(f"[Coordinator] 组装上下文: {graph_context.token_count} tokens")

                    agent_result = agent.handle(actual_query, context=dialog_context, filters=filters,
                                                graph_context=graph_context, user_theta=user_theta)
                else:
                    # LA-040-P2-QUIZ-FIX: seed_concepts 为空时，尝试文本检索兜底
                    print(f"[Coordinator] LA-040-P2-QUIZ-FIX: 无匹配概念，尝试文本检索兜底")
                    graph_context = self._build_fallback_context(graph_store, topic,
                                                                  budget=ContextBudget(max_tokens=2000, max_nodes=15))
                    if graph_context and graph_context.text:
                        print(f"[Coordinator] LA-040-P2-QUIZ-FIX: 文本检索兜底成功，{graph_context.token_count} tokens")
                        agent_result = agent.handle(actual_query, context=dialog_context, filters=filters,
                                                    graph_context=graph_context, user_theta=user_theta)
                    else:
                        print(f"[Coordinator] 文本检索兜底也失败，回退到旧方式")
                        agent_result = agent.handle(actual_query, context=dialog_context, filters=filters,
                                                    user_theta=user_theta)
            except Exception as e:
                print(f"[Coordinator] P0 模块调用失败，回退到旧模式: {e}")
                import traceback
                traceback.print_exc()
                agent_result = agent.handle(actual_query, context=dialog_context, filters=filters, user_theta=user_theta)
        else:
            # 非 quiz/concept/evaluate 意图，原方式执行
            agent_result = agent.handle(actual_query, context=dialog_context, filters=filters, user_theta=user_theta)

        # 保存 Agent 回复到对话历史
        agent_metadata = {}
        if isinstance(agent_result, dict) and agent_result.get("metadata"):
            meta = agent_result["metadata"]
            if meta.get("sources"):
                agent_metadata["sources"] = meta["sources"]
            if meta.get("media"):
                agent_metadata["media"] = meta["media"]

        self._dialog_manager.save_message(
            session_id=sid,
            turn_number=turn_number,
            role="agent",
            content=agent_result.get("text", "") if isinstance(agent_result, dict) else str(agent_result),
            agent_name=agent.agent_name,
            intent=agent_name,
            metadata=agent_metadata if agent_metadata else None
        )

        return {
            "agent": agent.agent_name,
            "result": agent_result,
        }

    # ==================== LA-UI-001: 多Agent串行执行 ====================

    def _execute_sequential(self, intent_result: IntentResult, resolved_query: str,
                            dialog_context, filters, user_theta,
                            sid: str, turn_number: int) -> Dict[str, Any]:
        """
        串行执行多Agent任务：按优先级依次调用Agent，中间结果传递给后续Agent。

        适用场景：任务有先后依赖，如"先评测再出题"。
        执行逻辑：
          1. 按 priority 排序任务
          2. 依次执行每个任务
          3. 将前置 Agent 的结果存入 shared_results，供后续 Agent 使用
          4. 最终返回最后一个 Agent 的结果（或聚合结果）
        """
        print(f"[Coordinator] LA-UI-001: 开始串行执行 {len(intent_result.agent_tasks)} 个Agent任务")

        # 按优先级排序（priority 越小优先级越高）
        sorted_tasks = sorted(intent_result.agent_tasks, key=lambda t: t.priority)

        # 存储各Agent的执行结果，供后续依赖的Agent使用
        shared_results: Dict[str, Dict[str, Any]] = {}
        last_result: Dict[str, Any] = {}

        for i, task in enumerate(sorted_tasks):
            print(f"[Coordinator] LA-UI-001: 串行执行 Step {i+1}/{len(sorted_tasks)}: agent={task.agent}, task={task.task}")

            # 如果有依赖，检查前置Agent是否已完成
            if task.depends_on:
                for dep in task.depends_on:
                    if dep not in shared_results:
                        print(f"[Coordinator] LA-UI-001: 警告 - 依赖的Agent '{dep}' 尚未执行")

            # 构建传递给当前Agent的上下文（包含前置Agent结果）
            task_context = dialog_context
            if task.depends_on and shared_results:
                # 将前置结果注入 sub_query 或 metadata
                dep_summaries = []
                for dep in task.depends_on:
                    if dep in shared_results:
                        dep_res = shared_results[dep]
                        dep_text = dep_res.get("text", "") if isinstance(dep_res, dict) else str(dep_res)
                        dep_summaries.append(f"[{dep}] 结果: {dep_text[:200]}...")

                if dep_summaries:
                    # 修改 sub_query，追加前置结果摘要
                    enhanced_sub_query = task.sub_query + "\n\n【前置分析结果】\n" + "\n".join(dep_summaries)
                    # 创建临时任务副本（不改变原始任务）
                    task = AgentTask(
                        agent=task.agent,
                        task=task.task,
                        sub_query=enhanced_sub_query,
                        priority=task.priority,
                        depends_on=task.depends_on,
                        estimated_output=task.estimated_output,
                    )
                    print(f"[Coordinator] LA-UI-001: 已注入前置结果到 sub_query")

            # 执行单Agent任务
            single_result = self._execute_single(task, resolved_query, task_context,
                                                  filters, user_theta, sid, turn_number)

            # 保存结果到共享池
            shared_results[task.agent] = single_result.get("result", {})
            last_result = single_result

            print(f"[Coordinator] LA-UI-001: Step {i+1} 完成: agent={single_result.get('agent')}")

        # 串行执行返回最后一个Agent的结果
        # TODO: 未来可扩展为返回聚合结果（所有Agent的结果列表）
        print(f"[Coordinator] LA-UI-001: 串行执行全部完成，返回最后结果 from {last_result.get('agent')}")
        return last_result

    # ==================== LA-UI-001: 多Agent并行执行 ====================

    def _execute_parallel(self, intent_result: IntentResult, resolved_query: str,
                          dialog_context, filters, user_theta,
                          sid: str, turn_number: int) -> Dict[str, Any]:
        """
        并行执行多Agent任务：同时调用多个无依赖关系的Agent。

        适用场景：任务相互独立，如"讲解概念同时出题"。
        执行逻辑：
          1. 筛选出无依赖的任务（priority 相同的任务）
          2. 使用线程池并发执行
          3. 聚合所有结果

        当前实现：使用 ThreadPoolExecutor 并发执行，
        返回第一个成功结果（简化版）。完整版应返回聚合结果。
        """
        print(f"[Coordinator] LA-UI-001: 开始并行执行 {len(intent_result.agent_tasks)} 个Agent任务")

        from concurrent.futures import ThreadPoolExecutor, as_completed

        # 筛选无依赖的任务（当前简化：全部并行）
        parallel_tasks = [t for t in intent_result.agent_tasks if not t.depends_on]
        if not parallel_tasks:
            # 所有任务都有依赖，回退到串行
            print(f"[Coordinator] LA-UI-001: 所有任务都有依赖，回退到串行执行")
            return self._execute_sequential(intent_result, resolved_query, dialog_context,
                                            filters, user_theta, sid, turn_number)

        results: Dict[str, Dict[str, Any]] = {}

        # 限制最大并行数（避免同时调用过多LLM）
        max_workers = min(len(parallel_tasks), 2)
        print(f"[Coordinator] LA-UI-001: 线程池大小={max_workers}")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_task = {}
            for task in parallel_tasks:
                future = executor.submit(
                    self._execute_single, task, resolved_query, dialog_context,
                    filters, user_theta, sid, turn_number
                )
                future_to_task[future] = task

            # 收集结果
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result()
                    results[task.agent] = result
                    print(f"[Coordinator] LA-UI-001: 并行任务完成: agent={task.agent}")
                except Exception as e:
                    print(f"[Coordinator] LA-UI-001: 并行任务失败: agent={task.agent}, error={e}")
                    results[task.agent] = {
                        "agent": task.agent,
                        "result": {"text": f"执行出错: {e}"},
                    }

        # 并行执行返回第一个成功的结果（简化版）
        # TODO: 未来应返回所有结果的聚合
        if results:
            first_agent = list(results.keys())[0]
            print(f"[Coordinator] LA-UI-001: 并行执行完成，返回首个结果 from {first_agent}")
            return results[first_agent]
        else:
            return {"agent": "unknown", "result": {"text": "所有并行任务均失败"}}

    # ==================== P0-INT-1: 辅助方法 ====================

    def _get_graph_store(self) -> GraphStore:
        """延迟初始化 GraphStore"""
        if self._graph_store is None:
            print(f"[Coordinator] 延迟初始化 GraphStore: {self.collection_name}")
            self._graph_store = GraphStore(self.collection_name)
        return self._graph_store

    def _get_retriever(self, graph_store: GraphStore) -> ConceptRetriever:
        """延迟初始化 ConceptRetriever，传入 HybridRetriever 作为 vector_store"""
        if self._retriever is None:
            print(f"[Coordinator] 延迟初始化 ConceptRetriever")
            # LA-051: 使用外部传入的 vector_store（权限感知）或创建默认的
            if self._vector_store is not None:
                vector_store = self._vector_store
                print(f"[Coordinator] 使用外部传入的 vector_store")
            else:
                vector_store = HybridRetriever(graph_store.collection_name)
                print(f"[Coordinator] 使用默认 vector_store")
            self._retriever = ConceptRetriever(
                graph_store=graph_store,
                vector_store=vector_store,
            )
        return self._retriever

    def _get_builder(self, graph_store: GraphStore) -> SubgraphBuilder:
        """延迟初始化 SubgraphBuilder"""
        if self._builder is None:
            print(f"[Coordinator] 延迟初始化 SubgraphBuilder")
            self._builder = SubgraphBuilder(graph_store=graph_store)
        return self._builder

    def _get_assembler(self) -> ContextAssembler:
        """延迟初始化 ContextAssembler"""
        if self._assembler is None:
            print(f"[Coordinator] 延迟初始化 ContextAssembler")
            self._assembler = ContextAssembler()
        return self._assembler

    def _get_irt(self) -> IRTEstimator:
        """延迟初始化 IRTEstimator"""
        if self._irt is None:
            print(f"[Coordinator] 延迟初始化 IRTEstimator")
            self._irt = IRTEstimator(calibration_stage=1)
        return self._irt

    # LA-040-P2-QUIZ-FIX: 当 ConceptRetriever 无法解析概念时，用 HybridRetriever 做文本检索兜底
    def _build_fallback_context(self, graph_store: GraphStore, topic: str, budget: ContextBudget):
        """
        文本检索兜底：当图谱中没有匹配的概念节点时，
        使用 HybridRetriever 检索与主题相关的文本片段，组装为简化版 GraphContext。
        """
        from core.graph_education.types import GraphContext, Subgraph, ConceptNode
        from core.graph_education.context_assembler import ContextAssembler

        try:
            print(f"[Coordinator] _build_fallback_context: 使用 HybridRetriever 检索主题 '{topic}'")
            # LA-051: 使用外部传入的 vector_store（权限感知）或创建默认的
            if self._vector_store is not None:
                vector_store = self._vector_store
                print(f"[Coordinator] _build_fallback_context: 使用外部传入的 vector_store")
            else:
                vector_store = HybridRetriever(graph_store.collection_name)
            results = vector_store.query(topic, n_results=budget.max_nodes)

            if not results:
                print(f"[Coordinator] _build_fallback_context: 无检索结果")
                return None

            # 将检索结果组装为文本上下文
            sections = []
            concept_nodes = []
            for i, doc in enumerate(results):
                text = doc.get("text", "")
                metadata = doc.get("metadata", {})
                if not text.strip():
                    continue
                source = metadata.get("source", "")
                heading = metadata.get("heading_path", "")
                # 构建引用标注
                ref_parts = []
                if source:
                    ref_parts.append(source)
                if heading:
                    ref_parts.append(heading)
                ref = f"[{' | '.join(ref_parts)}]" if ref_parts else f"[片段{i+1}]"
                sections.append(f"{ref}\n{text.strip()}")

                # 同时创建一个简化 ConceptNode（用于 subgraph，让 QuizAgent 能提取 concept_names）
                # 从文本前 20 个字符作为临时概念名
                pseudo_name = text.strip()[:20] + "..." if len(text.strip()) > 20 else text.strip()
                concept_nodes.append(ConceptNode(
                    canonical_id=f"fallback_{i}",
                    name=pseudo_name,
                    concept_type="fallback",
                    description=text.strip()[:200],
                ))

            full_text = "\n\n---\n\n".join(sections)
            # 包装为 GraphContext 格式（与正常 P0 上下文一致）
            assembled_text = f"## 相关知识片段\n\n{full_text}"

            # 构建简化 Subgraph
            subgraph = Subgraph(
                nodes=concept_nodes,
                edges=[],
                seed_concepts=[],
                build_mode="fallback"
            )

            token_count = len(assembled_text) * 1  # 粗略估算

            print(f"[Coordinator] _build_fallback_context: 组装完成，{len(sections)} 个片段，约 {token_count} tokens")
            return GraphContext(
                text=assembled_text,
                token_count=token_count,
                subgraph=subgraph,
                sections={"sources": full_text}
            )
        except Exception as e:
            print(f"[Coordinator] _build_fallback_context 失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _extract_topic_from_query(self, query: str) -> str:
        """
        从查询中提取主题关键词。

        支持模式：
          - "give me N questions on {topic}" -> {topic}
          - "evaluate my {topic} level" -> {topic}
          - "给我出 N 道 {topic} 题" -> {topic}
          - "关于 {topic} 的 {num} 道 {action}" -> {topic}
        """
        import re
        q = query.strip().lower()

        # 模式 1: "... on/about/关于 {topic}"
        m = re.search(r'(?:on|about|关于)\s+(.+?)(?:\s*$|\s+(?:的|question|题|quiz|test|exam|level))', q, re.IGNORECASE)
        if m:
            return m.group(1).strip()

        # 模式 2: "evaluate my {topic} level"
        m = re.search(r'evaluate\s+my\s+(.+?)\s+level', q, re.IGNORECASE)
        if m:
            return m.group(1).strip()

        # 模式 3: 传统关键词过滤（去除常见出题/请求词）
        stop_words = [
            "出题", "题目", "面试题", "练习题", "测试题", "考题", "试题",
            "考我", "测试我", "考一下", "测一下", "做道题", "来道题",
            "给我", "出一道", "来一道", "来几题", "出几题", "给我出题",
            "关于", "的", "一下", "几道", "几题", "请", "帮我",
            "give me", "questions on", "question on", "quiz on",
            "exam on", "test on", "evaluate my", "level",
            "给我出", "帮我出",
        ]
        topic = query
        for w in stop_words:
            topic = re.sub(r'\b' + re.escape(w) + r'\b', "", topic, flags=re.IGNORECASE)
        topic = re.sub(r'\b\d+\s*(?:道|题|questions?|s)\b', "", topic, flags=re.IGNORECASE)  # 去除 "5 道" / "5 questions" / "5 s"
        topic = " ".join(topic.split()).strip()

        if not topic:
            topic = query
        return topic

    # ==================== P0-INT-6: 消息总线 ====================

    def _setup_message_bus(self):
        """设置消息总线订阅关系"""
        bus = self._message_bus

        # CoachAgent 订阅 quiz 主题（接收出题事件，加入待评测队列）
        coach = self._agents.get("evaluate")
        if coach and hasattr(coach, "on_quiz_generated"):
            bus.subscribe("quiz", "CoachAgent", coach.on_quiz_generated)

        # QuizAgent 订阅 user_state 主题（接收能力更新，调整出题难度）
        quiz = self._agents.get("quiz")
        if quiz and hasattr(quiz, "on_ability_updated"):
            bus.subscribe("user_state", "QuizAgent", quiz.on_ability_updated)

        # TutorAgent 订阅 weak_area 主题（接收薄弱点检测，调整讲解策略）
        tutor = self._agents.get("concept")
        if tutor and hasattr(tutor, "on_weak_area_detected"):
            bus.subscribe("weak_area", "TutorAgent", tutor.on_weak_area_detected)

        print(f"[Coordinator] P0-INT-6: 消息总线订阅设置完成")
        print(f"[Coordinator] 当前订阅: {bus.get_stats()}")

    def get_bus_stats(self) -> Dict[str, Any]:
        """获取消息总线统计（用于测试和调试）"""
        return self._message_bus.get_stats()

    def get_bus_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取消息审计日志"""
        return self._message_bus.get_audit_log(limit)
