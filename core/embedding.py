"""
Embedding 模型管理器
支持智谱AI Embedding API，保留 HashEmbedding 离线降级方案
"""

import os
import sys
import time
import threading
import hashlib
from pathlib import Path
from typing import List, Optional

import numpy as np

from config.settings import CACHE_DIR, DEFAULT_EMBEDDING_DIM, ZHIPU_API_KEY, ZHIPU_EMBEDDING_BASE_URL, ZHIPU_EMBEDDING_MODEL


# 模型缓存目录（打包环境下指向可写目录）
if getattr(sys, 'frozen', False):
    _MODEL_CACHE_DIR = Path(os.path.dirname(sys.executable)) / "models"
else:
    _MODEL_CACHE_DIR = CACHE_DIR / "models"
_MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class HashEmbeddingFunction:
    """
    离线降级 embedding 函数（当 API 不可用时使用）。

    基于词哈希的确定性向量生成。搜索质量显著下降，但至少功能可用。
    """

    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIM):
        self.dim = dim
        self._warned = False

    def encode(self, texts, **kwargs):
        if not self._warned:
            print("[Embedding] WARNING: 使用降级 embedding（HashEmbedding）--搜索质量会下降")
            self._warned = True

        results = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            words = text.lower().split()
            for word in words:
                h1 = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim
                h2 = int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.dim
                vec[h1] += 1.0
                vec[h2] += 0.5
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            results.append(vec)
        return np.array(results)

    def __call__(self, texts: List[str]) -> List[List[float]]:
        return self.encode(texts).tolist()


class ApiEmbeddingClient:
    """
    智谱AI Embedding API 客户端（OpenAI 兼容格式）。

    支持批量调用，内置指数退避重试和请求间隔控制。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.api_key = api_key or ZHIPU_API_KEY
        self.base_url = (base_url or ZHIPU_EMBEDDING_BASE_URL).rstrip("/")
        self.model = model or ZHIPU_EMBEDDING_MODEL
        self.dimensions = dimensions or DEFAULT_EMBEDDING_DIM
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request_time = 0.0
        self._min_interval = 0.05  # 请求间隔 50ms，避免触发限流

    def _request(self, texts: List[str]) -> List[List[float]]:
        """发送单批 embedding 请求，含重试逻辑。"""
        if not self.api_key:
            raise RuntimeError("API key 未配置，无法调用远程 embedding 服务")

        import requests

        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": texts,
        }
        # 智谱 embedding-3 支持自定义维度，默认 2048
        if self.dimensions:
            payload["dimensions"] = self.dimensions

        for attempt in range(1, self.max_retries + 1):
            # 请求间隔控制
            elapsed = time.time() - self._last_request_time
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)

            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                self._last_request_time = time.time()

                if response.status_code == 200:
                    data = response.json()
                    # OpenAI 兼容格式: data[{"embedding": [...]}, ...]
                    embeddings = [item["embedding"] for item in data.get("data", [])]
                    # 确保返回顺序与输入一致
                    indexed = {item.get("index", i): item["embedding"] for i, item in enumerate(data.get("data", []))}
                    embeddings = [indexed.get(i, indexed.get(str(i), [])) for i in range(len(texts))]
                    return embeddings

                # 429 限流 -> 退避重试
                if response.status_code == 429:
                    wait = 2 ** attempt
                    print(f"[Embedding] WARNING: 限流 (429)，等待 {wait}s 后重试 ({attempt}/{self.max_retries})")
                    time.sleep(wait)
                    continue

                # 其他错误 -> 直接抛出
                response.raise_for_status()

            except requests.exceptions.Timeout:
                print(f"[Embedding] WARNING: 请求超时，重试 ({attempt}/{self.max_retries})")
                if attempt == self.max_retries:
                    raise
                time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                print(f"[Embedding] WARNING: 请求异常: {e}，重试 ({attempt}/{self.max_retries})")
                if attempt == self.max_retries:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError("Embedding API 调用失败，已耗尽重试次数")

    def encode(self, texts: List[str]) -> List[List[float]]:
        """
        批量编码文本为 embedding 向量。

        智谱 API 单次最多支持约 100 条输入，超过则自动分片。
        """
        if not texts:
            return []

        BATCH_SIZE = 100  # 智谱 embedding API 建议的单批上限
        all_embeddings = []

        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            embeddings = self._request(batch)
            all_embeddings.extend(embeddings)

        return all_embeddings

    def __call__(self, texts: List[str]) -> List[List[float]]:
        return self.encode(texts)


class EmbeddingManager:
    """
    Embedding 模型单例管理器。

    优先使用智谱AI Embedding API，API 不可用时自动降级为 HashEmbedding。

    使用方式:
        manager = EmbeddingManager()
        embeddings = manager.embed(["text1", "text2"])
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._client = None
                    cls._instance._fallback = False
        return cls._instance

    def _init_client(self):
        """初始化 embedding 客户端，优先 API，失败则降级。"""
        if self._client is not None:
            return self._client

        # 检查 API key 是否配置
        if not ZHIPU_API_KEY:
            print("[Embedding] WARNING: ZHIPU_API_KEY 未配置，启用降级 embedding")
            self._client = HashEmbeddingFunction(dim=DEFAULT_EMBEDDING_DIM)
            self._fallback = True
            return self._client

        # 尝试 API 客户端
        try:
            client = ApiEmbeddingClient()
            # 发一个测试请求验证连通性
            test_result = client.encode(["test"])
            if len(test_result) == 1 and len(test_result[0]) > 0:
                print(f"[Embedding] OK: 智谱AI Embedding API 连接成功 (model={client.model}, dim={len(test_result[0])})")
                self._client = client
                self._fallback = False
                return self._client
        except Exception as e:
            print(f"[Embedding] WARNING: 智谱AI API 初始化失败: {e}")

        # 降级
        print("[Embedding] WARNING: 启用降级 embedding（HashEmbedding）--搜索质量会下降")
        self._client = HashEmbeddingFunction(dim=DEFAULT_EMBEDDING_DIM)
        self._fallback = True
        return self._client

    @property
    def is_fallback(self) -> bool:
        """是否正在使用降级 embedding"""
        return self._fallback

    def embed(self, texts: List[str]) -> List[List[float]]:
        """生成文本 embedding 列表"""
        if not texts:
            return []
        client = self._init_client()
        return client.encode(texts)

    def embed_single(self, text: str) -> List[float]:
        """生成单条文本 embedding"""
        return self.embed([text])[0]

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算两个 embedding 的 cosine 相似度"""
        a_arr = np.array(a)
        b_arr = np.array(b)
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))
