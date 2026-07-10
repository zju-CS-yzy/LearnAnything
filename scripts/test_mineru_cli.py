"""
MinerU CLI 测试脚本
调用本地已安装的 mineru-open-api 工具，测试 PDF 解析效果。

前置条件:
    1. 已安装 mineru-open-api CLI（PowerShell: irm ... | iex）
    2. 已配置 MinerU Token（环境变量 $env:MINERU_TOKEN 或 --token 参数）

用法:
    cd D:\MyCS\AI\Project\LearnAnything
    python scripts\test_mineru_cli.py

CLI 用法参考: docs/mineru-cli-guide.md
"""

import os
import sys
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List


# ========== 配置（开箱即用，无需手动设置环境变量）==========

# 如果 CLI 不在 PATH 中，直接指定路径（Windows 默认安装位置）
# 安装脚本: irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex
# 默认安装位置: C:\Users\<用户名>\.mineru\bin\mineru-open-api.exe
MINERU_CLI_PATH = os.environ.get(
    "MINERU_CLI_PATH",
    r"C:\Users\lenovo\.mineru\bin\mineru-open-api.exe"
)

# MinerU Token（从环境变量读取，或从 API.txt 读取，或脚本内指定）
MINERU_TOKEN = os.environ.get("MINERU_TOKEN", "")
# 如果环境变量未设置，尝试从项目 API.txt 读取
if not MINERU_TOKEN:
    api_txt_path = Path(__file__).parent.parent / "API.txt"
    if api_txt_path.exists():
        content = api_txt_path.read_text(encoding="utf-8")
        # 查找 MinerU 行
        for line in content.split("\n"):
            if line.strip().startswith("MinerU:"):
                MINERU_TOKEN = line.strip().split(":", 1)[1].strip()
                break

# 测试 PDF 目录
TEST_PDF_DIR = Path(__file__).parent.parent / "knowledge_base" / "generic" / "raw"

# 输出目录
OUTPUT_DIR = Path(__file__).parent.parent / "scripts" / "mineru_test_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# CLI 可执行文件名称
CLI_NAME = "mineru-open-api"


# ========== 自动查找 CLI 路径 ==========

def find_mineru_cli() -> str:
    """
    查找 mineru-open-api CLI 可执行文件路径。

    搜索顺序:
        1. 脚本顶部硬编码的默认路径 (MINERU_CLI_PATH)
        2. 环境变量 MINERU_CLI_PATH
        3. 系统 PATH (shutil.which)
        4. 常见安装目录

    Returns:
        完整可执行文件路径

    Raises:
        FileNotFoundError: 找不到 CLI
    """
    # 1. 脚本内置默认路径
    default_path = Path(MINERU_CLI_PATH)
    if default_path.exists():
        return str(default_path)

    # 2. 环境变量指定（优先级高于默认但低于内置路径）
    env_path = os.environ.get("MINERU_CLI_PATH", "")
    if env_path and Path(env_path).exists():
        return env_path

    # 3. 系统 PATH
    path_cmd = shutil.which(CLI_NAME)
    if path_cmd:
        return path_cmd

    # 4. 常见安装目录搜索（Windows）
    search_dirs = [
        Path.home() / ".local" / "bin",
        Path.home() / "AppData" / "Local" / "Programs" / "mineru-open-api",
        Path.home() / "AppData" / "Roaming" / "mineru-open-api",
        Path.home() / "mineru-open-api",
        Path("C:") / "ProgramData" / "mineru-open-api",
        Path("C:") / "Program Files" / "mineru-open-api",
        Path("C:") / "Program Files (x86)" / "mineru-open-api",
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        exe_name = CLI_NAME + ".exe"
        exe_path = search_dir / exe_name
        if exe_path.exists():
            return str(exe_path)

        for subdir in search_dir.iterdir():
            if subdir.is_dir():
                exe_path = subdir / exe_name
                if exe_path.exists():
                    return str(exe_path)

    # 5. 遍历用户目录（应急搜索，限制深度）
    home = Path.home()
    for root, dirs, files in os.walk(home):
        depth = root.count(os.sep) - str(home).count(os.sep)
        if depth > 3:
            del dirs[:]
            continue
        if CLI_NAME + ".exe" in files:
            return os.path.join(root, CLI_NAME + ".exe")

    raise FileNotFoundError(
        f"找不到 {CLI_NAME} CLI。\n"
        f"请确认已安装: irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex\n"
        f"或修改脚本顶部 MINERU_CLI_PATH 变量指向正确路径。"
    )


# ========== CLI 调用封装 ==========

class MinerUCLIClient:
    """MinerU CLI 客户端封装。"""
    
    def __init__(self, cli_path: str, token: str = ""):
        self.cli_path = cli_path
        self.token = token
        self._version = None
    
    def _run(self, args: List[str]) -> subprocess.CompletedProcess:
        """执行 CLI 命令。"""
        cmd = [self.cli_path] + args
        print(f"[CLI] 执行: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result
    
    def version(self) -> str:
        """获取 CLI 版本。"""
        result = self._run(["version"])
        if result.returncode == 0:
            return result.stdout.strip()
        return f"unknown (exit={result.returncode})"
    
    def extract(self, pdf_path: Path, output_dir: Path, token: str = "", format: str = "md") -> Path:
        """
        使用 Extract 模式解析 PDF（需要 Token）。
        
        Args:
            pdf_path: PDF 文件路径
            output_dir: 输出目录
            token: API Token（为空则使用环境变量或初始化时的 token）
            format: 输出格式，默认 md
        
        Returns:
            输出目录路径（包含 Markdown 等文件）
        """
        use_token = token or self.token
        if not use_token:
            raise ValueError("Extract 模式需要 Token，请设置 token 参数或环境变量 MINERU_TOKEN")
        
        args = [
            "extract",
            str(pdf_path),
            "-o", str(output_dir),
            "-f", format,
            "--token", use_token,
        ]
        
        result = self._run(args)
        
        if result.returncode != 0:
            print(f"[CLI] ❌ 错误输出:\n{result.stderr}")
            raise RuntimeError(f"MinerU CLI 执行失败 (exit={result.returncode})")
        
        print(f"[CLI] ✅ 解析完成")
        if result.stdout.strip():
            print(f"[CLI] 输出:\n{result.stdout[:1000]}")
        
        return output_dir
    
    def flash_extract(self, pdf_path: Path) -> str:
        """
        使用 Flash 模式解析 PDF（免 Token，限制 10MB/20页）。
        
        Args:
            pdf_path: PDF 文件路径
        
        Returns:
            Markdown 文本内容
        """
        args = [
            "flash-extract",
            str(pdf_path),
        ]
        
        result = self._run(args)
        
        if result.returncode != 0:
            print(f"[CLI] ❌ 错误输出:\n{result.stderr}")
            raise RuntimeError(f"MinerU CLI 执行失败 (exit={result.returncode})")
        
        return result.stdout


# ========== 测试流程 ==========

def test_mineru_cli():
    """测试 MinerU CLI 是否能正常工作。"""
    print("=" * 60)
    print("🔍 步骤 1: 查找 MinerU CLI")
    print("=" * 60)
    
    try:
        cli_path = find_mineru_cli()
        print(f"✅ 找到 CLI: {cli_path}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        print("\n💡 解决方案:")
        print("   1. 确认已安装 CLI: irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex")
        print("   2. 或设置环境变量: $env:MINERU_CLI_PATH=\"C:\\path\\to\\mineru-open-api.exe\"")
        print("   3. 或修改脚本顶部 MINERU_CLI_PATH 变量")
        sys.exit(1)
    
    client = MinerUCLIClient(cli_path, token=MINERU_TOKEN)
    
    # 测试版本
    print(f"\n🔍 步骤 2: 验证 CLI 版本")
    version = client.version()
    print(f"✅ CLI 版本: {version}")
    
    return client


def test_flash_mode(client: MinerUCLIClient, test_pdf: Path) -> str:
    """测试 Flash 模式（免 Token）。"""
    print(f"\n{'=' * 60}")
    print("🔍 步骤 3: 测试 Flash 模式（免 Token）")
    print(f"=" * 60)
    print(f"📄 测试文件: {test_pdf.name}")
    print(f"📄 文件大小: {test_pdf.stat().st_size / 1024:.1f} KB")
    
    # 检查文件大小限制（Flash 模式 ≤ 10MB）
    if test_pdf.stat().st_size > 10 * 1024 * 1024:
        print(f"⚠️ 文件超过 10MB，Flash 模式可能失败，将跳过此测试")
        return ""
    
    try:
        markdown = client.flash_extract(test_pdf)
        
        # 保存结果
        output_file = OUTPUT_DIR / f"mineru_flash_{test_pdf.stem[:30]}.md"
        output_file.write_text(markdown, encoding="utf-8")
        print(f"✅ Flash 模式成功，输出保存到: {output_file}")
        print(f"   输出长度: {len(markdown)} 字符")
        
        # 预览
        preview = markdown[:1000].replace("\n", " ")
        print(f"\n📝 预览（前1000字符）:\n{preview}...")
        
        return markdown
    except Exception as e:
        print(f"❌ Flash 模式失败: {e}")
        return ""


def test_extract_mode(client: MinerUCLIClient, test_pdf: Path) -> Optional[Path]:
    """测试 Extract 模式（需要 Token）。"""
    print(f"\n{'=' * 60}")
    print("🔍 步骤 4: 测试 Extract 模式（需要 Token）")
    print(f"=" * 60)
    print(f"📄 测试文件: {test_pdf.name}")
    print(f"📄 文件大小: {test_pdf.stat().st_size / 1024:.1f} KB")
    
    if not MINERU_TOKEN:
        print("❌ 未设置 MinerU Token，跳过 Extract 模式测试")
        print("   请设置环境变量: $env:MINERU_TOKEN=\"your-token\"")
        return None
    
    # 创建临时输出目录
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "mineru_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            client.extract(test_pdf, output_dir, token=MINERU_TOKEN, format="md")
            
            # 查找输出文件
            md_files = list(output_dir.rglob("*.md"))
            if md_files:
                md_file = md_files[0]
                markdown = md_file.read_text(encoding="utf-8")
                
                # 保存到永久目录
                final_output = OUTPUT_DIR / f"mineru_extract_{test_pdf.stem[:30]}.md"
                final_output.write_text(markdown, encoding="utf-8")
                print(f"✅ Extract 模式成功，输出保存到: {final_output}")
                print(f"   输出长度: {len(markdown)} 字符")
                
                # 列出所有输出文件
                all_files = list(output_dir.rglob("*"))
                print(f"\n📁 输出目录结构:")
                for f in all_files:
                    if f.is_file():
                        rel = f.relative_to(output_dir)
                        print(f"   {rel} ({f.stat().st_size / 1024:.1f} KB)")
                
                # 预览
                preview = markdown[:1000].replace("\n", " ")
                print(f"\n📝 预览（前1000字符）:\n{preview}...")
                
                return final_output
            else:
                print(f"⚠️ 未找到 Markdown 输出文件，输出目录内容:")
                for f in output_dir.rglob("*"):
                    print(f"   {f.relative_to(output_dir)}")
                return None
        except Exception as e:
            print(f"❌ Extract 模式失败: {e}")
            return None


def compare_with_pymupdf(test_pdf: Path) -> str:
    """用 PyMuPDF 提取，作为对比基准。"""
    print(f"\n{'=' * 60}")
    print("📋 步骤 5: PyMuPDF 提取（对比基准）")
    print(f"=" * 60)
    
    try:
        import fitz
        doc = fitz.open(str(test_pdf))
        texts = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text().strip()
            if text:
                texts.append(f"--- Page {page_num + 1} ---\n{text}")
        doc.close()
        
        pymupdf_text = "\n\n".join(texts)
        
        output_file = OUTPUT_DIR / f"pymupdf_{test_pdf.stem[:30]}.txt"
        output_file.write_text(pymupdf_text, encoding="utf-8")
        print(f"✅ PyMuPDF 输出已保存: {output_file}")
        print(f"   文本长度: {len(pymupdf_text)} 字符")
        
        return pymupdf_text
    except Exception as e:
        print(f"❌ PyMuPDF 提取失败: {e}")
        return ""


def main():
    print("=" * 60)
    print("🧪 MinerU CLI 测试脚本")
    print("=" * 60)
    
    # 1. 查找 CLI 并验证
    client = test_mineru_cli()
    
    # 2. 选择测试 PDF
    pdf_files = list(TEST_PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"❌ 未在 {TEST_PDF_DIR} 找到 PDF 文件")
        sys.exit(1)
    
    # 优先选择 RAG Fusion（较小，测试快），再选最小的
    test_pdf = None
    for pf in pdf_files:
        if "RAG" in pf.name and "Fusion" in pf.name:
            test_pdf = pf
            break
    if not test_pdf:
        test_pdf = min(pdf_files, key=lambda p: p.stat().st_size)
    
    # 3. 测试 Flash 模式
    flash_md = test_flash_mode(client, test_pdf)
    
    # 4. 测试 Extract 模式
    extract_md = test_extract_mode(client, test_pdf)
    
    # 5. PyMuPDF 对比
    pymupdf_text = compare_with_pymupdf(test_pdf)
    
    # 6. 总结
    print(f"\n{'=' * 60}")
    print("📊 测试总结")
    print(f"=" * 60)
    print(f"   Flash 模式: {'✅ 成功' if flash_md else '❌ 失败/跳过'}")
    print(f"   Extract 模式: {'✅ 成功' if extract_md else '❌ 失败/跳过'}")
    print(f"   PyMuPDF: {'✅ 完成' if pymupdf_text else '❌ 失败'}")
    print(f"\n所有输出保存在: {OUTPUT_DIR}")
    print(f"{'=' * 60}")
    
    if not flash_md and not extract_md:
        print("\n⚠️ 两种模式均失败，请检查:")
        print("   1. CLI 是否正确安装并可执行")
        print("   2. 网络是否能访问 MinerU 云端服务")
        print("   3. Token 是否有效（Extract 模式）")
        sys.exit(1)
    else:
        print("\n✅ 至少一种模式成功，可以继续集成到项目。")


if __name__ == "__main__":
    main()
