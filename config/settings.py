"""
LearnAnything API 配置中心 (LA-DEPLOY-FEAT)

按功能模块而非模型组织 API 配置：
    1. 语言处理 (llm)      - 智能对话、语义提取、评测
    2. 视觉处理 (vlm)      - 图片描述、表格提取、公式识别
    3. 文本向量化 (embedding) - 文本向量化、语义搜索
    4. PDF 解析 (mineru)   - PDF 结构化提取
    5. 学术资料检索 (openalex) - 公开题录检索与 DOI 摘要补齐

每个功能模块独立配置，用户可根据可用 API 自由选择提供商。
"""

import configparser
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ========== 项目根目录 ==========

PROJECT_ROOT = Path(__file__).parent.parent


def get_user_home() -> Path:
    """Resolve the current user's home, with an isolated-test override."""
    override = os.getenv("LEARNANYTHING_USER_HOME")
    return Path(override).expanduser() if override else Path.home()


# ========== LA-051-STRUCT: 数据根目录（分层方案）==========

def get_data_root() -> Path:
    """
    获取数据根目录。
    开发环境（源码运行）: PROJECT_ROOT/data/
    打包环境（PyInstaller）: ~/.learnanything/
    """
    if getattr(sys, 'frozen', False):
        return get_user_home() / ".learnanything"
    else:
        return PROJECT_ROOT / "data"


DATA_ROOT = get_data_root()


def ensure_data_root_marker() -> None:
    """Mark the packaged application's data root for safe uninstallation."""
    if not getattr(sys, "frozen", False):
        return
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    marker = DATA_ROOT / ".learnanything-data.json"
    if marker.exists():
        return
    payload = {
        "product": "LearnAnything",
        "kind": "data-root",
        "format_version": 1,
    }
    temp_marker = marker.with_suffix(".tmp")
    temp_marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_marker, marker)


ensure_data_root_marker()

# 知识库根目录（新结构 v2）
KNOWLEDGE_BASE_DIR = DATA_ROOT / "knowledge_base"
SHARE_KB_DIR = KNOWLEDGE_BASE_DIR / "Share"
USERS_KB_DIR = KNOWLEDGE_BASE_DIR / "Users"

# 用户数据目录
USERS_DIR = DATA_ROOT / "users"
USERS_DB_PATH = DATA_ROOT / "users.db"

# 旧结构兼容（迁移检测用）
OLD_KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
OLD_USERS_DATA_DIR = get_user_home() / ".learnanything"


# ========== LA-051-STRUCT: 学科路径辅助函数（统一入口）==========

def get_share_subject_dir(subject_id: str) -> Path:
    """获取共享学科目录。创建完整的学科内聚结构。"""
    if not subject_id or not str(subject_id).strip():
        raise ValueError("subject_id must not be empty")
    d = SHARE_KB_DIR / subject_id
    _ensure_subject_structure(d)
    return d


def get_user_root_dir(user_id: str) -> Path:
    """获取用户知识库根目录，但不创建任何学科级子目录。"""
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id must not be empty")
    d = USERS_KB_DIR / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_user_subject_dir(user_id: str, subject_id: str) -> Path:
    """获取用户私有学科目录。创建完整的学科内聚结构。"""
    if not subject_id or not str(subject_id).strip():
        raise ValueError("subject_id must not be empty")
    d = USERS_KB_DIR / user_id / subject_id
    _ensure_subject_structure(d)
    return d


def _ensure_subject_structure(base_dir: Path) -> None:
    """创建学科内聚目录结构（raw/ + media/images/ + media/thumbnails/）。"""
    (base_dir / "raw").mkdir(parents=True, exist_ok=True)
    (base_dir / "media" / "images").mkdir(parents=True, exist_ok=True)
    (base_dir / "media" / "thumbnails").mkdir(parents=True, exist_ok=True)
    # New layout: Kuzu files live under <subject>/graph/.  A legacy
    # <subject>/graph file is left in place and migrated before opening Kuzu.
    graph_dir = base_dir / "graph"
    if not graph_dir.exists():
        graph_dir.mkdir(parents=True, exist_ok=True)
    elif graph_dir.is_file():
        # Do not call mkdir on a legacy Kuzu database file.  GraphStore will
        # migrate it to graph/graph before opening the database.
        return


def migrate_legacy_graph_db(subject_dir: Path) -> None:
    """Move legacy <subject>/graph[.wal] files into the graph directory."""
    subject_dir = Path(subject_dir)
    legacy_db = subject_dir / "graph"
    legacy_wal = subject_dir / "graph.wal"
    graph_dir = subject_dir / "graph"
    target_db = graph_dir / "graph"
    target_wal = graph_dir / "graph.wal"

    if not legacy_db.is_file():
        graph_dir.mkdir(parents=True, exist_ok=True)
        return

    tmp_dir = subject_dir / ".graph_migration_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    moved_db = tmp_dir / "graph"
    moved_wal = tmp_dir / "graph.wal"
    try:
        shutil.move(str(legacy_db), str(moved_db))
        if legacy_wal.is_file():
            shutil.move(str(legacy_wal), str(moved_wal))
        graph_dir.mkdir(parents=True, exist_ok=True)
        if not target_db.exists():
            shutil.move(str(moved_db), str(target_db))
        else:
            moved_db.unlink(missing_ok=True)
        if moved_wal.exists():
            if not target_wal.exists():
                shutil.move(str(moved_wal), str(target_wal))
            else:
                moved_wal.unlink(missing_ok=True)
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


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
    return d / "graph" / "graph"


def get_subject_gap_db_path(subject_id: str, user_id: str = None) -> Path:
    """Return the subject-scoped Gap Flow SQLite database path."""
    if user_id:
        d = get_user_subject_dir(user_id, subject_id)
    else:
        d = get_share_subject_dir(subject_id)
    return d / "gap_flow.db"


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
    "openalex": {
        "name": "OpenAlex",
        "url": "https://openalex.org/settings/api",
        "docs_url": "https://developers.openalex.org/api-reference/introduction",
        "icon": "🔎",
        "description": "公开学术元数据检索与 DOI 摘要补齐",
        "features": ["openalex"],
        "models": {},
        "default_base_url": "https://api.openalex.org",
        "api_key_format": "OpenAlex API Key",
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
    openalex: FeatureConfig = field(default_factory=lambda: FeatureConfig(
        provider="openalex",
        api_key=os.getenv("OPENALEX_API_KEY", "").strip(),
        base_url="https://api.openalex.org",
    ))
    
    # MinerU 特殊配置（CLI 路径等）
    mineru_cli_path: str = ""


# ========== 配置文件路径 ==========

# 可变且含密钥的 API 配置属于运行时用户数据，不能写入 PyInstaller 的
# _internal/config 资源目录。PROJECT_ROOT/config 仅存放随程序发布的只读模板。
CONFIG_DIR = DATA_ROOT / "config"
API_CONFIG_PATH = CONFIG_DIR / "api_config.ini"
BUNDLED_CONFIG_DIR = PROJECT_ROOT / "config"
LEGACY_API_CONFIG_PATH = BUNDLED_CONFIG_DIR / "api_config.ini"
LEGACY_API_KEYS_PATH = BUNDLED_CONFIG_DIR / "api_keys.ini"


def migrate_legacy_api_config(
    runtime_path: Path = API_CONFIG_PATH,
    legacy_path: Path = LEGACY_API_CONFIG_PATH,
    remove_source: Optional[bool] = None,
) -> bool:
    """Move the old program-directory API config into the user data root.

    Source runs keep the ignored legacy file as a fallback copy. Frozen builds
    remove it after an atomic migration so secrets no longer remain beneath
    ``_internal`` and the portable package can be removed cleanly.
    """
    if runtime_path.exists() or not legacy_path.is_file():
        return False

    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = runtime_path.with_name(f".{runtime_path.name}.{os.getpid()}.tmp")
    try:
        shutil.copyfile(legacy_path, temp_path)
        os.replace(temp_path, runtime_path)
        try:
            os.chmod(runtime_path, 0o600)
        except OSError:
            pass
        should_remove = getattr(sys, "frozen", False) if remove_source is None else remove_source
        if should_remove:
            try:
                legacy_path.unlink()
            except OSError as exc:
                print(f"[Config] 旧 API 配置已迁移，但旧文件删除失败: {exc}")
        print(f"[Config] 旧 API 配置已迁移到 {runtime_path}")
        return True
    finally:
        if temp_path.exists():
            temp_path.unlink()


migrate_legacy_api_config()


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
        
        for feature in ["llm", "llm_fallback", "vlm", "embedding", "mineru", "openalex"]:
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
    if not old_ini.exists():
        old_ini = LEGACY_API_KEYS_PATH
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
    
    for feature in ["llm", "llm_fallback", "vlm", "embedding", "mineru", "openalex"]:
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
    
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(CONFIG_DIR),
            prefix=".api_config.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            parser.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, API_CONFIG_PATH)
        try:
            os.chmod(API_CONFIG_PATH, 0o600)
        except OSError:
            pass
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
    
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

    # OpenAlex academic metadata / DOI abstract enrichment.
    # Clear stale process state when the integration is disabled or its key is removed.
    if config.openalex.enabled and config.openalex.api_key:
        os.environ["OPENALEX_API_KEY"] = config.openalex.api_key
    else:
        os.environ.pop("OPENALEX_API_KEY", None)


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


def get_openalex_config() -> FeatureConfig:
    """获取 OpenAlex 学术检索配置"""
    return _CONFIG.openalex


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
    save_api_config(config)
    _CONFIG = config
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
        "openalex": is_feature_available("openalex"),
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

# LA-051-DIR-FIX: VECTOR_DB_DIR 不再自动创建，学科使用内聚路径
# VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
