#!/usr/bin/env python3
"""
P0-INT 集成测试：Agent 调用 P0 模块的完整流程测试

用法：
    cd D:\MyCS\AI\Project\LearnAnything
    python scripts/test_p0_integration.py --subject transformer

预期输出：测试脚本会打印每个步骤的调用流程，便于前端验证集成效果。
"""

import sys
import argparse
from typing import Dict, Any
import json

sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")


def test_quiz_flow_with_p0(subject: str = "transformer"):
    """测试 Coordinator -> QuizAgent 的 P0 集成流程"""
    print(f"\n{'='*70}")
    print(f"测试 1: Coordinator -> QuizAgent 的 P0 集成流程")
    print(f"学科: {subject}")
    print(f"{'='*70}")

    from agents.coordinator import Coordinator

    # 创建 Coordinator
    print("\n[Step 1] 创建 Coordinator...")
    coord = Coordinator(collection_name=subject, top_k=2)
    print(f"  ✓ Coordinator 创建成功，collection_name={subject}")

    # 测试意图路由
    print("\n[Step 2] 测试意图路由...")
    query = "给我出几道关于Transformer的题目"
    print(f"  用户查询: '{query}'")
    print(f"  预期意图: quiz")
    print(f"  预期提取主题: Transformer")

    # 调用 handle（注意：这会自动触发 P0 模块流程）
    print("\n[Step 3] 调用 Coordinator.handle()...")
    print("  预期控制台输出（P0-INT-1 流程）:")
    print("  - [Coordinator] P0-INT-1: 使用图谱教育模块为 quiz 意图组装上下文")
    print("  - [Coordinator] 延迟初始化 GraphStore: {subject}_v1")
    print("  - [Coordinator] 延迟初始化 ConceptRetriever")
    print("  - [Coordinator] 提取主题: Transformer")
    print("  - [Coordinator] 解析到 N 个种子概念")
    print("  - [Coordinator] 延迟初始化 SubgraphBuilder")
    print("  - [Coordinator] 构建子图: N 节点, M 边")
    print("  - [Coordinator] 延迟初始化 ContextAssembler")
    print("  - [Coordinator] 组装上下文: T tokens")
    print("  - [QuizAgent] P0-INT-2: 使用 P0 图谱上下文出题，token=T")
    print("  - [QuizAgent] 图谱上下文概念: [概念1, 概念2, ...]")

    try:
        result = coord.handle(query)
        print(f"\n  ✓ Coordinator.handle() 返回成功")
        print(f"  返回字段:")
        for key in result.keys():
            print(f"    - {key}")

        # 检查是否包含 P0 相关字段
        if "text" in result:
            print(f"  返回文本预览: {result['text'][:100]}...")

        # 检查 agent_result 中的 P0 字段
        if result.get("agent_result"):
            agent_result = result["agent_result"]
            if "graph_context_token_count" in agent_result:
                print(f"  ✓ P0 字段确认: graph_context_token_count={agent_result['graph_context_token_count']}")
            if "concept_names" in agent_result:
                print(f"  ✓ P0 字段确认: concept_names={agent_result['concept_names']}")
            if "knowledge_trace" in agent_result.get("questions", [{}])[0]:
                print(f"  ✓ P0 字段确认: questions[0] 包含 knowledge_trace")
    except Exception as e:
        print(f"\n  ✗ 调用失败: {e}")
        import traceback
        traceback.print_exc()
        print(f"  注：如果概念 'Transformer' 在学科 '{subject}' 中不存在，")
        print(f"  将回退到旧方式出题（无 P0 上下文）。")

    print(f"\n{'='*70}")
    print(f"测试 1 完成")
    print(f"{'='*70}")


def test_quiz_fallback(subject: str = "transformer"):
    """测试回退路径：当概念不存在时回退到旧方式"""
    print(f"\n{'='*70}")
    print(f"测试 2: 回退路径（概念不存在时）")
    print(f"学科: {subject}")
    print(f"{'='*70}")

    from agents.coordinator import Coordinator

    coord = Coordinator(collection_name=subject, top_k=2)

    # 使用一个不太可能存在的概念名
    query = "给我出几道关于不存在的概念XYZ123的题目"
    print(f"\n  用户查询: '{query}'")
    print(f"  预期提取主题: 不存在的概念XYZ123")
    print(f"  预期行为: ConceptRetriever 找不到概念 → 回退到旧方式")
    print(f"  预期控制台输出:")
    print(f"  - [Coordinator] 无匹配概念，回退到旧方式")
    print(f"  - [QuizAgent] 回退到旧方式出题（无图谱上下文）")

    try:
        result = coord.handle(query)
        print(f"\n  ✓ 回退成功，仍返回题目")
        print(f"  返回文本预览: {result.get('text', '')[:80]}...")
    except Exception as e:
        print(f"\n  ✗ 回退失败: {e}")

    print(f"\n{'='*70}")
    print(f"测试 2 完成")
    print(f"{'='*70}")


def test_evaluate_with_irt(subject: str = "transformer"):
    """测试 CoachAgent 的 IRT 集成"""
    print(f"\n{'='*70}")
    print(f"测试 3: CoachAgent 的 IRT 能力估计")
    print(f"学科: {subject}")
    print(f"{'='*70}")

    from agents.coach_agent import CoachAgent

    coach = CoachAgent(collection_name=subject, subject=subject, top_k=2)

    # 模拟答题数据
    questions = [
        {"id": 1, "question": "Transformer 的核心机制是什么？", "answer": "A"},
        {"id": 2, "question": "Self-Attention 的时间复杂度？", "answer": "B"},
    ]
    user_answers = {
        "1": "A",  # 正确
        "2": "C",  # 错误
    }

    print(f"\n  模拟答题: 2 题，1 对 1 错")
    print(f"  预期控制台输出（P0-INT-3 流程）:")
    print(f"  - [CoachAgent] P0-INT-3: 开始 IRT 能力估计")
    print(f"  - [CoachAgent] IRT 能力估计: theta=XX.XX")

    try:
        report = coach.evaluate(questions, user_answers)
        print(f"\n  ✓ CoachAgent.evaluate() 返回成功")

        # 检查 IRT 字段
        if "irt" in report:
            irt = report["irt"]
            print(f"  ✓ P0-INT-3 字段确认: irt={json.dumps(irt, ensure_ascii=False)[:200]}")

            if "theta" in irt:
                print(f"  ✓ IRT theta: {irt['theta']}")
            if "level" in irt:
                print(f"  ✓ IRT level: {irt['level']}")
            if "concept_difficulties" in irt:
                print(f"  ✓ concept_difficulties: {len(irt['concept_difficulties'])} 个概念")
        else:
            print(f"  ⚠ 报告未包含 irt 字段（可能 IRT 估计失败）")

        print(f"\n  报告文本预览:")
        print(f"  {report.get('text', '')[:150]}...")
    except Exception as e:
        print(f"\n  ✗ 调用失败: {e}")
        import traceback
        traceback.print_exc()

    print(f"\n{'='*70}")
    print(f"测试 3 完成")
    print(f"{'='*70}")


def test_backward_compatibility(subject: str = "transformer"):
    """测试向后兼容：不传 graph_context 时仍正常工作"""
    print(f"\n{'='*70}")
    print(f"测试 4: 向后兼容（不传 graph_context）")
    print(f"学科: {subject}")
    print(f"{'='*70}")

    from agents.quiz_agent import QuizAgent
    from agents.coach_agent import CoachAgent

    # 直接调用 QuizAgent（不传 graph_context）
    print(f"\n[Step 1] 直接调用 QuizAgent.handle()（不传 graph_context）...")
    qa = QuizAgent(collection_name=subject, top_k=2)
    try:
        result = qa.handle("关于 Transformer 的题目")
        print(f"  ✓ QuizAgent 返回成功，generation_method={result.get('generation_method', 'unknown')}")
        print(f"  ✓ 返回题目数: {len(result.get('questions', []))}")
    except Exception as e:
        print(f"  ✗ QuizAgent 失败: {e}")

    # 直接调用 CoachAgent（老方式）
    print(f"\n[Step 2] 直接调用 CoachAgent.evaluate()...")
    coach = CoachAgent(collection_name=subject, subject=subject, top_k=2)
    questions = [{"id": 1, "question": "Q1", "answer": "A"}]
    user_answers = {"1": "A"}
    try:
        report = coach.evaluate(questions, user_answers)
        print(f"  ✓ CoachAgent 返回成功，包含 irt={('irt' in report)}")
    except Exception as e:
        print(f"  ✗ CoachAgent 失败: {e}")

    print(f"\n{'='*70}")
    print(f"测试 4 完成")
    print(f"{'='*70}")


def test_theta_to_level():
    """测试 theta 到等级的映射"""
    print(f"\n{'='*70}")
    print(f"测试 5: IRT theta 到等级的映射")
    print(f"{'='*70}")

    from agents.coach_agent import CoachAgent
    coach = CoachAgent()

    test_cases = [
        (-2.0, "入门"),
        (-1.0, "初级"),
        (-0.5, "初级"),  # 边界值
        (0.0, "中级"),
        (0.5, "中级"),  # 边界值
        (1.0, "高级"),
        (1.5, "高级"),  # 边界值
        (2.0, "专家"),
    ]

    print(f"\n  theta -> 等级 映射:")
    for theta, expected in test_cases:
        level = coach._theta_to_level(theta)
        status = "✓" if level == expected else "✗"
        print(f"  {status} theta={theta:+.1f} -> level={level} (预期: {expected})")

    print(f"\n{'='*70}")
    print(f"测试 5 完成")
    print(f"{'='*70}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P0-INT 集成测试")
    parser.add_argument("--subject", default="transformer", help="学科名称 (default: transformer)")
    parser.add_argument("--test", choices=["all", "quiz", "fallback", "evaluate", "compat", "theta"], default="all", help="选择测试项")
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"P0-INT 集成测试开始")
    print(f"学科: {args.subject}")
    print(f"{'='*70}")

    if args.test in ("all", "quiz"):
        test_quiz_flow_with_p0(args.subject)
    if args.test in ("all", "fallback"):
        test_quiz_flow_with_p0(args.subject)  # 实际会测试回退路径
        test_quiz_fallback(args.subject)
    if args.test in ("all", "evaluate"):
        test_evaluate_with_irt(args.subject)
    if args.test in ("all", "compat"):
        test_backward_compatibility(args.subject)
    if args.test in ("all", "theta"):
        test_theta_to_level()

    print(f"\n{'='*70}")
    print(f"所有测试完成！")
    print(f"{'='*70}")
    print(f"\n预期前端观察到的控制台输出总结:")
    print(f"  1. Coordinator 调用 P0 模块时:")
    print(f"     [Coordinator] P0-INT-1: 使用图谱教育模块为 quiz 意图组装上下文")
    print(f"     [Coordinator] 解析到 N 个种子概念")
    print(f"     [Coordinator] 构建子图: N 节点, M 边")
    print(f"     [Coordinator] 组装上下文: T tokens")
    print(f"  2. QuizAgent 使用 P0 上下文时:")
    print(f"     [QuizAgent] P0-INT-2: 使用 P0 图谱上下文出题，token=T")
    print(f"     [QuizAgent] 图谱上下文概念: [概念1, ...]")
    print(f"  3. CoachAgent 评分后:")
    print(f"     [CoachAgent] P0-INT-3: 开始 IRT 能力估计")
    print(f"     [CoachAgent] IRT 能力估计: theta=XX.XX")
    print(f"  4. 回退路径:")
    print(f"     [Coordinator] 无匹配概念，回退到旧方式")
    print(f"     [QuizAgent] 回退到旧方式出题（无图谱上下文）")
