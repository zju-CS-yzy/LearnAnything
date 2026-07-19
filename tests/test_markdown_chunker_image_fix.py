"""
测试 MarkdownChunker 图片引用修复（LA-035-P21）
验证纯图片行（如公式图片）不会在分块时被过滤丢失。
"""

from core.markdown_chunker import MarkdownChunker

def test_image_ref_preservation():
    """测试：纯图片段落不会被过滤导致 image_refs 丢失"""
    
    md_text = """# 第一章 行列式

行列式是线性代数中的重要概念。

![公式：转置行列式](images/formula1.png)

![公式：行列式性质](images/formula2.png)

行列式有以下性质：交换两行，行列式变号。

## 1.1 行列式的定义

行列式是由方阵元素计算得到的一个标量值。

![图1：三阶行列式示例](images/diagram1.png)

对于 n 阶行列式，其值可以通过展开定理计算。

## 1.2 行列式的性质

性质1：|A| = |A^T|
性质2：交换两行变号

![图2：交换两行示意图](images/diagram2.png)

这些性质在线性代数中非常重要。
"""

    chunker = MarkdownChunker()
    chunks = chunker.chunk_markdown(
        markdown_text=md_text,
        source_metadata={"source": "test_formula.pdf", "subject": "linear_algebra"}
    )
    
    # 统计各类型 chunk
    type_counts = {}
    for c in chunks:
        ct = c["metadata"]["chunk_type"]
        type_counts[ct] = type_counts.get(ct, 0) + 1
    
    print(f"=== Chunk 类型分布 ===")
    for ct, count in sorted(type_counts.items()):
        print(f"  {ct}: {count}")
    
    # 检查 heading chunks 的图片引用
    print(f"\n=== Heading Chunk 图片引用检查 ===")
    heading_chunks = [c for c in chunks if c["metadata"]["chunk_type"] == "heading"]
    
    total_image_refs = 0
    for c in heading_chunks:
        img_refs = c["metadata"].get("image_refs", [])
        if img_refs:
            print(f"  [{c['id']}] {len(img_refs)} 个图片引用:")
            for ref in img_refs:
                print(f"    - path={ref.get('path')}, alt={ref.get('alt', '')}")
            total_image_refs += len(img_refs)
    
    # 验证：第一章应该有 2 个公式图片 + 1 个 diagram 图片
    first_chapter = [c for c in heading_chunks if c["metadata"]["heading_level"] == 1]
    if first_chapter:
        fc = first_chapter[0]
        fc_img_count = len(fc["metadata"].get("image_refs", []))
        print(f"\n  第一章 ({fc['metadata']['heading_path']}) 图片引用数: {fc_img_count}")
        
        # 断言：第一章应该有 2 个公式图片（formula1.png, formula2.png）+ 1 个 diagram
        expected_min = 2  # 至少 2 个
        if fc_img_count < expected_min:
            print(f"  ❌ FAIL: 第一章应有至少 {expected_min} 个图片引用，实际只有 {fc_img_count}")
        else:
            print(f"  ✅ PASS: 第一章有 {fc_img_count} 个图片引用，>= {expected_min}")
    
    # 验证：1.1 节应该有 1 个图片
    sec_1_1 = [c for c in heading_chunks if "1.1" in c.get("text", "")]
    if sec_1_1:
        s = sec_1_1[0]
        s_img_count = len(s["metadata"].get("image_refs", []))
        print(f"\n  1.1 节 ({s['metadata']['heading_path']}) 图片引用数: {s_img_count}")
        if s_img_count < 1:
            print(f"  ❌ FAIL: 1.1 节应有至少 1 个图片引用，实际只有 {s_img_count}")
        else:
            print(f"  ✅ PASS: 1.1 节有 {s_img_count} 个图片引用")
    
    print(f"\n=== 总体统计 ===")
    print(f"  Heading chunks: {len(heading_chunks)}")
    print(f"  总图片引用数: {total_image_refs}")
    
    # 旧行为：纯图片行被过滤，第一章的 image_refs 只有 1 个（diagram）
    # 新行为：纯图片行保留引用，第一章的 image_refs 有 3 个（2 公式 + 1 diagram）
    if total_image_refs >= 3:
        print(f"  ✅ PASS: 图片引用未丢失（总计 {total_image_refs} 个）")
    else:
        print(f"  ❌ FAIL: 图片引用丢失（总计 {total_image_refs} 个，期望 >= 3）")


if __name__ == "__main__":
    test_image_ref_preservation()
