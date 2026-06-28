"""
意图路由模块
基于关键词规则的用户意图分类，无需额外模型
"""

from typing import List, Dict, Any, Tuple

INTENT_KEYWORDS = {
    "quiz": [
        "出题", "题目", "面试题", "练习题", "测试题", "考题", "试题",
        "考我", "测试我", "考一下", "测一下", "做道题", "来道题",
        "quiz", "question", "exam", "test me", "give me a question",
        "出一道", "来一道", "来几题", "出几题", "给我出题",
    ],
    "job": [
        "职位", "招聘", "找工作", "求职", "工作", "岗位", "JD",
        "简历", "投递", "面试机会", "内推", "猎头",
        "job", "position", "hiring", "recruit", "career", "apply",
        "推荐工作", "推荐职位", "有什么职位", "招什么人",
    ],
    "evaluate": [
        "评测", "评估", "评分", "打分", "测水平", "测能力",
        "我水平", "我能力", "测一下我", "评估我", "评价我",
        "evaluate", "assess", "score", "rate me", "my level",
        "我懂多少", "我学得怎么样", "我掌握",
    ],
    "concept": [],
}

INTENT_PRIORITY = ["quiz", "job", "evaluate", "concept"]

INTENT_META = {
    "quiz": {"name": "出题", "description": "生成面试题或练习题", "agent": "QuizAgent", "fallback": "concept"},
    "job": {"name": "职位推荐", "description": "搜索和推荐职位", "agent": "HeadhunterAgent", "fallback": "concept"},
    "evaluate": {"name": "能力评测", "description": "评估用户知识水平", "agent": "CoachAgent", "fallback": "concept"},
    "concept": {"name": "概念讲解", "description": "讲解技术概念和原理", "agent": "TutorAgent", "fallback": None},
}


class IntentRouter:
    """意图路由器"""

    def __init__(self, keywords: Dict[str, List[str]] = None):
        self.keywords = keywords or INTENT_KEYWORDS
        self.priority = INTENT_PRIORITY
        self.last_match_detail: Dict[str, Any] = {}

    def classify(self, query: str) -> str:
        if not query or not query.strip():
            return "concept"

        query_lower = query.lower()
        for intent in self.priority:
            if intent == "concept":
                continue
            keywords = self.keywords.get(intent, [])
            for kw in keywords:
                if kw.lower() in query_lower:
                    self.last_match_detail = {"intent": intent, "matched_keyword": kw, "query": query}
                    return intent

        self.last_match_detail = {"intent": "concept", "matched_keyword": None, "query": query}
        return "concept"

    def classify_with_score(self, query: str) -> Tuple[str, float]:
        intent = self.classify(query)
        confidence = 1.0 if self.last_match_detail.get("matched_keyword") else 0.0
        return intent, confidence

    def get_meta(self, intent: str) -> Dict[str, Any]:
        return INTENT_META.get(intent, INTENT_META["concept"])

    def is_enabled(self, intent: str, enabled: List[str] = None) -> bool:
        if enabled is None:
            return True
        return intent in enabled

    def get_fallback(self, intent: str) -> str:
        return self.get_meta(intent).get("fallback", "concept")

    def route(self, query: str, enabled: List[str] = None) -> Tuple[str, str]:
        original = self.classify(query)
        if self.is_enabled(original, enabled):
            return original, original
        fallback = self.get_fallback(original)
        if not self.is_enabled(fallback, enabled):
            fallback = "concept"
        return fallback, original
