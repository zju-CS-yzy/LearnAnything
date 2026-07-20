#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CycleDetector 测试脚本
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.cycle_detector import CycleDetector, CycleError


def test_basic():
    """测试 1: 基本无环"""
    d = CycleDetector()
    assert d.add_edge("A", "B")
    assert d.add_edge("B", "C")
    assert d.add_edge("C", "D")
    print("[PASS] 基本无环")


def test_cycle_detection():
    """测试 2: 检测环"""
    d = CycleDetector()
    d.add_edge("A", "B")
    d.add_edge("B", "C")
    d.add_edge("C", "D")
    
    try:
        d.add_edge("D", "A")
        assert False, "应该检测到环"
    except CycleError as e:
        print(f"[PASS] 正确检测到环: {e}")


def test_self_loop():
    """测试 3: 自环"""
    d = CycleDetector()
    assert d.would_form_cycle("X", "X")
    print("[PASS] 自环检测")


def test_no_cycle():
    """测试 4: 不形成环"""
    d = CycleDetector()
    d.add_edge("A", "B")
    d.add_edge("B", "C")
    assert not d.would_form_cycle("C", "D")
    print("[PASS] 不形成环")


def test_paradigm_validation():
    """测试 5: 范式 type-level 检查"""
    d = CycleDetector()
    
    result = d.validate_paradigm_types("test", {
        "A": {"R1": ["B"]},
        "B": {"R2": ["C"]},
    })
    assert result is None
    print("[PASS] 无环范式检查")
    
    result = d.validate_paradigm_types("test", {
        "A": {"R1": ["B"]},
        "B": {"R2": ["A"]},
    })
    assert result is not None
    print(f"[PASS] 有环范式检查: {result}")


def test_engineering_pattern():
    """测试 6: engineering 范式场景"""
    d = CycleDetector()
    
    # 正常提取：需求驱动技术
    d.add_edge("提升训练效率", "多GPU并行训练")  # IMPLEMENTS
    
    # 技术分解出子需求（不同的 requirement 实例）
    d.add_edge("多GPU并行训练", "保证梯度同步")  # DEPEND_ON
    
    print("[PASS] engineering 正常场景无环")
    
    # 尝试建立环（同一个需求既驱动技术，又作为技术的子需求）
    try:
        d.add_edge("多GPU并行训练", "提升训练效率")
        assert False, "应该检测到环"
    except CycleError as e:
        print(f"[PASS] engineering 环检测正确: {e}")


def main():
    print("="*60)
    print("CycleDetector 测试套件")
    print("="*60)
    
    test_basic()
    test_cycle_detection()
    test_self_loop()
    test_no_cycle()
    test_paradigm_validation()
    test_engineering_pattern()
    
    print("\n" + "="*60)
    print("[PASS] 所有测试通过!")
    print("="*60)


if __name__ == "__main__":
    main()
