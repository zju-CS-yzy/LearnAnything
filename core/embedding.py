"""
Embedding 模型管理器 (LA-DEPLOY-FEAT)

按功能模块读取配置：文本向量化 (embedding)
支持任意 OpenAI 兼容的 Embedding API。
保留 HashEmbedding 离线降级方案。
"""

import time
import threading
import hashlib
import math
import random
import re
from typing import List, Optional

import numpy as np

from config.settings import DEFAULT_EMBEDDING_DIM, get_embedding_config

# 当前实现只使用远程 Embedding API 或内存中的 HashEmbedding 降级方案，
# 不下载、不读取本地模型。旧版本曾为本地 sentence-transformers 预留
# <程序目录>/models 缓存，但目录从未实际使用，因此不应在模块导入时创建。


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

    # embedding-3 documents a 3072-token limit per input. Keep headroom for
    # differences between the local estimate and the provider tokenizer.
    MAX_ESTIMATED_INPUT_TOKENS = 2800
    MAX_ESTIMATED_BATCH_TOKENS = 7000
    MAX_BATCH_ITEMS = 32
    TRANSPORT_RECOVERY_COOLDOWN = 3.0
    _CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    _TOKEN_PARTS = re.compile(
        r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
        r"|[A-Za-z0-9_]+|[^\s]"
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
        timeout: int = 30,
        max_retries: int = 4,
    ):
        # LA-DEPLOY-FEAT: 按功能模块读取配置
        cfg = get_embedding_config()
        self.api_key = api_key or cfg.api_key
        self.base_url = (base_url or cfg.base_url or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        self.model = model or cfg.model or "embedding-3"
        self.dimensions = dimensions or DEFAULT_EMBEDDING_DIM
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request_time = 0.0
        self._min_interval = 0.15
        self._session = None
        self._request_lock = threading.RLock()

    def _get_session(self):
        """Reuse healthy TLS connections and recreate the pool after SSL EOF."""
        import requests

        if getattr(self, "_session", None) is None:
            self._session = requests.Session()
        return self._session

    def _reset_session(self) -> None:
        session = getattr(self, "_session", None)
        self._session = None
        if session is not None:
            try:
                session.close()
            except Exception:
                pass

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        import requests

        if isinstance(exc, (
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        )):
            return True
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return status in {408, 425, 429, 500, 502, 503, 504}

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        return min(8.0, 2 ** max(0, attempt - 1)) + random.uniform(0.0, 0.75)

    @classmethod
    def _estimated_token_cost(cls, part: str) -> int:
        if re.fullmatch(r"[A-Za-z0-9_]+", part):
            # English/code BPE averages roughly four characters per token,
            # while short words still consume at least one token.
            return max(1, math.ceil(len(part) / 4))
        return 1

    @classmethod
    def _prepare_input(cls, value: object) -> str:
        """Return API-safe text without changing the input/output cardinality."""
        text = value if isinstance(value, str) else str(value or "")
        text = cls._CONTROL_CHARS.sub(" ", text)
        # Replace isolated surrogate code points before requests serializes the
        # payload. They occasionally appear in OCR output from damaged PDFs.
        text = text.encode("utf-8", errors="replace").decode("utf-8")
        if not text.strip():
            return " "

        token_total = 0
        cut_at = len(text)
        for match in cls._TOKEN_PARTS.finditer(text):
            token_total += cls._estimated_token_cost(match.group(0))
            if token_total > cls.MAX_ESTIMATED_INPUT_TOKENS:
                cut_at = match.start()
                break
        return text[:cut_at].rstrip() or " "

    @classmethod
    def _estimated_tokens(cls, text: str) -> int:
        return sum(
            cls._estimated_token_cost(match.group(0))
            for match in cls._TOKEN_PARTS.finditer(text)
        )

    @classmethod
    def _make_batches(cls, texts: List[str]) -> List[List[str]]:
        """Pack inputs by both item count and the model's 8K context budget."""
        batches: List[List[str]] = []
        current: List[str] = []
        current_tokens = 0
        for text in texts:
            cost = max(1, cls._estimated_tokens(text))
            if current and (
                len(current) >= cls.MAX_BATCH_ITEMS
                or current_tokens + cost > cls.MAX_ESTIMATED_BATCH_TOKENS
            ):
                batches.append(current)
                current = []
                current_tokens = 0
            current.append(text)
            current_tokens += cost
        if current:
            batches.append(current)
        return batches

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
                with self._request_lock:
                    response = self._get_session().post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=(10, self.timeout),
                    )
                self._last_request_time = time.time()

                if response.status_code == 200:
                    data = response.json()
                    # OpenAI 兼容格式: data[{"embedding": [...]}, ...]
                    embeddings = [item["embedding"] for item in data.get("data", [])]
                    # 确保返回顺序与输入一致
                    indexed = {item.get("index", i): item["embedding"] for i, item in enumerate(data.get("data", []))}
                    embeddings = [indexed.get(i, indexed.get(str(i), [])) for i in range(len(texts))]
                    if len(embeddings) != len(texts) or any(not item for item in embeddings):
                        raise RuntimeError(
                            f"Embedding API 返回数量不完整: expected={len(texts)}, "
                            f"actual={sum(bool(item) for item in embeddings)}"
                        )
                    return embeddings

                # 400/500 等错误 -> 打印详细业务错误码
                try:
                    error_data = response.json()
                    error_code = error_data.get("error", {}).get("code", "unknown")
                    error_message = error_data.get("error", {}).get("message", response.text[:200])
                    print(f"[Embedding] ERROR: API 返回错误 (HTTP {response.status_code})")
                    print(f"[Embedding]   业务错误码: {error_code}")
                    print(f"[Embedding]   错误消息: {error_message}")
                    print(f"[Embedding]   请求模型: {self.model}")
                    print(f"[Embedding]   请求文本数: {len(texts)}")
                    lengths = [len(text) for text in texts]
                    print(f"[Embedding]   文本长度范围: {min(lengths, default=0)}-{max(lengths, default=0)}")
                    print(
                        f"[Embedding]   估算 Token 总数: "
                        f"{sum(self._estimated_tokens(text) for text in texts)}"
                    )
                except Exception:
                    print(f"[Embedding] ERROR: API 返回错误 (HTTP {response.status_code}): {response.text[:200]}")

                # 429 限流 -> 退避重试
                if response.status_code == 429:
                    if attempt == self.max_retries:
                        response.raise_for_status()
                    wait = 2 ** attempt
                    print(f"[Embedding] WARNING: 限流 (429)，等待 {wait}s 后重试 ({attempt}/{self.max_retries})")
                    time.sleep(wait)
                    continue

                # 400 等客户端错误 -> 通常重试无用，但按配置重试
                if response.status_code == 400:
                    print(f"[Embedding] WARNING: 请求参数错误 (400)，通常重试无法解决")
                    # Retrying an identical invalid payload only delays a graph
                    # build. encode() will bisect the batch and isolate the bad
                    # input instead.
                    response.raise_for_status()

                # 其他错误 -> 直接抛出
                response.raise_for_status()

            except requests.exceptions.Timeout as exc:
                if attempt == self.max_retries:
                    raise
                wait = self._retry_delay(attempt)
                print(
                    f"[Embedding] WARNING: 请求超时，{wait:.1f}s 后重试 "
                    f"({attempt}/{self.max_retries}): {exc}"
                )
                time.sleep(wait)
            except requests.exceptions.RequestException as e:
                if getattr(getattr(e, "response", None), "status_code", None) == 400:
                    raise
                if attempt == self.max_retries:
                    raise
                if isinstance(e, (requests.exceptions.SSLError, requests.exceptions.ConnectionError)):
                    self._reset_session()
                wait = self._retry_delay(attempt)
                print(
                    f"[Embedding] WARNING: 瞬时网络/SSL异常，已重建连接池，"
                    f"{wait:.1f}s 后重试 ({attempt}/{self.max_retries}): {e}"
                )
                time.sleep(wait)

        raise RuntimeError("Embedding API 调用失败，已耗尽重试次数")

    def encode(self, texts: List[str]) -> List[List[float]]:
        """
        批量编码文本为 embedding 向量。

        智谱 API 单次最多支持约 100 条输入，超过则自动分片。
        如果 API 调用失败，自动降级到 HashEmbeddingFunction。
        """
        if not texts:
            return []

        prepared = [self._prepare_input(text) for text in texts]
        changed = sum(original != clean for original, clean in zip(texts, prepared))
        if changed:
            print(f"[Embedding] INFO: 已清洗或截断 {changed}/{len(texts)} 条输入")

        all_embeddings = []
        fallback = HashEmbeddingFunction(dim=self.dimensions)

        def request_resilient(batch: List[str]) -> List[List[float]]:
            """Keep valid API embeddings when one member makes a batch invalid."""
            try:
                return self._request(batch)
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status == 400 and len(batch) > 1:
                    midpoint = len(batch) // 2
                    print(
                        f"[Embedding] WARNING: 参数错误批次二分隔离 "
                        f"({len(batch)} -> {midpoint}+{len(batch) - midpoint})"
                    )
                    return request_resilient(batch[:midpoint]) + request_resilient(batch[midpoint:])
                if status == 400 and len(batch) == 1:
                    print("[Embedding] WARNING: 单条输入仍被 API 拒绝，仅对该条使用降级 embedding")
                    return fallback.encode(batch).tolist()
                raise

        batches = self._make_batches(prepared)
        if len(batches) > 1:
            print(
                f"[Embedding] INFO: {len(prepared)} 条输入按条数/Token预算拆为 "
                f"{len(batches)} 批"
            )
        batch_results: List[Optional[List[List[float]]]] = [None] * len(batches)
        deferred: List[tuple[int, List[str], Exception]] = []
        for batch_index, batch in enumerate(batches):
            try:
                batch_results[batch_index] = request_resilient(batch)
            except Exception as e:
                if not self._is_transient_error(e):
                    raise
                deferred.append((batch_index, batch, e))
                print(
                    f"[Embedding] WARNING: 第 {batch_index + 1}/{len(batches)} 批遇到瞬时故障，"
                    "延后到其余批次完成后重试"
                )

        if deferred:
            print(
                f"[Embedding] INFO: {len(deferred)} 个失败批次将在 "
                f"{self.TRANSPORT_RECOVERY_COOLDOWN:.1f}s 冷却后重试"
            )
            time.sleep(self.TRANSPORT_RECOVERY_COOLDOWN)
            for batch_index, batch, first_error in deferred:
                try:
                    self._reset_session()
                    batch_results[batch_index] = request_resilient(batch)
                except Exception as retry_error:
                    raise RuntimeError(
                        "Embedding 服务持续不可用；为避免在同一向量库混用 API 与 "
                        f"HashEmbedding，已中止本次写入。batch={batch_index + 1}/"
                        f"{len(batches)}, first_error={first_error}, retry_error={retry_error}"
                    ) from retry_error

        for result in batch_results:
            if result is None:
                raise RuntimeError("Embedding 批次结果缺失，已中止写入")
            all_embeddings.extend(result)

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

        # LA-DEPLOY-FEAT: 检查 embedding 配置
        cfg = get_embedding_config()
        if not cfg.api_key:
            print("[Embedding] WARNING: 文本向量化 API 未配置，启用降级 embedding")
            self._client = HashEmbeddingFunction(dim=DEFAULT_EMBEDDING_DIM)
            self._fallback = True
            return self._client

        # 尝试 API 客户端
        try:
            client = ApiEmbeddingClient()
            # 发一个测试请求验证连通性
            test_result = client.encode(["test"])
            if len(test_result) == 1 and len(test_result[0]) > 0:
                print(f"[Embedding] OK: Embedding API 连接成功 (provider={cfg.provider}, model={client.model}, dim={len(test_result[0])})")
                self._client = client
                self._fallback = False
                return self._client
        except Exception as e:
            print(f"[Embedding] WARNING: Embedding API 初始化失败: {e}")

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
