#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段 1 测试脚本：对话上下文管理器验证

验证内容:
1. 会话创建与恢复
2. 消息持久化
3. 对话历史查询
4. 指代解析（基础版）
5. 跨会话持久化（重启后数据仍在）
"""

import sys
import os
import time

# 添加项目根目录到路径
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.dialog_context import DialogContextManager, DialogContext
from core.graph_education.user_state_store import UserStateStore


def test_1_session_creation():
    """测试 1: 会话创建与恢复"""
    print("\n" + "="*60)
    print("测试 1: 会话创建与恢复")
    print("="*60)
    
    manager = DialogContextManager()
    
    # 创建新会话
    sid1, session1 = manager.get_or_create_session(user_id="test_user", subject_id="rag")
    print(f"[OK] 创建会话: session_id={sid1[:8]}..., subject_id={session1['subject_id']}")
    
    # 同一用户 + 同学科 -> 应该恢复同一会话
    sid2, session2 = manager.get_or_create_session(user_id="test_user", subject_id="rag")
    print(f"[OK] 恢复会话: session_id={sid2[:8]}..., 同一会话={sid1 == sid2}")
    
    # 不同用户 -> 创建新会话
    sid3, session3 = manager.get_or_create_session(user_id="other_user", subject_id="rag")
    print(f"[OK] 新用户会话: session_id={sid3[:8]}..., 不同会话={sid3 != sid1}")
    
    # 显式传入 session_id -> 恢复
    sid4, session4 = manager.get_or_create_session(user_id="test_user", session_id=sid1)
    print(f"[OK] 显式恢复: session_id={sid4[:8]}..., 恢复成功={sid4 == sid1}")
    
    assert sid1 == sid2, "同一用户同学科应恢复同一会话"
    assert sid3 != sid1, "不同用户应创建新会话"
    assert sid4 == sid1, "显式传入 session_id 应恢复同一会话"
    
    print("[PASS] 测试 1 通过")
    return sid1, sid3


def test_2_message_persistence(sid1, sid3):
    """测试 2: 消息持久化与查询"""
    print("\n" + "="*60)
    print("测试 2: 消息持久化与查询")
    print("="*60)
    
    manager = DialogContextManager()
    
    # 保存用户消息
    manager.save_message(sid1, turn_number=1, role="user", content="RAG 是什么？", intent="concept")
    print(f"[OK] 保存用户消息 (turn 1)")
    
    # 保存 Agent 回复
    manager.save_message(sid1, turn_number=1, role="agent", content="RAG 是检索增强生成...", agent_name="TutorAgent", intent="concept")
    print(f"[OK] 保存 Agent 回复 (turn 1)")
    
    # 第二轮
    manager.save_message(sid1, turn_number=2, role="user", content="它和 GraphRAG 有什么区别？", intent="concept")
    manager.save_message(sid1, turn_number=2, role="agent", content="GraphRAG 是...", agent_name="TutorAgent", intent="concept")
    print(f"[OK] 保存第二轮消息")
    
    # 查询历史
    history = manager.get_history(sid1, limit=10)
    print(f"[OK] 查询历史: {len(history)} 条消息")
    for msg in history:
        print(f"  - [{msg['role']}] {msg['content'][:40]}...")
    
    assert len(history) == 4, f"应有 4 条消息，实际 {len(history)}"
    
    # 验证另一个会话没有数据
    history2 = manager.get_history(sid3, limit=10)
    print(f"[OK] 其他会话历史: {len(history2)} 条消息（应为 0）")
    assert len(history2) == 0, "其他会话应无消息"
    
    print("[PASS] 测试 2 通过")


def test_3_dialog_context(sid1):
    """测试 3: 构建 DialogContext"""
    print("\n" + "="*60)
    print("测试 3: 构建 DialogContext")
    print("="*60)
    
    manager = DialogContextManager()
    
    # 更新会话状态
    manager.update_session(sid1, current_topic="RAG", turn_count=2)
    
    # 构建上下文
    context = manager.get_context(sid1)
    print(f"[OK] 构建上下文: session_id={context.session_id[:8]}...")
    print(f"[OK] 当前话题: {context.current_topic}")
    print(f"[OK] 历史轮次: {context.turn_number}")
    print(f"[OK] 历史消息数: {len(context.history)}")
    
    # 测试 to_prompt_context
    prompt_text = context.to_prompt_context(max_turns=5)
    print(f"[OK] Prompt 上下文:\n{prompt_text}")
    
    assert context.current_topic == "RAG"
    assert context.turn_number == 2
    assert len(context.history) == 4
    assert "RAG 是什么？" in prompt_text
    assert "它和 GraphRAG 有什么区别？" in prompt_text
    
    print("[PASS] 测试 3 通过")
    return context


def test_4_reference_resolution(context):
    """测试 4: 指代解析"""
    print("\n" + "="*60)
    print("测试 4: 指代解析")
    print("="*60)
    
    manager = DialogContextManager()
    
    # 测试代词替换
    query1 = "它有哪些应用场景？"
    resolved1 = manager.resolve_references(query1, context)
    print(f"[OK] 代词替换: '{query1}' -> '{resolved1}'")
    assert "RAG" in resolved1, "'它' 应替换为 'RAG'"
    
    # 测试省略主语补全
    query2 = "和 GraphRAG 有什么区别？"
    resolved2 = manager.resolve_references(query2, context)
    print(f"[OK] 省略补全: '{query2}' -> '{resolved2}'")
    assert "RAG" in resolved2, "应补全主语为 'RAG'"
    
    # 无指代词 -> 原样返回
    query3 = "Embedding 是什么？"
    resolved3 = manager.resolve_references(query3, context)
    print(f"[OK] 无指代: '{query3}' -> '{resolved3}'")
    assert resolved3 == query3, "无指代词应原样返回"
    
    print("[PASS] 测试 4 通过")


def test_5_cross_session_persistence(sid1):
    """测试 5: 跨会话持久化（模拟重启）"""
    print("\n" + "="*60)
    print("测试 5: 跨会话持久化（模拟重启）")
    print("="*60)
    
    # 模拟重启：创建新的 Manager 实例
    manager2 = DialogContextManager()
    
    # 恢复会话
    sid_recovered, session = manager2.get_or_create_session(
        user_id="test_user", 
        subject_id="rag",
        session_id=sid1
    )
    print(f"[OK] 恢复会话: session_id={sid_recovered[:8]}..., 匹配={sid_recovered == sid1}")
    
    # 验证历史仍在
    history = manager2.get_history(sid_recovered, limit=10)
    print(f"[OK] 历史消息数: {len(history)}")
    assert len(history) == 4, "重启后历史应仍在"
    
    # 验证上下文对象
    context = manager2.get_context(sid_recovered)
    print(f"[OK] 上下文话题: {context.current_topic}")
    print(f"[OK] 上下文轮次: {context.turn_number}")
    assert context.current_topic == "RAG"
    assert context.turn_number == 2
    
    print("[PASS] 测试 5 通过")


def test_6_session_timeout():
    """测试 6: 会话超时"""
    print("\n" + "="*60)
    print("测试 6: 会话超时（模拟）")
    print("="*60)
    
    manager = DialogContextManager()
    
    # 创建会话（手动设置超时时间，便于测试）
    manager.SESSION_TIMEOUT_MINUTES = 0  # 立即超时
    
    sid, _ = manager.get_or_create_session(user_id="timeout_user", subject_id="rag")
    print(f"[OK] 创建会话: {sid[:8]}...")
    
    # 立即再次请求（应创建新会话，因为已超时）
    sid2, _ = manager.get_or_create_session(user_id="timeout_user", subject_id="rag")
    print(f"[OK] 超时后新会话: {sid2[:8]}..., 不同会话={sid2 != sid}")
    
    # 恢复默认超时
    manager.SESSION_TIMEOUT_MINUTES = 30
    
    assert sid2 != sid, "超时会话应创建新会话"
    print("[PASS] 测试 6 通过")


def cleanup(sid1, sid3):
    """清理测试数据"""
    print("\n" + "="*60)
    print("清理测试数据")
    print("="*60)
    
    manager = DialogContextManager()
    
    # 删除测试消息
    import sqlite3
    db_path = manager.db_path
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dialog_messages WHERE session_id IN (?, ?)", (sid1, sid3))
        cursor.execute("DELETE FROM dialog_sessions WHERE session_id IN (?, ?)", (sid1, sid3))
        conn.commit()
        print(f"[OK] 清理完成: 删除会话 {sid1[:8]}..., {sid3[:8]}...")
    finally:
        conn.close()


def main():
    """主测试入口"""
    print("\n" + "="*60)
    print("阶段 1 对话上下文管理器 -- 测试套件")
    print("="*60)
    
    try:
        # 运行测试
        sid1, sid3 = test_1_session_creation()
        test_2_message_persistence(sid1, sid3)
        context = test_3_dialog_context(sid1)
        test_4_reference_resolution(context)
        test_5_cross_session_persistence(sid1)
        test_6_session_timeout()
        
        print("\n" + "="*60)
        print("[PASS] 所有测试通过！")
        print("="*60)
        
    except AssertionError as e:
        print(f"\n[FAIL] 测试失败: {e}")
        raise
    except Exception as e:
        print(f"\n[FAIL] 测试异常: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        # 清理
        try:
            cleanup(sid1, sid3)
        except:
            pass


if __name__ == "__main__":
    main()
