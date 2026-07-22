#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Client
接入 DeepSeek API，支持聊天和流式输出。
所有引用 LLMClient 的模块在此实现下会真正工作。

使用方式:
    from core.llm_client import LLMClient
    client = LLMClient()
    response = client.chat(messages, temperature=0.3, max_tokens=800)

环境变量:
    DEEPSEEK_API_KEY: API Key（必须设置）
    DEEPSEEK_BASE_URL: 可选，默认 https://api.deepseek.com/v1
    DEEPSEEK_MODEL: 可选，默认 deepseek-chat
"""

import os
import time
from typing import List, Dict, Any, Optional

import requests


class LLMClient:
    """LLM 客户端 — 接入 DeepSeek API"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
        timeout: int = 60,
        max_retries: int = 2,
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")).rstrip("/")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.timeout = timeout
        self.max_retries = max_retries
        self._available = None

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
    ) -> str:
        """
        发送对话请求，返回文本内容。

        Args:
            messages: 消息列表，每个消息包含 role 和 content
            temperature: 温度参数
            max_tokens: 最大返回 token 数
            system_prompt: 可选的系统提示，会插入到 messages 最前面

        Returns:
            模型返回的文本内容

        Raises:
            RuntimeError: API Key 未设置或请求失败
        """
        if not self.available:
            raise RuntimeError(
                "LLMClient unavailable: DEEPSEEK_API_KEY not set. "
                "Please set environment variable DEEPSEEK_API_KEY."
            )

        # 构建请求消息
        req_messages = list(messages)
        if system_prompt:
            req_messages.insert(0, {"role": "system", "content": system_prompt})

        payload = {
            "model": self.model,
            "messages": req_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()

                # 提取返回内容
                choices = data.get("choices", [])
                if not choices:
                    raise RuntimeError("LLM response has no choices")

                content = choices[0].get("message", {}).get("content", "")
                if not content:
                    raise RuntimeError("LLM response content is empty")

                return content.strip()

            except requests.exceptions.HTTPError as e:
                # 如果是 429（限流）或 5xx，重试
                status = e.response.status_code
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

        raise RuntimeError(f"LLM request failed after {self.max_retries + 1} attempts: {last_exception}")

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
                "LLMClient unavailable: DEEPSEEK_API_KEY not set. "
                "Please set environment variable DEEPSEEK_API_KEY."
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
