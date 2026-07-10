"""
MinerU PDF 批量测试脚本
测试 3-5 个不同 PDF，分析 MinerU 提取效果，对比 PyMuPDF。

用法:
    cd D:\MyCS\AI\Project\LearnAnything
    python scripts\test_mineru_batch.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mineru_client import MinerUClient
from core.document_processor import DocumentProcessor


# 测试文件列表（不同特征）
TEST_PDFS = [
    # 1. 表格测试：Attention 进阶面试题（含复杂表格、公式）
    {
        "path": r"D:\MyCS\AI\Project\IWork\yuque_download\pdfs\Attention 进阶面试题.pdf",
        "name": "Attention进阶面试题",
        "features": ["表格", "公式", "架构图"],
    },
    # 2. 纯文本测试：RAG Fusion（以文字为主）
    {
        "path": r"D:\MyCS\AI\Project\LearnAnything\knowledge_base\generic\raw\RAG Fusion优化策略面试题.pdf",
        "name": "RAG_Fusion",
        "features": ["流程图", "列表", "公式"],
    },
    # 3. 公式测试：Transformers（大量公式）
    {
        "path": r"D:\MyCS\AI\Project\IWork\yuque_download\pdfs\Transformers 操作面试题.pdf",
        "name": "Transformers操作",
        "features": ["公式", "代码"],
    },
    # 4. 表格密集：大模型微调（表格+数据）
    {
        "path": r"D:\MyCS\AI\Project\IWork\yuque_download\pdfs\大模型微调面试题.pdf",
        "name": "大模型微调",
        "features": ["表格", "对比数据"],
    },
]

OUTPUT_DIR = Path(__file__).parent.parent / "scripts" / "mineru_batch_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def analyze_markdown(markdown_text: str) -> dict:
    """分析 Markdown 文本的结构特征。"""
    lines = markdown_text.split("\n")
    
    # 标题统计
    h1 = [l for l in lines if l.startswith("# ") and not l.startswith("## ")]
    h2 = [l for l in lines if l.startswith("## ") and not l.startswith("### ")]
    h3 = [l for l in lines if l.startswith("### ") and not l.startswith("#### ")]
    
    # 图片
    images = [l for l in lines if l.strip().startswith("![")]
    
    # 公式
    block_formulas = re.findall(r'\$\$(.*?)\$\$', markdown_text, re.DOTALL)
    inline_formulas = re.findall(r'(?<!\$)\$(?!\$)([^\$]+)\$(?!\$)', markdown_text)
    
    # 表格
    table_lines = [l for l in lines if l.strip().startswith("|")]
    
    # 列表
    unordered = [l for l in lines if re.match(r'^\s*[-*+]\s', l)]
    ordered = [l for l in lines if re.match(r'^\s*\d+\.\s', l)]
    
    # 代码块
    code_blocks = markdown_text.count("```") // 2
    
    return {
        "total_chars": len(markdown_text),
        "total_lines": len(lines),
        "headings": {"h1": len(h1), "h2": len(h2), "h3": len(h3), "samples_h2": [l[:60] for l in h2[:5]]},
        "images": {"count": len(images), "samples": [l[:80] for l in images[:3]]},
        "formulas": {"block": len(block_formulas), "inline": len(inline_formulas), "samples": [f[:80] for f in block_formulas[:3]]},
        "tables": {"lines": len(table_lines), "samples": [l[:80] for l in table_lines[:5]]},
        "lists": {"unordered": len(unordered), "ordered": len(ordered)},
        "code_blocks": code_blocks,
    }


def test_single_pdf(client: MinerUClient, pdf_info: dict) -> dict:
    """测试单个 PDF。"""
    path = Path(pdf_info["path"])
    if not path.exists():
        print(f"  [SKIP] 文件不存在: {path}")
        return None
    
    print(f"\n  文件: {pdf_info['name']} ({path.stat().st_size/1024:.0f} KB)")
    print(f"  特征: {', '.join(pdf_info['features'])}")
    
    result = {"name": pdf_info["name"], "features": pdf_info["features"], "path": str(path)}
    
    # --- MinerU 解析 ---
    try:
        print(f"  [MinerU] 解析中...")
        md_text, output_dir, img_paths = client.parse_pdf_to_markdown(str(path))
        
        # 保存 Markdown
        md_file = OUTPUT_DIR / f"mineru_{pdf_info['name']}.md"
        md_file.write_text(md_text, encoding="utf-8")
        
        # 分析结构
        analysis = analyze_markdown(md_text)
        result["mineru"] = {
            "chars": analysis["total_chars"],
            "chunks_estimated": analysis["headings"]["h2"] + 1,  # 估算 chunk 数
            **analysis,
        }
        
        print(f"  [MinerU] OK - {analysis['total_chars']} chars, "
              f"{analysis['headings']['h2']} H2, "
              f"{analysis['formulas']['block']} block-formulas, "
              f"{analysis['images']['count']} images, "
              f"{analysis['tables']['lines']} table-lines")
        
    except Exception as e:
        print(f"  [MinerU] ERROR: {e}")
        result["mineru"] = {"error": str(e)}
    
    # --- PyMuPDF 解析（对比）---
    try:
        print(f"  [PyMuPDF] 解析中...")
        processor = DocumentProcessor(pdf_engine="pymupdf")
        chunks = processor.process_file(str(path), subject="test", source_name=path.name)
        
        # 估算纯文本长度
        total_text = "\n".join(c["text"] for c in chunks)
        
        result["pymupdf"] = {
            "chunks": len(chunks),
            "chars": len(total_text),
        }
        print(f"  [PyMuPDF] OK - {len(chunks)} chunks, {len(total_text)} chars")
        
    except Exception as e:
        print(f"  [PyMuPDF] ERROR: {e}")
        result["pymupdf"] = {"error": str(e)}
    
    return result


def main():
    print("=" * 70)
    print("MinerU PDF Batch Test - 3~5 PDFs")
    print("=" * 70)
    
    client = MinerUClient()
    print(f"CLI: {client.cli_path}")
    print(f"Token: {'OK' if client.has_token() else 'MISSING'}")
    
    results = []
    for pdf_info in TEST_PDFS:
        result = test_single_pdf(client, pdf_info)
        if result:
            results.append(result)
    
    # 保存汇总
    summary_file = OUTPUT_DIR / "batch_test_summary.json"
    summary_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 打印汇总表
    print(f"\n{'=' * 70}")
    print("Summary Table")
    print(f"{'=' * 70}")
    print(f"{'Name':<18} {'Chars(M/P)':<14} {'H2':<4} {'Formulas':<9} {'Images':<7} {'Tables':<7} {'Status':<10}")
    print("-" * 70)
    
    for r in results:
        m = r.get("mineru", {})
        p = r.get("pymupdf", {})
        chars = f"{m.get('chars',0)}/{p.get('chars',0)}"
        h2 = str(m.get('headings', {}).get('h2', 0))
        formulas = str(m.get('formulas', {}).get('block', 0) + m.get('formulas', {}).get('inline', 0))
        images = str(m.get('images', {}).get('count', 0))
        tables = str(m.get('tables', {}).get('lines', 0))
        status = "OK" if "error" not in m else "FAIL"
        print(f"{r['name']:<18} {chars:<14} {h2:<4} {formulas:<9} {images:<7} {tables:<7} {status:<10}")
    
    print(f"\n详细结果保存到: {OUTPUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    import re
    main()
