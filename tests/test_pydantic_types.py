"""
Pydantic 类型定义快速验证测试
验证：序列化/反序列化兼容性、旧数据格式兼容、API 输出格式一致
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.types import (
    MediaRef, ImageRef, ChunkMetadata, Chunk,
    ExtractedConcept, CanonicalConcept, RelationEdge,
    GraphNodeResponse, GraphEdgeResponse, ChunkResponse,
)

def dump(obj):
    """兼容 to_dict 或 model_dump。"""
    if hasattr(obj, 'to_dict'):
        return obj.to_dict()
    return obj.model_dump(mode="json")

def test_media_ref():
    print("[Test] MediaRef...")
    
    old_dict = {
        "type": "image",
        "path": "test.png",
        "thumbnail_path": "thumb.png",
        "description": "test image",
        "width": 800,
        "height": 600,
    }
    
    mr = MediaRef(**old_dict)
    assert mr.type == "image"
    assert mr.path == "test.png"
    assert mr.width == 800
    
    d = dump(mr)
    assert d["type"] == "image"
    assert d["path"] == "test.png"
    print("  [OK] MediaRef")


def test_chunk_metadata():
    print("[Test] ChunkMetadata...")
    
    old_meta = {
        "source": "test.pdf",
        "subject": "ai",
        "chunk_type": "title",  # 旧格式 "title" 应映射为 "heading"
        "heading_path": "深度学习 > Transformer",
        "heading_level": 2,
        "parent_id": "doc_001",
        "child_ids": ["h3_001"],
        "paragraph_ids": ["p_001", "p_002"],
        "line_range": [10, 25],
        "image_refs": [{"alt": "arch", "path": "arch.png"}],
        "media_refs": [{"type": "image", "path": "arch.png"}],
        "formula_count": 2,
        "table_lines": 0,
        "page_number": 5,
    }
    
    meta = ChunkMetadata(**old_meta)
    assert meta.chunk_type == "heading"
    assert meta.heading_level == 2
    assert len(meta.image_refs) == 1
    assert len(meta.media_refs) == 1
    assert meta.page_number == 5
    
    d = dump(meta)
    assert d["chunk_type"] == "heading"
    print("  [OK] ChunkMetadata")


def test_chunk():
    print("[Test] Chunk...")
    
    old_chunk = {
        "id": "chunk_001",
        "text": "Transformer 是一种...",
        "metadata": {
            "source": "test.pdf",
            "chunk_type": "paragraph",
            "heading_path": "深度学习",
        },
        "source": "test.pdf",
    }
    
    chunk = Chunk(**old_chunk)
    assert chunk.id == "chunk_001"
    assert chunk.metadata.chunk_type == "paragraph"
    
    assert chunk["id"] == "chunk_001"
    assert "metadata" in chunk
    assert chunk.get("source") == "test.pdf"
    
    d = dump(chunk)
    assert d["id"] == "chunk_001"
    assert d["metadata"]["chunk_type"] == "paragraph"
    print("  [OK] Chunk")


def test_extracted_concept():
    print("[Test] ExtractedConcept...")
    
    old_concept = {
        "id": "ec_001",
        "name": "Transformer",
        "concept_type": "definition",
        "relation": "DEFINES",
        "description": "基于自注意力...",
        "parent_hint": "深度学习",
        "source_chunk": "chunk_001",
        "media_refs": [{"type": "image", "path": "arch.png"}],
    }
    
    ec = ExtractedConcept(**old_concept)
    assert ec.name == "Transformer"
    assert ec.get("relation") == "DEFINES"
    assert len(ec.media_refs) == 1
    
    d = dump(ec)
    assert d["name"] == "Transformer"
    print("  [OK] ExtractedConcept")


def test_canonical_concept():
    print("[Test] CanonicalConcept...")
    
    old_cc = {
        "canonical_id": "cc_001",
        "name": "Transformer",
        "aliases": '["transformer", "Transformer模型"]',
        "source_chunks": '["chunk_001", "chunk_002"]',
        "type_votes": '{"definition": 3, "technology": 1}',
        "media_refs": '[{"type": "image", "path": "arch.png"}]',
    }
    
    cc = CanonicalConcept(**old_cc)
    assert "transformer" in cc.aliases
    assert "chunk_001" in cc.source_chunks
    assert cc.type_votes["definition"] == 3
    assert len(cc.media_refs) == 1
    
    d = dump(cc)
    assert d["name"] == "Transformer"
    print("  [OK] CanonicalConcept")


def test_relation_edge():
    print("[Test] RelationEdge...")
    
    edge = {
        "parent_id": "cc_001",
        "child_id": "cc_002",
        "relation_type": "SOLUTION",
        "confidence": 0.92,
        "reason": "test",
        "stage": "parent_hint",
    }
    
    re = RelationEdge(**edge)
    assert re.parent_id == "cc_001"
    assert re.child_id == "cc_002"
    assert re.relation_type == "SOLUTION"
    
    d = dump(re)
    assert d["confidence"] == 0.92
    print("  [OK] RelationEdge")


def test_api_response():
    print("[Test] API 响应模型...")
    
    node = GraphNodeResponse(
        id="cc_001",
        label="Transformer",
        type="definition",
        media_refs=[MediaRef(type="image", path="arch.png")],
    )
    d = dump(node)
    assert d["id"] == "cc_001"
    assert d["media_refs"][0]["type"] == "image"
    
    chunk_resp = ChunkResponse(
        id="chunk_001",
        text="test",
        metadata=ChunkMetadata(chunk_type="paragraph"),
        chunk_type="paragraph",  # 顶层字段
    )
    d = dump(chunk_resp)
    assert d["chunk_type"] == "paragraph"
    
    print("  [OK] API 响应模型")


if __name__ == "__main__":
    try:
        test_media_ref()
        test_chunk_metadata()
        test_chunk()
        test_extracted_concept()
        test_canonical_concept()
        test_relation_edge()
        test_api_response()
        
        print("\n" + "=" * 50)
        print("所有类型定义测试通过!")
        print("=" * 50)
    except Exception as e:
        print(f"\n[FAIL] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
