"""
批量导入 IWork PDF 测试数据到 LearnAnything
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

import os
from core.document_processor import DocumentProcessor
from core.vector_store import VectorStore
from core.subject_manager import record_import, save_raw_file, create_subject
from core.graph_builder import GraphBuilder

# 配置
PDF_DIR = Path("D:/MyCS/AI/Project/IWork/yuque_download/pdfs")
SUBJECT = "test_pdf"
SUBJECT_NAME = "AI后端技术测试"


def import_pdfs():
    """批量导入 PDF 文件。"""
    # 查找所有 PDF
    pdf_files = list(PDF_DIR.glob("*.pdf"))
    print(f"[Import] Found {len(pdf_files)} PDF files")

    # 创建学科目录（如果不存在）
    try:
        create_subject(
            id=SUBJECT,
            name=SUBJECT_NAME,
            description="IWork项目PDF测试数据，用于验证跨文档chunk关系",
            keywords=["AI", "backend", "RAG", "LLM"],
        )
        print(f"[Import] Created subject: {SUBJECT}")
    except Exception as e:
        print(f"[Import] Subject may already exist: {e}")

    processor = DocumentProcessor()
    store = VectorStore(f"{SUBJECT}_v1")

    total_chunks = 0
    success_count = 0

    for i, pdf_path in enumerate(pdf_files[:20]):  # 先导入前20个测试
        print(f"\n[Import] [{i+1}/{min(20, len(pdf_files))}] {pdf_path.name}")
        try:
            # 读取 PDF 内容
            with open(pdf_path, "rb") as f:
                content = f.read()

            # 保存原始文件
            raw_path = save_raw_file(SUBJECT, pdf_path.name, content)
            print(f"  Raw saved: {raw_path}")

            # 处理文件
            chunks = processor.process_file(
                str(pdf_path),
                subject=SUBJECT,
                source_name=pdf_path.name,
                raw_path=str(raw_path),
            )
            print(f"  Processed: {len(chunks)} chunks")

            # 存入向量库
            if chunks:
                store.add_documents(chunks)
                total_chunks += len(chunks)
                record_import(SUBJECT, pdf_path.name, str(raw_path), len(chunks))
                success_count += 1
                print(f"  Added to vector store: {store.count()} total")

        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n=== Import Summary ===")
    print(f"  PDF files processed: {success_count}/{min(20, len(pdf_files))}")
    print(f"  Total chunks: {total_chunks}")
    print(f"  Vector store count: {store.count()}")

    # 构建图谱
    print(f"\n[Graph] Building knowledge graph...")
    builder = GraphBuilder(f"{SUBJECT}_v1")
    result = builder.build_all(force_rebuild=True)
    print(f"[Graph] Done: {result['chunks_total']} nodes, "
          f"{result['belongs_to_edges']} belongs_to, "
          f"{result['adjacent_to_edges']} adjacent_to")

    return result


if __name__ == "__main__":
    import_pdfs()
