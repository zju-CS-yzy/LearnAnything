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
