"""
MarkdownChunker v2.0 测试脚本
验证: 自然段分块、标题树构建、层级归属、chunk 输出格式
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.markdown_chunker import MarkdownChunker

# 测试用例 1: 简单两层结构
TEST_MD_1 = """# 第一章 引言

这是第一章的引言段落。它包含了一些背景信息。

这是第二个自然段，继续阐述引言的内容。

## 1.1 研究背景

研究背景的第一段，介绍了问题的由来。

研究背景的第二段，详细说明了研究的意义。

## 1.2 研究目标

研究目标段落，说明了本文的主要目标。

# 第二章 相关工作

第二章的第一段，介绍了相关领域的研究现状。

## 2.1 方法A

方法A的详细描述段落。

### 2.1.1 子方法A1

子方法A1的具体实现段落。

## 2.2 方法B

方法B的描述段落。
"""

# 测试用例 2: 跳级标题（# 后直接 ###）
TEST_MD_2 = """# 一级标题

一级标题下的段落。

### 三级标题

三级标题下的段落。

#### 四级标题

四级标题下的段落。

## 二级标题

二级标题下的段落。
"""

# 测试用例 3: 含图片引用
TEST_MD_3 = """# 架构设计

系统采用分层架构，如下图所示。

![架构图](images/arch.png)

## 数据层

数据层负责数据存储。

![ER图](images/er.png)

数据层还包含缓存模块。
"""


def print_chunks(chunks, title="Chunks"):
    print(f"\n{'='*60}")
    print(f"{title}: {len(chunks)} chunks")
    print("="*60)
    
    for i, chunk in enumerate(chunks):
        meta = chunk["metadata"]
        ctype = meta["chunk_type"]
        level = meta.get("heading_level", "-")
        path = meta.get("heading_path", "-")
        parent = meta.get("parent_id", "-")
        children = meta.get("child_ids", [])
        paragraphs = meta.get("paragraph_ids", [])
        
        text_preview = chunk["text"][:80].replace("\n", " ")
        if len(chunk["text"]) > 80:
            text_preview += "..."
        
        print(f"\n[{i}] {chunk['id']}")
        print(f"    type={ctype}, level={level}, path='{path}'")
        print(f"    parent={parent[:30] if parent else '-'}, children={len(children)}, paragraphs={len(paragraphs)}")
        print(f"    text: {text_preview}")
        
        if meta.get("image_refs"):
            print(f"    images: {len(meta['image_refs'])}")


def test_basic():
    """测试基本功能"""
    print("\n" + "="*60)
    print("TEST 1: 基本两层结构")
    print("="*60)
    
    chunker = MarkdownChunker()
    chunks = chunker.chunk_markdown(TEST_MD_1, {"source": "test1.pdf", "subject": "test"})
    
    print_chunks(chunks, "Test 1")
    
    # 验证结构
    headings = [c for c in chunks if c["metadata"]["chunk_type"] == "heading"]
    paragraphs = [c for c in chunks if c["metadata"]["chunk_type"] == "paragraph"]
    documents = [c for c in chunks if c["metadata"]["chunk_type"] == "document"]
    
    print(f"\n统计:")
    print(f"  DocumentChunk: {len(documents)}")
    print(f"  HeadingChunk: {len(headings)}")
    print(f"  ParagraphChunk: {len(paragraphs)}")
    
    # 验证层级
    levels = [c["metadata"]["heading_level"] for c in headings]
    print(f"  标题层级分布: {sorted(set(levels))}")
    
    # 验证段落归属
    for para in paragraphs:
        parent_id = para["metadata"]["parent_id"]
        parent = next((c for c in chunks if c["id"] == parent_id), None)
        assert parent is not None, f"段落 {para['id']} 的父节点 {parent_id} 不存在"
        assert para["id"] in parent["metadata"]["paragraph_ids"], \
            f"段落 {para['id']} 不在父节点 {parent_id} 的 paragraph_ids 中"
    
    print("  [OK] 段落归属验证通过")
    
    # 验证 heading_path
    h3 = next((c for c in headings if "2.1.1" in c["text"]), None)
    if h3:
        expected_path = "第二章 相关工作 > 2.1 方法A > 2.1.1 子方法A1"
        actual_path = h3["metadata"]["heading_path"]
        print(f"  三级标题路径: '{actual_path}'")
        assert expected_path == actual_path, f"路径不匹配: 期望 '{expected_path}', 实际 '{actual_path}'"
        print("  [OK] 路径验证通过")
    
    return chunks


def test_skip_level():
    """测试跳级标题"""
    print("\n" + "="*60)
    print("TEST 2: 跳级标题（# 后直接 ###）")
    print("="*60)
    
    chunker = MarkdownChunker()
    chunks = chunker.chunk_markdown(TEST_MD_2, {"source": "test2.pdf", "subject": "test"})
    
    print_chunks(chunks, "Test 2")
    
    headings = [c for c in chunks if c["metadata"]["chunk_type"] == "heading"]
    
    # 验证层级
    for h in headings:
        level = h["metadata"]["heading_level"]
        text = h["text"][:30]
        print(f"  level={level}: {text}...")
    
    # 验证三级标题的父是二级还是一级（跳级时应该是一级）
    h3 = next((c for c in headings if "三级" in c["text"]), None)
    if h3:
        parent_id = h3["metadata"]["parent_id"]
        parent = next((c for c in chunks if c["id"] == parent_id), None)
        print(f"  三级标题的父: level={parent['metadata']['heading_level']}, text={parent['text'][:30]}")
        # 跳级时，### 的父应该是 #（因为没有 ##）
        assert parent["metadata"]["heading_level"] == 1, "跳级标题的父应该是最近的更高级标题"
        print("  [OK] 跳级归属验证通过")


def test_image_refs():
    """测试图片引用提取"""
    print("\n" + "="*60)
    print("TEST 3: 图片引用提取")
    print("="*60)
    
    chunker = MarkdownChunker()
    chunks = chunker.chunk_markdown(TEST_MD_3, {"source": "test3.pdf", "subject": "test"})
    
    print_chunks(chunks, "Test 3")
    
    # 验证图片引用
    for chunk in chunks:
        refs = chunk["metadata"].get("image_refs", [])
        if refs:
            print(f"  {chunk['id']} ({chunk['metadata']['chunk_type']}) 包含 {len(refs)} 个图片引用:")
            for ref in refs:
                print(f"    - {ref['alt']}: {ref['path']}")
    
    # 验证架构图在第一章 heading 和 paragraph 中都出现
    arch_headings = [c for c in chunks if "架构" in c["text"] and c["metadata"]["chunk_type"] == "heading"]
    assert len(arch_headings) == 1, "应该有1个'架构设计'标题"
    assert len(arch_headings[0]["metadata"]["image_refs"]) == 1, "架构设计标题应该有1个图片"
    print("  [OK] 图片引用验证通过")


def test_empty_document():
    """测试没有标题的文档"""
    print("\n" + "="*60)
    print("TEST 4: 无标题文档")
    print("="*60)
    
    md = "这是第一段。\n\n这是第二段。\n\n这是第三段。"
    chunker = MarkdownChunker()
    chunks = chunker.chunk_markdown(md, {"source": "test4.pdf", "subject": "test"})
    
    print_chunks(chunks, "Test 4")
    
    paragraphs = [c for c in chunks if c["metadata"]["chunk_type"] == "paragraph"]
    assert len(paragraphs) == 3, f"应该有3个段落，实际有{len(paragraphs)}"
    print("  [OK] 无标题文档验证通过")


def test_long_paragraph():
    """测试超长段落切分"""
    print("\n" + "="*60)
    print("TEST 5: 超长段落切分")
    print("="*60)
    
    # 生成一个超长段落（超过 4000 字符）
    long_sentences = [f"这是第{i}个句子，用来测试超长段落的切分功能。" for i in range(100)]
    long_para = "".join(long_sentences)
    
    md = f"# 标题\n\n{long_para}\n\n这是短段落。"
    
    chunker = MarkdownChunker(max_para_chars=1000)
    chunks = chunker.chunk_markdown(md, {"source": "test5.pdf", "subject": "test"})
    
    print_chunks(chunks, "Test 5")
    
    paragraphs = [c for c in chunks if c["metadata"]["chunk_type"] == "paragraph"]
    print(f"  段落数量: {len(paragraphs)}")
    for p in paragraphs:
        print(f"    - 长度: {len(p['text'])}")
    
    # 验证所有段落都不超过 max_para_chars（允许少量溢出，因为是按句子切分）
    for p in paragraphs:
        assert len(p["text"]) <= 1200, f"段落长度 {len(p['text'])} 超过限制"
    print("  [OK] 超长段落切分验证通过")


if __name__ == "__main__":
    try:
        test_basic()
        test_skip_level()
        test_image_refs()
        test_empty_document()
        test_long_paragraph()
        
        print("\n" + "="*60)
        print("所有测试通过! [OK]")
        print("="*60)
    except AssertionError as e:
        print(f"\n[FAIL] 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
