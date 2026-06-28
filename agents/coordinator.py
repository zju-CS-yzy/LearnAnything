#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
协调器 (Coordinator)
统一入口：意图路由 -> Agent 分发 -> 监控贯穿 -> 结果聚合
"""

import time
from typing import Dict, Any, List, Optional

from core.intent_router import IntentRouter
from core.monitoring import get_monitor

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

        # 执行 Agent
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
