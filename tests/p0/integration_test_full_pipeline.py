"""
LA-040-P0: 完整流程集成测试脚本

从出题意图 → 概念检索 → 子图构建 → 上下文组装

运行方式:
    cd D:\MyCS\AI\Project\LearnAnything
    python tests\p0\integration_test_full_pipeline.py

输出: 完整的上下文组装结果，用于人工判断是否合理
"""

import sys
import tempfile
import shutil
from pathlib import Path

# 设置 UTF-8 编码（Windows 兼容）
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

import kuzu

# 限制测试数据库内存占用
_original_kuzu = kuzu.Database.__init__
def _patched(self, database_path=None, *, buffer_pool_size=0, **kwargs):
    if buffer_pool_size == 0:
        buffer_pool_size = 64 * 1024 * 1024  # 64MB
    _original_kuzu(self, database_path, buffer_pool_size=buffer_pool_size, **kwargs)
kuzu.Database.__init__ = _patched

from core.graph_store import GraphStore
from core.graph_education import (
    ConceptRetriever, SubgraphBuilder, ContextAssembler,
    ConceptNode, Subgraph, ContextBudget, QuestionPattern, UserKnowledgeState
)


# ═══════════════════════════════════════════════
# 1. 创建测试数据库
# ═══════════════════════════════════════════════

def setup_test_database():
    """创建包含 5 个概念的测试数据库"""
    temp_dir = Path(tempfile.mkdtemp(prefix="la_pipeline_"))
    db_path = temp_dir / "test_graph"
    
    store = GraphStore(str(db_path))
    store.init_schema(force=True)
    
    # 添加 Chunk 节点（带 heading_path 和 page_number）
    # 注意：add_chunk_nodes 从 metadata 中读取 heading_path 和 page_number
    chunks = [
        {
            "id": "chunk_001",
            "text": "注意力机制是 Transformer 的核心",
            "metadata": {
                "source": "Attention_Is_All_You_Need.pdf",
                "subject": "transformer",
                "heading_path": "3.2 注意力机制",
                "page_number": 4,
            },
        },
        {
            "id": "chunk_002",
            "text": "多头注意力并行运行多组注意力",
            "metadata": {
                "source": "Attention_Is_All_You_Need.pdf",
                "subject": "transformer",
                "heading_path": "3.2.2 多头注意力",
                "page_number": 5,
            },
        },
        {
            "id": "chunk_003",
            "text": "缩放点积除以 sqrt(d_k) 防止饱和",
            "metadata": {
                "source": "Attention_Is_All_You_Need.pdf",
                "subject": "transformer",
                "heading_path": "3.2.1 缩放点积注意力",
                "page_number": 5,
            },
        },
    ]
    store.add_chunk_nodes(chunks)
    
    # 添加概念
    import json
    concepts = [
        ("concept_c1", "注意力机制", "concept", "让模型自动关注输入重要部分的技术",
         '["Attention", "Attention Mechanism"]', "chunk_001"),
        ("concept_c2", "多头注意力", "technology", "并行运行多组注意力计算",
         '["Multi-Head Attention", "MHA"]', "chunk_002"),
        ("concept_c3", "缩放点积注意力", "sub_technology", "除以 sqrt(d_k) 防止梯度消失",
         '["Scaled Dot-Product Attention"]', "chunk_003"),
        ("concept_c4", "Transformer", "technology", "基于自注意力机制的深度学习架构",
         '["Transformer", "Transformer模型"]', "chunk_001"),
        ("concept_c5", "位置编码", "sub_technology", "为序列添加位置信息使模型感知顺序",
         '["Positional Encoding"]', "chunk_001"),
    ]
    
    conn = store._ensure_db()
    for cid, name, ctype, desc, aliases, source_chunks in concepts:
        cypher = f"""
            CREATE (c:CanonicalConcept {{
                canonical_id: '{cid}',
                name: '{name}',
                concept_type: '{ctype}',
                description: '{store._escape_cypher_string(desc)}',
                aliases: '{aliases}',
                source_chunks: '{source_chunks}'
            }})
        """
        store._execute(conn, cypher)
    
    # 添加语义边
    edges = [
        ("concept_c2", "concept_c3", "DEPENDS_ON", 0.95),  # 多头注意力 → 依赖 → 缩放点积
        ("concept_c2", "concept_c1", "SOLUTION", 0.9),      # 多头注意力 → 解决 → 注意力机制
        ("concept_c3", "concept_c1", "DEPENDS_ON", 0.95),  # 缩放点积 → 依赖 → 注意力机制
        ("concept_c4", "concept_c2", "SOLUTION", 0.9),      # Transformer → 解决 → 多头注意力
        ("concept_c4", "concept_c5", "DEPENDS_ON", 0.8),    # Transformer → 依赖 → 位置编码
    ]
    
    for src, dst, rel, conf in edges:
        cypher = f"""
            MATCH (a:CanonicalConcept {{canonical_id: '{src}'}}), 
                  (b:CanonicalConcept {{canonical_id: '{dst}'}})
            CREATE (a)-[:{rel} {{confidence: {conf}}}]->(b)
        """
        store._execute(conn, cypher)
    
    return store, temp_dir


# ═══════════════════════════════════════════════
# 2. 完整流程
# ═══════════════════════════════════════════════

def run_full_pipeline(store, target_concept_name="多头注意力"):
    """执行完整流程"""
    
    print("=" * 60)
    print(f"LA-040-P0: 完整流程集成测试")
    print(f"目标概念: {target_concept_name}")
    print("=" * 60)
    
    # ───────────────────────────────────────────────
    # 步骤 1: 概念检索
    # ───────────────────────────────────────────────
    print("\n【步骤 1】概念检索...")
    retriever = ConceptRetriever(graph_store=store)
    
    # 解析目标概念名称
    seed_concepts = retriever.resolve([target_concept_name])
    print(f"  ✓ 解析到 {len(seed_concepts)} 个种子概念:")
    for c in seed_concepts:
        print(f"    - {c.name} (id={c.canonical_id}, type={c.concept_type})")
    
    # 扩展相关概念
    related = retriever.expand(seed_concepts, hop=1, max_nodes=10)
    print(f"  ✓ 扩展后共 {len(related)} 个概念（含种子）")
    
    # ───────────────────────────────────────────────
    # 步骤 2: 子图构建
    # ───────────────────────────────────────────────
    print("\n【步骤 2】子图构建...")
    builder = SubgraphBuilder(graph_store=store)
    
    # 构建题型专用子图（解答题模式）
    pattern = QuestionPattern(
        pattern_id="essay",
        name="解答题",
        concept_depth=2,
        max_concepts_per_question=10,
        require_concept_chain=True,
        context_budget=ContextBudget(max_tokens=3000, max_nodes=10)
    )
    
    subgraph = builder.build_for_pattern(seed_concepts[0], pattern)
    print(f"  ✓ 构建子图: {subgraph.node_count} 节点, {subgraph.edge_count} 边")
    print(f"  ✓ 模式: {subgraph.build_mode}")
    print(f"  ✓ 种子: {subgraph.seed_concepts}")
    
    # 展示子图结构
    print(f"\n  子图节点:")
    for i, node in enumerate(subgraph.nodes, 1):
        print(f"    {i}. {node.name} (id={node.canonical_id})")
    
    print(f"\n  子图边:")
    for edge in subgraph.edges:
        src = subgraph.node_map.get(edge.source_id)
        dst = subgraph.node_map.get(edge.target_id)
        if src and dst:
            print(f"    {src.name} --{edge.edge_type}--> {dst.name}")
    
    # ───────────────────────────────────────────────
    # 步骤 3: 上下文组装（出题）
    # ───────────────────────────────────────────────
    print("\n【步骤 3】上下文组装（出题）...")
    # 传入 graph_store，让来源文档显示文件名/章节/页码
    assembler = ContextAssembler(graph_store=store)
    
    question_context = assembler.assemble(
        subgraph=subgraph,
        budget=pattern.context_budget,
        include_prerequisites=True,
        target_concept=seed_concepts[0]
    )
    
    print(f"  ✓ Token 估算: {question_context.token_count}")
    print(f"  ✓ 预算: {pattern.context_budget.max_tokens}")
    print(f"  ✓ 段落数: {len(question_context.sections)}")
    
    # ───────────────────────────────────────────────
    # 步骤 4: IRT 参数估计与能力更新
    # ───────────────────────────────────────────────
    print("\n【步骤 4】IRT 参数估计与能力更新...")
    from core.graph_education.irt_estimator import IRTEstimator
    
    irt = IRTEstimator(calibration_stage=1)
    
    # 估计目标概念的 IRT 参数
    irt_params = irt.estimate_irt_params(seed_concepts[0], question_type="choice")
    print(f"  ✓ 启发式难度 b: {irt_params.b}")
    print(f"  ✓ 区分度 a: {irt_params.a}")
    print(f"  ✓ 猜测度 c: {irt_params.c}")
    print(f"  ✓ 校准阶段: {irt_params.calibration_stage}")
    
    # 模拟用户能力更新（假设初始 θ=0，答错后更新）
    theta_before = 0.0
    p = irt.compute_probability(theta_before, irt_params.a, irt_params.b, irt_params.c)
    print(f"  ✓ 初始能力 θ={theta_before}，答对概率 P={p:.2%}")
    
    # 模拟答错
    theta_after = irt.update_theta(theta_before, is_correct=0.0,
                                    a=irt_params.a, b=irt_params.b, c=irt_params.c)
    print(f"  ✓ 答错后能力 θ={theta_after}")
    
    # 计算信息量
    info = irt.compute_information(theta_before, irt_params.a, irt_params.b, irt_params.c)
    print(f"  ✓ 题目信息量 I(θ)={info:.4f}")
    
    # ───────────────────────────────────────────────
    # 步骤 5: 上下文组装（讲解）
    # ───────────────────────────────────────────────
    print("\n【步骤 5】上下文组装（讲解）...")
    
    # 模拟用户状态（基于 IRT 能力估计）
    user_states = {}
    for node in subgraph.nodes:
        if node.canonical_id == seed_concepts[0].canonical_id:
            # 目标概念：低掌握度（θ 映射到 mastery）
            mastery = irt.theta_to_mastery(theta_after)
        else:
            # 其他概念：中等掌握度
            mastery = 0.6
        user_states[node.canonical_id] = UserKnowledgeState(
            canonical_id=node.canonical_id,
            canonical_name=node.name,
            mastery_level=round(mastery, 2),
            test_count=3,
            streak=-1
        )
    
    explanation_context = assembler.assemble_explanation(
        subgraph=subgraph,
        user_states=user_states,
        target_concept=seed_concepts[0],
        depth="L2",
        user_answer="C"
    )
    
    print(f"  ✓ Token 估算: {explanation_context.token_count}")
    
    # ───────────────────────────────────────────────
    # 输出结果
    # ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("【最终输出】出题上下文")
    print("=" * 60)
    print(question_context.text)
    
    print("\n" + "=" * 60)
    print("【IRT 参数】")
    print("=" * 60)
    print(f"目标概念: {target_concept_name}")
    print(f"难度 b: {irt_params.b}")
    print(f"区分度 a: {irt_params.a}")
    print(f"猜测度 c: {irt_params.c}")
    print(f"初始能力 θ: {theta_before}")
    print(f"答错后能力 θ: {theta_after}")
    print(f"信息量 I(θ): {info:.4f}")
    
    print("\n" + "=" * 60)
    print("【最终输出】讲解上下文")
    print("=" * 60)
    print(explanation_context.text)
    
    print("\n" + "=" * 60)
    print("【评估】")
    print("=" * 60)
    
    # 自动评估
    checks = {
        "出题上下文包含目标概念": target_concept_name in question_context.text,
        "出题上下文包含关联概念": len(subgraph.nodes) > 1,
        "出题上下文包含来源文档": "来源文档" in question_context.text,
        "出题上下文包含文件名": "Attention_Is_All_You_Need.pdf" in question_context.text,
        "出题上下文包含章节": "章节:" in question_context.text or "heading" in question_context.text.lower(),
        "出题上下文包含页码": "页码:" in question_context.text,
        "IRT 参数已估计": irt_params.b != 0.0,
        "能力更新正确": theta_after < theta_before,  # 答错后能力下降
        "信息量 > 0": info > 0,
        "讲解上下文包含错因定位": "错因" in explanation_context.text or "掌握度" in explanation_context.text,
        "讲解上下文包含知识网络": "知识网络" in explanation_context.text or "概念" in explanation_context.text,
        "讲解上下文包含推荐学习": "推荐" in explanation_context.text or "优先" in explanation_context.text,
        "出题上下文在预算内": question_context.token_count <= pattern.context_budget.max_tokens,
        "讲解上下文在预算内": explanation_context.token_count <= 3000,
    }
    
    all_pass = True
    for check, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {check}")
        if not passed:
            all_pass = False
    
    print(f"\n{'全部通过' if all_pass else '存在失败项'}!")
    
    return {
        "question_context": question_context,
        "explanation_context": explanation_context,
        "subgraph": subgraph,
        "all_pass": all_pass
    }


# ═══════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("LA-040-P0: 图谱教育 Agent 完整流程测试")
    print("=" * 60)
    
    store, temp_dir = setup_test_database()
    try:
        result = run_full_pipeline(store, target_concept_name="多头注意力")
        
        if result["all_pass"]:
            print("\n✓ 流程测试通过，上下文组装结果合理")
        else:
            print("\n✗ 部分检查未通过，需要审查")
    finally:
        # 清理
        store._db = None
        store._conn = None
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"\n[清理] 临时数据库已删除: {temp_dir}")
