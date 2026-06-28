"""
LearnAnything 全局配置
"""

import configparser
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


# ========== API 密钥加载（环境变量优先，回退到配置文件） ==========

def _load_api_keys():
    """
    加载 API 密钥配置。

    优先级：
        1. 环境变量（ZHIPU_API_KEY, DEEPSEEK_API_KEY）
        2. config/api_keys.ini 配置文件
        3. 空字符串（降级模式）
    """
    keys = {
        "zhipu_api_key": "",
        "deepseek_api_key": "",
        "zhipu_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "zhipu_embedding_model": "embedding-3",
    }

    # 1. 从配置文件读取（如果存在）
    ini_path = PROJECT_ROOT / "config" / "api_keys.ini"
    if ini_path.exists():
        parser = configparser.ConfigParser()
        parser.read(ini_path, encoding="utf-8")
        if parser.has_section("api_keys"):
            for key in keys:
                if parser.has_option("api_keys", key):
                    keys[key] = parser.get("api_keys", key).strip()

    # 2. 环境变量覆盖配置文件
    env_map = {
        "zhipu_api_key": "ZHIPU_API_KEY",
        "deepseek_api_key": "DEEPSEEK_API_KEY",
        "zhipu_base_url": "ZHIPU_EMBEDDING_BASE_URL",
        "zhipu_embedding_model": "ZHIPU_EMBEDDING_MODEL",
    }
    for cfg_key, env_key in env_map.items():
        env_val = os.environ.get(env_key, "").strip()
        if env_val:
            keys[cfg_key] = env_val

    return keys


_API_KEYS = _load_api_keys()

# 智谱AI Embedding API 配置
ZHIPU_API_KEY = _API_KEYS["zhipu_api_key"]
ZHIPU_EMBEDDING_BASE_URL = _API_KEYS["zhipu_base_url"]
ZHIPU_EMBEDDING_MODEL = _API_KEYS["zhipu_embedding_model"]

# DeepSeek LLM API 配置（供 core/llm_client.py 使用）
DEEPSEEK_API_KEY = _API_KEYS["deepseek_api_key"]

# 将 DeepSeek key 同步到环境变量（兼容 llm_client.py 的 os.getenv 读取）
if DEEPSEEK_API_KEY:
    os.environ.setdefault("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY)


# ========== 目录配置 ==========

# 知识库目录
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"

# 向量数据库目录
VECTOR_DB_DIR = KNOWLEDGE_BASE_DIR / "vector_db"

# 缓存目录
CACHE_DIR = KNOWLEDGE_BASE_DIR / "cache"


# ========== 模型配置 ==========

# 默认 Embedding 模型（智谱AI embedding-3）
DEFAULT_EMBEDDING_MODEL = "embedding-3"
DEFAULT_EMBEDDING_DIM = 2048

# 默认 Reranker 模型
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


# ========== 业务配置 ==========

# 分块配置
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200
MAX_CHUNK_SIZE = 3000
MIN_CHUNK_SIZE = 100

# 检索配置
TOP_K_RETRIEVE = 20
TOP_K_RETURN = 5
BM25_TOP_K = 100

# MMR 配置
MMR_LAMBDA = 0.7

# 缓存配置
CACHE_TTL_SECONDS = 86400
CACHE_MAX_ENTRIES = 10000

# 监控配置
MONITOR_DB_PATH = CACHE_DIR / "monitor.db"
MONITOR_RETENTION_DAYS = 30

# 学科配置目录
SUBJECT_CONFIG_DIR = PROJECT_ROOT / "config" / "subjects"


# ========== 初始化 ==========

# 创建必要目录
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

