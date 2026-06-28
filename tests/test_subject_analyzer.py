#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 SubjectAnalyzer 自适应学科分析
"""

import sys, io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.subject_analyzer import SubjectAnalyzer, analyze_subject, save_subject_config

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=" * 60)
print("SubjectAnalyzer Adaptive Analysis Test")
print("=" * 60)

# Test 1: Chemistry-like materials
print("\n[TEST 1] Chemistry-like materials")
chem_chunks = [
    {"text": "# 化学键\n\n化学键是原子之间强烈的相互作用。主要有离子键和共价键两种类型。\n\n## 离子键\n离子键是通过电子转移形成的化学键。例如 NaCl 中，钠原子失去一个电子成为 Na+，氯原子获得一个电子成为 Cl-。\n\n## 共价键\n共价键是通过电子共享形成的化学键。例如 H2O 中，氧原子与两个氢原子共享电子对。\n\n化学方程式：2H2 + O2 → 2H2O", "metadata": {"source": "chem_ch1.md", "header_path": "化学键"}},
    {"text": "# 有机化学\n\n有机化学研究含碳化合物的结构、性质和反应。\n\n## 烷烃\n烷烃是只含碳碳单键和碳氢键的饱和烃。通式为 CnH2n+2。\n\n## 烯烃\n烯烃含有碳碳双键。通式为 CnH2n。", "metadata": {"source": "chem_ch2.md", "header_path": "有机化学"}},
    {"text": "实验题：请设计一个实验验证酸碱中和反应。\n\nA. 使用酚酞指示剂\nB. 测量温度变化\nC. 观察沉淀生成\nD. 测量 pH 值变化", "metadata": {"source": "chem_exam.md", "header_path": "实验题"}},
]

analyzer = SubjectAnalyzer()
config = analyze_subject(chem_chunks, subject_name="chemistry_test")
print(f"  Subject: {config['subject']} ({config['name']})")
print(f"  Question types: {list(config['question_types'].keys())}")
print(f"  Difficulty levels: {list(config['difficulty_levels'].keys())}")
print(f"  Knowledge hierarchy: {list(config['knowledge_hierarchy'].keys())}")
print(f"  Special features: {config['special_features']}")
print(f"  Analysis basis: {config['analysis_basis']}")

# Test 2: Civil service-like materials
print("\n[TEST 2] Civil service-like materials")
cs_chunks = [
    {"text": "# 申论写作\n\n申论是公务员考试的重要科目，主要考察考生的阅读理解、综合分析、提出对策和文字表达能力。\n\n## 归纳概括\n归纳概括题要求考生从给定材料中提取核心观点，进行简洁准确的概括。\n\n## 综合分析\n综合分析题要求考生对某一观点、现象或问题进行多角度分析。", "metadata": {"source": "cs_shenlun.md", "header_path": "申论写作"}},
    {"text": "# 行测言语理解\n\n言语理解与表达主要考察选词填空、片段阅读、语句表达等题型。\n\n请根据上下文选择最合适的词语填入空白处。", "metadata": {"source": "cs_xingce.md", "header_path": "行测言语理解"}},
]

config2 = analyze_subject(cs_chunks, subject_name="civil_service_test")
print(f"  Subject: {config2['subject']} ({config2['name']})")
print(f"  Question types: {list(config2['question_types'].keys())}")
print(f"  Special features: {config2['special_features']}")

# Test 3: Generic/tech materials
print("\n[TEST 3] Tech/AI materials")
tech_chunks = [
    {"text": "# RAG 检索增强生成\n\nRAG（Retrieval-Augmented Generation）结合了检索和生成技术。\n\n## 向量检索\n使用 Embedding 模型将文本转为向量，通过近似最近邻搜索找到相关内容。\n\n## 重排序\n使用 CrossEncoder 对初步检索结果重新排序，提升相关性。", "metadata": {"source": "tech_rag.md", "header_path": "RAG"}},
    {"text": "```python\nfrom transformers import AutoModel\nmodel = AutoModel.from_pretrained('bert-base-chinese')\n```", "metadata": {"source": "tech_code.md", "header_path": "代码示例"}},
]

config3 = analyze_subject(tech_chunks, subject_name="tech_test")
print(f"  Subject: {config3['subject']} ({config3['name']})")
print(f"  Question types: {list(config3['question_types'].keys())}")
print(f"  Special features: {config3['special_features']}")

# Test 4: Save and load config
print("\n[TEST 4] Save and load config")
path = save_subject_config(config, "chemistry_test")
print(f"  Saved to: {path}")
loaded = SubjectAnalyzer.load_config("chemistry_test")
print(f"  Loaded: {loaded['name'] if loaded else 'None'}")

# Test 5: Generic fallback
print("\n[TEST 5] Generic fallback")
generic = SubjectAnalyzer.get_generic_config()
print(f"  Generic config: {generic['subject']} ({generic['name']})")
print(f"  Question types: {list(generic['question_types'].keys())}")

print("\n" + "=" * 60)
print("SubjectAnalyzer test complete!")
print("=" * 60)
