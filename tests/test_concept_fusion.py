"""
LA-035 Phase 3: 概念融合验证测试

测试场景：图片概念与文本概念的去重合并

模拟数据：
  - Text chunk: "Transformer 是一种基于自注意力机制的深度学习模型架构"
    提取概念: "Transformer", "自注意力机制"
  
  - Image pseudo chunk: "[图片 - Transformer架构] 图中展示了Transformer的编码器-解码器结构，
    包含多头注意力层、前馈神经网络和残差连接"
    提取概念: "Transformer", "多头注意力层", "编码器-解码器结构"
    media_refs: [{"type": "image", "path": "transformer_arch.png", ...}]

验证目标：
  1. "Transformer" 被文本和图片都提到，去重后只保留一个 CanonicalConcept
  2. 合并后的 "Transformer" CanonicalConcept 同时包含 text 和 image 的来源
  3. "Transformer" CanonicalConcept 的 media_refs 包含图片引用
  4. "多头注意力层" 只来自图片，CanonicalConcept 有 media_refs
  5. "自注意力机制" 只来自文本，CanonicalConcept 无 media_refs
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.graph_store import GraphStore
from core.concept_deduper import ConceptDeduper

TEST_COLLECTION = "test_concept_fusion"


def test_concept_fusion():
    print("=" * 60)
    print("LA-035 Phase 3: 概念融合验证测试")
    print("=" * 60)

    # Step 1: 重建数据库 Schema
    print("\n[Step 1] 重建数据库 Schema...")
    store = GraphStore(TEST_COLLECTION)
    store.init_schema(force=True)
    print("  [OK] Schema 重建完成")

    # Step 2: 添加 Chunk 节点
    print("\n[Step 2] 添加 Chunk 节点...")
    text_chunk = {
        "id": "text_chunk_001",
        "text": "Transformer 是一种基于自注意力机制的深度学习模型架构",
        "metadata": {
            "source": "test.pdf",
            "subject": "generic",
            "chunk_type": "paragraph",
            "heading_path": "深度学习架构 > Transformer架构",
            "page_number": 1,
        },
    }
    image_pseudo_chunk = {
        "id": "img_pseudo_001",
        "text": "[图片 - Transformer架构] 图中展示了Transformer的编码器-解码器结构，包含多头注意力层、前馈神经网络和残差连接",
        "metadata": {
            "source": "test.pdf",
            "subject": "generic",
            "chunk_type": "image_pseudo",
            "heading_path": "深度学习架构 > Transformer架构",
            "parent_id": "h2_001",
            "media_refs": [
                {
                    "type": "image",
                    "path": "generic_v1_images/transformer_arch.png",
                    "thumbnail_path": "generic_v1_thumbnails/transformer_arch.png",
                    "description": "Transformer 编码器-解码器架构图",
                    "width": 1200,
                    "height": 800,
                }
            ],
            "description_source": "vlm",
        },
    }
    store.add_chunk_nodes([text_chunk, image_pseudo_chunk])
    print("  [OK] 添加 2 个 Chunk 节点")

    # Step 3: 添加 ExtractedConcept（模拟语义提取结果）
    print("\n[Step 3] 添加 ExtractedConcept（模拟语义提取结果）...")
    
    # 文本 chunk 提取的概念（不含 media_refs）
    text_concepts = [
        {
            "id": "ec_text_transformer",
            "name": "Transformer",
            "concept_type": "definition",
            "relation": "DEFINES",
            "description": "基于自注意力机制的深度学习模型架构",
            "parent_hint": "",
        },
        {
            "id": "ec_text_attention",
            "name": "自注意力机制",
            "concept_type": "definition",
            "relation": "DEFINES",
            "description": "允许模型同时关注所有输入位置的机制",
            "parent_hint": "Transformer",
        },
    ]
    
    # 图片 pseudo chunk 提取的概念（含 media_refs）
    image_concepts = [
        {
            "id": "ec_img_transformer",
            "name": "Transformer",
            "concept_type": "definition",
            "relation": "DEFINES",
            "description": "编码器-解码器结构的深度学习模型",
            "parent_hint": "",
            "media_refs": [
                {
                    "type": "image",
                    "path": "generic_v1_images/transformer_arch.png",
                    "thumbnail_path": "generic_v1_thumbnails/transformer_arch.png",
                    "description": "Transformer 编码器-解码器架构图",
                    "width": 1200,
                    "height": 800,
                }
            ],
        },
        {
            "id": "ec_img_multi_head",
            "name": "多头注意力层",
            "concept_type": "definition",
            "relation": "DEFINES",
            "description": "Transformer 中并行的多个注意力头",
            "parent_hint": "Transformer",
            "media_refs": [
                {
                    "type": "image",
                    "path": "generic_v1_images/transformer_arch.png",
                    "thumbnail_path": "generic_v1_thumbnails/transformer_arch.png",
                    "description": "Transformer 编码器-解码器架构图",
                    "width": 1200,
                    "height": 800,
                }
            ],
        },
        {
            "id": "ec_img_encoder_decoder",
            "name": "编码器-解码器结构",
            "concept_type": "definition",
            "relation": "DEFINES",
            "description": "由编码器和解码器两部分组成的模型架构",
            "parent_hint": "Transformer",
            "media_refs": [
                {
                    "type": "image",
                    "path": "generic_v1_images/transformer_arch.png",
                    "thumbnail_path": "generic_v1_thumbnails/transformer_arch.png",
                    "description": "Transformer 编码器-解码器架构图",
                    "width": 1200,
                    "height": 800,
                }
            ],
        },
    ]
    
    added_text = store.add_concepts("text_chunk_001", text_concepts)
    added_img = store.add_concepts("img_pseudo_001", image_concepts)
    print(f"  [OK] Text: {added_text} 个概念, Image: {added_img} 个概念")

    # Step 4: 读取 ExtractedConcept 验证 media_refs
    print("\n[Step 4] 读取 ExtractedConcept 验证 media_refs...")
    extracted = store.get_extracted_concepts(limit=100)
    for ec in extracted:
        refs = ec.get("media_refs", [])
        has_refs = "[有media_refs]" if refs else "[无media_refs]"
        print(f"    - {ec['name']} ({ec['source_chunk']}): {has_refs}")
    
    # 验证
    transformer_text = next((c for c in extracted if c["name"] == "Transformer" and c["source_chunk"] == "text_chunk_001"), None)
    transformer_img = next((c for c in extracted if c["name"] == "Transformer" and c["source_chunk"] == "img_pseudo_001"), None)
    multi_head = next((c for c in extracted if c["name"] == "多头注意力层"), None)
    
    assert transformer_text is not None, "未找到 text 来源的 Transformer"
    assert transformer_img is not None, "未找到 image 来源的 Transformer"
    assert len(transformer_text.get("media_refs", [])) == 0, "text 来源的 Transformer 应无 media_refs"
    assert len(transformer_img.get("media_refs", [])) == 1, "image 来源的 Transformer 应有 1 个 media_refs"
    assert len(multi_head.get("media_refs", [])) == 1, "多头注意力层 应有 1 个 media_refs"
    print("  [OK] ExtractedConcept media_refs 分布正确")

    # Step 5: 去重合并
    print("\n[Step 5] 运行 ConceptDeduper 去重合并...")
    deduper = ConceptDeduper(TEST_COLLECTION, graph_store=store)
    canonicals = deduper.dedupe_all()
    print(f"  [OK] 生成 {len(canonicals)} 个 CanonicalConcept")
    
    for c in canonicals:
        print(f"    - {c['name']} (aliases={c['alias_count']}, sources={c['source_chunk_count']}, media_refs={len(c.get('media_refs', []))})")

    # Step 6: 验证去重合并结果
    print("\n[Step 6] 验证去重合并结果...")
    
    # 6a. "Transformer" 应该合并为一个 CanonicalConcept（同名概念被合并）
    transformer_cc = next((c for c in canonicals if c["name"] == "Transformer"), None)
    assert transformer_cc is not None, "未找到 Transformer CanonicalConcept"
    # alias_count=1 因为两个 "Transformer" 同名（set 去重后只剩一个），但 source_chunk_count=2
    assert transformer_cc["source_chunk_count"] >= 2, f"Transformer 应有至少 2 个来源, 实际 {transformer_cc['source_chunk_count']}"
    print(f"  [OK] Transformer 合并了 {transformer_cc['source_chunk_count']} 个来源")
    
    # 6b. "Transformer" 的 source_chunks 应包含 text 和 image 两个来源
    source_chunks = transformer_cc.get("source_chunks", [])
    has_text_source = any("text" in s for s in source_chunks)
    has_img_source = any("img" in s for s in source_chunks)
    assert has_text_source, "Transformer 应包含 text 来源"
    assert has_img_source, "Transformer 应包含 image 来源"
    print(f"  [OK] Transformer source_chunks: {source_chunks}")
    
    # 6c. "Transformer" 的 media_refs 应包含图片引用（来自 image pseudo chunk）
    cc_media_refs = transformer_cc.get("media_refs", [])
    assert len(cc_media_refs) >= 1, f"Transformer CanonicalConcept 应保留 media_refs, 实际 {len(cc_media_refs)}"
    assert cc_media_refs[0]["type"] == "image", "media_refs[0] 应为 image 类型"
    assert "transformer_arch" in cc_media_refs[0].get("path", ""), "media_refs 应指向 transformer_arch 图片"
    print(f"  [OK] Transformer media_refs: {cc_media_refs[0]['path']}")
    
    # 6d. "多头注意力层" 应该有 media_refs（只来自图片）
    multi_head_cc = next((c for c in canonicals if c["name"] == "多头注意力层"), None)
    assert multi_head_cc is not None, "未找到 多头注意力层 CanonicalConcept"
    mh_refs = multi_head_cc.get("media_refs", [])
    assert len(mh_refs) == 1, f"多头注意力层 应有 1 个 media_refs, 实际 {len(mh_refs)}"
    print(f"  [OK] 多头注意力层 media_refs: {mh_refs[0]['path']}")
    
    # 6e. "自注意力机制" 应该没有 media_refs（只来自文本）
    attention_cc = next((c for c in canonicals if c["name"] == "自注意力机制"), None)
    assert attention_cc is not None, "未找到 自注意力机制 CanonicalConcept"
    att_refs = attention_cc.get("media_refs", [])
    assert len(att_refs) == 0, f"自注意力机制 应无 media_refs, 实际 {len(att_refs)}"
    print(f"  [OK] 自注意力机制 无 media_refs")

    # Step 7: 从数据库读取验证
    print("\n[Step 7] 从 KùzuDB 读取 CanonicalConcept 验证...")
    db_concepts = store.get_canonical_concepts(limit=100)
    transformer_db = next((c for c in db_concepts if c["name"] == "Transformer"), None)
    assert transformer_db is not None, "数据库中未找到 Transformer"
    db_refs = transformer_db.get("media_refs", [])
    assert len(db_refs) >= 1, f"数据库中 Transformer 应有 media_refs"
    print(f"  [OK] 数据库中 Transformer 保留 {len(db_refs)} 个 media_refs")

    print("\n" + "=" * 60)
    print("概念融合测试全部通过!")
    print("=" * 60)
    print("\n核心验证点:")
    print("  1. [OK] 重复概念 'Transformer' 正确合并为 1 个 CanonicalConcept")
    print("  2. [OK] 合并后的 'Transformer' 同时包含 text 和 image 来源")
    print("  3. [OK] 合并后的 'Transformer' 保留图片 media_refs")
    print("  4. [OK] 图片独有概念 '多头注意力层' 保留 media_refs")
    print("  5. [OK] 文本独有概念 '自注意力机制' 无 media_refs")
    
    return True


if __name__ == "__main__":
    try:
        success = test_concept_fusion()
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
