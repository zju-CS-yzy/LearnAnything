#!/usr/bin/env python3
"""
修复 graph_store.py 中 v2.0 Schema 不兼容的函数
"""
import re

filepath = r"D:\MyCS\AI\Project\LearnAnything\core\graph_store.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. 删除第一个 get_semantic_edges（保留第二个，稍后修改）
# 找到 "    def get_semantic_edges..." 第一次出现的位置，到第二次出现之间的内容
# 用 split 分割
parts = content.split("    def get_semantic_edges(self, limit: int = 200) -> List[Dict[str, Any]]:\n")

if len(parts) >= 3:
    # parts[0]: 第一个函数之前的内容
    # parts[1]: 第一个函数的内容（从 def 后到 return edges...）
    # parts[2]: 第二个函数的内容
    # 删除第一个函数：保留 parts[0] + parts[2]
    
    # 确认 parts[1] 以 return edges 结尾
    first_func = parts[1]
    # 找 first_func 中最后一个 return edges
    # first_func 从 def 之后开始，包含到第二个 def 之前
    # 但实际上 split 会在 "def get_semantic_edges" 处分割
    # parts[1] = 第一个 def 之后到第二个 def 之间的内容
    # parts[2] = 第二个 def 之后到文件末尾
    
    # 删除第一个函数
    new_content = parts[0] + "    def get_semantic_edges(self, limit: int = 200) -> List[Dict[str, Any]]:\n" + parts[2]
    
    print(f"Deleted first get_semantic_edges, now {new_content.count('def get_semantic_edges')} remaining")
else:
    print(f"Unexpected split count: {len(parts)}")
    new_content = content

with open(filepath, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Step 1 done: Removed duplicate get_semantic_edges")
