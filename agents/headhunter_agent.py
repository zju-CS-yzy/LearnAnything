#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HeadhunterAgent: 职位/目标推荐 Agent
当前为占位实现，后续接入职位数据源
"""

import re
from typing import Dict, Any, List, Optional

from agents.base_agent import BaseAgent


class HeadhunterAgent(BaseAgent):
    """职位推荐 Agent（占位）"""

    @property
    def agent_name(self) -> str:
        return "HeadhunterAgent"

    def __init__(self):
        pass

    def handle(self, query: str, **kwargs) -> Dict[str, Any]:
        parsed = self._parse_query(query)
        text = f"""【职位/目标推荐】

已收到您的需求：
- 技术方向：{', '.join(parsed.get('tech', ['未指定']))}
- 工作年限：{parsed.get('experience', '未指定')}
- 城市：{parsed.get('city', '未指定')}

⚠️ 当前职位推荐功能为占位实现，尚未接入实际数据源。

后续将支持：
- 接入招聘网站 API
- 职位匹配算法（基于技能标签 + 向量相似度）
- 简历匹配度评分
- 面试准备建议（基于知识盲区分析）
"""
        return {"text": text, "parsed": parsed, "status": "placeholder"}

    def _parse_query(self, query: str) -> Dict[str, Any]:
        parsed = {"tech": [], "experience": None, "city": None, "salary": None}
        tech_keywords = ["大模型", "LLM", "AI", "人工智能", "机器学习", "深度学习", "NLP", "算法", "后端", "前端", "Python", "Java", "C++", "Go", "大数据", "云计算"]
        for kw in tech_keywords:
            if kw in query:
                parsed["tech"].append(kw)
        exp_match = re.search(r'(\d+)\s*年', query)
        if exp_match:
            parsed["experience"] = f"{exp_match.group(1)}年"
        elif "应届" in query:
            parsed["experience"] = "应届生"
        cities = ["北京", "上海", "深圳", "广州", "杭州", "成都", "武汉", "南京", "苏州", "西安"]
        for city in cities:
            if city in query:
                parsed["city"] = city
                break
        salary_match = re.search(r'(\d+)[kK]-?(\d+)?[kK]?', query)
        if salary_match:
            low, high = salary_match.group(1), salary_match.group(2) or salary_match.group(1)
            parsed["salary"] = f"{low}K-{high}K"
        return parsed
