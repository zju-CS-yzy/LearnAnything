"""
LA-035 Phase 2.3: 语义聚合验证测试

测试场景:
    文档结构:
        # 深度学习架构
        ## Transformer架构
           - 段落: "Transformer是一种基于自注意力机制的深度学习模型..."
           - 提取概念: "Transformer", "自注意力机制"
        ## RNN
           - 段落: "RNN是循环神经网络..."
           - 提取概念: "RNN"

    期望结果:
        - "Transformer架构" 标题匹配 "Transformer" 主题概念
        - HAS_DETAIL: Transformer -> 自注意力机制
        - "RNN" 标题匹配 "RNN" 主题概念（无细节概念）
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.graph_store import GraphStore
from core.concept_deduper import ConceptDeduper
from core.semantic_aggregator import SemanticAggregator

TEST_COLLECTION = "test_semantic_aggregator"


def setup_test_data():
    """设置测试数据"""
    print("=" * 60)
    print("LA-035 Phase 2.3: 语义聚合验证测试")
    print("=" * 60)

    # Step 1: 重建数据库 Schema
    print("\n[Setup] 重建数据库 Schema...")
    store = GraphStore(TEST_COLLECTION)
    store.init_schema(force=True)
    print("  [OK] Schema 重建完成")

    # Step 2: 添加 Chunk 节点（模拟 MarkdownChunker v2.0 输出）
    print("\n[Setup] 添加 Chunk 节点...")
    chunks = [
        # Document root
        {
            "id": "doc_001",
            "text": "[文档: test.pdf]",
            "metadata": {
                "source": "test.pdf",
                "chunk_type": "document",
                "heading_path": "",
                "heading_level": 0,
                "child_ids": ["h1_001"],
            },
        },
        # Level 1 Heading
        {
            "id": "h1_001",
            "text": "# 深度学习架构\n\n本文介绍深度学习中的主要架构。",
            "metadata": {
                "source": "test.pdf",
                "chunk_type": "heading",
                "heading_path": "深度学习架构",
                "heading_level": 1,
                "parent_id": "doc_001",
                "child_ids": ["h2_001", "h2_002"],
                "paragraph_ids": ["p_001"],
            },
        },
        # Paragraph under h1_001
        {
            "id": "p_001",
            "text": "本文介绍深度学习中的主要架构，包括Transformer和RNN。",
            "metadata": {
                "source": "test.pdf",
                "chunk_type": "paragraph",
                "heading_path": "深度学习架构",
                "heading_level": 1,
                "parent_id": "h1_001",
            },
        },
        # Level 2 Heading: Transformer
        {
            "id": "h2_001",
            "text": "## Transformer架构\n\nTransformer是一种基于自注意力机制的深度学习模型架构。",
            "metadata": {
                "source": "test.pdf",
                "chunk_type": "heading",
                "heading_path": "深度学习架构 > Transformer架构",
                "heading_level": 2,
                "parent_id": "h1_001",
                "child_ids": [],
                "paragraph_ids": ["p_002", "p_003"],
            },
        },
        # Paragraphs under h2_001
        {
            "id": "p_002",
            "text": "Transformer是一种基于自注意力机制的深度学习模型架构，由Vaswani等人在2017年提出。",
            "metadata": {
                "source": "test.pdf",
                "chunk_type": "paragraph",
                "heading_path": "深度学习架构 > Transformer架构",
                "heading_level": 2,
                "parent_id": "h2_001",
            },
        },
        {
            "id": "p_003",
            "text": "自注意力机制允许模型同时关注输入序列中的所有位置，从而捕捉长距离依赖关系。",
            "metadata": {
                "source": "test.pdf",
                "chunk_type": "paragraph",
                "heading_path": "深度学习架构 > Transformer架构",
                "heading_level": 2,
                "parent_id": "h2_001",
            },
        },
        # Level 2 Heading: RNN
        {
            "id": "h2_002",
            "text": "## RNN\n\nRNN是循环神经网络，用于处理序列数据。",
            "metadata": {
                "source": "test.pdf",
                "chunk_type": "heading",
                "heading_path": "深度学习架构 > RNN",
                "heading_level": 2,
                "parent_id": "h1_001",
                "child_ids": [],
                "paragraph_ids": ["p_004"],
            },
        },
        # Paragraph under h2_002
        {
            "id": "p_004",
            "text": "RNN是循环神经网络，通过隐藏状态传递信息，适合处理时序数据。",
            "metadata": {
                "source": "test.pdf",
                "chunk_type": "paragraph",
                "heading_path": "深度学习架构 > RNN",
                "heading_level": 2,
                "parent_id": "h2_002",
            },
        },
    ]

    store.add_chunk_nodes(chunks)
    print(f"  [OK] 添加 {len(chunks)} 个 Chunk 节点")

    # Step 3: 添加 ExtractedConcept 节点
    print("\n[Setup] 添加 ExtractedConcept 节点...")
    extracted_concepts = {
        "p_002": [
            {"id": "ec_transformer", "name": "Transformer", "concept_type": "definition", "relation": "DEFINES", "description": "基于自注意力机制的深度学习模型架构"},
            {"id": "ec_attention", "name": "自注意力机制", "concept_type": "definition", "relation": "DEFINES", "description": "允许模型同时关注所有输入位置的机制"},
        ],
        "p_003": [
            {"id": "ec_attention2", "name": "自注意力机制", "concept_type": "definition", "relation": "DEFINES", "description": "捕捉长距离依赖关系的机制"},
            {"id": "ec_long_distance", "name": "长距离依赖", "concept_type": "definition", "relation": "DEFINES", "description": "序列中相隔较远元素之间的关联"},
        ],
        "p_004": [
            {"id": "ec_rnn", "name": "RNN", "concept_type": "definition", "relation": "DEFINES", "description": "循环神经网络，通过隐藏状态传递信息"},
        ],
    }

    for chunk_id, concepts in extracted_concepts.items():
        store.add_concepts(chunk_id, concepts)
    print(f"  [OK] 添加 {sum(len(v) for v in extracted_concepts.values())} 个 ExtractedConcept")

    # Step 4: 去重生成 CanonicalConcept
    print("\n[Setup] 去重生成 CanonicalConcept...")
    deduper = ConceptDeduper(TEST_COLLECTION, graph_store=store)
    canonicals = deduper.dedupe_all()
    print(f"  [OK] 生成 {len(canonicals)} 个 CanonicalConcept")

    # 打印 canonical 概念列表
    for c in canonicals:
        print(f"    - {c['name']} ({c['id']})")

    return chunks, store, canonicals


def test_semantic_aggregation():
    """测试语义聚合"""
    chunks, store, canonicals = setup_test_data()

    # Step 5: 运行语义聚合
    print("\n[Test] 运行 SemanticAggregator...")
    aggregator = SemanticAggregator(TEST_COLLECTION, graph_store=store)
    result = aggregator.aggregate(chunks)

    print(f"\n  结果统计:")
    print(f"    - HeadingChunk 数量: {result['heading_count']}")
    print(f"    - 主题概念数量: {len(result['theme_concepts'])}")
    print(f"    - HAS_DETAIL 关系: {result['has_detail_edges']} 条")

    # Step 6: 验证 HAS_DETAIL 关系
    print("\n[Test] 验证 HAS_DETAIL 关系...")
    edges = store.get_has_detail_edges(limit=100)
    print(f"  从数据库读取到 {len(edges)} 条 HAS_DETAIL 关系:")

    for edge in edges:
        print(f"    - {edge['source']} --[HAS_DETAIL]--> {edge['target']} (confidence={edge['confidence']})")

    # 验证: Transformer 标题下应该有 HAS_DETAIL 关系
    # 主题概念应该是 "Transformer" 或 "自注意力机制"
    transformer_theme = None
    attention_theme = None
    for c in canonicals:
        if c["name"] == "Transformer":
            transformer_theme = c["id"]
        elif c["name"] == "自注意力机制":
            attention_theme = c["id"]

    # 验证关系数量
    assert len(edges) > 0, "应该有 HAS_DETAIL 关系"
    print(f"  [OK] 存在 {len(edges)} 条 HAS_DETAIL 关系")

    # 验证关系的方向: 主题 -> 细节
    if transformer_theme:
        theme_edges = [e for e in edges if e["source"] == transformer_theme]
        print(f"  [INFO] Transformer 作为主题的边: {len(theme_edges)} 条")

    if attention_theme:
        theme_edges = [e for e in edges if e["source"] == attention_theme]
        print(f"  [INFO] 自注意力机制 作为主题的边: {len(theme_edges)} 条")

    print("\n" + "=" * 60)
    print("语义聚合测试完成!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    try:
        success = test_semantic_aggregation()
        sys.exit(0 if success else 1)
    except AssertionError as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
