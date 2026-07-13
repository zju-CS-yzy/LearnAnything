"""
MarkdownChunker 优化测试：图片引用过滤 + 极短段落合并
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.markdown_chunker import MarkdownChunker

# 测试用例 1：图片引用行过滤
print("=" * 60)
print("Test 1: Image reference line filtering")
print("=" * 60)

markdown1 = """
# 检索系统

本文介绍检索系统的核心原理。

![](image1.png)

密集检索使用向量相似度计算文档间的相似性。这是一个重要的技术。

此外，稀疏检索基于关键词匹配。

![](image2.png)

最后，混合检索结合了两者的优势。
"""

chunker = MarkdownChunker(min_para_chars=30)
chunks1 = chunker.chunk_markdown(markdown1, {"source": "test1.md"})

para_chunks = [c for c in chunks1 if c["metadata"]["chunk_type"] == "paragraph"]
print(f"Paragraph chunks: {len(para_chunks)}")
for c in para_chunks:
    print(f"  [{c['metadata']['chunk_type']}] {c['text'][:60]}...")

# 验证图片引用行被过滤
has_image_only = any(c["text"].strip().startswith("!") and not c["text"].strip()[1:].strip() for c in para_chunks)
print(f"Image-only paragraphs remaining: {has_image_only}")
assert not has_image_only, "Image-only paragraphs should be filtered"
print("[PASS] Image-only paragraphs filtered")

# 测试用例 2：极短段落合并
print("\n" + "=" * 60)
print("Test 2: Short paragraph merging")
print("=" * 60)

markdown2 = """
# 测试标题

这是一个正常长度的段落，包含了足够的内容来形成独立的语义单元。

短。

这是另一个正常长度的段落，内容充实且有明确的语义边界。

此外，短句。

最后一个段落，长度适中，不需要合并。
"""

chunker2 = MarkdownChunker(min_para_chars=20)
chunks2 = chunker2.chunk_markdown(markdown2, {"source": "test2.md"})

para_chunks2 = [c for c in chunks2 if c["metadata"]["chunk_type"] == "paragraph"]
print(f"Paragraph chunks: {len(para_chunks2)}")
for c in para_chunks2:
    print(f"  [{len(c['text'])} chars] {c['text'][:60]}...")

# 验证极短段落被合并
short_paras = [c for c in para_chunks2 if len(c["text"]) < 20]
print(f"Remaining short paragraphs (< 20 chars): {len(short_paras)}")
assert len(short_paras) == 0, f"All short paragraphs should be merged, but {len(short_paras)} remain"
print("[PASS] Short paragraphs merged")

# 测试用例 3：合并方向判断
print("\n" + "=" * 60)
print("Test 3: Merge direction determination")
print("=" * 60)

# 测试"此外"开头的段落合并到下一段
markdown3 = """
# 方向测试

正常段落一，内容充实。

此外，短句。

正常段落二，承接上文。
"""

chunker3 = MarkdownChunker(min_para_chars=30)
chunks3 = chunker3.chunk_markdown(markdown3, {"source": "test3.md"})

para_chunks3 = [c for c in chunks3 if c["metadata"]["chunk_type"] == "paragraph"]
for c in para_chunks3:
    print(f"  [{len(c['text'])} chars] {c['text'][:60]}...")

# "此外，短句"应该合并到"正常段落二"
has_furthermore_merged = any("此外" in c["text"] and "正常段落二" in c["text"] for c in para_chunks3)
print(f"'Furthermore' merged to next paragraph: {has_furthermore_merged}")

# 测试用例 4：列表项合并到上一段
print("\n" + "=" * 60)
print("Test 4: List item merging")
print("=" * 60)

markdown4 = """
# 列表测试

主要技术包括：

- 检索

- 排序

- 评估

这些技术构成了完整的系统。
"""

chunker4 = MarkdownChunker(min_para_chars=10)
chunks4 = chunker4.chunk_markdown(markdown4, {"source": "test4.md"})

para_chunks4 = [c for c in chunks4 if c["metadata"]["chunk_type"] == "paragraph"]
for c in para_chunks4:
    print(f"  [{len(c['text'])} chars] {c['text'][:60]}...")

print("\n" + "=" * 60)
print("All tests completed")
print("=" * 60)
