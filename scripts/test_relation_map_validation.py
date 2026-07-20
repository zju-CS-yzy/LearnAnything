#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 SemanticLinker 的 relation_map 校验修复。
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.semantic_linker import _build_relation_validator, _is_valid_relation


def test_relation_validator():
    """测试 relation_map 校验器。"""
    print("="*60)
    print("测试: relation_map 校验")
    print("="*60)
    
    # 获取 engineering 范式的 relation_map
    relation_map = _build_relation_validator("engineering")
    print(f"\nengineering relation_map: {relation_map}")
    
    # 合法连接
    assert _is_valid_relation(relation_map, "requirement", "IMPLEMENTS", "technology") == True
    assert _is_valid_relation(relation_map, "technology", "DEPEND_ON", "requirement") == True
    print("  [PASS] requirement --IMPLEMENTS--> technology: 合法")
    print("  [PASS] technology --DEPEND_ON--> requirement: 合法")
    
    # 非法连接（问题所在）
    assert _is_valid_relation(relation_map, "technology", "DEPEND_ON", "technology") == False
    print("  [PASS] technology --DEPEND_ON--> technology: 非法（已拒绝）")
    
    # 其他非法连接
    assert _is_valid_relation(relation_map, "requirement", "DEPEND_ON", "technology") == False
    print("  [PASS] requirement --DEPEND_ON--> technology: 非法（relation_type 不匹配）")
    
    print("\n[PASS] relation_map 校验测试通过")


if __name__ == "__main__":
    test_relation_validator()
