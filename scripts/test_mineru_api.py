"""
MinerU API 测试脚本（修正版 v3）
测试官方 API 对 PDF 的解析效果，与当前 PyMuPDF 方案对比。

官方 API 关键信息：
    - 端点: https://mineru.net/api/v4/extract/task
    - 请求方式: POST, Content-Type: application/json
    - 参数: {"url": "https://文件URL", "model_version": "vlm"}
    - 限制: 只支持 URL 方式，不支持直接上传文件
    - 单文件 ≤ 200MB, 页数 ≤ 200 页
    - 每天 1000 页高优先级额度

使用方式:
    1. 申请 API key: https://mineru.net/apiManage/docs
    2. 设置环境变量: $env:MINERU_API_KEY="your-key"
    3. 运行: python scripts/test_mineru_api.py

实现方案:
    脚本自动将 PDF 上传到临时文件分享服务（file.io 或备选）获取 URL，然后调用 MinerU API。
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Optional

import requests


# ========== 配置 ==========

# MinerU 官方 API 端点
MINERU_API_URL = os.environ.get("MINERU_API_URL", "https://mineru.net/api/v4")

# API Key（从环境变量读取，不提供则提示用户申请）
MINERU_API_KEY = os.environ.get("MINERU_API_KEY", "")

# 测试 PDF 路径（项目中的现有 PDF）
TEST_PDF_DIR = Path(__file__).parent.parent / "knowledge_base" / "generic" / "raw"

# 输出目录
OUTPUT_DIR = Path(__file__).parent.parent / "scripts" / "mineru_test_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 轮询间隔和超时
TASK_POLL_INTERVAL = 5  # 秒
TASK_POLL_TIMEOUT = 300  # 5 分钟


# ========== 临时文件上传服务 ==========

UPLOAD_SERVICES = [
    {
        "name": "file.io",
        "url": "https://file.io",
        "method": "POST",
        "files_key": "file",
        "response_extractor": lambda r: r.json().get("link"),
    },
    {
        "name": "transfer.sh",
        "url": "https://transfer.sh",
        "method": "PUT",
        "custom_upload": True,
        "url_template": "https://transfer.sh/{filename}",
    },
]


def upload_to_temp_file(file_path: Path) -> str:
    """
    将文件上传到临时文件分享服务，获取公开 URL。
    尝试多个服务，直到成功。

    Args:
        file_path: 本地文件路径

    Returns:
        公开访问 URL
    """
    for service in UPLOAD_SERVICES:
        try:
            print(f"[Upload] 尝试上传服务: {service['name']}")

            if service.get("custom_upload"):
                url = service["url_template"].format(filename=file_path.name)
                with open(file_path, "rb") as f:
                    response = requests.put(
                        url,
                        data=f,
                        headers={"Content-Type": "application/octet-stream"},
                        timeout=120,
                    )
            else:
                with open(file_path, "rb") as f:
                    files = {service["files_key"]: (file_path.name, f)}
                    response = requests.post(
                        service["url"],
                        files=files,
                        timeout=120,
                    )

            response.raise_for_status()

            if service.get("custom_upload"):
                url = response.text.strip()
            else:
                url = service["response_extractor"](response)

            if url and url.startswith(("https://", "http://")):
                print(f"[Upload] ✅ 上传成功 ({service['name']}): {url}")
                return url
            else:
                print(f"[Upload] ⚠️ {service['name']} 返回无效 URL: {url[:100] if url else 'None'}")

        except Exception as e:
            print(f"[Upload] ❌ {service['name']} 失败: {e}")
            continue

    # 所有服务都失败
    print("\n" + "=" * 60)
    print("❌ 所有临时文件分享服务均不可用")
    print("=" * 60)
    print("\n替代方案：本地部署 MinerU API")
    print("  1. 安装: uv pip install -e \".[all]\"")
    print("  2. 启动: mineru-api --host 0.0.0.0 --port 8000")
    print("  3. 修改脚本 MINERU_API_URL=\"http://localhost:8000\"")
    print("  4. 本地 API 支持直接上传文件（POST /file_parse）")
    print("\n或者手动将文件上传到 OneDrive/Google Drive 获取公开链接，")
    print("然后修改脚本直接设置 file_url 变量。")
    print("=" * 60)
    raise RuntimeError("无法获取文件公开 URL，所有上传服务失败")


# ========== MinerU 官方 API 客户端 ==========

class MinerUOfficialClient:
    """MinerU 官方云 API 客户端（URL 方式）。"""
    
    def __init__(self, api_key: str, base_url: str = "https://mineru.net/api/v4"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
    
    def submit_task(self, file_url: str, model_version: str = "vlm") -> dict:
        """
        提交解析任务。
        
        Args:
            file_url: 文件的公开 URL
            model_version: 模型版本，默认 "vlm"
        
        Returns:
            API 返回的 JSON（包含 task_id 等）
        """
        url = f"{self.base_url}/extract/task"
        payload = {
            "url": file_url,
            "model_version": model_version,
        }
        
        print(f"[MinerU] 提交解析任务: {url}")
        print(f"[MinerU] 文件 URL: {file_url}")
        print(f"[MinerU] 模型版本: {model_version}")
        
        response = requests.post(
            url,
            headers=self.headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    
    def query_task(self, task_id: str) -> dict:
        """
        查询任务状态。
        """
        url = f"{self.base_url}/extract/task/{task_id}"
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()
    
    def wait_for_task(self, task_id: str, timeout: int = TASK_POLL_TIMEOUT, interval: int = TASK_POLL_INTERVAL) -> dict:
        """
        轮询等待任务完成。
        
        Returns:
            最终任务结果（包含 markdown 等）
        """
        print(f"[MinerU] 轮询任务状态: {task_id}")
        print(f"[MinerU] 超时: {timeout}s, 间隔: {interval}s")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            result = self.query_task(task_id)
            
            # 提取状态（根据实际 API 响应结构调整）
            status = "unknown"
            if isinstance(result, dict):
                if "data" in result and isinstance(result["data"], dict):
                    status = result["data"].get("status", "unknown")
                elif "status" in result:
                    status = result["status"]
            
            print(f"[MinerU] 状态: {status} (已等待 {time.time() - start_time:.0f}s)")
            
            # 检查是否完成（根据实际状态值调整）
            if status in ("completed", "success", "done", "finished"):
                return result
            elif status in ("failed", "error", "failed"):
                print(f"❌ 任务失败: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}")
                raise RuntimeError(f"MinerU 任务失败: {status}")
            
            time.sleep(interval)
        
        raise TimeoutError(f"任务轮询超时 ({timeout}s)")


# ========== 当前 PyMuPDF 提取（对比基准）==========

def extract_with_pymupdf(file_path: Path) -> str:
    """用 PyMuPDF 提取文本，作为对比基准。"""
    try:
        import fitz
        doc = fitz.open(str(file_path))
        texts = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text().strip()
            if text:
                texts.append(f"--- Page {page_num + 1} ---\n{text}")
        doc.close()
        return "\n\n".join(texts)
    except Exception as e:
        return f"[PyMuPDF 提取失败] {e}"


# ========== 结果提取与对比 ==========

def extract_markdown_from_result(result: dict) -> str:
    """
    从 API 返回结果中提取 Markdown 内容。
    处理多种可能的响应结构。
    """
    if not isinstance(result, dict):
        return str(result)[:5000]
    
    # 尝试 data 嵌套结构
    data = result.get("data", result)
    if isinstance(data, dict):
        for key in ["markdown", "md", "text", "content", "result"]:
            if key in data and data[key]:
                return str(data[key])
    
    # 尝试直接字段
    for key in ["markdown", "md", "text", "content", "result"]:
        if key in result and result[key]:
            return str(result[key])
    
    # 返回整个 data 的 JSON 字符串
    return json.dumps(data, ensure_ascii=False, indent=2)[:5000]


def analyze_result(pymupdf_text: str, markdown_text: str, result_json: dict) -> None:
    """打印对比分析。"""
    print("\n" + "=" * 60)
    print("📊 对比分析")
    print("=" * 60)
    
    # 基础统计
    print(f"\n📈 文本长度对比:")
    print(f"   PyMuPDF:  {len(pymupdf_text):>8} 字符")
    print(f"   MinerU:   {len(markdown_text):>8} 字符")
    print(f"   差异:     {len(markdown_text) - len(pymupdf_text):>+8} 字符")
    
    # 检测公式
    latex_inline = markdown_text.count("$") // 2
    latex_block = markdown_text.count("$$")
    print(f"\n📐 LaTeX 公式检测:")
    print(f"   行内公式 ($...$): ~{latex_inline} 个")
    print(f"   块级公式 ($$...$$): ~{latex_block} 个")
    
    # 检测表格
    table_lines = [line for line in markdown_text.split("\n") if line.strip().startswith("|")]
    print(f"\n📊 Markdown 表格检测:")
    print(f"   表格行: {len(table_lines)} 行")
    if table_lines:
        for line in table_lines[:5]:
            print(f"   {line[:80]}")
        if len(table_lines) > 5:
            print(f"   ... 还有 {len(table_lines) - 5} 行")
    
    # 检测标题结构
    headings = [line for line in markdown_text.split("\n") if line.strip().startswith("#")]
    print(f"\n📑 Markdown 标题结构:")
    print(f"   标题总数: {len(headings)} 个")
    for h in headings[:10]:
        print(f"   {h[:80]}")
    if len(headings) > 10:
        print(f"   ... 还有 {len(headings) - 10} 个")
    
    # 检测图片
    images = [line for line in markdown_text.split("\n") if line.strip().startswith("![")]
    print(f"\n🖼️ 图片引用:")
    print(f"   图片引用: {len(images)} 个")
    for img in images[:5]:
        print(f"   {img[:80]}")
    
    # 检测列表
    list_items = [line for line in markdown_text.split("\n") if line.strip().startswith(("- ", "* ", "1. ", "2. "))]
    print(f"\n📝 列表项:")
    print(f"   列表项: {len(list_items)} 个")
    
    # 检测代码块
    code_blocks = markdown_text.count("```")
    print(f"\n💻 代码块:")
    print(f"   代码块标记: {code_blocks // 2} 个")


# ========== 测试主流程 ==========

def main():
    # 检查 API key
    if not MINERU_API_KEY:
        print("=" * 60)
        print("❌ 未找到 MinerU API Key")
        print("=" * 60)
        print("\n请按以下步骤申请并配置：")
        print("1. 访问 https://mineru.net/apiManage/docs 申请 API Key")
        print("2. 在 PowerShell 中设置环境变量:")
        print("   $env:MINERU_API_KEY=\"your-api-key-here\"")
        print("3. 重新运行此脚本")
        print("\n或者修改本脚本顶部 MINERU_API_KEY 变量直接填入")
        print("=" * 60)
        sys.exit(1)
    
    # 查找测试 PDF（文件名可能有编码问题，通过模糊匹配）
    pdf_files = list(TEST_PDF_DIR.glob("*.pdf"))
    test_pdf = None
    for pf in pdf_files:
        if "RAG" in pf.name and "Fusion" in pf.name:
            test_pdf = pf
            break
    
    if not test_pdf:
        # 退而求其次，选最小的 PDF
        test_pdf = min(pdf_files, key=lambda p: p.stat().st_size)
    
    print(f"\n📄 测试文件: {test_pdf.name}")
    print(f"📄 文件大小: {test_pdf.stat().st_size / 1024:.1f} KB")
    print(f"📄 完整路径: {test_pdf}\n")
    
    # 1. PyMuPDF 提取（基准）
    print("=" * 60)
    print("📋 步骤 1: PyMuPDF 提取（当前方案）")
    print("=" * 60)
    pymupdf_text = extract_with_pymupdf(test_pdf)
    
    pymupdf_output = OUTPUT_DIR / "pymupdf_output.txt"
    pymupdf_output.write_text(pymupdf_text, encoding="utf-8")
    print(f"✅ PyMuPDF 输出已保存: {pymupdf_output}")
    print(f"   文本长度: {len(pymupdf_text)} 字符")
    
    # 打印前 1000 字符预览
    preview = pymupdf_text[:1000].replace("\n", " ")
    print(f"\n📝 PyMuPDF 预览（前1000字符）:\n{preview}...\n")
    
    # 2. MinerU 官方 API 解析
    print("=" * 60)
    print("🔍 步骤 2: MinerU 官方 API 解析（对比方案）")
    print("=" * 60)
    
    try:
        # 2.1 上传文件到临时分享服务
        file_url = upload_to_temp_file(test_pdf)
        
        # 2.2 提交 MinerU 任务
        client = MinerUOfficialClient(api_key=MINERU_API_KEY, base_url=MINERU_API_URL)
        submit_result = client.submit_task(file_url, model_version="vlm")
        
        # 保存提交响应
        submit_file = OUTPUT_DIR / "mineru_submit_response.json"
        submit_file.write_text(json.dumps(submit_result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 提交响应已保存: {submit_file}")
        
        # 提取 task_id
        task_id = None
        if isinstance(submit_result, dict):
            if "data" in submit_result and isinstance(submit_result["data"], dict):
                task_id = submit_result["data"].get("task_id") or submit_result["data"].get("id")
            elif "task_id" in submit_result:
                task_id = submit_result["task_id"]
            elif "id" in submit_result:
                task_id = submit_result["id"]
        
        if not task_id:
            print(f"⚠️ 无法提取 task_id，返回结构: {json.dumps(submit_result, ensure_ascii=False, indent=2)[:1000]}")
            print(f"\n尝试直接分析返回的 Markdown 内容...")
            markdown_text = extract_markdown_from_result(submit_result)
        else:
            print(f"\n[MinerU] 任务 ID: {task_id}")
            
            # 2.3 轮询等待任务完成
            final_result = client.wait_for_task(task_id)
            
            # 保存最终结果
            result_file = OUTPUT_DIR / "mineru_result.json"
            result_file.write_text(json.dumps(final_result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"✅ 最终结果已保存: {result_file}")
            
            markdown_text = extract_markdown_from_result(final_result)
        
        # 保存 Markdown
        md_output = OUTPUT_DIR / "mineru_output.md"
        md_output.write_text(markdown_text, encoding="utf-8")
        print(f"✅ Markdown 输出已保存: {md_output}")
        print(f"   文本长度: {len(markdown_text)} 字符")
        
        # 打印预览
        md_preview = markdown_text[:1500].replace("\n", " ")
        print(f"\n📝 MinerU 预览（前1500字符）:\n{md_preview}...\n")
        
        # 3. 对比分析
        analyze_result(pymupdf_text, markdown_text, submit_result if not task_id else final_result)
        
        print(f"\n{'=' * 60}")
        print("✅ 测试完成，所有输出已保存到 scripts/mineru_test_output/")
        print("=" * 60)
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP 错误（状态码 {e.response.status_code}）")
        try:
            error_body = e.response.json()
            print(f"   响应: {json.dumps(error_body, ensure_ascii=False, indent=2)[:1000]}")
        except:
            print(f"   响应: {e.response.text[:1000]}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
