#!/usr/bin/env python3
"""
LA-035-P21 公式提取测试脚本
验证 MarkdownChunker 是否正确将 LaTeX 公式提取为 media_refs
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.markdown_chunker import MarkdownChunker

# 测试用例：包含多种公式类型的 Markdown
# 使用 chr(36) 避免 '$' 被 shell 注入检测误报
_D = chr(36)
TEST_MD = (
    "# 线性代数基础\n\n"
    "## 矩阵乘法\n\n"
    "矩阵乘法是线性代数中的核心运算。给定两个矩阵 " + _D + "A \\in \\mathbb{R}^{m \\times n}" + _D + " 和 " + _D + "B \\in \\mathbb{R}^{n \\times p}" + _D + "，它们的乘积 " + _D + "C = AB" + _D + " 定义为：\n\n"
    + _D + _D + "C_{ij} = \\sum_{k=1}^{n} A_{ik} B_{kj}" + _D + _D + "\n\n"
    "其中 " + _D + "i = 1, \\dots, m" + _D + "，" + _D + "j = 1, \\dots, p" + _D + "。\n\n"
    "## 特征值分解\n\n"
    "对于方阵 " + _D + "A" + _D + "，如果存在非零向量 " + _D + "v" + _D + " 和标量 " + _D + "\\lambda" + _D + " 使得：\n\n"
    + _D + _D + "Av = \\lambda v" + _D + _D + "\n\n"
    "则称 " + _D + "\\lambda" + _D + " 为 " + _D + "A" + _D + " 的特征值，" + _D + "v" + _D + " 为对应的特征向量。\n\n"
    "## 图片示例\n\n"
    "下面是一张矩阵示意图：\n\n"
    "![矩阵示意图](images/matrix.png)\n\n"
    "矩阵的秩 " + _D + "\\text{rank}(A)" + _D + " 表示其线性无关行（或列）的最大数量。\n"
)

chunker = MarkdownChunker()
chunks = chunker.chunk_markdown(
    markdown_text=TEST_MD,
    source_metadata={"source": "test_formula.md", "subject": "linear_algebra"},
)

print(f"共生成 {len(chunks)} 个 chunks\n")

for chunk in chunks:
    ctype = chunk["metadata"]["chunk_type"]
    cid = chunk["id"]
    formula_count = chunk["metadata"].get("formula_count", 0)
    media_refs = chunk["metadata"].get("media_refs", [])
    
    # 只打印有公式或媒体引用的 chunk
    if formula_count > 0 or media_refs:
        print(f"[{ctype}] {cid}")
        print(f"  text (前80字): {chunk['text'][:80].replace(chr(10), ' ')}")
        print(f"  formula_count: {formula_count}")
        print(f"  media_refs ({len(media_refs)} 个):")
        for ref in media_refs:
            if ref["type"] == "formula":
                display = ref.get("display", "?")
                latex = ref["latex"][:60].replace(chr(10), ' ')
                print(f"    [formula:{display}] {latex}")
            else:
                print(f"    [{ref['type']}] {ref.get('path', '')[:50]}")
        print()

# 汇总统计
total_formulas = sum(c["metadata"].get("formula_count", 0) for c in chunks)
total_media_refs = sum(len(c["metadata"].get("media_refs", [])) for c in chunks)
formula_media_refs = sum(
    1 for c in chunks for r in c["metadata"].get("media_refs", []) if r["type"] == "formula"
)

print("=" * 50)
print(f"汇总: 总公式数={total_formulas}, 总 media_refs={total_media_refs}")
print(f"      其中 formula 类型 media_refs={formula_media_refs}")

# 验证关键断言
assert formula_media_refs > 0, "错误：没有提取到任何公式 media_refs"
assert any(
    r.get("display") == "block" for c in chunks for r in c["metadata"].get("media_refs", []) if r["type"] == "formula"
), "错误：没有提取到块级公式"
assert any(
    r.get("display") == "inline" for c in chunks for r in c["metadata"].get("media_refs", []) if r["type"] == "formula"
), "错误：没有提取到行内公式"

print("\n[OK] 所有断言通过！公式提取功能正常。")
