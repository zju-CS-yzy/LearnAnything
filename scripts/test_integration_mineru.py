"""
快速集成测试脚本
验证 DocumentProcessor 使用 MinerU 引擎解析 PDF 是否正常。
"""
import sys
from pathlib import Path

# 添加到项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.document_processor import DocumentProcessor
from config.settings import KNOWLEDGE_BASE_DIR


def main():
    print("=" * 60)
    print("DocumentProcessor + MinerU Integration Test")
    print("=" * 60)
    
    # 1. 测试 MinerU 引擎
    print("\n[Test 1] MinerU Engine")
    print("-" * 60)
    
    processor = DocumentProcessor(pdf_engine="mineru")
    
    # 查找测试 PDF
    pdf_dir = KNOWLEDGE_BASE_DIR / "generic" / "raw"
    pdf_files = list(pdf_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("ERROR: No PDF files found")
        return
    
    # 选择 RAG Fusion（较小）
    test_pdf = None
    for pf in pdf_files:
        if "RAG" in pf.name and "Fusion" in pf.name:
            test_pdf = pf
            break
    if not test_pdf:
        test_pdf = min(pdf_files, key=lambda p: p.stat().st_size)
    
    print(f"Test file: {test_pdf.name}")
    
    try:
        chunks = processor.process_file(
            str(test_pdf),
            subject="generic",
            source_name=test_pdf.name,
        )
        
        print(f"OK! Parsed {len(chunks)} chunks")
        
        # 统计 chunk 类型
        type_counts = {}
        for chunk in chunks:
            chunk_type = chunk.get("metadata", {}).get("chunk_type", "unknown")
            type_counts[chunk_type] = type_counts.get(chunk_type, 0) + 1
        
        print(f"\nChunk type distribution:")
        for chunk_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"   {chunk_type}: {count}")
        
        # 打印前 3 个 chunk 预览
        print(f"\nFirst 3 chunks preview:")
        for i, chunk in enumerate(chunks[:3]):
            text = chunk["text"][:200].replace("\n", " ")
            chunk_type = chunk.get("metadata", {}).get("chunk_type", "unknown")
            heading = chunk.get("metadata", {}).get("heading_path", "")[:50]
            image_refs = chunk.get("metadata", {}).get("image_refs", [])
            print(f"\n   [{i+1}] {chunk_type} | {chunk['id'][:40]}")
            print(f"       heading: {heading}")
            print(f"       text: {text}...")
            if image_refs:
                print(f"       images: {len(image_refs)}")
        
        # 2. 测试 PyMuPDF 引擎（对比）
        print(f"\n{'=' * 60}")
        print("[Test 2] PyMuPDF Engine (Comparison)")
        print("-" * 60)
        
        processor2 = DocumentProcessor(pdf_engine="pymupdf")
        chunks2 = processor2.process_file(
            str(test_pdf),
            subject="generic",
            source_name=test_pdf.name,
        )
        
        print(f"OK! PyMuPDF parsed {len(chunks2)} chunks")
        
        type_counts2 = {}
        for chunk in chunks2:
            chunk_type = chunk.get("metadata", {}).get("chunk_type", "unknown")
            type_counts2[chunk_type] = type_counts2.get(chunk_type, 0) + 1
        
        print(f"\nChunk type distribution:")
        for chunk_type, count in sorted(type_counts2.items(), key=lambda x: -x[1]):
            print(f"   {chunk_type}: {count}")
        
        # 3. 对比总结
        print(f"\n{'=' * 60}")
        print("Comparison Summary")
        print("=" * 60)
        print(f"   MinerU:  {len(chunks)} chunks")
        print(f"   PyMuPDF: {len(chunks2)} chunks")
        
        # 图片 chunk 对比
        mineru_images = sum(1 for c in chunks if c.get("metadata", {}).get("chunk_type") == "image")
        pymupdf_images = sum(1 for c in chunks2 if c.get("metadata", {}).get("chunk_type") == "image")
        print(f"   MinerU image chunks:  {mineru_images}")
        print(f"   PyMuPDF image chunks: {pymupdf_images}")
        
        # 公式检测
        mineru_formulas = sum(c.get("metadata", {}).get("formula_count", 0) for c in chunks)
        print(f"   MinerU formulas: {mineru_formulas}")
        
        print(f"\n{'=' * 60}")
        print("Integration test completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
