#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLM 客户端 — 封装智谱 GLM-4.5V 多模态 API
支持图片理解、表格提取、流程图分析、公式识别
"""

import base64
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import requests

from config.settings import ZHIPU_API_KEY, ZHIPU_EMBEDDING_BASE_URL


class VLMClient:
    """
    视觉语言模型客户端（智谱 GLM-4.5V）

    使用智谱统一 API Key，复用 ZHIPU_API_KEY 和 base_url。
    """

    # 模型名称
    MODEL = "glm-4.5v"
    
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

    def __init__(self):
        self.api_key = ZHIPU_API_KEY
        self.base_url = ZHIPU_EMBEDDING_BASE_URL.rstrip("/")
        self.available = bool(self.api_key)
        if not self.available:
            print("[VLMClient] Warning: ZHIPU_API_KEY not set, VLM features disabled")

    def _image_to_base64(self, image_path: str) -> str:
        """将图片文件转为 base64 编码"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _image_bytes_to_base64(self, image_bytes: bytes) -> str:
        """将图片 bytes 转为 base64 编码"""
        return base64.b64encode(image_bytes).decode("utf-8")

    def _call_api(self, messages: List[Dict[str, Any]], max_tokens: int = 4096) -> Optional[str]:
        """调用智谱 VLM API"""
        if not self.available:
            return None

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            
            # LA-035: 打印详细业务错误码
            if resp.status_code != 200:
                try:
                    error_data = resp.json()
                    error_code = error_data.get("error", {}).get("code", "unknown")
                    error_message = error_data.get("error", {}).get("message", resp.text[:200])
                    print(f"[VLMClient] ERROR: API 返回错误 (HTTP {resp.status_code})")
                    print(f"[VLMClient]   业务错误码: {error_code}")
                    print(f"[VLMClient]   错误消息: {error_message}")
                    print(f"[VLMClient]   模型: {self.MODEL}")
                except Exception:
                    print(f"[VLMClient] ERROR: API 返回错误 (HTTP {resp.status_code}): {resp.text[:200]}")
                return None
            
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[VLMClient] API call failed: {e}")
            return None

    def analyze_image(self, image_path: str, task: str = "describe") -> Optional[str]:
        """
        分析单张图片。

        Args:
            image_path: 图片文件路径
            task: 任务类型 — describe/table/formula/diagram/chart

        Returns:
            VLM 生成的文本描述，失败返回 None
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
        分析 PDF 页面图片。

        Args:
            page_image_bytes: 页面渲染后的 PNG bytes
            page_type: 页面类型 — table/formula/diagram/chart/image/scan
            page_num: 页码（用于日志）

        Returns:
            结构化文本描述
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
        print(f"[VLMClient] Page {page_num} done in {elapsed:.1f}s")

        return result

    def batch_analyze(self, items: List[Tuple[bytes, str, int]]) -> List[Optional[str]]:
        """
        批量分析多个页面。

        Args:
            items: [(image_bytes, page_type, page_num), ...]

        Returns:
            [result_text, ...]（与输入顺序一致）
        """
        results = []
        for img_bytes, ptype, pnum in items:
            result = self.analyze_pdf_page(img_bytes, ptype, pnum)
            results.append(result)
        return results


# 便捷函数

def vlm_describe(image_path: str) -> Optional[str]:
    """便捷函数：描述图片内容"""
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
