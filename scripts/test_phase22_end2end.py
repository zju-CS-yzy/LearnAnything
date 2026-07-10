"""
Phase 2.2 端到端测试：图片 → VLM 描述 → 概念提取

完整流程:
    PDF → MinerU → MarkdownChunker → ImageConceptExtractor → SemanticExtractor → Concepts

验证目标:
    1. 图片通过 VLM 生成描述
    2. 图片描述作为伪文本 chunk 参与概念提取
    3. 提取的概念携带 media_refs
    4. 概念与文本概念融合到同一 CanonicalConcept

用法:
    cd D:\MyCS\AI\Project\LearnAnything
    python scripts\test_phase22_end2end.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mineru_client import MinerUClient
from core.markdown_chunker import MarkdownChunker
from core.image_concept_extractor import ImageConceptExtractor
from core.semantic_extractor import SemanticExtractor
from config.settings import KNOWLEDGE_BASE_DIR


def main():
    print("=" * 60)
    print("Phase 2.2 End-to-End Test")
    print("Image -> VLM Description -> Concept Extraction")
    print("=" * 60)
    
    # 1. 解析 PDF
    print("\n[Step 1] Parsing PDF with MinerU...")
    test_pdf = KNOWLEDGE_BASE_DIR / "generic" / "raw" / "RAG Fusion优化策略面试题.pdf"
    
    client = MinerUClient()
    md_text, output_dir, img_paths = client.parse_pdf_to_markdown(str(test_pdf))
    print(f"  Images: {len(img_paths)}")
    
    # 2. Markdown 分块
    print("\n[Step 2] Chunking Markdown...")
    chunker = MarkdownChunker()
    parent_chunks, child_chunks = chunker.chunk_markdown(
        md_text,
        source_metadata={"source": test_pdf.name, "subject": "generic"},
    )
    
    # 合并为统一列表
    chunks = []
    for parent in parent_chunks:
        chunks.append(parent)
        for child in child_chunks:
            if child["metadata"].get("parent_id") == parent["id"]:
                chunks.append(child)
    
    print(f"  Chunks: {len(chunks)}")
    
    # 3. 图片 VLM 描述增强
    print("\n[Step 3] Enriching with VLM image descriptions...")
    extractor = ImageConceptExtractor()
    enhanced_chunks = extractor.enrich_chunks_with_image_descriptions(
        chunks, subject="generic", base_dir=output_dir
    )
    
    pseudo_chunks = [c for c in enhanced_chunks if c.get("metadata", {}).get("chunk_type") == "image_pseudo"]
    print(f"  Pseudo chunks: {len(pseudo_chunks)}")
    
    # 4. 概念提取（只提取伪文本 chunks）
    print("\n[Step 4] Extracting concepts from image pseudo chunks...")
    semantic = SemanticExtractor()
    
    all_concepts = []
    for chunk in pseudo_chunks:
        try:
            concepts = semantic.extract_concepts(chunk_text=chunk["text"])
            
            # 给每个概念添加 media_refs
            for concept in concepts:
                concept["media_refs"] = chunk["metadata"].get("media_refs", [])
                concept["source_chunk_type"] = "image_pseudo"
            
            all_concepts.extend(concepts)
            print(f"  [{chunk['id'][:30]}] -> {len(concepts)} concepts")
            
        except Exception as e:
            print(f"  ERROR: {e}")
    
    # 5. 结果展示
    print(f"\n[Step 5] Results:")
    print(f"  Total image concepts: {len(all_concepts)}")
    
    print(f"\n  Image concepts preview:")
    for i, concept in enumerate(all_concepts[:10]):
        name = concept.get("name", "N/A")
        concept_type = concept.get("type", "unknown")
        media_count = len(concept.get("media_refs", []))
        print(f"    [{i+1}] {name} ({concept_type}) - {media_count} media refs")
    
    # 6. 对比：同时提取文本 chunks 的概念
    print(f"\n[Step 6] Extracting concepts from text chunks (comparison)...")
    text_chunks = [c for c in enhanced_chunks if c.get("metadata", {}).get("chunk_type") in ("title", "paragraph")]
    
    text_concepts = []
    for chunk in text_chunks[:5]:  # 只取前 5 个文本 chunk，避免太长
        try:
            concepts = semantic.extract_concepts(chunk_text=chunk["text"])
            text_concepts.extend(concepts)
        except Exception as e:
            pass
    
    print(f"  Text concepts (first 5 chunks): {len(text_concepts)}")
    
    # 7. 检查是否有重叠概念
    image_concept_names = {c["name"] for c in all_concepts}
    text_concept_names = {c["name"] for c in text_concepts}
    overlap = image_concept_names & text_concept_names
    
    print(f"\n[Step 7] Concept overlap analysis:")
    print(f"  Image concept names: {len(image_concept_names)}")
    print(f"  Text concept names: {len(text_concept_names)}")
    print(f"  Overlap: {len(overlap)}")
    if overlap:
        print(f"  Overlapping concepts: {', '.join(list(overlap)[:5])}")
    
    # 8. 保存结果
    import json
    output_dir = Path(__file__).parent.parent / "scripts" / "phase22_test_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    result = {
        "image_concepts": all_concepts,
        "text_concepts_sample": text_concepts[:20],
        "overlap": list(overlap),
    }
    
    result_file = output_dir / "phase22_end2end_result.json"
    result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Saved to: {result_file}")
    
    print("\n" + "=" * 60)
    print("Phase 2.2 End-to-End Test Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
