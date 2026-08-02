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

import os
import requests
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.settings import (
    AppConfig, FeatureConfig,
    SUPPORTED_PROVIDERS, FEATURE_DEFAULT_MODELS,
    API_CONFIG_PATH, update_config, reload_config,
    is_first_run, check_all_features, is_feature_available,
)


# ========== Pydantic 模型 ==========

class FeatureConfigRequest(BaseModel):
    """单个功能模块配置请求"""
    provider: str = Field(..., description="提供商ID")
    api_key: str = Field(..., description="API Key")
    base_url: str = Field("", description="Base URL（可选，留空使用提供商默认）")
    model: str = Field("", description="模型名称（可选，留空使用功能默认）")
    enabled: bool = Field(True, description="是否启用")
    custom_model: str = Field("", description="自定义模型名称")


class SetupConfigRequest(BaseModel):
    """完整配置请求"""
    llm: FeatureConfigRequest
    llm_fallback: Optional[FeatureConfigRequest] = None  # LLM-ROBUST: 备用 LLM
    vlm: FeatureConfigRequest
    embedding: FeatureConfigRequest
    mineru: FeatureConfigRequest
    mineru_cli_path: str = Field("", description="MinerU CLI 路径（可选）")


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
    config_path: str = Field(..., description="配置文件路径")
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


# ========== API 端点 ==========

@router.get("/status", response_model=SetupStatus)
async def get_setup_status():
    """获取首次启动状态"""
    checks = check_all_features()
    return SetupStatus(
        is_first_run=is_first_run(),
        features_configured=checks,
        config_path=str(API_CONFIG_PATH),
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
async def get_config():
    """获取当前配置（密钥脱敏）"""
    from config.settings import get_full_config
    cfg = get_full_config()
    
    def mask_key(key: str) -> str:
        if len(key) <= 16:
            return "***" if key else ""
        return key[:8] + "..." + key[-4:]
    
    def serialize(fc: FeatureConfig) -> dict:
        return {
            "provider": fc.provider,
            "api_key": mask_key(fc.api_key),
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


@router.get("/config-raw")
async def get_config_raw():
    """获取当前完整配置（包含完整 API Key，仅本地应用使用）"""
    from config.settings import get_full_config
    cfg = get_full_config()

    def serialize(fc: FeatureConfig) -> dict:
        return {
            "provider": fc.provider,
            "api_key": fc.api_key,  # 完整 key，仅本地填充表单
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
async def save_config(request: SetupConfigRequest):
    """保存完整配置"""
    # 验证必填项
    if not request.llm.api_key.strip():
        raise HTTPException(status_code=400, detail="语言处理 (LLM) API Key 不能为空")
    if not request.embedding.api_key.strip():
        raise HTTPException(status_code=400, detail="文本向量化 (Embedding) API Key 不能为空")
    
    # 构建配置
    def to_fc(req: FeatureConfigRequest) -> FeatureConfig:
        # 如果 base_url 为空，使用提供商默认
        base_url = req.base_url.strip()
        if not base_url and req.provider in SUPPORTED_PROVIDERS:
            base_url = SUPPORTED_PROVIDERS[req.provider]["default_base_url"]
        
        # 如果 model 为空，使用功能默认
        model = req.model.strip()
        if not model:
            for feature, defaults in FEATURE_DEFAULT_MODELS.items():
                if req.provider in defaults:
                    # 这里需要外部传入 feature 名，简化处理
                    pass
        
        return FeatureConfig(
            provider=req.provider,
            api_key=req.api_key.strip(),
            base_url=base_url,
            model=model,
            enabled=req.enabled,
            custom_model=req.custom_model.strip(),
        )
    
    config = AppConfig(
        llm=to_fc(request.llm),
        llm_fallback=to_fc(request.llm_fallback) if request.llm_fallback else FeatureConfig(),
        vlm=to_fc(request.vlm),
        embedding=to_fc(request.embedding),
        mineru=to_fc(request.mineru),
        mineru_cli_path=request.mineru_cli_path.strip(),
    )
    
    # 补充默认模型
    for feature in ["llm", "vlm", "embedding"]:
        fc: FeatureConfig = getattr(config, feature)
        if not fc.model and fc.provider in FEATURE_DEFAULT_MODELS.get(feature, {}):
            fc.model = FEATURE_DEFAULT_MODELS[feature][fc.provider]
    
    update_config(config)
    
    return {
        "status": "success",
        "message": "配置已保存",
        "config_path": str(API_CONFIG_PATH),
        "features": check_all_features(),
    }


@router.post("/test/{feature}", response_model=TestResult)
async def test_feature_api(feature: str, request: FeatureConfigRequest):
    """测试单个功能模块的 API 连通性"""
    if feature not in ["llm", "llm_fallback", "vlm", "embedding", "mineru"]:
        raise HTTPException(status_code=400, detail=f"不支持的功能: {feature}")
    
    if not request.api_key.strip():
        raise HTTPException(status_code=400, detail="API Key 不能为空")
    
    # 确定 base_url
    base_url = request.base_url.strip()
    if not base_url and request.provider in SUPPORTED_PROVIDERS:
        base_url = SUPPORTED_PROVIDERS[request.provider]["default_base_url"]
    
    # 确定 model
    model = request.model.strip()
    if not model and feature in FEATURE_DEFAULT_MODELS:
        model = FEATURE_DEFAULT_MODELS[feature].get(request.provider, "")
    
    # 执行测试
    if feature == "llm" or feature == "llm_fallback":
        return _test_llm(request.api_key, base_url, model)
    elif feature == "vlm":
        return _test_vlm(request.api_key, base_url, model)
    elif feature == "embedding":
        return _test_embedding(request.api_key, base_url, model)
    elif feature == "mineru":
        return _test_mineru(request.api_key)
    
    return TestResult(
        feature=feature,
        provider=request.provider,
        model=model,
        success=False,
        message="未知错误",
    )


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
        
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
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
        
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
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
        
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
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
