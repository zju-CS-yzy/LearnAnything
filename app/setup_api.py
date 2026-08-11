#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setup Wizard API — 首次启动配置向导 (LA-DEPLOY-FEAT)

按功能模块配置 API：
    - llm:       语言处理（对话、语义提取、评测）
    - vlm:       视觉处理（图片描述、表格提取、公式识别）
    - embedding: 文本向量化（语义搜索）
    - mineru:    PDF 结构化解析
"""

import ipaddress
import json
import os
import requests
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import require_admin
from config.settings import (
    FeatureConfig,
    SUPPORTED_PROVIDERS, FEATURE_DEFAULT_MODELS,
    DATA_ROOT, update_config, get_full_config,
    is_first_run, check_all_features,
)


# ========== Pydantic 模型 ==========

class FeatureConfigRequest(BaseModel):
    """单个功能模块配置请求"""
    provider: Optional[str] = Field(None, description="提供商ID")
    api_key: Optional[str] = Field(None, description="新 API Key；省略或留空表示保持原值")
    base_url: Optional[str] = Field(None, description="Base URL")
    model: Optional[str] = Field(None, description="模型名称")
    enabled: Optional[bool] = Field(None, description="是否启用")
    custom_model: Optional[str] = Field(None, description="自定义模型名称")


class SetupConfigRequest(BaseModel):
    """完整配置请求"""
    llm: Optional[FeatureConfigRequest] = None
    llm_fallback: Optional[FeatureConfigRequest] = None
    vlm: Optional[FeatureConfigRequest] = None
    embedding: Optional[FeatureConfigRequest] = None
    mineru: Optional[FeatureConfigRequest] = None
    mineru_cli_path: Optional[str] = Field(None, description="MinerU CLI 路径")


class TestResult(BaseModel):
    """API 连通性测试结果"""
    feature: str = Field(..., description="功能名称")
    provider: str = Field(..., description="提供商")
    model: str = Field("", description="测试使用的模型")
    success: bool = Field(..., description="是否成功")
    message: str = Field("", description="结果描述")
    latency_ms: Optional[float] = Field(None, description="延迟（毫秒）")


class SetupStatus(BaseModel):
    """首次启动状态"""
    is_first_run: bool = Field(..., description="是否为首次启动")
    features_configured: Dict[str, bool] = Field(..., description="各功能配置状态")
    required_features: List[str] = Field(default=["llm", "embedding"], description="必需功能")


class ProviderInfo(BaseModel):
    """提供商信息"""
    id: str
    name: str
    url: str
    docs_url: str
    icon: str
    description: str
    features: List[str]
    models: Dict[str, str]
    default_base_url: str
    api_key_format: str


# ========== 路由 ==========

router = APIRouter(prefix="/api/setup", tags=["setup"])

FEATURE_NAMES = ("llm", "llm_fallback", "vlm", "embedding", "mineru")
AUDIT_LOG_PATH = DATA_ROOT / "logs" / "admin_audit.jsonl"
_AUDIT_LOCK = threading.Lock()


def _select_secret(candidate: Optional[str], current: str) -> str:
    """Keep the stored secret when a client omits it or sends a legacy mask."""
    if candidate is None:
        return current
    value = candidate.strip()
    if not value or value == "***":
        return current
    return value


def _validate_provider(feature: str, provider: str) -> None:
    if feature == "mineru":
        if provider not in ("", "mineru"):
            raise HTTPException(status_code=400, detail="Unsupported MinerU provider")
        return
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    provider_feature = "llm" if feature == "llm_fallback" else feature
    if provider_feature not in SUPPORTED_PROVIDERS[provider]["features"]:
        raise HTTPException(
            status_code=400,
            detail=f"Provider {provider} does not support {provider_feature}",
        )


def _resolve_base_url(provider: str, candidate: Optional[str], current: str) -> str:
    if candidate is not None:
        value = candidate.strip()
        if value:
            return value
    if provider in SUPPORTED_PROVIDERS:
        return SUPPORTED_PROVIDERS[provider]["default_base_url"]
    return current.strip()


def _validate_base_url(provider: str, base_url: str) -> None:
    """Reject local/private targets and provider-host mismatches."""
    parsed = urlparse(base_url)
    allow_private = os.getenv("LEARNANYTHING_ALLOW_PRIVATE_API_ENDPOINTS") == "1"
    allowed_schemes = {"https", "http"} if allow_private else {"https"}
    if parsed.scheme.lower() not in allowed_schemes or not parsed.hostname:
        raise HTTPException(status_code=400, detail="A valid HTTPS API base URL is required")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="API base URL must not contain credentials")

    hostname = parsed.hostname.lower().rstrip(".")
    if not allow_private:
        if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
            raise HTTPException(status_code=400, detail="Private API endpoints are disabled")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address and not address.is_global:
            raise HTTPException(status_code=400, detail="Private API endpoints are disabled")

    if provider in SUPPORTED_PROVIDERS and provider != "custom":
        default_host = urlparse(SUPPORTED_PROVIDERS[provider]["default_base_url"]).hostname
        if default_host and hostname != default_host.lower().rstrip("."):
            raise HTTPException(
                status_code=400,
                detail="Use the custom provider for a non-standard API host",
            )


def _merge_feature_config(
    feature: str,
    current: FeatureConfig,
    incoming: FeatureConfigRequest,
) -> FeatureConfig:
    provider = (incoming.provider if incoming.provider is not None else current.provider).strip()
    _validate_provider(feature, provider)
    new_key = (incoming.api_key or "").strip()
    if provider != current.provider and (not new_key or new_key == "***"):
        raise HTTPException(
            status_code=400,
            detail="A new API Key is required when changing provider",
        )

    if incoming.base_url is None and provider == current.provider:
        base_url = current.base_url.strip()
    else:
        base_url = _resolve_base_url(provider, incoming.base_url, current.base_url)
    if feature != "mineru":
        _validate_base_url(provider, base_url)

    model = (incoming.model if incoming.model is not None else current.model).strip()
    defaults_feature = "llm" if feature == "llm_fallback" else feature
    if not model:
        model = FEATURE_DEFAULT_MODELS.get(defaults_feature, {}).get(provider, "")

    return FeatureConfig(
        provider=provider,
        api_key=_select_secret(incoming.api_key, current.api_key),
        base_url=base_url,
        model=model,
        enabled=current.enabled if incoming.enabled is None else incoming.enabled,
        custom_model=(
            incoming.custom_model
            if incoming.custom_model is not None
            else current.custom_model
        ).strip(),
    )


def _write_audit_event(user_id: str, action: str, details: dict) -> None:
    """Append a secret-free administrator audit event."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "action": action,
        "details": details,
    }
    with _AUDIT_LOCK:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        try:
            os.chmod(AUDIT_LOG_PATH, 0o600)
        except OSError:
            pass


# ========== API 端点 ==========

@router.get("/status", response_model=SetupStatus)
async def get_setup_status():
    """获取首次启动状态"""
    checks = check_all_features()
    return SetupStatus(
        is_first_run=is_first_run(),
        features_configured=checks,
    )


@router.get("/providers", response_model=List[ProviderInfo])
async def list_providers():
    """获取所有支持的 API 提供商列表"""
    providers = []
    for pid, info in SUPPORTED_PROVIDERS.items():
        providers.append(ProviderInfo(
            id=pid,
            name=info["name"],
            url=info["url"],
            docs_url=info["docs_url"],
            icon=info["icon"],
            description=info["description"],
            features=info["features"],
            models=info["models"],
            default_base_url=info["default_base_url"],
            api_key_format=info["api_key_format"],
        ))
    return providers


@router.get("/config")
async def get_config(admin_user_id: str = Depends(require_admin)):
    """获取当前配置；永不返回 API Key 内容。"""
    cfg = get_full_config()

    def serialize(fc: FeatureConfig) -> dict:
        return {
            "provider": fc.provider,
            "configured": bool(fc.api_key.strip()),
            "base_url": fc.base_url,
            "model": fc.model,
            "enabled": fc.enabled,
            "custom_model": fc.custom_model,
        }

    return {
        "llm": serialize(cfg.llm),
        "llm_fallback": serialize(cfg.llm_fallback),
        "vlm": serialize(cfg.vlm),
        "embedding": serialize(cfg.embedding),
        "mineru": serialize(cfg.mineru),
        "mineru_cli_path": cfg.mineru_cli_path,
    }


@router.post("/config")
async def save_config(
    request: SetupConfigRequest,
    admin_user_id: str = Depends(require_admin),
):
    """Partially update configuration without ever reading old keys to the client."""
    config = get_full_config()
    changed_features = []

    for feature in FEATURE_NAMES:
        incoming = getattr(request, feature)
        if incoming is None:
            continue
        current = getattr(config, feature)
        setattr(config, feature, _merge_feature_config(feature, current, incoming))
        changed_features.append(feature)

    if request.mineru_cli_path is not None:
        config.mineru_cli_path = request.mineru_cli_path.strip()
        changed_features.append("mineru_cli_path")

    if not config.llm.api_key.strip():
        raise HTTPException(status_code=400, detail="LLM API Key is required")
    if not config.embedding.api_key.strip():
        raise HTTPException(status_code=400, detail="Embedding API Key is required")

    update_config(config)
    _write_audit_event(admin_user_id, "config.update", {"features": changed_features})

    return {
        "status": "success",
        "message": "Configuration saved",
        "features": check_all_features(),
    }


@router.post("/test/{feature}", response_model=TestResult)
async def test_feature_api(
    feature: str,
    request: FeatureConfigRequest,
    admin_user_id: str = Depends(require_admin),
):
    """Test one configured provider; only a system administrator may call it."""
    if feature not in FEATURE_NAMES:
        raise HTTPException(status_code=400, detail=f"Unsupported feature: {feature}")

    current = getattr(get_full_config(), feature)
    provider = (request.provider or current.provider).strip()
    api_key = _select_secret(request.api_key, current.api_key)
    base_url = _resolve_base_url(provider, request.base_url, current.base_url)
    model = (request.model if request.model is not None else current.model).strip()
    if not model:
        defaults_feature = "llm" if feature == "llm_fallback" else feature
        model = FEATURE_DEFAULT_MODELS.get(defaults_feature, {}).get(provider, "")

    _validate_provider(feature, provider)
    if feature != "mineru":
        _validate_base_url(provider, base_url)
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key is required")

    if feature in ("llm", "llm_fallback"):
        result = _test_llm(api_key, base_url, model)
    elif feature == "vlm":
        result = _test_vlm(api_key, base_url, model)
    elif feature == "embedding":
        result = _test_embedding(api_key, base_url, model)
    else:
        result = _test_mineru(api_key)

    result.feature = feature
    result.provider = provider
    _write_audit_event(
        admin_user_id,
        "config.test",
        {"feature": feature, "provider": provider, "success": result.success},
    )
    return result


# ========== 测试实现 ==========

def _test_llm(api_key: str, base_url: str, model: str) -> TestResult:
    """测试语言处理 API（LA-DEPLOY-FIX: 严格使用用户传入的 model）"""
    # 如果没有传入模型，返回错误提示而非硬编码猜测
    if not model:
        return TestResult(
            feature="llm", provider="", model="",
            success=False,
            message="未选择模型，请从下拉框选择或输入自定义模型名称"
        )
    
    start = time.time()
    try:
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,  # 严格使用用户传入的模型
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 10,
        }
        
        resp = requests.post(url, headers=headers, json=payload, timeout=15, allow_redirects=False)
        latency = (time.time() - start) * 1000
        
        if resp.status_code == 200:
            data = resp.json()
            used_model = data.get("model", model)
            return TestResult(
                feature="llm",
                provider="",
                model=used_model,
                success=True,
                message=f"连接成功",
                latency_ms=round(latency, 1),
            )
        else:
            error = resp.text[:200]
            # 如果是模型名称错误，给出更友好的提示
            if "model" in error.lower() and ("not found" in error.lower() or "invalid" in error.lower() or "supported" in error.lower()):
                return TestResult(
                    feature="llm",
                    provider="",
                    model=model,
                    success=False,
                    message=f"模型名称可能不正确: {model}。错误: {error}",
                    latency_ms=round(latency, 1),
                )
            return TestResult(
                feature="llm",
                provider="",
                model=model,
                success=False,
                message=f"API 错误 (HTTP {resp.status_code}): {error}",
                latency_ms=round(latency, 1),
            )
    except requests.exceptions.Timeout:
        return TestResult(
            feature="llm", provider="", model=model,
            success=False, message="请求超时，请检查网络连接"
        )
    except Exception as e:
        return TestResult(
            feature="llm", provider="", model=model,
            success=False, message=f"连接失败: {str(e)[:200]}"
        )


def _test_vlm(api_key: str, base_url: str, model: str) -> TestResult:
    """测试视觉处理 API（使用最小图片测试）"""
    start = time.time()
    try:
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # 1x1 像素透明 PNG 的 base64
        tiny_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        payload = {
            "model": model or "glm-4.5v",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{tiny_png}"}},
                        {"type": "text", "text": "What is this?"},
                    ],
                }
            ],
            "max_tokens": 10,
        }
        
        resp = requests.post(url, headers=headers, json=payload, timeout=15, allow_redirects=False)
        latency = (time.time() - start) * 1000
        
        if resp.status_code == 200:
            return TestResult(
                feature="vlm", provider="", model=model,
                success=True, message="连接成功",
                latency_ms=round(latency, 1)
            )
        else:
            error = resp.text[:200]
            return TestResult(
                feature="vlm", provider="", model=model,
                success=False, message=f"API 错误 (HTTP {resp.status_code}): {error}",
                latency_ms=round(latency, 1)
            )
    except requests.exceptions.Timeout:
        return TestResult(
            feature="vlm", provider="", model=model,
            success=False, message="请求超时，请检查网络连接"
        )
    except Exception as e:
        return TestResult(
            feature="vlm", provider="", model=model,
            success=False, message=f"连接失败: {str(e)[:200]}"
        )


def _test_embedding(api_key: str, base_url: str, model: str) -> TestResult:
    """测试文本向量化 API"""
    start = time.time()
    try:
        url = f"{base_url.rstrip('/')}/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or "embedding-3",
            "input": ["test"],
        }
        
        resp = requests.post(url, headers=headers, json=payload, timeout=15, allow_redirects=False)
        latency = (time.time() - start) * 1000
        
        if resp.status_code == 200:
            data = resp.json()
            emb = data.get("data", [{}])[0].get("embedding", [])
            dim = len(emb)
            return TestResult(
                feature="embedding", provider="", model=model,
                success=True, message=f"连接成功，维度: {dim}",
                latency_ms=round(latency, 1)
            )
        else:
            error = resp.text[:200]
            return TestResult(
                feature="embedding", provider="", model=model,
                success=False, message=f"API 错误 (HTTP {resp.status_code}): {error}",
                latency_ms=round(latency, 1)
            )
    except requests.exceptions.Timeout:
        return TestResult(
            feature="embedding", provider="", model=model,
            success=False, message="请求超时，请检查网络连接"
        )
    except Exception as e:
        return TestResult(
            feature="embedding", provider="", model=model,
            success=False, message=f"连接失败: {str(e)[:200]}"
        )


def _test_mineru(token: str) -> TestResult:
    """测试 MinerU CLI 可用性（支持开发模式 + PyInstaller 打包）"""
    try:
        from core.mineru_client import _resolve_mineru_cli_path
        
        # LA-DEPLOY: 使用统一的 CLI 路径解析（支持 _MEIPASS / _internal / 开发模式）
        cli_path = _resolve_mineru_cli_path()
        
        if not cli_path:
            return TestResult(
                feature="mineru", provider="mineru", model="",
                success=False, message="未找到 MinerU CLI。请确保 tools/mineru/ 目录下有 CLI 可执行文件，或已安装 MinerU。"
            )
        
        # 检查 token
        if not token:
            return TestResult(
                feature="mineru", provider="mineru", model="",
                success=False, message="Token 未配置"
            )
        
        return TestResult(
            feature="mineru", provider="mineru", model="",
            success=True, message=f"CLI 已找到: {cli_path}"
        )
    except Exception as e:
        return TestResult(
            feature="mineru", provider="mineru", model="",
            success=False, message=f"检测失败: {str(e)[:200]}"
        )
