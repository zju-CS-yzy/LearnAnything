"""
LA-035-P18: 验证 add_chunk_nodes media_refs 写入 + _get_media_refs_from_chunks 回退逻辑

测试目标:
    1. add_chunk_nodes 现在将 metadata 中的 media_refs 写入 Chunk 节点
    2. _get_media_refs_from_chunks 在 Chunk media_refs 为空时，正确回退到 image_path

测试步骤:
    1. 重建数据库 Schema
    2. 添加带 media_refs 的 Chunk 节点 → 验证 Chunk.media_refs 已写入
    3. 添加不带 media_refs 但有 image_path 的 Chunk 节点
    4. 创建一个 CanonicalConcept，关联到该 Chunk，media_refs 为空
    5. 调用 _get_media_refs_from_chunks 回退 → 验证能拿到 image_path 构建的 media_refs
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.graph_store import GraphStore

TEST_COLLECTION = "test_p18_fix"


def test_add_chunk_nodes_media_refs():
    """测试1: add_chunk_nodes 是否正确写入 media_refs"""
    print("=" * 60)
    print("[测试1] add_chunk_nodes media_refs 写入验证")
    print("=" * 60)
    
    store = GraphStore(TEST_COLLECTION)
    store.init_schema(force=True)
    
    # 添加带 media_refs 的 Chunk
    test_chunks = [
        {
            "id": "chunk_with_media",
            "text": "测试文本",
            "metadata": {
                "source": "test.pdf",
                "chunk_type": "paragraph",
                "heading_path": "测试",
                "page_number": 1,
                "media_refs": [
                    {
                        "type": "image",
                        "path": "images/test.png",
                        "thumbnail_path": "thumbnails/test.png",
                        "description": "测试图片",
                        "width": 100,
                        "height": 200,
                    }
                ],
            },
        },
    ]
    
    added = store.add_chunk_nodes(test_chunks)
    print(f"  添加 {added} 个 Chunk 节点")
    assert added == 1, "应添加 1 个 Chunk"
    
    # 直接查询 Chunk 节点的 media_refs
    conn = store._ensure_db()
    result = store._execute(conn, "MATCH (c:Chunk {chunk_id: 'chunk_with_media'}) RETURN c.media_refs")
    assert result.has_next(), "应能查询到 Chunk"
    row = result.get_next()
    media_refs_json = row[0]
    
    assert media_refs_json and media_refs_json != "", f"Chunk.media_refs 应为非空 JSON, 实际为: {repr(media_refs_json)}"
    
    import json
    media_refs = json.loads(media_refs_json)
    assert len(media_refs) == 1, f"应有 1 个 media_refs, 实际 {len(media_refs)}"
    assert media_refs[0]["type"] == "image", "media_refs[0] 应为 image 类型"
    assert media_refs[0]["path"] == "images/test.png", f"path 应为 images/test.png, 实际 {media_refs[0].get('path')}"
    
    print(f"  [OK] Chunk.media_refs 正确写入: {media_refs}")
    return True


def test_fallback_with_image_path():
    """测试2: _get_media_refs_from_chunks 回退逻辑"""
    print("\n" + "=" * 60)
    print("[测试2] _get_media_refs_from_chunks 回退逻辑验证")
    print("=" * 60)
    
    store = GraphStore(TEST_COLLECTION)
    store.init_schema(force=True)
    
    # 添加一个 Chunk: 无 media_refs 但有 image_path（模拟旧数据或图片 chunk）
    test_chunks = [
        {
            "id": "chunk_image_only",
            "text": "图片描述",
            "metadata": {
                "source": "test.pdf",
                "chunk_type": "image_pseudo",
                "heading_path": "图片",
                "page_number": 2,
                # 注意: 不提供 media_refs，只提供 image_path
                "image_path": "images/fig1.png",
                "thumbnail_path": "thumbnails/fig1.png",
                "width": 300,
                "height": 400,
            },
        },
    ]
    
    added = store.add_chunk_nodes(test_chunks)
    print(f"  添加 {added} 个 Chunk 节点（无 media_refs，有 image_path）")
    
    # 验证 Chunk 的 media_refs 为空（因为 metadata 没提供）
    conn = store._ensure_db()
    result = store._execute(conn, "MATCH (c:Chunk {chunk_id: 'chunk_image_only'}) RETURN c.media_refs")
    assert result.has_next()
    row = result.get_next()
    chunk_media_refs = row[0]
    
    # 由于 metadata 没有 media_refs，且 add_chunk_nodes 中使用了 meta.get("media_refs", []) 
    # 所以写入的是空字符串 ""，不是 null
    # 但 image_path 已经写入
    print(f"  Chunk.media_refs = {repr(chunk_media_refs)}")
    
    # 测试 _get_media_refs_from_chunks 回退逻辑
    # 当 CanonicalConcept 的 media_refs 为空，应回退到 Chunk 的 image_path
    media_refs = store._get_media_refs_from_chunks(conn, ["chunk_image_only"])
    
    print(f"  _get_media_refs_from_chunks 返回: {media_refs}")
    assert len(media_refs) >= 1, f"回退应返回至少 1 个 media_refs, 实际 {len(media_refs)}"
    assert media_refs[0]["type"] == "image", "回退的 media_refs 应为 image 类型"
    assert media_refs[0]["path"] == "images/fig1.png", f"path 应为 images/fig1.png"
    
    print(f"  [OK] 回退逻辑正确: 从 image_path 构建 media_refs")
    return True


def test_chunk_with_empty_media_refs_and_image_path():
    """测试3: Chunk 有 media_refs 字段但值为空，同时有 image_path → 应回退"""
    print("\n" + "=" * 60)
    print("[测试3] 空 media_refs + 有 image_path 回退验证")
    print("=" * 60)
    
    store = GraphStore(TEST_COLLECTION)
    store.init_schema(force=True)
    
    # 手动添加一个 Chunk: media_refs 为空 JSON 数组，但有 image_path
    # 这模拟新 schema 但数据未正确填充的情况
    conn = store._ensure_db()
    cypher = """
        CREATE (c:Chunk {
            chunk_id: 'chunk_empty_media',
            text: '描述',
            heading_path: '测试',
            source: 'test.pdf',
            page_number: 3,
            chunk_type: 'image_pseudo',
            image_path: 'images/fig2.png',
            thumbnail_path: 'thumbnails/fig2.png',
            width: 500,
            height: 600,
            media_refs: ''
        })
    """
    store._execute(conn, cypher)
    print("  手动创建 Chunk（media_refs=''，image_path='images/fig2.png'）")
    
    # 测试回退逻辑
    media_refs = store._get_media_refs_from_chunks(conn, ["chunk_empty_media"])
    
    print(f"  _get_media_refs_from_chunks 返回: {media_refs}")
    assert len(media_refs) >= 1, f"应回退到 image_path, 实际返回 {len(media_refs)} 个"
    assert media_refs[0]["path"] == "images/fig2.png", f"path 应为 images/fig2.png"
    
    print(f"  [OK] 空 media_refs 时正确回退到 image_path")
    return True


def run_all_tests():
    try:
        test_add_chunk_nodes_media_refs()
        test_fallback_with_image_path()
        test_chunk_with_empty_media_refs_and_image_path()
        
        print("\n" + "=" * 60)
        print("所有测试通过!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n[FAIL] 断言失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n[ERROR] 异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
