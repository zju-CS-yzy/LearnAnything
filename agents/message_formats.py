#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 标准化输出格式（LA-050-C）

为各 Agent 的 handle 输出提供统一的结构化格式，便于前端渲染和跨 Agent 协作。

核心设计原则：
1. 向后兼容：现有 Agent.handle() 返回格式不变
2. 统一包装：通过 AgentOutput.from_agent_result() 将原始输出转为标准格式
3. 类型安全：使用 TypedDict 定义标准字段
"""

from typing import Dict, List, Any, Optional, TypedDict
from dataclasses import dataclass, field
from datetime import datetime


class SourceRef(TypedDict, total=False):
    """引用来源"""
    source_id: str
    source_type: str  # "chunk" | "concept" | "document"
    title: str
    page: Optional[int]
    confidence: float


class StandardMetadata(TypedDict, total=False):
    """标准元数据"""
    agent: str  # "tutor" | "quiz" | "coach" | "headhunter"
    intent: str
    topic: Optional[str]
    timestamp: str
    # TutorAgent 特有
    concepts: List[str]
    media: List[Dict[str, Any]]
    sources: List[SourceRef]
    has_context: bool
    # QuizAgent 特有
    question_count: int
    question_types: List[str]
    # CoachAgent 特有
    irt_theta: Optional[float]
    accuracy: Optional[float]
    weak_areas: List[str]
    strong_areas: List[str]


class AgentOutput:
    """
    标准化 Agent 输出。

    所有 Agent 的输出最终都应包装为此格式，供 Coordinator 统一处理和前端渲染。
    """

    def __init__(self,
                 agent: str,
                 text: str,
                 content_type: str = "text",  # text | quiz | evaluation | card | command
                 data: Optional[Dict[str, Any]] = None,
                 metadata: Optional[StandardMetadata] = None):
        self.agent = agent
        self.text = text
        self.content_type = content_type
        self.data = data or {}
        self.metadata = metadata or StandardMetadata()
        self.metadata["agent"] = agent
        self.metadata["timestamp"] = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """转为字典（供 API 序列化）"""
        return {
            "agent": self.agent,
            "text": self.text,
            "content_type": self.content_type,
            "data": self.data,
            "metadata": self.metadata,
        }

    @classmethod
    def from_tutor_result(cls, result: Dict[str, Any], query: str = "") -> "AgentOutput":
        """
        将 TutorAgent 原始输出转为标准格式。

        TutorAgent 原始格式:
            {
                "text": str,
                "metadata": {
                    "source": str,
                    "concepts": List[str],
                    "token_count": int,
                    "media": List[Dict],
                    "has_context": bool,
                    "sources": List[Dict],
                },
                "chunks": List[Dict],
            }
        """
        metadata = result.get("metadata", {})
        return cls(
            agent="tutor",
            text=result.get("text", ""),
            content_type="text",
            data={
                "chunks": result.get("chunks", []),
                "cache_hit": metadata.get("cache_hit", False),
            },
            metadata=StandardMetadata(
                agent="tutor",
                intent="concept_explanation",
                concepts=metadata.get("concepts", []),
                media=metadata.get("media", []),
                sources=[
                    SourceRef(
                        source_id=s.get("source_id", ""),
                        source_type=s.get("source_type", "chunk"),
                        title=s.get("title", ""),
                        page=s.get("page"),
                        confidence=s.get("confidence", 0.0),
                    )
                    for s in metadata.get("sources", [])
                ],
                has_context=metadata.get("has_context", False),
            )
        )

    @classmethod
    def from_quiz_result(cls, result: Dict[str, Any], query: str = "") -> "AgentOutput":
        """
        将 QuizAgent 原始输出转为标准格式。

        QuizAgent 原始格式:
            {
                "text": str,
                "questions": List[Dict],
                "graph_context_token_count": int,
                "concept_names": List[str],
                "topic": str,
                "subject_config": Dict,
            }
        """
        subject_config = result.get("subject_config", {})
        return cls(
            agent="quiz",
            text=result.get("text", ""),
            content_type="quiz",
            data={
                "questions": result.get("questions", []),
                "graph_context_token_count": result.get("graph_context_token_count", 0),
                "concept_names": result.get("concept_names", []),
            },
            metadata=StandardMetadata(
                agent="quiz",
                intent="quiz_generation",
                topic=result.get("topic", ""),
                question_count=len(result.get("questions", [])),
                question_types=subject_config.get("question_types_used", []),
            )
        )

    @classmethod
    def from_coach_result(cls, result: Dict[str, Any], query: str = "") -> "AgentOutput":
        """
        将 CoachAgent 原始输出转为标准格式。

        CoachAgent 有两种返回模式:
        1. 开始评测: {"text": str, "questions": List, "topic": str, "subject_config": Dict}
        2. 提交答案: {"text": str, "percentage": int, "level": str, "irt": Dict, "details": List, ...}
        """
        # 判断是评测结果还是出题结果
        if "percentage" in result or "irt" in result:
            # 评测结果
            irt = result.get("irt", {})
            return cls(
                agent="coach",
                text=result.get("text", ""),
                content_type="evaluation",
                data={
                    "percentage": result.get("percentage", 0),
                    "level": result.get("level", ""),
                    "correct_count": result.get("correct_count", 0),
                    "total_questions": result.get("total_questions", 0),
                    "details": result.get("details", []),
                    "weak_areas": result.get("weak_areas", []),
                    "strong_areas": result.get("strong_areas", []),
                },
                metadata=StandardMetadata(
                    agent="coach",
                    intent="evaluation_result",
                    topic=result.get("topic", ""),
                    irt_theta=irt.get("theta") if isinstance(irt, dict) else None,
                    accuracy=result.get("percentage", 0),
                    weak_areas=result.get("weak_areas", []),
                    strong_areas=result.get("strong_areas", []),
                )
            )
        else:
            # 出题结果（开始评测）
            subject_config = result.get("subject_config", {})
            return cls(
                agent="coach",
                text=result.get("text", ""),
                content_type="quiz",
                data={
                    "questions": result.get("questions", []),
                },
                metadata=StandardMetadata(
                    agent="coach",
                    intent="evaluation_start",
                    topic=result.get("topic", ""),
                    question_count=len(result.get("questions", [])),
                    question_types=subject_config.get("question_types", []),
                )
            )

    @classmethod
    def from_headhunter_result(cls, result: Dict[str, Any], query: str = "") -> "AgentOutput":
        """
        将 HeadhunterAgent 原始输出转为标准格式。
        """
        return cls(
            agent="headhunter",
            text=result.get("text", ""),
            content_type="text",
            data={
                "jobs": result.get("jobs", []),
                "recommendations": result.get("recommendations", []),
            },
            metadata=StandardMetadata(
                agent="headhunter",
                intent="job_recommendation",
            )
        )

    @classmethod
    def from_agent_result(cls, agent_name: str, result: Dict[str, Any], query: str = "") -> "AgentOutput":
        """
        通用工厂方法：根据 Agent 名称自动选择转换器。

        Args:
            agent_name: "tutor" | "quiz" | "coach" | "headhunter"
            result: Agent.handle() 的原始返回值
            query: 用户查询（用于上下文）

        Returns:
            AgentOutput 标准格式
        """
        converters = {
            "tutor": cls.from_tutor_result,
            "quiz": cls.from_quiz_result,
            "coach": cls.from_coach_result,
            "headhunter": cls.from_headhunter_result,
        }
        converter = converters.get(agent_name, cls._from_unknown)
        return converter(result, query)

    @classmethod
    def _from_unknown(cls, result: Dict[str, Any], query: str = "") -> "AgentOutput":
        """未知 Agent 类型的兜底转换"""
        return cls(
            agent="unknown",
            text=result.get("text", str(result)),
            content_type="text",
            data=result,
        )


def wrap_agent_output(agent_name: str, result: Dict[str, Any], query: str = "") -> Dict[str, Any]:
    """
    便捷函数：将 Agent 原始输出包装为标准字典。

    用法:
        raw_result = tutor_agent.handle(query)
        standard = wrap_agent_output("tutor", raw_result, query)
        # standard 现在包含统一的 agent/text/content_type/data/metadata 结构
    """
    output = AgentOutput.from_agent_result(agent_name, result, query)
    return output.to_dict()
