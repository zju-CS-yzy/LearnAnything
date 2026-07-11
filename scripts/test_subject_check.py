#!/usr/bin/env python3
"""
检查 测试 学科的概念数据 - 写入文件
"""
import csv
from pathlib import Path

csv_path = Path(r"D:\MyCS\AI\Project\LearnAnything\knowledge_base\测试_v1_concepts.csv")

with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

out = []
out.append(f"总记录数: {len(rows)}")

empty_names = [r for r in rows if not r.get("name", "").strip()]
out.append(f"空 name: {len(empty_names)}")

empty_desc = [r for r in rows if not r.get("description", "").strip()]
out.append(f"空 description: {len(empty_desc)}")

# 查找特定关键词
keywords = ["数据检索", "文本分块", "关键词检索"]
for kw in keywords:
    found = [r for r in rows if kw in r.get("name", "")]
    if found:
        for r in found:
            out.append(f"找到: {kw}")
            out.append(f"  id={r['id']}")
            out.append(f"  name={r['name']}")
            out.append(f"  type={r.get('concept_type','')}")
            out.append(f"  desc={r.get('description','')[:80]}")
    else:
        # 尝试用别名搜索
        found = [r for r in rows if kw in r.get("aliases", "")]
        if found:
            for r in found:
                out.append(f"别名中找到: {kw}")
                out.append(f"  id={r['id']}")
                out.append(f"  name={r['name']}")
                out.append(f"  aliases={r.get('aliases','')}")
        else:
            out.append(f"未找到: {kw}")

# 查找 2e3b5de367
for r in rows:
    if '2e3b5de367' in r['id']:
        out.append(f"\n找到 2e3b5de367:")
        out.append(f"  id={r['id']}")
        out.append(f"  name={r['name']}")
        out.append(f"  type={r.get('concept_type','')}")
        out.append(f"  desc={r.get('description','')[:100]}")

# 空 source_chunks
empty_chunks = [r for r in rows if not r.get("source_chunks", "").strip()]
out.append(f"\n空 source_chunks: {len(empty_chunks)}")

# 打印所有 name 用于确认
out.append("\n所有概念名称:")
for r in rows:
    out.append(f"  {r['id']}: {r['name']}")

with open(r"D:\MyCS\AI\Project\LearnAnything\scripts\test_subject_result.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))

print("结果写入 test_subject_result.txt")
