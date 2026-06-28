"""
查询改写模块
将口语化查询改写为多个技术化查询变体
"""

from typing import List, Dict

TERM_EXPANSIONS = {
    "rag": ["检索增强生成", "RAG优化", "RAG检索准确率提升"],
    "transformer": ["Transformer架构原理", "自注意力机制详解", "Transformer模型训练"],
    "agent": ["AI Agent架构", "智能体设计", "多Agent协作系统"],
    "mcp": ["模型上下文协议MCP", "MCP通信机制", "MCP工具集成"],
    "llm": ["大语言模型原理", "LLM训练与微调", "大模型应用架构"],
    "prompt": ["提示词工程", "Prompt Engineering", "Prompt优化策略"],
    "embedding": ["词向量Embedding", "Embedding模型选择", "语义向量化"],
    "微调": ["模型微调Fine-tuning", "参数高效微调PEFT", "LoRA微调技术"],
    "向量数据库": ["向量检索HNSW", "近似最近邻搜索ANN", "向量索引优化"],
    "训练": ["分布式训练DeepSpeed", "模型训练优化", "PyTorch分布式训练"],
    "面试": ["AI面试题", "大模型八股文", "算法面试考点"],
    "优化": ["性能优化方法", "系统优化策略", "算法优化技巧"],
    "缓存": ["多级缓存架构", "Redis缓存策略", "语义缓存设计"],
    "评估": ["模型评估指标BLEU", "ROUGE评分", "生成质量评估"],
    "检索": ["语义检索", "混合检索BM25", "多路召回策略"],
}


class QueryRewriter:
    """查询改写器"""

    def __init__(self):
        self._llm = None
        self._llm_available = None

    def _check_llm(self) -> bool:
        if self._llm_available is not None:
            return self._llm_available
        try:
            from core.llm_client import LLMClient
            self._llm = LLMClient()
            self._llm_available = True
        except Exception:
            self._llm_available = False
        return self._llm_available

    def rewrite(self, query: str, n_variants: int = 3) -> List[str]:
        if not query or not query.strip():
            return [query] if query else [""]

        if self._check_llm():
            try:
                return self._llm_rewrite(query, n_variants)
            except Exception as e:
                print(f"[QueryRewriter] LLM rewrite failed: {e}, fallback to rules")

        return self._rule_rewrite(query, n_variants)

    def _llm_rewrite(self, query: str, n_variants: int) -> List[str]:
        prompt = f"""你是查询改写专家。将用户查询改写为{n_variants}个专业查询变体，用于知识库检索。
要求：保留核心意图，使用专业术语，每个变体侧重不同角度。
直接返回查询列表，每行一个，不要编号。

用户查询：{query}

改写结果："""
        response = self._llm.chat([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=200)
        variants = [line.strip() for line in response.strip().split('\n') if line.strip()]
        if query not in variants:
            variants.insert(0, query)
        return variants[:n_variants]

    def _rule_rewrite(self, query: str, n_variants: int) -> List[str]:
        variants = [query]
        query_lower = query.lower()

        for term, expansions in TERM_EXPANSIONS.items():
            if term.lower() in query_lower:
                for exp in expansions[:2]:
                    if term in query:
                        variant = query.replace(term, exp, 1)
                    elif term.capitalize() in query:
                        variant = query.replace(term.capitalize(), exp, 1)
                    else:
                        variant = f"{query} {exp}"
                    if variant not in variants:
                        variants.append(variant)
                        break
                break

        suffixes = ["原理", "详解", "面试题", "优化方法", "实践指南"]
        for suffix in suffixes:
            variant = f"{query} {suffix}"
            if variant not in variants and len(variants) < n_variants:
                variants.append(variant)
            if len(variants) >= n_variants:
                break

        return variants[:n_variants]

    def extract_keywords(self, query: str) -> List[str]:
        import re
        stopwords = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这", "怎么", "什么", "讲讲", "说说", "介绍一下", "一下", "请", "帮我", "给我", "怎样", "如何", "为什么", "吗", "呢", "吧", "啊", "哦", "嗯"}
        words = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+', query)
        return [w for w in words if len(w) > 1 and w not in stopwords]
