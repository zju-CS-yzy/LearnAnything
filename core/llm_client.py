#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Client (LA-DEPLOY-FEAT)

按功能模块读取配置：语言处理 (llm)
支持任意 OpenAI 兼容 API：DeepSeek、OpenAI、硅基流动等。

使用方式:
    from core.llm_client import LLMClient
    client = LLMClient()
    response = client.chat(messages, temperature=0.3, max_tokens=800)
"""

import os
import time
from typing import List, Dict, Any, Optional

import requests

from config.settings import get_llm_config, get_llm_fallback_config


class LLMClient:
    """LLM 客户端 — 语言处理功能

    支持任意 OpenAI 兼容 API：DeepSeek、Kimi、OpenAI、硅基流动等。
    支持两种方式初始化：
    1. 直接使用参数传入（保留旧兼容）
    2. 从功能配置创建（推荐新代码使用）

    使用方式:
        from core.llm_client import LLMClient
        client = LLMClient()  # 自动读取 llm 配置
        response = client.chat(messages, temperature=0.3, max_tokens=800)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 2,
        feature_config=None,
    ):
        """
        Args:
            api_key: API Key（直接传入，优先级最高）
            base_url: API Base URL
            model: 模型名称
            timeout: 请求超时（秒）
            max_retries: 最大重试次数
            feature_config: FeatureConfig 对象，传入时从中读取配置
                           用于支持多 Provider 切换（Kimi/DeepSeek 等）
        """
        # LA-ROBUST: 区分三种初始化模式，防止跨 Provider 配置污染
        # 模式1: 显式 feature_config（推荐新代码）
        # 模式2: 显式参数传入（如 from_provider）
        # 模式3: 无显式配置，回退到全局配置 + 环境变量（兼容旧代码）

        if feature_config is not None:
            # 模式1: 从 feature_config 读取，支持 api_key/base_url/model 覆盖
            self.api_key = (api_key if api_key is not None else feature_config.api_key) or ""
            self.base_url = ((base_url if base_url is not None else feature_config.base_url) or "").rstrip("/")
            self.model = (model if model is not None else feature_config.model) or ""
            _mode = "feature_config"
        elif api_key is not None or base_url is not None or model is not None:
            # 模式2: 显式参数，严格使用传入值，不回退到全局配置
            self.api_key = api_key or ""
            self.base_url = (base_url or "").rstrip("/")
            self.model = model or ""
            _mode = "explicit"
        else:
            # 模式3: 回退到全局配置 + 环境变量兜底（兼容旧代码）
            cfg = get_llm_config()
            self.api_key = cfg.api_key or ""
            self.base_url = (cfg.base_url or "").rstrip("/")
            self.model = cfg.model or ""
            _mode = "fallback"

            # 环境变量兜底（仅兼容模式）
            if not self.api_key:
                self.api_key = os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("KIMI_API_KEY", "")
            if not self.base_url:
                self.base_url = (os.getenv("DEEPSEEK_BASE_URL", "") or os.getenv("KIMI_BASE_URL", "https://api.deepseek.com/v1")).rstrip("/")
            if not self.model:
                self.model = os.getenv("DEEPSEEK_MODEL", "") or os.getenv("KIMI_MODEL", "deepseek-chat")

        self.timeout = timeout
        self.max_retries = max_retries
        self._available = None

        # LA-ROBUST: 调试日志，帮助排查多 Provider 切换问题
        import hashlib
        key_hash = hashlib.md5(self.api_key.encode()).hexdigest()[:6] if self.api_key else "(empty)"
        print(f"[LLMClient] init mode={_mode}, base_url={self.base_url}, model={self.model}, key_hash={key_hash}")

    @classmethod
    def from_feature_config(cls, feature_config, timeout: int = 60, max_retries: int = 2):
        """从 FeatureConfig 创建 LLMClient（推荐新代码使用）。

        Args:
            feature_config: settings.FeatureConfig 对象
            timeout: 请求超时（秒）
            max_retries: 最大重试次数

        Returns:
            LLMClient 实例
        """
        return cls(
            feature_config=feature_config,
            timeout=timeout,
            max_retries=max_retries,
        )

    @classmethod
    def from_provider(cls, provider: str, timeout: int = 60, max_retries: int = 2):
        """按 provider 名称创建 LLMClient。

        自动从全局配置中查找对应 provider 的配置。
        用于快速切换模型（如 SemanticExtractor 中指定 provider）。

        Args:
            provider: 提供商名称（deepseek / kimi / openai / siliconflow / custom）
            timeout: 请求超时（秒）
            max_retries: 最大重试次数

        Returns:
            LLMClient 实例，若配置不存在则返回默认配置
        """
        from config.settings import get_full_config

        full_config = get_full_config()
        llm_cfg = full_config.llm

        # 如果当前 LLM 配置就是目标 provider，直接使用
        if llm_cfg.provider == provider:
            return cls.from_feature_config(llm_cfg, timeout, max_retries)

        # 否则尝试从环境变量构造（用户可能配置了多个 provider 但未保存到配置文件）
        # LA-ROBUST: 支持通过环境变量切换 provider
        if provider == "kimi":
            api_key = os.getenv("KIMI_API_KEY", "")
            base_url = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
            model = os.getenv("KIMI_MODEL", "kimi-k2.5")
            if not api_key:
                raise RuntimeError(
                    "Kimi API Key 未配置。请通过以下方式之一配置：\n"
                    "1. 编辑 config/api_config.ini，将 [llm] 段的 provider 改为 'kimi' 并填写 api_key\n"
                    "2. 设置环境变量 KIMI_API_KEY=your_key\n"
                    "3. 在前端选择 '自动（跟随全局配置）'，使用当前已配置的默认 LLM"
                )
            return cls(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout=timeout,
                max_retries=max_retries,
            )
        elif provider == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY", "")
            base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
            model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            if not api_key:
                raise RuntimeError(
                    "DeepSeek API Key 未配置。请通过以下方式之一配置：\n"
                    "1. 编辑 config/api_config.ini，在 [llm] 段填写 api_key\n"
                    "2. 设置环境变量 DEEPSEEK_API_KEY=your_key"
                )
            return cls(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout=timeout,
                max_retries=max_retries,
            )

        # 兜底：返回默认配置
        return cls(timeout=timeout, max_retries=max_retries)

    def _check_available(self) -> bool:
        """检查 LLM 是否可用（有 API Key 即可）"""
        if self._available is not None:
            return self._available
        self._available = bool(self.api_key)
        return self._available

    @property
    def available(self) -> bool:
        return self._check_available()

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 800,
        system_prompt: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """
        发送对话请求，返回文本内容。

        Args:
            messages: 消息列表，每个消息包含 role 和 content
            temperature: 温度参数
            max_tokens: 最大返回 token 数
            system_prompt: 可选的系统提示，会插入到 messages 最前面
            timeout: 可选，覆盖默认超时时间（秒）

        Returns:
            模型返回的文本内容

        Raises:
            RuntimeError: API Key 未设置或请求失败
        """
        if not self.available:
            raise RuntimeError(
                "LLMClient unavailable: 语言处理 API 未配置。"
                "请在首次启动向导中配置语言处理（LLM）API Key。"
            )

        # 构建请求消息
        req_messages = list(messages)
        if system_prompt:
            req_messages.insert(0, {"role": "system", "content": system_prompt})

        # LA-ROBUST: 检测需要特殊处理的模型
        is_kimi_fixed_temp = self.model.startswith("kimi-k2")
        is_deepseek_v4 = self.model.startswith("deepseek-v4")

        # 构建基础 payload
        payload = {
            "model": self.model,
            "messages": req_messages,
            "max_tokens": max_tokens,
        }

        # Kimi K2.x: 不支持 temperature 调整（固定为 1）
        if is_kimi_fixed_temp:
            print(f"[LLMClient] Kimi 固定温度模型: {self.model}, 忽略 temperature 参数")
        else:
            payload["temperature"] = temperature

        # DeepSeek V4: 默认开启 thinking 模式，reasoning_content 占用大量 token
        # 导致 content 为空。关闭 thinking 模式，让输出直接进入 content。
        if is_deepseek_v4:
            print(f"[LLMClient] DeepSeek V4 模型: {self.model}, 关闭 thinking 模式")
            payload["thinking"] = {"type": "disabled"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        last_exception = None
        actual_timeout = timeout or self.timeout
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=actual_timeout,
                )
                response.raise_for_status()
                data = response.json()

                # 提取返回内容
                choices = data.get("choices", [])
                if not choices:
                    raise RuntimeError("LLM response has no choices")

                # LA-ROBUST: 安全提取 content，处理 null / 空字符串 / 缺失的情况
                msg = choices[0].get("message", {})
                content = msg.get("content") or ""
                
                # 调试日志：当 content 为空时打印完整响应结构
                if not content:
                    print(f"[LLMClient] content 为空，message keys: {list(msg.keys())}")
                    print(f"[LLMClient] 完整响应预览: {str(data)[:500]}")
                    raise RuntimeError("LLM response content is empty")

                return content.strip()

            except requests.exceptions.HTTPError as e:
                # LA-ROBUST: 增强 400 错误日志，打印响应体帮助诊断
                status = e.response.status_code
                try:
                    resp_body = e.response.text[:500]
                except:
                    resp_body = "(无法读取响应体)"
                print(f"[LLMClient] HTTP {status} 错误，响应: {resp_body}")
                
                # 如果是 429（限流）或 5xx，重试
                if status in (429, 502, 503, 504) and attempt < self.max_retries:
                    wait = 2 ** attempt
                    time.sleep(wait)
                    continue
                last_exception = e
                break
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                # LA-027 FIX: SSL/连接错误使用指数退避重试（网络不稳定时）
                last_exception = e
                if attempt < self.max_retries:
                    wait = 3 ** attempt  # 3s, 9s, 27s 退避
                    print(f"[LLMClient] SSL/连接错误，{wait}s 后重试 ({attempt+1}/{self.max_retries}): {e}")
                    time.sleep(wait)
                    continue
                break
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    time.sleep(1)
                    continue
                break

        raise RuntimeError(
            f"LLM request failed after {self.max_retries + 1} attempts. "
            f"Last error: {type(last_exception).__name__}: {last_exception}"
        )

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 800,
        system_prompt: Optional[str] = None,
    ):
        """
        流式发送对话请求，返回生成器（逐字/逐句返回）。

        Yields:
            str: 每个 chunk 的文本内容（delta 部分）

        Raises:
            RuntimeError: API Key 未设置或请求失败
        """
        if not self.available:
            raise RuntimeError(
                "LLMClient unavailable: 语言处理 API 未配置。"
                "请在首次启动向导中配置语言处理（LLM）API Key。"
            )

        req_messages = list(messages)
        if system_prompt:
            req_messages.insert(0, {"role": "system", "content": system_prompt})

        payload = {
            "model": self.model,
            "messages": req_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
                stream=True,
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    data = line_str[6:]  # 去掉 "data: " 前缀
                    if data == "[DONE]":
                        break
                    try:
                        import json as _json
                        chunk = _json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except Exception:
                        continue
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"LLM stream request failed: {e}")
        except Exception as e:
            raise RuntimeError(f"LLM stream error: {e}")

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 1200,
        system_prompt: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        发送请求并解析返回为 JSON。
        适合评测、评分等需要结构化输出的场景。

        会自动在 system_prompt 中追加 JSON 输出要求。
        """
        json_system = (
            "你必须以 JSON 格式输出，不要包含任何 markdown 代码块标记或额外解释。"
            "只输出纯 JSON 字符串，确保可以被 Python json.loads 解析。"
        )
        combined_system = f"{system_prompt or ''}\n\n{json_system}".strip()

        content = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=combined_system,
            timeout=timeout,
        )

        # 尝试清理可能的 markdown 代码块
        cleaned = content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        import json as _json
        try:
            return _json.loads(cleaned)
        except _json.JSONDecodeError as e:
            raise RuntimeError(f"LLM returned invalid JSON: {e}\nContent: {cleaned[:500]}")


# ========== LLM-ROBUST: FallbackLLMClient ==========

class FallbackLLMClient:
    """
    LLM-ROBUST: 带自动故障转移的 LLM 客户端。

    包装两个 LLMClient（主 + 备用），当主 LLM 发生可恢复错误时，
    自动切换到备用 LLM 重试。

    使用方式:
        from core.llm_client import FallbackLLMClient
        client = FallbackLLMClient()
        response = client.chat(messages)  # 主失败时自动切备用
    """

    def __init__(
        self,
        primary: Optional[LLMClient] = None,
        fallback: Optional[LLMClient] = None,
        timeout: int = 60,
        max_retries: int = 2,
    ):
        """
        Args:
            primary: 主 LLMClient，None 时从全局配置自动创建
            fallback: 备用 LLMClient，None 时从全局 fallback 配置自动创建
            timeout: 请求超时（秒）
            max_retries: 每个 Provider 的最大重试次数
        """
        # 主 LLM
        if primary is not None:
            self.primary = primary
        else:
            cfg = get_llm_config()
            self.primary = LLMClient.from_feature_config(cfg, timeout=timeout, max_retries=max_retries)

        # 备用 LLM
        if fallback is not None:
            self.fallback = fallback
        else:
            cfg_fb = get_llm_fallback_config()
            if cfg_fb.api_key:
                self.fallback = LLMClient.from_feature_config(cfg_fb, timeout=timeout, max_retries=max_retries)
            else:
                self.fallback = None

        self.fallback_enabled = self.fallback is not None and self.fallback.available
        self.timeout = timeout
        self.max_retries = max_retries

        # 统计信息
        self._stats = {
            "primary_success": 0,
            "primary_fail": 0,
            "fallback_success": 0,
            "fallback_fail": 0,
            "last_error": None,
            "last_fallback_time": None,
        }

        fb_info = f"{self.fallback.model}@{self.fallback.base_url}" if self.fallback_enabled else "disabled"
        print(f"[FallbackLLMClient] primary={self.primary.model}, fallback={fb_info}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 800,
        system_prompt: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """发送对话请求，主 LLM 失败时自动切换到备用 LLM。"""
        actual_timeout = timeout or self.timeout

        # 1. 尝试主 LLM
        try:
            result = self.primary.chat(
                messages=messages, temperature=temperature,
                max_tokens=max_tokens, system_prompt=system_prompt,
                timeout=actual_timeout,
            )
            self._stats["primary_success"] += 1
            return result
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError, requests.exceptions.SSLError,
                requests.exceptions.RequestException, RuntimeError) as e:
            self._stats["primary_fail"] += 1
            self._stats["last_error"] = str(e)
            print(f"[FallbackLLMClient] Primary failed: {type(e).__name__}: {str(e)[:200]}")

            # 2. 主失败，尝试备用 LLM
            if self.fallback_enabled:
                print(f"[FallbackLLMClient] -> fallback {self.fallback.model}")
                self._stats["last_fallback_time"] = time.time()
                try:
                    result = self.fallback.chat(
                        messages=messages, temperature=temperature,
                        max_tokens=max_tokens, system_prompt=system_prompt,
                        timeout=actual_timeout,
                    )
                    self._stats["fallback_success"] += 1
                    print(f"[FallbackLLMClient] Fallback succeeded")
                    return result
                except Exception as e2:
                    self._stats["fallback_fail"] += 1
                    raise RuntimeError(
                        f"Both primary and fallback LLM failed.\n"
                        f"Primary ({self.primary.model}): {e}\n"
                        f"Fallback ({self.fallback.model}): {e2}"
                    )
            else:
                raise

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 800,
        system_prompt: Optional[str] = None,
    ):
        """流式发送对话请求，支持故障转移。"""
        return self._chat_stream_with_fallback(
            messages=messages, temperature=temperature,
            max_tokens=max_tokens, system_prompt=system_prompt,
        )

    def _chat_stream_with_fallback(
        self, messages, temperature, max_tokens, system_prompt,
    ):
        """内部：流式调用的故障转移实现。"""
        primary_failed = False

        try:
            for chunk in self.primary.chat_stream(
                messages=messages, temperature=temperature,
                max_tokens=max_tokens, system_prompt=system_prompt,
            ):
                yield chunk
            self._stats["primary_success"] += 1
            return
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError, requests.exceptions.SSLError,
                requests.exceptions.RequestException, RuntimeError) as e:
            self._stats["primary_fail"] += 1
            self._stats["last_error"] = str(e)
            print(f"[FallbackLLMClient] Primary stream failed: {type(e).__name__}: {str(e)[:200]}")
            primary_failed = True

        if primary_failed and self.fallback_enabled:
            print(f"[FallbackLLMClient] -> fallback stream {self.fallback.model}")
            self._stats["last_fallback_time"] = time.time()
            try:
                for chunk in self.fallback.chat_stream(
                    messages=messages, temperature=temperature,
                    max_tokens=max_tokens, system_prompt=system_prompt,
                ):
                    yield chunk
                self._stats["fallback_success"] += 1
                print(f"[FallbackLLMClient] Fallback stream succeeded")
                return
            except Exception as e2:
                self._stats["fallback_fail"] += 1
                raise RuntimeError(
                    f"Both primary and fallback LLM stream failed.\n"
                    f"Primary ({self.primary.model}): {e}\n"
                    f"Fallback ({self.fallback.model}): {e2}"
                )
        elif primary_failed:
            raise

    def chat_json(self, messages, temperature=0.1, max_tokens=1200,
                  system_prompt=None, timeout=None):
        """发送请求并解析返回为 JSON，支持故障转移。"""
        json_system = (
            "你必须以 JSON 格式输出，不要包含任何 markdown 代码块标记或额外解释。"
            "只输出纯 JSON 字符串，确保可以被 Python json.loads 解析。"
        )
        combined = f"{system_prompt or ''}\n\n{json_system}".strip()
        content = self.chat(messages=messages, temperature=temperature,
                           max_tokens=max_tokens, system_prompt=combined,
                           timeout=timeout)
        cleaned = content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        import json as _json
        try:
            return _json.loads(cleaned)
        except _json.JSONDecodeError as e:
            raise RuntimeError(f"LLM returned invalid JSON: {e}\nContent: {cleaned[:500]}")

    def get_stats(self) -> Dict[str, Any]:
        """获取故障转移统计信息"""
        return dict(self._stats)

    def is_fallback_enabled(self) -> bool:
        """备用 LLM 是否可用"""
        return self.fallback_enabled
