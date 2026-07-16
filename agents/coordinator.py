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

from agents.base_agent import BaseAgent
from agents.tutor_agent import TutorAgent
from agents.quiz_agent import QuizAgent
from agents.coach_agent import CoachAgent
from agents.headhunter_agent import HeadhunterAgent


class Coordinator:
    """
    多 Agent 协调器。

    使用方式:
        coordinator = Coordinator()
        result = coordinator.handle("给我出几道化学题")
    """

    def __init__(self, collection_name: str = "learnanything_v1", top_k: int = 5, enabled_intents: List[str] = None):
        self.collection_name = collection_name
        self.top_k = top_k
        self.enabled_intents = enabled_intents or ["concept", "quiz", "job", "evaluate"]

        self._intent_router = IntentRouter()
        self._agents: Dict[str, BaseAgent] = {}

        # 延迟初始化各 Agent
        self._agents["concept"] = TutorAgent(collection_name=collection_name, top_k=top_k)
        self._agents["quiz"] = QuizAgent(collection_name=collection_name, top_k=top_k)
        self._agents["evaluate"] = CoachAgent(collection_name=collection_name, top_k=top_k)
        self._agents["job"] = HeadhunterAgent()

        # P0-INT-1: 延迟初始化 P0 模块（避免立即连接数据库）
        self._graph_store = None
        self._retriever = None
        self._builder = None
        self._assembler = None
        self._irt = None

    def handle(self, query: str, filters: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        处理用户查询的统一入口。

        Returns:
            {
                "question": str,
                "text": str,
                "intent": {"original": ..., "resolved": ..., "confidence": ..., "fallback": ...},
                "agent": str,
                "result": dict,
                "monitoring": {"query_id": ..., "total_duration_ms": ...},
            }
        """
        start_time = time.time()
        monitor = get_monitor()
        query_id = monitor.start_query(query, user_id=user_id, session_id=session_id)

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

        # P0-INT-1: 对 quiz 意图使用图谱教育模块组装出题上下文
        if resolved_intent == "quiz":
            try:
                print(f"[Coordinator] P0-INT-1: 使用图谱教育模块为 quiz 意图组装上下文")
                graph_store = self._get_graph_store()
                retriever = self._get_retriever(graph_store)

                # 提取主题
                topic = self._extract_topic_from_query(query)
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

                    # 将组装后的上下文传递给 QuizAgent
                    agent_result = agent.handle(query, filters=filters, graph_context=graph_context)
                else:
                    print(f"[Coordinator] 无匹配概念，回退到旧方式")
                    agent_result = agent.handle(query, filters=filters)
            except Exception as e:
                print(f"[Coordinator] P0 模块调用失败，回退到旧模式: {e}")
                import traceback
                traceback.print_exc()
                agent_result = agent.handle(query, filters=filters)
        else:
            # 非 quiz 意图，原方式执行
            agent_result = agent.handle(query, filters=filters)

        total_duration_ms = (time.time() - start_time) * 1000

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
        }

    # ==================== P0-INT-1: 辅助方法 ====================

    def _get_graph_store(self) -> GraphStore:
        """延迟初始化 GraphStore"""
        if self._graph_store is None:
            print(f"[Coordinator] 延迟初始化 GraphStore: {self.collection_name}")
            self._graph_store = GraphStore(self.collection_name)
        return self._graph_store

    def _get_retriever(self, graph_store: GraphStore) -> ConceptRetriever:
        """延迟初始化 ConceptRetriever"""
        if self._retriever is None:
            print(f"[Coordinator] 延迟初始化 ConceptRetriever")
            self._retriever = ConceptRetriever(graph_store=graph_store)
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
        """从查询中简单提取主题（去除常见出题关键词后取第一个有意义的短语）"""
        # 去除常见出题关键词
        stop_words = [
            "出题", "题目", "面试题", "练习题", "测试题", "考题", "试题",
            "考我", "测试我", "考一下", "测一下", "做道题", "来道题",
            "给我", "出一道", "来一道", "来几题", "出几题", "给我出题",
            "关于", "的", "一下", "几道", "几题", "请", "帮我",
            "quiz", "question", "exam", "test", "给我出", "帮我出",
        ]
        topic = query
        for w in stop_words:
            topic = topic.replace(w, "")
        topic = " ".join(topic.split()).strip()
        if not topic:
            topic = query
        return topic
