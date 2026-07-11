#!/usr/bin/env python3
"""
诊断CSV中name为空的记录
"""
import csv
from pathlib import Path

def diagnose_csv():
    csv_path = Path(r"D:\MyCS\AI\Project\LearnAnything\knowledge_base\generic_v1_concepts.csv")
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    total = len(rows)
    empty_name = 0
    empty_type = 0
    empty_desc = 0
    type_counts = {}
    
    for row in rows:
        name = row.get("name", "").strip()
        ctype = row.get("concept_type", "").strip()
        desc = row.get("description", "").strip()
        
        if not name:
            empty_name += 1
        if not ctype:
            empty_type += 1
        if not desc:
            empty_desc += 1
        
        type_counts[ctype] = type_counts.get(ctype, 0) + 1
    
    print(f"CSV总记录数: {total}")
    print(f"空 name: {empty_name} ({empty_name/total*100:.1f}%)")
    print(f"空 type: {empty_type} ({empty_type/total*100:.1f}%)")
    print(f"空 description: {empty_desc} ({empty_desc/total*100:.1f}%)")
    print(f"\n类型分布:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t or '(空)'}: {c}")
    
    print(f"\n空 name 示例 (前10个):")
    for row in rows:
        name = row.get("name", "").strip()
        if not name:
            cid = row.get("id", "")
            ctype = row.get("concept_type", "")
            desc = row.get("description", "")[:60]
            print(f"  id={cid}, type={ctype}, desc={desc}")

if __name__ == "__main__":
    diagnose_csv()
