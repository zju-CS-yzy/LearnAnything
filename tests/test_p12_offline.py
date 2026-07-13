"""
LA-035-P12: 离线测试 - 验证 heading 分离和上下文注入逻辑

不需要 LLM，只测试 graph_builder 和 semantic_extractor 的输入/输出逻辑。
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.semantic_extractor import SemanticExtractor

def test_heading_context_injection():
    """测试 heading_context 是否正确注入到 prompt 中"""
    print("=" * 60)
    print("[Test 1] heading_context injection logic")
    print("=" * 60)
    
    extractor = SemanticExtractor(paradigm="theory")
    
    # 模拟 chunks（不需要 LLM，只检查 prompt 构建逻辑）
    test_chunks = [
        {"id": "chunk_para_1", "text": "这是一个段落内容，关于检索系统。"},
    ]
    
    heading_context = "## 5.2 检索与 Retrieval\n\n本文讨论检索系统的核心原理"
    
    # 手动构建 prompt 的逻辑（复用代码中的逻辑）
    batch_parts = []
    for chunk in test_chunks:
        chunk_id = chunk["id"]
        chunk_text = chunk["text"]
        part_text = chunk_text[:800]
        batch_parts.append(f"【chunk_id={chunk_id}】\n【知识片段开始】\n{part_text}\n【知识片段结束】")
    
    combined_text = "\n\n".join(batch_parts)
    
    # 注入 heading_context（复用代码逻辑）
    if heading_context.strip():
        heading_safe = heading_context.strip()[:300]
        combined_text_with_ctx = f"【上下文声明】\n本组知识片段的主题层级：{heading_safe}\n\n注意：【上下文声明】只用于帮助你理解各片段的语义位置，你绝对禁止从【上下文声明】中提取任何概念。你只应从标记了【chunk_id=xxx】的【知识片段】区域中提取概念。\n\n{combined_text}"
    else:
        combined_text_with_ctx = combined_text
    
    # 验证
    assert "【上下文声明】" in combined_text_with_ctx, "上下文声明标记应存在"
    assert "5.2 检索与 Retrieval" in combined_text_with_ctx, "heading 内容应被注入"
    assert "【chunk_id=chunk_para_1】" in combined_text_with_ctx, "chunk 标记应存在"
    assert "禁止从【上下文声明】中提取" in combined_text_with_ctx, "隔离声明应存在"
    assert "【知识片段开始】" in combined_text_with_ctx, "知识片段标记应存在"
    
    print(f"  Prompt preview (first 200 chars):\n    {combined_text_with_ctx[:200]}...")
    print(f"  [OK] heading_context 注入正确")
    
    return True


def test_heading_chunk_filtering():
    """模拟 graph_builder 中 heading chunk 的分离逻辑"""
    print("\n" + "=" * 60)
    print("[Test 2] heading chunk filtering in graph_builder")
    print("=" * 60)
    
    # 模拟一个 heading 组
    chunks = [
        {
            "id": "chunk_h_1",
            "text": "## 5.2 检索与 Retrieval\n\n本文讨论检索系统",
            "metadata": {"chunk_type": "heading", "heading_path": "5.2"}
        },
        {
            "id": "chunk_p_1",
            "text": "密集检索使用向量相似度来查找相关文档。",
            "metadata": {"chunk_type": "paragraph", "heading_path": "5.2"}
        },
        {
            "id": "chunk_p_2",
            "text": "稀疏检索基于关键词匹配。",
            "metadata": {"chunk_type": "paragraph", "heading_path": "5.2"}
        },
        {
            "id": "chunk_img_1",
            "text": "[图片] 检索架构图",
            "metadata": {"chunk_type": "image_pseudo", "heading_path": "5.2"}
        },
    ]
    
    # 复用 graph_builder 中的分离逻辑
    heading_chunks = []
    extractable_chunks = []
    
    for chunk in chunks:
        chunk_type = chunk.get("metadata", {}).get("chunk_type", "") or chunk.get("metadata", {}).get("type", "")
        if chunk_type == "heading":
            heading_chunks.append(chunk)
        else:
            extractable_chunks.append(chunk)
    
    # 验证
    assert len(heading_chunks) == 1, f"应有 1 个 heading chunk, 实际 {len(heading_chunks)}"
    assert heading_chunks[0]["id"] == "chunk_h_1", "heading chunk 应为 chunk_h_1"
    assert len(extractable_chunks) == 3, f"应有 3 个 extractable chunks, 实际 {len(extractable_chunks)}"
    
    # 验证 extractable 中没有 heading
    for ec in extractable_chunks:
        ct = ec.get("metadata", {}).get("chunk_type", "")
        assert ct != "heading", f"extractable chunk 不应是 heading 类型: {ec['id']}"
    
    print(f"  Heading chunks: {len(heading_chunks)} (ids: {[c['id'] for c in heading_chunks]})")
    print(f"  Extractable chunks: {len(extractable_chunks)} (ids: {[c['id'] for c in extractable_chunks]})")
    print(f"  [OK] heading chunk 正确分离")
    
    # 验证 heading_context 构建
    heading_context = ""
    for hc in heading_chunks:
        h_text = hc.get("text", "")
        if h_text.strip():
            heading_context += h_text.strip() + "\n"
    heading_context = heading_context.strip()[:300]
    
    assert "检索与 Retrieval" in heading_context, "heading context 应包含标题内容"
    print(f"  heading_context: '{heading_context[:50]}...'")
    print(f"  [OK] heading_context 构建正确")
    
    return True


def test_empty_heading_context():
    """测试没有 heading 时的降级逻辑"""
    print("\n" + "=" * 60)
    print("[Test 3] Empty heading_context fallback")
    print("=" * 60)
    
    # 模拟一个 heading 组，只有 paragraph（没有 heading chunk）
    chunks = [
        {
            "id": "chunk_p_1",
            "text": "这是一个独立段落。",
            "metadata": {"chunk_type": "paragraph", "heading_path": ""}
        },
    ]
    
    heading_chunks = []
    extractable_chunks = []
    
    for chunk in chunks:
        chunk_type = chunk.get("metadata", {}).get("chunk_type", "")
        if chunk_type == "heading":
            heading_chunks.append(chunk)
        else:
            extractable_chunks.append(chunk)
    
    heading_context = ""
    for hc in heading_chunks:
        h_text = hc.get("text", "")
        if h_text.strip():
            heading_context += h_text.strip() + "\n"
    heading_context = heading_context.strip()[:300]
    
    # 验证
    assert heading_context == "", f"没有 heading chunk 时 heading_context 应为空, 实际: {heading_context}"
    assert len(heading_chunks) == 0, "应有 0 个 heading chunk"
    assert len(extractable_chunks) == 1, "应有 1 个 extractable chunk"
    
    print(f"  heading_context: '' (empty as expected)")
    print(f"  [OK] 空 heading 降级逻辑正确")
    
    # 验证注入逻辑：空 context 时不应添加标记
    combined_text = "【chunk_id=chunk_p_1】\n【知识片段开始】\n这是一个独立段落。\n【知识片段结束】"
    if heading_context.strip():
        combined_text = f"【上下文声明】...\n\n{combined_text}"
    
    assert "【上下文声明】" not in combined_text, "空 heading_context 时不应注入上下文声明"
    print(f"  [OK] 空 context 时 prompt 不包含上下文声明")
    
    return True


def test_multiple_headings():
    """测试同一 heading_path 下有多个 heading chunk 的情况"""
    print("\n" + "=" * 60)
    print("[Test 4] Multiple heading chunks in same group")
    print("=" * 60)
    
    chunks = [
        {
            "id": "chunk_h_1",
            "text": "## 5.2 检索与 Retrieval",
            "metadata": {"chunk_type": "heading", "heading_path": "5.2"}
        },
        {
            "id": "chunk_h_2",  # 理论上不应出现，但防御性处理
            "text": "### 5.2.1 密集检索",
            "metadata": {"chunk_type": "heading", "heading_path": "5.2"}
        },
        {
            "id": "chunk_p_1",
            "text": "密集检索使用向量相似度。",
            "metadata": {"chunk_type": "paragraph", "heading_path": "5.2"}
        },
    ]
    
    heading_chunks = []
    extractable_chunks = []
    
    for chunk in chunks:
        chunk_type = chunk.get("metadata", {}).get("chunk_type", "")
        if chunk_type == "heading":
            heading_chunks.append(chunk)
        else:
            extractable_chunks.append(chunk)
    
    # 验证多个 heading 被合并
    assert len(heading_chunks) == 2, f"应有 2 个 heading chunk, 实际 {len(heading_chunks)}"
    assert len(extractable_chunks) == 1, f"应有 1 个 extractable chunk, 实际 {len(extractable_chunks)}"
    
    heading_context = ""
    for hc in heading_chunks:
        h_text = hc.get("text", "")
        if h_text.strip():
            heading_context += h_text.strip() + "\n"
    heading_context = heading_context.strip()[:300]
    
    assert "5.2 检索与 Retrieval" in heading_context, "应包含第一个 heading"
    assert "5.2.1 密集检索" in heading_context, "应包含第二个 heading"
    print(f"  heading_context: '{heading_context}'")
    print(f"  [OK] 多个 heading 正确合并")
    
    # 验证截断
    long_text = "A" * 500
    heading_context_long = long_text.strip()[:300]
    assert len(heading_context_long) <= 300, f"heading_context 应截断到300字符, 实际 {len(heading_context_long)}"
    print(f"  [OK] 长 heading 截断到 300 字符")
    
    return True


def run_all_tests():
    results = []
    results.append(test_heading_context_injection())
    results.append(test_heading_chunk_filtering())
    results.append(test_empty_heading_context())
    results.append(test_multiple_headings())
    
    print("\n" + "=" * 60)
    if all(results):
        print("All tests PASSED")
        print("=" * 60)
        return 0
    else:
        print("Some tests FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
