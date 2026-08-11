#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 基类
定义统一接口，所有 Agent 必须实现
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from core.dialog_context import DialogContext


class BaseAgent(ABC):
    """
    Agent 基类。

    所有 Agent 必须实现 handle() 方法，接收用户查询，返回统一格式结果。
    """

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Agent 名称标识"""
        pass

    @abstractmethod
    def handle(self, query: str, context: Optional[DialogContext] = None, **kwargs) -> Dict[str, Any]:
        """
        处理用户查询。

        Args:
            query: 用户查询文本（已解析指代后的完整文本）
            context: 对话上下文（阶段 1 新增，可选，向后兼容）
            **kwargs: 其他参数（如 filters, graph_context 等）

        Returns:
            {
                "text": str,  # 回答文本
                "metadata": dict,  # 额外元数据
            }
        """
        pass

    # ==================== LA-UI-001: 统一上下文注入工具 ====================

    def get_history_text(self, context: Optional[DialogContext], max_turns: int = 5) -> str:
        """
        从 DialogContext 提取对话历史文本，用于注入 LLM prompt。

        所有子类在构建 prompt 时都应该调用此方法，确保 Agent 之间上下文互通。

        Args:
            context: 对话上下文
            max_turns: 最多取最近几轮对话

        Returns:
            格式化后的历史文本，如为空则返回 ""
        """
        if context is None:
            return ""
        if not hasattr(context, 'to_prompt_context'):
            return ""

        history = context.to_prompt_context(max_turns=max_turns)
        if history:
            print(f"[{self.agent_name}] 上下文注入: {len(history)} 字符历史")
        return history or ""

    def build_prompt_with_history(self, base_prompt: str, context: Optional[DialogContext] = None,
                                   history_text: str = "",
                                   history_header: str = "## 对话历史",
                                   max_turns: int = 5) -> str:
        """
        将对话历史注入到 prompt 中。

        使用方式：
            # 方式1: 传入 context，自动提取历史
            prompt = self.build_prompt_with_history(base_prompt, context)
            
            # 方式2: 直接传入已提取的历史文本
            prompt = self.build_prompt_with_history(base_prompt, history_text=history_text)

        Args:
            base_prompt: 原始 prompt（不含历史）
            context: 对话上下文（可选，与 history_text 二选一）
            history_text: 已提取的历史文本（可选，与 context 二选一）
            history_header: 历史部分的前缀标题
            max_turns: 最多取几轮（仅当使用 context 时有效）

        Returns:
            带历史前缀的完整 prompt
        """
        if not history_text and context:
            history_text = self.get_history_text(context, max_turns)

        if not history_text:
            return base_prompt

        return f"{history_header}\n\n{history_text}\n\n---\n\n{base_prompt}"

    def format_result_for_history(self, result: Dict[str, Any]) -> str:
        """
        将 Agent 的输出格式化为可保存到对话历史的文本。

        各子类可覆盖此方法，将特殊格式的输出（如 QuizAgent 的 questions 列表）
        转换为可读的文本。

        默认实现返回 result["text"] 或 str(result)。

        Args:
            result: Agent.handle() 的返回值

        Returns:
            可保存到 dialog_messages 的文本内容
        """
        if not isinstance(result, dict):
            return str(result)

        text = result.get("text", "")
        if text:
            return text

        # 默认：返回字典的字符串表示（有限长度）
        return str(result)[:2000]
