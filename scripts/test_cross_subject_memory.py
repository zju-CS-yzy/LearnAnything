#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试脚本：跨学科记忆分层 + 日志观察

验证内容:
1. 跨学科切换检测（RAG -> Transformer 应创建新会话）
2. 全局画像共享（同用户跨学科共享职业/技术栈）
3. 学科隔离（对话历史不跨学科泄露）
4. 控制台日志输出（便于观察）

运行方式:
    cd D:\MyCS\AI\Project\LearnAnything
    python scripts/test_cross_subject_memory.py
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.dialog_context import DialogContextManager, DialogContext, UserProfile


def test_cross_subject_isolation():
    """Test cross-subject memory isolation"""
    print("\n" + "="*70)
    print("测试: 跨学科记忆隔离 (RAG vs Transformer)")
    print("="*70)
    
    manager = DialogContextManager()
    user_id = "test_engineer"
    
    # 预设用户画像
    manager.update_profile(
        user_id=user_id,
        profession="Backend Engineer",
        tech_stack=["C++", "Python", "Redis"],
        experience_level="Intermediate",
        weak_areas_global=["Linear Algebra"]
    )
    print(f"[TEST] Profile preset: profession=Backend Engineer, tech_stack=[C++, Python, Redis]")
    
    # ========== Subject 1: RAG ==========
    print("\n--- Step 1: User enters RAG subject ---")
    sid_rag, _ = manager.get_or_create_session(user_id=user_id, subject_id="rag")
    
    # Save RAG conversation
    manager.save_message(sid_rag, 1, "user", "What is RAG?", intent="concept")
    manager.save_message(sid_rag, 1, "agent", "RAG is Retrieval Augmented Generation...", agent_name="TutorAgent", intent="concept")
    manager.save_message(sid_rag, 2, "user", "What is the difference with GraphRAG?", intent="concept")
    manager.save_message(sid_rag, 2, "agent", "GraphRAG uses graph structure...", agent_name="TutorAgent", intent="concept")
    manager.update_session(sid_rag, current_topic="RAG", turn_count=2)
    
    # Build RAG context
    ctx_rag = manager.build_context(sid_rag)
    print(f"\n[VERIFY] RAG context:")
    print(f"  - session_id: {sid_rag[:8]}...")
    print(f"  - subject: {ctx_rag.subject_id}")
    print(f"  - topic: {ctx_rag.current_topic}")
    print(f"  - history: {len(ctx_rag.history)} messages")
    print(f"  - profile profession: {ctx_rag.user_profile.profession if ctx_rag.user_profile else 'None'}")
    print(f"  - global_weak: {ctx_rag.weak_areas_global}")
    
    # ========== Subject 2: Transformer ==========
    print("\n--- Step 2: User switches to Transformer subject ---")
    sid_transformer, _ = manager.get_or_create_session(user_id=user_id, subject_id="transformer")
    
    # Save Transformer conversation
    manager.save_message(sid_transformer, 1, "user", "What is Transformer attention?", intent="concept")
    manager.save_message(sid_transformer, 1, "agent", "Attention mechanism is...", agent_name="TutorAgent", intent="concept")
    manager.update_session(sid_transformer, current_topic="Transformer", turn_count=1)
    
    # Build Transformer context
    ctx_transformer = manager.build_context(sid_transformer)
    print(f"\n[VERIFY] Transformer context:")
    print(f"  - session_id: {sid_transformer[:8]}...")
    print(f"  - subject: {ctx_transformer.subject_id}")
    print(f"  - topic: {ctx_transformer.current_topic}")
    print(f"  - history: {len(ctx_transformer.history)} messages")
    print(f"  - profile profession: {ctx_transformer.user_profile.profession if ctx_transformer.user_profile else 'None'}")
    print(f"  - global_weak: {ctx_transformer.weak_areas_global}")
    
    # ========== Verify isolation ==========
    print("\n--- Step 3: Verify isolation ---")
    
    # 1. Session IDs should differ
    assert sid_rag != sid_transformer, "Cross-subject should create different sessions"
    print(f"[PASS] Session isolation: RAG={sid_rag[:8]}... != Transformer={sid_transformer[:8]}...")
    
    # 2. RAG history should not leak to Transformer
    transformer_history_text = "\n".join(m.get("content", "") for m in ctx_transformer.history)
    assert "GraphRAG" not in transformer_history_text, "RAG history should not leak to Transformer"
    print(f"[PASS] History isolation: No GraphRAG in Transformer session")
    
    # 3. Global profile should be shared
    assert ctx_rag.user_profile is not None, "RAG should have profile"
    assert ctx_transformer.user_profile is not None, "Transformer should have profile"
    assert ctx_rag.user_profile.profession == "Backend Engineer", f"RAG profile profession={ctx_rag.user_profile.profession}"
    assert ctx_transformer.user_profile.profession == "Backend Engineer", f"Transformer profile profession={ctx_transformer.user_profile.profession}"
    print(f"[PASS] Profile shared: Both subjects identify 'Backend Engineer'")
    
    # 4. Global weak areas should be shared
    assert "Linear Algebra" in ctx_rag.weak_areas_global, "RAG should know global weak area"
    assert "Linear Algebra" in ctx_transformer.weak_areas_global, "Transformer should know global weak area"
    print(f"[PASS] Weak area shared: Both subjects know 'Linear Algebra' weak")
    
    print("\n" + "="*70)
    print("[PASS] Cross-subject memory isolation test passed!")
    print("="*70)
    
    return sid_rag, sid_transformer


def test_prompt_layer_structure():
    """Test Prompt layered structure"""
    print("\n" + "="*70)
    print("Test: Prompt Layer Structure")
    print("="*70)
    
    manager = DialogContextManager()
    user_id = "test_prompt_user"
    
    # Create profile
    manager.update_profile(user_id, profession="Algorithm Engineer", tech_stack=["Python", "PyTorch"])
    
    # Create session
    sid, _ = manager.get_or_create_session(user_id, subject_id="nlp")
    manager.save_message(sid, 1, "user", "What is BERT?", intent="concept")
    manager.save_message(sid, 1, "agent", "BERT is a pre-trained language model...", agent_name="TutorAgent", intent="concept")
    manager.update_session(sid, current_topic="BERT", turn_count=1)
    
    # Build context
    ctx = manager.build_context(sid)
    prompt = ctx.to_prompt_context(max_turns=5)
    
    print("\n[Full Prompt Output]:")
    print("-" * 50)
    print(prompt)
    print("-" * 50)
    
    # Verify layer structure
    assert "User Profile" in prompt or "用户画像" in prompt, "Should have user profile layer"
    assert "Current Subject" in prompt or "当前学科" in prompt, "Should have subject layer"
    assert "Dialog History" in prompt or "对话历史" in prompt, "Should have history layer"
    
    print("\n[PASS] Prompt layer structure correct!")
    print("  - [User Profile] layer: included")
    print("  - [Current Subject] layer: included")
    print("  - [Dialog History] layer: included")
    
    return sid


def cleanup(manager, *session_ids):
    """清理测试数据"""
    import sqlite3
    conn = sqlite3.connect(str(manager.db_path))
    try:
        cursor = conn.cursor()
        for sid in session_ids:
            cursor.execute("DELETE FROM dialog_messages WHERE session_id = ?", (sid,))
            cursor.execute("DELETE FROM dialog_sessions WHERE session_id = ?", (sid,))
        # 清理测试用户画像
        cursor.execute("DELETE FROM user_profiles WHERE user_id LIKE 'test_%'")
        conn.commit()
        print(f"\n[清理] 删除测试数据完成")
    finally:
        conn.close()


def main():
    print("\n" + "="*70)
    print("Cross-Subject Memory Layering -- Test Suite")
    print("="*70)
    print("\n[Note] This test verifies:")
    print("  1. Cross-subject switching creates new session (subject isolation)")
    print("  2. User profile shared across subjects (global memory)")
    print("  3. Dialog history not leaked across subjects (isolated memory)")
    print("  4. Prompt layered structure (profile/subject/history)")
    print("  5. Console log output (for observation)")
    
    manager = DialogContextManager()
    sid_rag = None
    sid_transformer = None
    sid_nlp = None
    
    try:
        sid_rag, sid_transformer = test_cross_subject_isolation()
        sid_nlp = test_prompt_layer_structure()
        
        print("\n" + "="*70)
        print("[PASS] All tests passed!")
        print("="*70)
        
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n[FAIL] Test exception: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        if sid_rag and sid_transformer and sid_nlp:
            cleanup(manager, sid_rag, sid_transformer, sid_nlp)


if __name__ == "__main__":
    main()
