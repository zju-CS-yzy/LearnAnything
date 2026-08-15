#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLM Client (LA-DEPLOY-FEAT)

按功能模块读取配置：视觉处理 (vlm)
支持任意 OpenAI 兼容的多模态 API。

LA-050: 稳定性增强（重试机制 + 降级策略）
"""

import base64
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import requests

from config.settings import get_vlm_config


class VLMClient:
    """
    视觉语言模型客户端 (LA-DEPLOY-FEAT)

    按功能模块读取配置，支持任意 OpenAI 兼容的多模态 API。
    LA-050: 增加重试机制和降级策略，提升 API 调用稳定性。
    """

    # LA-050: 重试配置
    MAX_RETRIES = 3
    MAX_TIMEOUT_RETRIES = 1
    BASE_RETRY_DELAY = 2  # 秒
    # requests 的二元组分别表示连接超时和响应读取超时。
    # VLM 对复杂课件图片的推理经常超过 60 秒，因此给模型响应更充足的
    # 时间；纯超时只额外重试一次，避免批量导入时单张坏图长期阻塞。
    CONNECT_TIMEOUT = 15
    READ_TIMEOUT = 180
    
    # 系统提示词 — 根据任务类型切换
    SYSTEM_PROMPTS = {
        "describe": (
            "你是一位专业的文档分析助手。请仔细分析图片内容，"
            "用清晰、准确的中文描述图片中的关键信息。"
            "如果是图表，请描述数据趋势和关键数值。"
            "如果是示意图，请描述其结构和各部分的含义。"
            "如果是截图，请提取其中的关键文本信息。"
        ),
        "table": (
            "你是一位表格提取专家。请将图片中的表格转换为 Markdown 格式输出。\n"
            "要求：\n"
            "1. 保持表格的完整结构（表头、行列对齐）\n"
            "2. 所有单元格内容必须准确提取，不得遗漏\n"
            "3. 合并单元格用空值占位或标注说明\n"
            "4. 如果表格有标题，请在表格上方注明\n"
            "5. 只输出 Markdown 表格，不要额外解释\n"
            "6. 如果内容过多，确保每列至少保留关键信息"
        ),
        "formula": (
            "你是一位数学公式识别专家。请识别图片中的数学公式，"
            "并用 LaTeX 格式输出。\n"
            "要求：\n"
            "1. 准确识别所有数学符号、希腊字母、上下标\n"
            "2. 复杂公式使用标准的 LaTeX 语法\n"
            "3. 如果图片包含多个公式，请分别列出\n"
            "4. 只输出 LaTeX 代码，用 $$ 包裹行间公式，$ 包裹行内公式\n"
            "5. 如果识别不确定，标注 [?]"
        ),
        "diagram": (
            "你是一位流程图分析专家。请分析图片中的流程图或架构图，"
            "用结构化的文本描述其内容。\n"
            "要求：\n"
            "1. 描述整体结构和目的\n"
            "2. 列出所有节点/步骤及其关系\n"
            "3. 标注关键分支和判断条件\n"
            "4. 如果涉及数据流，描述输入和输出\n"
            "5. 使用清晰的层级结构（标题、列表、缩进）"
        ),
        "chart": (
            "你是一位数据分析专家。请分析图片中的数据图表，"
            "提取关键数据并用文本描述。\n"
            "要求：\n"
            "1. 说明图表类型（柱状图/折线图/饼图/散点图等）\n"
            "2. 列出所有数据系列及其数值\n"
            "3. 描述数据趋势和关键特征\n"
            "4. 标注最大值、最小值、异常点\n"
            "5. 如果包含坐标轴，标注坐标轴含义和单位"
        ),
    }

    def __init__(self, model: Optional[str] = None):
        # LA-DEPLOY-FEAT: 按功能模块读取配置
        cfg = get_vlm_config()
        self.api_key = cfg.api_key
        self.base_url = (cfg.base_url or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        self.model = model or cfg.model or "glm-4.5v"
        self.available = bool(self.api_key)
        if not self.available:
            print("[VLMClient] Warning: 视觉处理 API 未配置，VLM 功能已禁用")

    def _image_to_base64(self, image_path: str) -> str:
        """将图片文件转为 base64 编码"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _image_bytes_to_base64(self, image_bytes: bytes) -> str:
        """将图片 bytes 转为 base64 编码"""
        return base64.b64encode(image_bytes).decode("utf-8")

    def _call_api(self, messages: List[Dict[str, Any]], max_tokens: int = 4096) -> Optional[str]:
        """
        调用智谱 VLM API（LA-050: 增加重试机制和降级策略）

        重试策略:
            - HTTP 可重试错误/连接错误最多重试 MAX_RETRIES 次
            - 响应超时最多重试 MAX_TIMEOUT_RETRIES 次
            - 指数退避: delay = BASE_RETRY_DELAY * (2 ** attempt)
            - 仅对可重试错误（HTTP 429/500/502/503/504、超时、连接错误）进行重试
            - 对 400 类错误（请求参数错误）不重试

        降级策略:
            - 所有重试耗尽后返回 None
            - 调用方负责处理 None（使用空描述或跳过）
        """
        if not self.available:
            return None

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }

        request_timeout = (self.CONNECT_TIMEOUT, self.READ_TIMEOUT)
        timeout_failures = 0

        # LA-050: 重试循环
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=request_timeout)
                
                # 成功
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
                
                # LA-050: 解析错误响应
                error_code = "unknown"
                error_message = resp.text[:200]
                try:
                    error_data = resp.json()
                    error_code = error_data.get("error", {}).get("code", "unknown")
                    error_message = error_data.get("error", {}).get("message", resp.text[:200])
                except Exception:
                    pass

                # LA-050: 判断是否需要重试
                # 可重试: 429(限流) / 500 / 502 / 503 / 504
                # 不可重试: 400 / 401 / 403 / 404
                if resp.status_code in (429, 500, 502, 503, 504):
                    if attempt < self.MAX_RETRIES:
                        delay = self.BASE_RETRY_DELAY * (2 ** attempt)
                        print(f"[VLMClient] LA-050: 可重试错误 (HTTP {resp.status_code}, code={error_code})，"
                              f"第 {attempt + 1}/{self.MAX_RETRIES} 次重试，等待 {delay}s...")
                        time.sleep(delay)
                        continue
                    else:
                        print(f"[VLMClient] LA-050: 重试耗尽 (HTTP {resp.status_code}, code={error_code})，"
                              f"返回 None 降级")
                        return None
                else:
                    # 不可重试错误，直接返回 None
                    print(f"[VLMClient] LA-050: 不可重试错误 (HTTP {resp.status_code}, code={error_code})，"
                          f"message={error_message}，跳过")
                    return None

            except requests.exceptions.Timeout:
                # 超时 — 可重试
                timeout_failures += 1
                if timeout_failures <= self.MAX_TIMEOUT_RETRIES and attempt < self.MAX_RETRIES:
                    delay = self.BASE_RETRY_DELAY * (2 ** attempt)
                    print(
                        f"[VLMClient] LA-050: 请求超时（连接 {self.CONNECT_TIMEOUT}s / "
                        f"响应 {self.READ_TIMEOUT}s），第 {timeout_failures}/{self.MAX_TIMEOUT_RETRIES} "
                        f"次超时重试，等待 {delay}s..."
                    )
                    time.sleep(delay)
                    continue
                else:
                    print(
                        f"[VLMClient] LA-050: 重试耗尽（超时；连接 {self.CONNECT_TIMEOUT}s / "
                        f"响应 {self.READ_TIMEOUT}s），返回 None 降级"
                    )
                    return None

            except requests.exceptions.ConnectionError as e:
                # 连接错误 — 可重试
                if attempt < self.MAX_RETRIES:
                    delay = self.BASE_RETRY_DELAY * (2 ** attempt)
                    print(f"[VLMClient] LA-050: 连接错误 ({e})，第 {attempt + 1}/{self.MAX_RETRIES} 次重试，"
                          f"等待 {delay}s...")
                    time.sleep(delay)
                    continue
                else:
                    print(f"[VLMClient] LA-050: 重试耗尽（连接错误），返回 None 降级")
                    return None

            except Exception as e:
                # 其他异常 — 不可重试
                print(f"[VLMClient] LA-050: 未预期异常 ({type(e).__name__}: {e})，返回 None")
                return None

        # 理论上不会到达这里，但作为兜底
        print(f"[VLMClient] LA-050: 所有重试路径已耗尽，返回 None")
        return None

    def analyze_image(self, image_path: str, task: str = "describe") -> Optional[str]:
        """
        分析单张图片。

        Args:
            image_path: 图片文件路径
            task: 任务类型 — describe/table/formula/diagram/chart

        Returns:
            VLM 生成的文本描述，失败返回 None（LA-050: 调用方需处理 None）
        """
        system_prompt = self.SYSTEM_PROMPTS.get(task, self.SYSTEM_PROMPTS["describe"])
        b64 = self._image_to_base64(image_path)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {"type": "text", "text": "请分析这张图片。"},
                ],
            },
        ]

        return self._call_api(messages)

    def analyze_image_bytes(self, image_bytes: bytes, task: str = "describe") -> Optional[str]:
        """分析图片 bytes（避免写临时文件）"""
        system_prompt = self.SYSTEM_PROMPTS.get(task, self.SYSTEM_PROMPTS["describe"])
        b64 = self._image_bytes_to_base64(image_bytes)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {"type": "text", "text": "请分析这张图片。"},
                ],
            },
        ]

        return self._call_api(messages)

    def analyze_pdf_page(self, page_image_bytes: bytes, page_type: str, page_num: int) -> Optional[str]:
        """
        分析 PDF 页面图片（LA-050: 增加降级处理）。

        Args:
            page_image_bytes: 页面渲染后的 PNG bytes
            page_type: 页面类型 — table/formula/diagram/chart/image/scan
            page_num: 页码（用于日志）

        Returns:
            结构化文本描述，失败返回 None（调用方应使用空描述继续流程）
        """
        task_map = {
            "table": "table",
            "formula_heavy": "formula",
            "formula": "formula",
            "diagram": "diagram",
            "chart": "chart",
            "image": "describe",
            "scan": "describe",
            "mixed": "describe",
        }
        task = task_map.get(page_type, "describe")

        print(f"[VLMClient] Analyzing page {page_num} (type={page_type}, task={task})...")
        start = time.time()
        result = self.analyze_image_bytes(page_image_bytes, task=task)
        elapsed = time.time() - start

        if result is None:
            print(f"[VLMClient] LA-050: Page {page_num} FAILED after retries, returning None (downgrade)")
        else:
            print(f"[VLMClient] Page {page_num} done in {elapsed:.1f}s")

        return result

    def batch_analyze(self, items: List[Tuple[bytes, str, int]]) -> List[Optional[str]]:
        """
        批量分析多个页面（LA-050: 单个失败不影响整体流程）。

        Args:
            items: [(image_bytes, page_type, page_num), ...]

        Returns:
            [result_text, ...]（与输入顺序一致，失败项为 None）
        """
        results = []
        success_count = 0
        for img_bytes, ptype, pnum in items:
            result = self.analyze_pdf_page(img_bytes, ptype, pnum)
            results.append(result)
            if result is not None:
                success_count += 1
        
        print(f"[VLMClient] LA-050: Batch analyze complete | "
              f"success={success_count}/{len(items)}, failed={len(items) - success_count}")
        return results


# 便捷函数

def vlm_describe(image_path: str) -> Optional[str]:
    """便捷函数：描述图片内容（LA-050: 失败返回 None）"""
    client = VLMClient()
    return client.analyze_image(image_path, task="describe")


def vlm_extract_table(image_path: str) -> Optional[str]:
    """便捷函数：提取表格为 Markdown"""
    client = VLMClient()
    return client.analyze_image(image_path, task="table")


def vlm_extract_formula(image_path: str) -> Optional[str]:
    """便捷函数：识别公式为 LaTeX"""
    client = VLMClient()
    return client.analyze_image(image_path, task="formula")
