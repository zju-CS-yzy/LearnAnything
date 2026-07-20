#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MarkdownChunker 代码块修复测试

验证 _parse_headings 是否正确跳过代码块中的 # 注释，
以及 _split_to_paragraphs 是否将代码块作为整体保留。
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.markdown_chunker import MarkdownChunker


def test_parse_headings_skip_code_block():
    """测试 1-4: _parse_headings 跳过代码块中的 # 注释"""
    print("="*60)
    print("测试: _parse_headings 跳过代码块中的 # 注释")
    print("="*60)
    
    chunker = MarkdownChunker()
    
    # 测试 1: 围栏代码块
    md1 = """# 第一章

正文。

```python
# for a query that doesn't require retrieval
preds = model.generate(...)
for pred in preds:
    print("Model prediction: {0}".format(pred.outputs[0].text))
```

## 第二节

正文。
"""
    headings1 = chunker._parse_headings(md1.split("\n"))
    assert len(headings1) == 2
    assert [h['text'] for h in headings1] == ["第一章", "第二节"]
    print("  [PASS] 围栏代码块中的 # 注释被跳过")
    
    # 测试 2: 缩进代码块
    md2 = """# 主标题

正文。

    # 缩进代码块中的注释
    def hello():
        print("hello")

## 子标题
"""
    headings2 = chunker._parse_headings(md2.split("\n"))
    assert len(headings2) == 2
    print("  [PASS] 缩进代码块中的 # 注释被跳过")
    
    # 测试 3: 波浪线代码块
    md3 = """# 标题一

~~~python
# 注释
x = 1
~~~

## 标题二
"""
    headings3 = chunker._parse_headings(md3.split("\n"))
    assert len(headings3) == 2
    print("  [PASS] 波浪线代码块中的 # 注释被跳过")
    
    print("[PASS] _parse_headings 测试通过")


def test_split_to_paragraphs_code_block():
    """测试 5: _split_to_paragraphs 将代码块作为整体"""
    print("\n" + "="*60)
    print("测试: _split_to_paragraphs 代码块整体保留")
    print("="*60)
    
    chunker = MarkdownChunker()
    
    content = "普通段落文本。\n\n```python\n# 代码注释1\nx = 1\n\n# 代码注释2\ny = 2\n```\n\n另一个普通段落。"
    paras = chunker._split_to_paragraphs(content)
    
    print(f"  段落数量: {len(paras)}")
    for i, p in enumerate(paras):
        preview = p[:50].replace('\n', '\\n')
        is_code = chunker._is_code_block(p)
        print(f"  段落 {i}: is_code={is_code}, len={len(p)}, text={preview}...")
    
    assert len(paras) >= 2, f"应至少 2 个段落，实际 {len(paras)}"
    
    code_paras = [p for p in paras if chunker._is_code_block(p)]
    assert len(code_paras) == 1, f"应有 1 个代码块段落，实际 {len(code_paras)}"
    assert "# 代码注释1" in code_paras[0]
    assert "# 代码注释2" in code_paras[0]
    print("  [PASS] 代码块作为整体段落，内部空行未导致拆分")


def test_chunk_markdown_code_block():
    """测试 6: chunk_markdown 中代码块标记 is_code_block"""
    print("\n" + "="*60)
    print("测试: chunk_markdown 代码块标记")
    print("="*60)
    
    chunker = MarkdownChunker()
    
    md = """# 主标题

普通段落文本。

```python
# 代码注释
x = 1
```

另一个普通段落。
"""
    
    chunks = chunker.chunk_markdown(md, source_metadata={"source": "test"})
    para_chunks = [c for c in chunks if c["metadata"]["chunk_type"] == "paragraph"]
    
    print(f"  paragraph chunks 数量: {len(para_chunks)}")
    for c in para_chunks:
        preview = c['text'][:40].replace('\n', '\\n')
        is_code = c['metadata'].get('is_code_block', False)
        print(f"    is_code={is_code}, text={preview}...")
    
    code_chunks = [c for c in para_chunks if c['metadata'].get('is_code_block')]
    assert len(code_chunks) == 1, f"应有 1 个代码块 chunk，实际 {len(code_chunks)}"
    assert code_chunks[0]['metadata']['is_code_block'] == True
    print("  [PASS] chunk_markdown 正确标记代码块")


if __name__ == "__main__":
    test_parse_headings_skip_code_block()
    test_split_to_paragraphs_code_block()
    test_chunk_markdown_code_block()
    print("\n" + "="*60)
    print("[PASS] 所有测试通过!")
    print("="*60)
