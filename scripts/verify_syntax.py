#!/usr/bin/env python3
"""
验证修复后的 graph_store.py 语法
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

# 语法检查
import py_compile
try:
    py_compile.compile(r"D:\MyCS\AI\Project\LearnAnything\core\graph_store.py", doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"Syntax error: {e}")

# 导入检查
try:
    from core.graph_store import GraphStore
    print("Import check: OK")
except Exception as e:
    print(f"Import error: {e}")
