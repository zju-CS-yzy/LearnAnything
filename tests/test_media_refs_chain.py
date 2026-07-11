"""
LA-035-P4: media_refs 传递链修复验证测试

验证路径:
    Chunk(media_refs) 
    -> SemanticExtractor(media_context) 
    -> ExtractedConcept(media_refs in KuzuDB)
    -> ConceptDeduper(collect_all_concepts reads media_refs)
    -> CanonicalConcept(media_refs merged)

测试步骤:
    1. 重建数据库 Schema (force=True)
    2. 添加测试 Chunk 节点
    3. 添加带 media_refs 的 ExtractedConcept
    4. 读取 ExtractedConcept 验证 media_refs
    5. 运行去重，验证 CanonicalConcept 中 media_refs 被合并
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.graph_store import GraphStore
from core.concept_deduper import ConceptDeduper

TEST_COLLECTION = "test_media_refs_chain"


def test_media_refs_chain():
    print("=" * 60)
    print("LA-035-P4: media_refs 传递链验证测试")
    print("=" * 60)
    
    # Step 1: 重建数据库 Schema
    print("\n[Step 1] 重建数据库 Schema...")
    store = GraphStore(TEST_COLLECTION)
    store.init_schema(force=True)
    print("  [OK] Schema 重建完成")
    
    # Step 2: 添加测试 Chunk 节点
    print("\n[Step 2] 添加测试 Chunk 节点...")
    test_chunks = [
        {
            "id": "test_chunk_001",
            "text": "Transformer 是一种基于自注意力机制的深度学习架构",
            "metadata": {
                "source": "test.pdf",
                "subject": "test",
                "chunk_type": "paragraph",
                "heading_path": "深度学习架构",
                "page_number": 1,
                "media_refs": [
                    {
                        "type": "image",
                        "path": "test_v1_images/arch.png",
                        "thumbnail_path": "test_v1_thumbnails/arch.png",
                        "description": "Transformer 架构图",
                        "width": 800,
                        "height": 600,
                    }
                ],
            },
        },
        {
            "id": "test_chunk_002",
            "text": "RNN 是循环神经网络，用于序列建模",
            "metadata": {
                "source": "test.pdf",
                "subject": "test",
                "chunk_type": "paragraph",
                "heading_path": "循环神经网络",
                "page_number": 2,
            },
        },
    ]
    added = store.add_chunk_nodes(test_chunks)
    print(f"  [OK] 添加 {added} 个 Chunk 节点")
    
    # Step 3: 添加带 media_refs 的 ExtractedConcept
    print("\n[Step 3] 添加带 media_refs 的 ExtractedConcept...")
    concepts_001 = [
        {
            "id": "test_concept_001",
            "name": "Transformer",
            "concept_type": "definition",
            "relation": "DEFINES",
            "description": "基于自注意力机制的深度学习架构",
            "parent_hint": "深度学习",
            "media_refs": [
                {
                    "type": "image",
                    "path": "test_v1_images/arch.png",
                    "thumbnail_path": "test_v1_thumbnails/arch.png",
                    "description": "Transformer 架构图",
                    "width": 800,
                    "height": 600,
                }
            ],
        },
        {
            "id": "test_concept_002",
            "name": "自注意力机制",
            "concept_type": "definition",
            "relation": "DEFINES",
            "description": "允许模型同时关注所有输入元素的机制",
            "parent_hint": "Transformer",
        },
    ]
    concepts_002 = [
        {
            "id": "test_concept_003",
            "name": "RNN",
            "concept_type": "definition",
            "relation": "DEFINES",
            "description": "循环神经网络，用于序列建模",
            "parent_hint": "神经网络",
        },
    ]
    
    added_001 = store.add_concepts("test_chunk_001", concepts_001)
    added_002 = store.add_concepts("test_chunk_002", concepts_002)
    print(f"  [OK] Chunk 001: {added_001} 个概念, Chunk 002: {added_002} 个概念")
    
    # Step 4: 读取 ExtractedConcept，验证 media_refs
    print("\n[Step 4] 读取 ExtractedConcept 验证 media_refs...")
    extracted = store.get_extracted_concepts(limit=100)
    print(f"  读取到 {len(extracted)} 个 ExtractedConcept")
    
    for ec in extracted:
        refs = ec.get("media_refs", [])
        has_refs = "[有media_refs]" if refs else "[无media_refs]"
        print(f"    - {ec['name']}: {has_refs}")
        if refs:
            for ref in refs:
                print(f"      -> type={ref.get('type')}, path={ref.get('path', 'N/A')}")
    
    # 验证: Transformer 必须有 media_refs
    transformer_ec = next((c for c in extracted if c["name"] == "Transformer"), None)
    assert transformer_ec is not None, "未找到 Transformer ExtractedConcept"
    assert len(transformer_ec.get("media_refs", [])) == 1, f"Transformer 应有 1 个 media_refs, 实际 {len(transformer_ec.get('media_refs', []))}"
    assert transformer_ec["media_refs"][0]["type"] == "image", "media_refs[0] 应为 image 类型"
    print("  [OK] ExtractedConcept media_refs 验证通过")
    
    # 验证: RNN 应该没有 media_refs
    rnn_ec = next((c for c in extracted if c["name"] == "RNN"), None)
    assert rnn_ec is not None, "未找到 RNN ExtractedConcept"
    assert len(rnn_ec.get("media_refs", [])) == 0, f"RNN 应无 media_refs, 实际 {len(rnn_ec.get('media_refs', []))}"
    print("  [OK] RNN 无 media_refs 验证通过")
    
    # Step 5: 运行去重，验证 CanonicalConcept 中 media_refs
    print("\n[Step 5] 运行 ConceptDeduper 验证 media_refs 合并...")
    deduper = ConceptDeduper(TEST_COLLECTION, graph_store=store)
    canonical_concepts = deduper.dedupe_all()
    print(f"  [OK] 生成 {len(canonical_concepts)} 个 CanonicalConcept")
    
    # 验证: Transformer 的 CanonicalConcept 必须保留 media_refs
    transformer_cc = next((c for c in canonical_concepts if c["name"] == "Transformer"), None)
    assert transformer_cc is not None, "未找到 Transformer CanonicalConcept"
    cc_media_refs = transformer_cc.get("media_refs", [])
    assert len(cc_media_refs) >= 1, f"Transformer CanonicalConcept 应保留 media_refs, 实际 {len(cc_media_refs)}"
    print(f"  [OK] Transformer CanonicalConcept 保留 {len(cc_media_refs)} 个 media_refs")
    
    # 验证: RNN 的 CanonicalConcept 应该没有 media_refs
    rnn_cc = next((c for c in canonical_concepts if c["name"] == "RNN"), None)
    assert rnn_cc is not None, "未找到 RNN CanonicalConcept"
    assert len(rnn_cc.get("media_refs", [])) == 0, f"RNN CanonicalConcept 应无 media_refs"
    print("  [OK] RNN CanonicalConcept 无 media_refs 验证通过")
    
    # 从数据库读取 CanonicalConcept 验证
    print("\n[Step 6] 从 KùzuDB 读取 CanonicalConcept 验证...")
    db_concepts = store.get_canonical_concepts(limit=100)
    transformer_db = next((c for c in db_concepts if c["name"] == "Transformer"), None)
    assert transformer_db is not None, "数据库中未找到 Transformer"
    db_refs = transformer_db.get("media_refs", [])
    assert len(db_refs) >= 1, f"数据库中 Transformer 应有 media_refs"
    print(f"  [OK] 数据库中 Transformer 保留 {len(db_refs)} 个 media_refs")
    
    print("\n" + "=" * 60)
    print("所有测试通过! media_refs 传递链完整")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        success = test_media_refs_chain()
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
