#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 DocumentProcessor 多格式输入处理
"""

import sys, io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.document_processor import DocumentProcessor

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=" * 60)
print("DocumentProcessor Test")
print("=" * 60)

processor = DocumentProcessor()

# Test 1: Text file
print("\n[TEST 1] Text file processing")
text_content = """# 化学键

化学键是原子之间强烈的相互作用。

## 离子键
离子键是通过电子转移形成的化学键。

## 共价键
共价键是通过电子共享形成的化学键。
"""

test_file = Path(__file__).parent.parent / "knowledge_base" / "test_chemistry.txt"
test_file.parent.mkdir(parents=True, exist_ok=True)
test_file.write_text(text_content, encoding='utf-8')

chunks = processor.process_file(str(test_file), subject="chemistry")
print(f"  Chunks: {len(chunks)}")
for i, c in enumerate(chunks[:3]):
    print(f"  [{i+1}] {c['text'][:80]}...")

# Test 2: Page type detection
print("\n[TEST 2] Page type detection")
# Simulate text page
text_page = "This is a normal text page with sufficient content. " * 50
result = processor._detect_page_type(None, text_page)
print(f"  Text page: {result}")

# Simulate scan page
scan_page = ""
result = processor._detect_page_type(None, scan_page)
print(f"  Scan page (empty): {result}")

# Simulate formula page
formula_page = "H$_2$O + CO$_2$ → H$_2$CO$_3$ \frac{a}{b} \sum_{i=1}^n x_i α β γ δ"
result = processor._detect_page_type(None, formula_page)
print(f"  Formula page: {result}")

print("\n" + "=" * 60)
print("DocumentProcessor test complete!")
print("=" * 60)
