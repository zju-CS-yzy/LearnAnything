"""
LearnAnything API 配置中心 (LA-DEPLOY-FEAT)

按功能模块而非模型组织 API 配置：
    1. 语言处理 (llm)      - 智能对话、语义提取、评测
    2. 视觉处理 (vlm)      - 图片描述、表格提取、公式识别
    3. 文本向量化 (embedding) - 文本向量化、语义搜索
    4. PDF 解析 (mineru)   - PDF 结构化提取

每个功能模块独立配置，用户可根据可用 API 自由选择提供商。
"""

import configparser
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ========== 项目根目录 ==========

PROJECT_ROOT = Path(__file__).parent.parent


# ========== LA-051-STRUCT: 数据根目录（分层方案）==========

def get_data_root() -> Path:
    """
    获取数据根目录。
    开发环境（源码运行）: PROJECT_ROOT/data/
    打包环境（PyInstaller）: ~/.learnanything/
    """
    if getattr(sys, 'frozen', False):
        return Path.home() / ".learnanything"
    else:
        return PROJECT_ROOT / "data"


DATA_ROOT = get_data_root()

# 知识库根目录（新结构 v2）
KNOWLEDGE_BASE_DIR = DATA_ROOT / "knowledge_base"
SHARE_KB_DIR = KNOWLEDGE_BASE_DIR / "Share"
USERS_KB_DIR = KNOWLEDGE_BASE_DIR / "Users"

# 用户数据目录
USERS_DIR = DATA_ROOT / "users"
USERS_DB_PATH = DATA_ROOT / "users.db"

# 旧结构兼容（迁移检测用）
OLD_KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
OLD_USERS_DATA_DIR = Path.home() / ".learnanything"


# ========== 学科路径辅助函数（LA-051-STRUCT）==========

def get_share_subject_dir(subject_id: str) -> Path:
    """获取共享学科目录"""
    d = SHARE_KB_DIR / subject_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_user_subject_dir(user_id: str, subject_id: str) -> Path:
    """获取用户私有学科目录"""
    d = USERS_KB_DIR / user_id / subject_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_subject_vector_db_path(subject_id: str, user_id: str = None) -> Path:
    """获取学科向量数据库路径（学科内聚）。"""
    if user_id:
        d = get_user_subject_dir(user_id, subject_id)
    else:
        d = get_share_subject_dir(subject_id)
    return d / "vector.db"


def get_subject_graph_db_path(subject_id: str, user_id: str = None) -> Path:
    """获取学科图数据库路径（学科内聚）。"""
    if user_id:
        d = get_user_subject_dir(user_id, subject_id)
    else:
        d = get_share_subject_dir(subject_id)
    return d / "graph"


def get_subject_images_dir(subject_id: str, user_id: str = None) -> Path:
    """获取学科图片目录"""
    if user_id:
        d = get_user_subject_dir(user_id, subject_id)
    else:
        d = get_share_subject_dir(subject_id)
    img_dir = d / "media" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    return img_dir


def get_subject_thumbnails_dir(subject_id: str, user_id: str = None) -> Path:
    """获取学科缩略图目录"""
    if user_id:
        d = get_user_subject_dir(user_id, subject_id)
    else:
        d = get_share_subject_dir(subject_id)
    thumb_dir = d / "media" / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    return thumb_dir


# ========== 预设提供商配置 ==========

# LA-DEPLOY-FEAT: 内置支持的 API 提供商列表
# 每个提供商定义：名称、官方链接、支持的模型、功能类型

SUPPORTED_PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "url": "https://platform.deepseek.com",
        "docs_url": "https://platform.deepseek.com/api-docs",
        "icon": "🔷",
        "description": "高性价比的中文大语言模型",
        "features": ["llm"],
        "models": {
            "deepseek-v4-pro": "DeepSeek-V4-Pro (推荐)",
            "deepseek-v4-flash": "DeepSeek-V4-Flash (轻量)",
            "deepseek-chat": "DeepSeek-V3 (旧版名称)",
            "deepseek-reasoner": "DeepSeek-R1 (推理)",
        },
        "default_base_url": "https://api.deepseek.com/v1",
        "api_key_format": "sk-xxxxxxxx",
    },
    "kimi": {
        "name": "Kimi (月之暗面)",
        "url": "https://platform.moonshot.cn",
        "docs_url": "https://platform.moonshot.cn/docs/api",
        "icon": "🌙",
        "description": "支持超长上下文的中文大语言模型，OpenAI兼容",
        "features": ["llm"],
        "models": {
            "kimi-k2.5": "Kimi K2.5 (推荐, 256K上下文)",
            "kimi-k2.6": "Kimi K2.6 (旗舰)",
            "kimi-k2": "Kimi K2 (开源权重)",
            "kimi-k2.5-reasoning": "Kimi K2.5 Reasoning (推理)",
        },
        "default_base_url": "https://api.moonshot.cn/v1",
        "api_key_format": "sk-xxxxxxxx",
    },
    "zhipu": {
        "name": "智谱AI (Zhipu)",
        "url": "https://bigmodel.cn",
        "docs_url": "https://open.bigmodel.cn/dev/api",
        "icon": "🧠",
        "description": "支持多模态和文本向量化的国产平台",
        "features": ["vlm", "embedding"],
        "models": {
            "glm-4.5v": "GLM-4.5V (视觉理解)",
            "glm-4v": "GLM-4V (视觉理解)",
            "embedding-3": "Embedding-3 (文本向量化, 推荐)",
            "embedding-2": "Embedding-2 (文本向量化)",
        },
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_format": "xxxxxxxx.xxxxxxxxxxxxxxxx",
    },
    "openai": {
        "name": "OpenAI",
        "url": "https://platform.openai.com",
        "docs_url": "https://platform.openai.com/docs",
        "icon": "🅾️",
        "description": "国际领先的 AI 平台，模型选择丰富",
        "features": ["llm", "vlm", "embedding"],
        "models": {
            "gpt-4o": "GPT-4o (多模态, 推荐)",
            "gpt-4o-mini": "GPT-4o-mini (性价比)",
            "gpt-4-turbo": "GPT-4 Turbo",
            "text-embedding-3-large": "text-embedding-3-large (向量化)",
            "text-embedding-3-small": "text-embedding-3-small (向量化)",
            "text-embedding-ada-002": "text-embedding-ada-002 (向量化)",
        },
        "default_base_url": "https://api.openai.com/v1",
        "api_key_format": "sk-xxxxxxxx",
    },
    "siliconflow": {
        "name": "硅基流动 (SiliconFlow)",
        "url": "https://cloud.siliconflow.cn",
        "docs_url": "https://docs.siliconflow.cn",
        "icon": "💎",
        "description": "国内一站式大模型 API 平台，兼容 OpenAI 格式",
        "features": ["llm", "vlm", "embedding"],
        "models": {
            "deepseek-ai/DeepSeek-V3": "DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1": "DeepSeek-R1",
            "Qwen/Qwen2.5-VL-72B-Instruct": "Qwen2.5-VL (视觉)",
            "BAAI/bge-large-zh-v1.5": "BGE-large (向量化)",
        },
        "default_base_url": "https://api.siliconflow.cn/v1",
        "api_key_format": "sk-xxxxxxxx",
    },
    "custom": {
        "name": "自定义 (OpenAI 兼容)",
        "url": "",
        "docs_url": "",
        "icon": "🔧",
        "description": "任何支持 OpenAI 兼容 API 格式的服务商",
        "features": ["llm", "vlm", "embedding"],
        "models": {},
        "default_base_url": "https://your-api-endpoint.com/v1",
        "api_key_format": "your-api-key",
    },
}


# ========== 功能模块默认模型映射 ==========

# 当用户选择某个提供商时，推荐的默认模型
# LA-DEPLOY-FIX: 默认模型留空，让用户从列表选择或输入自定义名称，
# 避免不同 API 端点支持的模型名称不一致导致测试失败
FEATURE_DEFAULT_MODELS = {
    "llm": {
        "deepseek": "",
        "openai": "gpt-4o",
        "siliconflow": "deepseek-ai/DeepSeek-V3",
        "custom": "",
    },
    "vlm": {
        "zhipu": "glm-4.5v",
        "openai": "gpt-4o",
        "siliconflow": "Qwen/Qwen2.5-VL-72B-Instruct",
        "custom": "",
    },
    "embedding": {
        "zhipu": "embedding-3",
        "openai": "text-embedding-3-large",
        "siliconflow": "BAAI/bge-large-zh-v1.5",
        "custom": "",
    },
}


# ========== 配置数据类 ==========

@dataclass
class FeatureConfig:
    """单个功能模块的配置"""
    provider: str = ""           # 提供商ID (deepseek/zhipu/openai/...)
    api_key: str = ""            # API Key
    base_url: str = ""           # Base URL
    model: str = ""              # 模型名称
    enabled: bool = True         # 是否启用
    custom_model: str = ""       # 自定义模型名称（用于 custom 提供商）


@dataclass
class AppConfig:
    """应用完整配置"""
    # 功能模块配置
    llm: FeatureConfig = field(default_factory=lambda: FeatureConfig())
    llm_fallback: FeatureConfig = field(default_factory=lambda: FeatureConfig())  # LLM-ROBUST: 备用 LLM
    vlm: FeatureConfig = field(default_factory=lambda: FeatureConfig())
    embedding: FeatureConfig = field(default_factory=lambda: FeatureConfig())
    mineru: FeatureConfig = field(default_factory=lambda: FeatureConfig())
    
    # MinerU 特殊配置（CLI 路径等）
    mineru_cli_path: str = ""


# ========== 配置文件路径 ==========

CONFIG_DIR = PROJECT_ROOT / "config"
API_CONFIG_PATH = CONFIG_DIR / "api_config.ini"


# ========== 配置加载/保存 ==========

def _load_api_config() -> AppConfig:
    """
    从配置文件加载 API 配置。
    
    兼容旧配置：如果存在 api_keys.ini 但不存在 api_config.ini，
    读取旧配置到内存（不保存文件），等用户在向导中确认后再保存。
    """
    config = AppConfig()
    
    # 1. 尝试加载新格式配置
    if API_CONFIG_PATH.exists():
        parser = configparser.ConfigParser()
        parser.read(API_CONFIG_PATH, encoding="utf-8")
        
        for feature in ["llm", "llm_fallback", "vlm", "embedding", "mineru"]:
            if parser.has_section(feature):
                section = parser[feature]
                fc = FeatureConfig(
                    provider=section.get("provider", "").strip(),
                    api_key=section.get("api_key", "").strip(),
                    base_url=section.get("base_url", "").strip(),
                    model=section.get("model", "").strip(),
                    enabled=section.getboolean("enabled", True),
                    custom_model=section.get("custom_model", "").strip(),
                )
                setattr(config, feature, fc)
        
        if parser.has_section("mineru_extra"):
            config.mineru_cli_path = parser.get("mineru_extra", "cli_path", fallback="").strip()
        
        return config
    
    # 2. 兼容旧格式：从 api_keys.ini 读取到内存（不保存文件）
    # LA-DEPLOY-FIX: 不自动保存，让用户在向导中确认后再保存
    old_ini = CONFIG_DIR / "api_keys.ini"
    if old_ini.exists():
        parser = configparser.ConfigParser()
        parser.read(old_ini, encoding="utf-8")
        
        if parser.has_section("api_keys"):
            zhipu_key = parser.get("api_keys", "zhipu_api_key", fallback="").strip()
            deepseek_key = parser.get("api_keys", "deepseek_api_key", fallback="").strip()
            zhipu_url = parser.get("api_keys", "zhipu_base_url", fallback="https://open.bigmodel.cn/api/paas/v4").strip()
            deepseek_url = parser.get("api_keys", "deepseek_base_url", fallback="https://api.deepseek.com/v1").strip()
            zhipu_model = parser.get("api_keys", "zhipu_embedding_model", fallback="embedding-3").strip()
            deepseek_model = parser.get("api_keys", "deepseek_model", fallback="deepseek-chat").strip()
            
            if zhipu_key:
                config.vlm = FeatureConfig(
                    provider="zhipu",
                    api_key=zhipu_key,
                    base_url=zhipu_url,
                    model="glm-4.5v",
                )
                config.embedding = FeatureConfig(
                    provider="zhipu",
                    api_key=zhipu_key,
                    base_url=zhipu_url,
                    model=zhipu_model,
                )
            
            if deepseek_key:
                config.llm = FeatureConfig(
                    provider="deepseek",
                    api_key=deepseek_key,
                    base_url=deepseek_url,
                    model=deepseek_model,
                )
            
            print(f"[Config] 检测到旧配置 api_keys.ini，值已加载到内存（未保存文件），请在向导中确认")
    
    return config


def save_api_config(config: AppConfig) -> None:
    """保存 API 配置到文件"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    parser = configparser.ConfigParser()
    
    for feature in ["llm", "llm_fallback", "vlm", "embedding", "mineru"]:
        fc: FeatureConfig = getattr(config, feature)
        parser.add_section(feature)
        parser.set(feature, "provider", fc.provider)
        parser.set(feature, "api_key", fc.api_key)
        parser.set(feature, "base_url", fc.base_url)
        parser.set(feature, "model", fc.model)
        parser.set(feature, "enabled", str(fc.enabled))
        parser.set(feature, "custom_model", fc.custom_model)
    
    parser.add_section("mineru_extra")
    parser.set("mineru_extra", "cli_path", config.mineru_cli_path)
    
    with open(API_CONFIG_PATH, "w", encoding="utf-8") as f:
        parser.write(f)
    
    print(f"[Config] 配置已保存到 {API_CONFIG_PATH}")


# ========== 环境变量同步 ==========

def _sync_to_env(config: AppConfig):
    """将配置同步到环境变量（兼容旧代码的 os.getenv 读取）"""
    # LLM → DEEPSEEK_API_KEY（兼容）+ KIMI_API_KEY
    if config.llm.api_key:
        if config.llm.provider == "kimi":
            os.environ["KIMI_API_KEY"] = config.llm.api_key
            if config.llm.base_url:
                os.environ["KIMI_BASE_URL"] = config.llm.base_url
            if config.llm.model:
                os.environ["KIMI_MODEL"] = config.llm.model
        else:
            os.environ["DEEPSEEK_API_KEY"] = config.llm.api_key
            if config.llm.base_url:
                os.environ["DEEPSEEK_BASE_URL"] = config.llm.base_url
            if config.llm.model:
                os.environ["DEEPSEEK_MODEL"] = config.llm.model
    
    # VLM/Embedding → ZHIPU_API_KEY（兼容）
    # 如果 vlm 和 embedding 使用同一提供商，优先用 vlm 的 key
    if config.vlm.api_key:
        os.environ["ZHIPU_API_KEY"] = config.vlm.api_key
        if config.vlm.base_url:
            os.environ["ZHIPU_EMBEDDING_BASE_URL"] = config.vlm.base_url
    elif config.embedding.api_key:
        os.environ["ZHIPU_API_KEY"] = config.embedding.api_key
        if config.embedding.base_url:
            os.environ["ZHIPU_EMBEDDING_BASE_URL"] = config.embedding.base_url
    
    if config.embedding.model:
        os.environ["ZHIPU_EMBEDDING_MODEL"] = config.embedding.model
    
    # MinerU
    if config.mineru.api_key:
        os.environ["MINERU_TOKEN"] = config.mineru.api_key


# ========== 全局配置实例 ==========

_CONFIG = _load_api_config()
_sync_to_env(_CONFIG)


# ========== 便捷访问函数 ==========

def get_llm_config() -> FeatureConfig:
    """获取语言处理配置"""
    return _CONFIG.llm


def get_llm_fallback_config() -> FeatureConfig:
    """LLM-ROBUST: 获取备用语言处理配置"""
    return _CONFIG.llm_fallback


def get_vlm_config() -> FeatureConfig:
    """获取视觉处理配置"""
    return _CONFIG.vlm


def get_embedding_config() -> FeatureConfig:
    """获取文本向量化配置"""
    return _CONFIG.embedding


def get_mineru_config() -> FeatureConfig:
    """获取 MinerU 配置"""
    return _CONFIG.mineru


def get_full_config() -> AppConfig:
    """获取完整配置"""
    return _CONFIG


def reload_config():
    """重新加载配置（配置变更后调用）"""
    global _CONFIG
    _CONFIG = _load_api_config()
    _sync_to_env(_CONFIG)
    print("[Config] 配置已重新加载")


def update_config(config: AppConfig):
    """更新配置并保存"""
    global _CONFIG
    _CONFIG = config
    save_api_config(config)
    _sync_to_env(config)


# ========== 功能可用性检查 ==========

def is_feature_available(feature: str) -> bool:
    """检查某个功能是否已配置"""
    fc: FeatureConfig = getattr(_CONFIG, feature, FeatureConfig())
    return fc.enabled and bool(fc.api_key.strip())


def check_all_features() -> Dict[str, bool]:
    """检查所有功能的配置状态"""
    return {
        "llm": is_feature_available("llm"),
        "vlm": is_feature_available("vlm"),
        "embedding": is_feature_available("embedding"),
        "mineru": is_feature_available("mineru"),
    }


def is_first_run() -> bool:
    """
    检查是否为首次运行（新配置系统）。
    
    逻辑：如果 api_config.ini 不存在，视为首次运行（即使有旧配置也不自动跳过）。
    这允许用户删除 api_config.ini 后重新进入配置向导。
    """
    # LA-DEPLOY-FIX: 优先检查新配置文件是否存在
    if not API_CONFIG_PATH.exists():
        return True
    
    # 文件存在，检查内容是否完整
    checks = check_all_features()
    return not (checks["llm"] and checks["embedding"])


# ========== 目录配置（LA-051-STRUCT: 兼容层）==========
# 注意：KNOWLEDGE_BASE_DIR 等已在文件顶部定义（基于 DATA_ROOT）
# 以下保留集中式 vector_db / graph_db 作为过渡兼容层
# 新代码应使用 get_subject_vector_db_path() / get_subject_graph_db_path()

VECTOR_DB_DIR = KNOWLEDGE_BASE_DIR / "vector_db"
GRAPH_DB_DIR = KNOWLEDGE_BASE_DIR / "graph_db"
CACHE_DIR = KNOWLEDGE_BASE_DIR / "cache"

# ========== 模型配置（保持原有默认值） ==========

DEFAULT_EMBEDDING_MODEL = "embedding-3"
DEFAULT_EMBEDDING_DIM = 2048
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ========== 业务配置（保持原有） ==========

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200
MAX_CHUNK_SIZE = 3000
MIN_CHUNK_SIZE = 100
TOP_K_RETRIEVE = 20
TOP_K_RETURN = 5
BM25_TOP_K = 100
MMR_LAMBDA = 0.7
CACHE_TTL_SECONDS = 86400
CACHE_MAX_ENTRIES = 10000
MONITOR_DB_PATH = CACHE_DIR / "monitor.db"
MONITOR_RETENTION_DAYS = 30
SUBJECT_CONFIG_DIR = PROJECT_ROOT / "config" / "subjects"

# ========== 初始化（保持原有） ==========

VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
