"""
Phase 2.2 测试脚本：图片 → VLM 描述 → 伪文本 chunk

测试流程:
    1. 使用 MinerU 解析一个含图片的 PDF
    2. 用 MarkdownChunker 分块
    3. 用 ImageConceptExtractor 为图片生成 VLM 描述
    4. 输出伪文本 chunks

用法:
    cd D:\MyCS\AI\Project\LearnAnything
    python scripts\test_phase22_image_concepts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mineru_client import MinerUClient
from core.markdown_chunker import MarkdownChunker
from core.image_concept_extractor import ImageConceptExtractor
from core.vlm_client import VLMClient
from config.settings import KNOWLEDGE_BASE_DIR


def main():
    print("=" * 60)
    print("Phase 2.2 Test: Image -> VLM Description -> Pseudo Chunk")
    print("=" * 60)
    
    # 1. 检查 VLM 可用性
    print("\n[Step 1] Checking VLM API...")
    vlm = VLMClient()
    print(f"  API Key: {'OK' if vlm.available else 'MISSING'}")
    print(f"  Model: {vlm.MODEL}")
    print(f"  Base URL: {vlm.base_url}")
    
    if not vlm.available:
        print("  ERROR: VLM API not available, exiting")
        return
    
    # 2. 选择测试 PDF（含图片的）
    print("\n[Step 2] Selecting test PDF...")
    
    # 先用 RAG Fusion（已知有图片）
    test_pdf = KNOWLEDGE_BASE_DIR / "generic" / "raw" / "RAG Fusion优化策略面试题.pdf"
    if not test_pdf.exists():
        print(f"  ERROR: PDF not found: {test_pdf}")
        return
    
    print(f"  File: {test_pdf.name}")
    
    # 3. MinerU 解析
    print("\n[Step 3] Parsing with MinerU...")
    client = MinerUClient()
    
    try:
        md_text, output_dir, img_paths = client.parse_pdf_to_markdown(str(test_pdf))
        print(f"  Markdown length: {len(md_text)} chars")
        print(f"  Images found: {len(img_paths)}")
        for p in img_paths:
            print(f"    - {p.name}")
    except Exception as e:
        print(f"  ERROR: {e}")
        return
    
    # 4. Markdown 分块
    print("\n[Step 4] Chunking Markdown...")
    chunker = MarkdownChunker()
    parent_chunks, child_chunks = chunker.chunk_markdown(
        md_text,
        source_metadata={"source": test_pdf.name, "subject": "generic"},
    )
    print(f"  Parent chunks (titles): {len(parent_chunks)}")
    print(f"  Child chunks (paragraphs): {len(child_chunks)}")
    
    # 合并为统一列表
    chunks = []
    for parent in parent_chunks:
        chunks.append(parent)
        for child in child_chunks:
            if child["metadata"].get("parent_id") == parent["id"]:
                chunks.append(child)
    
    # 5. 检查哪些 chunk 包含图片
    print("\n[Step 5] Checking image references...")
    image_chunks = [c for c in chunks if c.get("metadata", {}).get("image_refs")]
    print(f"  Chunks with images: {len(image_chunks)}")
    
    for c in image_chunks:
        refs = c["metadata"]["image_refs"]
        heading = c["metadata"].get("heading_path", "")
        print(f"    [{heading[:40]}] -> {len(refs)} images")
    
    # 6. 使用 ImageConceptExtractor 生成描述
    print("\n[Step 6] Generating VLM descriptions for images...")
    print("  (This may take 30-60 seconds per image)")
    
    extractor = ImageConceptExtractor(vlm_client=vlm)
    enhanced_chunks = extractor.enrich_chunks_with_image_descriptions(
        chunks,
        subject="generic",
        base_dir=output_dir,  # 传入 MinerU 输出目录，用于解析相对路径
    )
    
    # 7. 统计结果
    print("\n[Step 7] Results:")
    pseudo_chunks = [c for c in enhanced_chunks if c.get("metadata", {}).get("chunk_type") == "image_pseudo"]
    print(f"  Original chunks: {len(chunks)}")
    print(f"  Enhanced chunks: {len(enhanced_chunks)}")
    print(f"  Pseudo chunks (image descriptions): {len(pseudo_chunks)}")
    
    # 8. 打印伪文本 chunk 预览
    print("\n[Step 8] Pseudo chunk previews:")
    for i, pc in enumerate(pseudo_chunks):
        text = pc["text"]
        parent_heading = pc["metadata"].get("heading_path", "")
        media_refs = pc["metadata"].get("media_refs", [])
        
        print(f"\n  --- Pseudo Chunk {i+1} ---")
        print(f"  Parent heading: {parent_heading}")
        print(f"  Media refs: {len(media_refs)}")
        print(f"  Text preview: {text[:300]}...")
    
    # 9. 保存结果
    output_dir = Path(__file__).parent.parent / "scripts" / "phase22_test_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    import json
    result_file = output_dir / "phase22_result.json"
    result_file.write_text(
        json.dumps(pseudo_chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n  Saved to: {result_file}")
    
    print("\n" + "=" * 60)
    print("Phase 2.2 Test Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
