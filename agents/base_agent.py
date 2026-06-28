#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 基类
定义统一接口，所有 Agent 必须实现
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


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
    def handle(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        处理用户查询。

        Returns:
            {
                "text": str,  # 回答文本
                "metadata": dict,  # 额外元数据
            }
        """
        pass
