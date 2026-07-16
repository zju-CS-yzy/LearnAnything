#!/usr/bin/env python3
"""P0-INT-6 消息总线集成测试"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from agents.coordinator import Coordinator

def test_message_bus():
    print("=" * 60)
    print("P0-INT-6: Agent 消息总线测试")
    print("=" * 60)

    # 创建 Coordinator（会自动设置消息总线）
    coord = Coordinator(collection_name="transformer", top_k=2)

    # 检查总线统计
    stats = coord.get_bus_stats()
    print("\n[1] 消息总线订阅状态:")
    print(f"    topics: {stats['topics']}")
    print(f"    subscribers: {stats['subscribers']}")

    # 模拟出题（触发 quiz_generated 事件）
    print("\n[2] QuizAgent 出题（预期触发 quiz_generated 事件）:")
    quiz_agent = coord._agents["quiz"]
    result = quiz_agent.handle("给我出几道 Transformer 的题目", n_questions=2)

    # 检查审计日志
    print("\n[3] 消息审计日志:")
    audit = coord.get_bus_audit_log(limit=10)
    for msg in audit:
        print(f"    {msg['id']}: {msg['event']} from {msg['sender']} -> delivered={msg['delivered']} dropped={msg['dropped']}")

    # 检查 CoachAgent 待评测队列
    print("\n[4] CoachAgent 待评测队列:")
    coach = coord._agents["evaluate"]
    print(f"    pending_quizzes: {len(coach._pending_quizzes)}")
    for q in coach._pending_quizzes:
        print(f"      - {q['topic']}: {q['question_count']} 题")

    # 模拟评测（触发 ability_updated 和 weak_area_detected 事件）
    print("\n[5] CoachAgent 评测（预期触发 ability_updated 和 weak_area_detected 事件）:")
    questions = [
        {"id": 1, "question": "Q1", "answer": "A", "type": "single_choice"},
        {"id": 2, "question": "Q2", "answer": "B", "type": "single_choice"},
    ]
    user_answers = {"1": "A", "2": "C"}  # 1 对 1 错
    report = coach.evaluate(questions, user_answers)
    print(f"    IRT theta: {report.get('irt', {}).get('theta', 'N/A')}")

    # 再次检查审计日志
    print("\n[6] 完整消息审计日志:")
    audit = coord.get_bus_audit_log(limit=20)
    for msg in audit:
        print(f"    {msg['timestamp'][-8:]} {msg['id']}: {msg['event']:20s} from {msg['sender']:12s} -> {msg['delivered']}")

    # 检查 QuizAgent 是否收到 ability_updated
    print("\n[7] QuizAgent 能力状态:")
    print(f"    user_theta: {quiz_agent._user_theta}")
    print(f"    weak_areas: {quiz_agent._user_weak_areas}")

    # 检查 TutorAgent 是否收到 weak_area_detected
    print("\n[8] TutorAgent 薄弱点记录:")
    tutor = coord._agents["concept"]
    print(f"    weak_areas: {tutor._user_weak_areas}")

    print("\n" + "=" * 60)
    print("测试完成！观察上方的 [MessageBus] PUBLISH/DELIVER 日志")
    print("=" * 60)

if __name__ == "__main__":
    test_message_bus()
