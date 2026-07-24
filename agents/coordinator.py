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

    def __init__(self, collection_name: str = "learnanything_v1", top_k: int = 5, enabled_intents: List[str] = None, graph_store=None, user_theta: Optional[float] = None):
        self.collection_name = collection_name
        self.top_k = top_k
        self.enabled_intents = enabled_intents or ["concept", "quiz", "job", "evaluate"]
        self.user_theta = user_theta

        self._intent_router = IntentRouter()
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
        self._graph_store = graph_store
        self._retriever = None
        self._builder = None
        self._assembler = None
        self._irt = None
        
        # 阶段 1: 延迟初始化 DialogContextManager
        self._dialog_manager = None

    def handle(self, query: str, filters: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None, session_id: Optional[str] = None, user_theta: Optional[float] = None) -> Dict[str, Any]:
        """
        处理用户查询的统一入口。
        阶段 1: 新增对话上下文管理（会话持久化、指代解析、历史注入）。
        LA-044-B: 话题提取、切换检测、追踪。
        LA-044-#2: 支持传入 user_theta 进行个性化讲解。

        Returns:
            {
                "question": str,
                "text": str,
                "intent": {...},
                "agent": str,
                "result": dict,
                "monitoring": {...},
                "session_id": str,  # 阶段 1 新增
            }
        """
        start_time = time.time()
        monitor = get_monitor()
        query_id = monitor.start_query(query, user_id=user_id, session_id=session_id)

        # 阶段 1 增强: 会话管理（含跨学科切换检测）
        if self._dialog_manager is None:
            self._dialog_manager = DialogContextManager()
        actual_user_id = user_id or "anonymous"
        
        # LA-044-B: 详细的函数链打印
        print(f"\n{'='*60}")
        print(f"[Coordinator] 🔗 函数链: Coordinator.handle() ENTER")
        print(f"[Coordinator] 📥 输入数据链:")
        print(f"[Coordinator]    - user_id: {actual_user_id}")
        print(f"[Coordinator]    - query: '{query[:80]}...'")
        print(f"[Coordinator]    - session_id: {session_id}")
        print(f"[Coordinator]    - collection_name: {self.collection_name}")
        print(f"[Coordinator]    - filters: {filters}")
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

        # 意图路由
        resolved_intent, original_intent = self._intent_router.route(query, self.enabled_intents)
        confidence = 1.0 if self._intent_router.last_match_detail.get("matched_keyword") else 0.0
        is_fallback = resolved_intent != original_intent

        intent_info = {
            "original": original_intent,
            "resolved": resolved_intent,
            "confidence": confidence,
            "fallback": is_fallback,
        }
        
        print(f"\n[Coordinator] 🎯 意图路由结果:")
        print(f"[Coordinator]    - original: {original_intent}")
        print(f"[Coordinator]    - resolved: {resolved_intent}")
        print(f"[Coordinator]    - is_fallback: {is_fallback}")

        monitor.log_stage(
            query_id=query_id,
            stage_name="route",
            agent_name="coordinator",
            metrics=intent_info,
            duration_ms=0,
            input_summary=query[:100],
            output_summary=f"resolved={resolved_intent}",
        )

        # Agent 分发
        agent = self._agents.get(resolved_intent)
        if agent is None:
            # 未实现的 Agent，回退到 concept
            resolved_intent = "concept"
            intent_info["resolved"] = "concept"
            intent_info["fallback"] = True
            agent = self._agents["concept"]

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
            intent=resolved_intent
        )

        # LA-044-B: 话题切换检测
        is_topic_switch, switch_target = self._dialog_manager.detect_topic_switch(query)
        if is_topic_switch:
            print(f"[Coordinator] LA-044-B: 用户意图切换话题 -> '{switch_target}'")
            # 强制更新 current_topic 为切换目标（如果有）
            if switch_target:
                self._dialog_manager.update_session_topic(sid, switch_target, turn_number)
                # 重新加载 dialog_context 以使用新话题
                dialog_context = self._dialog_manager.build_context(sid)

        # P0-INT-1: 对 quiz / concept 意图使用图谱教育模块组装上下文
        if resolved_intent in ("quiz", "concept"):
            try:
                print(f"[Coordinator] P0-INT-1: 使用图谱教育模块为 {resolved_intent} 意图组装上下文")
                graph_store = self._get_graph_store()
                retriever = self._get_retriever(graph_store)

                # 提取主题
                topic = self._extract_topic_from_query(resolved_query)
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

                    # 阶段 1: 传递 context 给 Agent
                    agent_result = agent.handle(resolved_query, context=dialog_context, filters=filters, graph_context=graph_context, user_theta=user_theta)
                else:
                    print(f"[Coordinator] 无匹配概念，回退到旧方式")
                    agent_result = agent.handle(resolved_query, context=dialog_context, filters=filters, user_theta=user_theta)
            except Exception as e:
                print(f"[Coordinator] P0 模块调用失败，回退到旧模式: {e}")
                import traceback
                traceback.print_exc()
                agent_result = agent.handle(resolved_query, context=dialog_context, filters=filters, user_theta=user_theta)
        else:
            # 非 quiz/concept 意图，原方式执行（但传递 context）
            agent_result = agent.handle(resolved_query, context=dialog_context, filters=filters, user_theta=user_theta)

        total_duration_ms = (time.time() - start_time) * 1000

        # 阶段 1: 保存 Agent 回复
        # LA-044: 将 sources 和 media 存入 metadata
        agent_metadata = {"query_id": query_id}
        if agent_result and isinstance(agent_result, dict):
            if agent_result.get("metadata"):
                meta = agent_result["metadata"]
                if meta.get("sources"):
                    agent_metadata["sources"] = meta["sources"]
                if meta.get("media"):
                    agent_metadata["media"] = meta["media"]
        
        self._dialog_manager.save_message(
            session_id=sid,
            turn_number=turn_number,
            role="agent",
            content=agent_result.get("text", ""),
            agent_name=agent.agent_name,
            intent=resolved_intent,
            metadata=agent_metadata
        )

        # LA-044-B: 从 Agent 回答中提取话题并更新会话
        answer_text = agent_result.get("text", "")
        concept_names = []
        if hasattr(agent_result, 'get') and agent_result.get("metadata"):
            concept_names = agent_result.get("metadata", {}).get("concepts", [])
        
        # 如果检测到话题切换，使用切换目标作为话题
        if is_topic_switch and switch_target:
            extracted_topic = switch_target
            print(f"[Coordinator] LA-044-B: 使用话题切换目标: '{extracted_topic}'")
        else:
            # 从回答中提取话题
            extracted_topic = self._dialog_manager.extract_topic(
                answer_text=answer_text,
                concept_names=concept_names,
                query=query
            )
        
        if extracted_topic:
            self._dialog_manager.update_session_topic(sid, extracted_topic, turn_number)
        else:
            # 如果没有提取到话题，保持原有 topic（如果有的话）
            pass

        # 阶段 1: 更新会话状态（turn_count, updated_at）
        self._dialog_manager.update_session(
            sid,
            turn_count=turn_number,
        )

        # 结束监控
        final_metrics = {
            "agent": agent.agent_name,
            "resolved_intent": resolved_intent,
            "original_intent": original_intent,
            "fallback": is_fallback,
        }
        monitor.end_query(query_id, final_metrics, status="completed")

        # P0-INT-1: 对 evaluate 意图，在 CoachAgent 返回后附加 IRT 能力估计
        if resolved_intent == "evaluate" and "result" in locals() and agent_result:
            try:
                print(f"[Coordinator] P0-INT-1: 对 evaluate 结果进行 IRT 能力估计")
                irt = self._get_irt()
                questions = agent_result.get("questions", [])
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
                    if isinstance(agent_result, dict):
                        agent_result["irt_theta"] = round(theta, 2)
            except Exception as e:
                print(f"[Coordinator] IRT 能力估计失败: {e}")

        # LA-044-B: 详细的函数链退出打印
        result_text = agent_result.get("text", "")[:100] if agent_result else ""
        print(f"\n{'='*60}")
        print(f"[Coordinator] 🔗 函数链: Coordinator.handle() EXIT")
        print(f"[Coordinator] 📤 输出数据链:")
        print(f"[Coordinator]    - session_id: {sid}")
        print(f"[Coordinator]    - agent: {agent.agent_name}")
        print(f"[Coordinator]    - intent: {resolved_intent}")
        print(f"[Coordinator]    - answer_len: {len(agent_result.get('text', '')) if agent_result else 0}")
        print(f"[Coordinator]    - answer_preview: '{result_text}...'")
        print(f"[Coordinator]    - duration_ms: {round(total_duration_ms, 2)}")
        print(f"[Coordinator]    - topic_chain: {self._dialog_manager.get_topic_chain(sid)[:5]}")
        print(f"{'='*60}\n")

        return {
            "question": query,
            "text": agent_result.get("text", ""),
            "intent": intent_info,
            "agent": agent.agent_name,
            "result": agent_result,
            "monitoring": {
                "query_id": query_id,
                "total_duration_ms": round(total_duration_ms, 2),
            },
            "session_id": sid,  # 阶段 1 新增
        }

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
            # P0-QUIZ-FIX: 传入 HybridRetriever 使 embedding 语义检索可用
            vector_store = HybridRetriever(graph_store.collection_name)
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
