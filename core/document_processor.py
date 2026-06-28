"""
文档处理模块 (DocumentProcessor)
支持多格式输入：文本、Markdown、PDF（文字型/扫描件）、图片、手写笔记、公式

处理流程:
  输入文件 → 格式检测 → 预处理 → 文本提取 → 结构化输出 → 分块 → 导入知识库

支持的格式:
  - .txt, .md: 直接读取
  - .pdf: PyMuPDF 提取文字型 / PaddleOCR 提取扫描件
  - .png, .jpg, .jpeg: PaddleOCR 提取文字 / pix2tex 提取公式
  - .docx: python-docx (后续支持)
"""

import hashlib
import io
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import fitz
from PIL import Image

from config.settings import KNOWLEDGE_BASE_DIR
from core.chunking import DocumentChunker
from core.subject_analyzer import SubjectAnalyzer, save_subject_config


class DocumentProcessor:
    """
    文档处理器。

    使用方式:
        processor = DocumentProcessor()
        chunks = processor.process_file("path/to/chemistry_notes.pdf", subject="chemistry")
        # chunks: [{"text": str, "metadata": dict, "source": str}, ...]
    """

    def __init__(self, ocr_engine: str = "paddleocr", formula_engine: str = "pix2tex"):
        self.ocr_engine = ocr_engine
        self.formula_engine = formula_engine
        self._ocr = None
        self._formula_ocr = None
        self.chunker = DocumentChunker()

    def _get_ocr(self):
        """延迟加载 OCR 引擎"""
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR
                self._ocr = PaddleOCR(
                    use_angle_cls=True,
                    lang='ch',
                    show_log=False,
                )
            except Exception as e:
                print(f"[DocumentProcessor] PaddleOCR init failed: {e}")
                self._ocr = None
        return self._ocr

    def _get_formula_ocr(self):
        """延迟加载公式 OCR 引擎"""
        if self._formula_ocr is None:
            try:
                from pix2tex.cli import LatexOCR
                self._formula_ocr = LatexOCR()
            except Exception as e:
                print(f"[DocumentProcessor] pix2tex init failed: {e}")
                self._formula_ocr = None
        return self._formula_ocr

    def process_file(self, file_path: str, subject: str = "generic", metadata: Dict[str, Any] = None, source_name: str = None, raw_path: str = None) -> List[Dict[str, Any]]:
        """
        处理单个文件，返回分块后的文本列表。

        Args:
            file_path: 文件路径
            subject: 学科标识（用于后续学科专用处理）
            metadata: 额外元数据
            source_name: 原始文件名（如果不是从文件路径提取）
            raw_path: 原始文件在知识库中的存储路径

        Returns:
            [{"text": str, "metadata": dict, "source": str}, ...]
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = path.suffix.lower()
        # 使用传入的 source_name，否则从路径提取
        source = source_name or path.name
        base_meta = metadata or {}
        base_meta["source"] = source
        base_meta["subject"] = subject
        base_meta["file_path"] = str(path)
        if raw_path:
            base_meta["raw_path"] = raw_path

        if ext in (".txt", ".md", ".markdown"):
            return self._process_text_file(path, base_meta)
        elif ext == ".pdf":
            return self._process_pdf(path, base_meta)
        elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff"):
            return self._process_image(path, base_meta)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def process_batch(self, file_paths: List[str], subject: str = "generic", metadata: Dict[str, Any] = None, auto_analyze: bool = True) -> List[Dict[str, Any]]:
        """
        批量处理多个文件，可选导入后自动分析学科配置。

        Args:
            file_paths: 文件路径列表
            subject: 学科标识
            metadata: 额外元数据
            auto_analyze: 是否自动分析并生成学科配置（默认 True）

        Returns:
            所有分块后的文本列表
        """
        all_chunks = []
        for fp in file_paths:
            try:
                chunks = self.process_file(fp, subject=subject, metadata=metadata)
                all_chunks.extend(chunks)
            except Exception as e:
                print(f"[DocumentProcessor] Failed to process {fp}: {e}")

        # 自动分析学科配置
        if auto_analyze and all_chunks:
            try:
                analyzer = SubjectAnalyzer()
                config = analyzer.analyze_materials(all_chunks, subject_name=subject)
                config_path = save_subject_config(config, subject_name=subject)
                print(f"[DocumentProcessor] Auto-generated subject config: {config_path}")
                print(f"  Detected name: {config.get('name', 'unknown')}")
                print(f"  Question types: {list(config.get('question_types', {}).keys())}")
                print(f"  Special features: {config.get('special_features', [])}")
            except Exception as e:
                print(f"[DocumentProcessor] Auto-analysis failed: {e}")

        return all_chunks

    def _process_text_file(self, path: Path, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        处理文本/Markdown 文件（Parent-Child 双层分块）。
        将整个文件视为一页，使用 chunk_page 进行语义分块。
        """
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()

        # 使用 Parent-Child 双层分块：文件=一页
        page_meta = {
            **metadata,
            "page_number": 1,
            "document_name": path.name,
        }
        parent, children = self.chunker.chunk_page(text, page_meta)

        result = []
        # Parent chunk
        result.append({
            "text": parent["text"],
            "metadata": {**metadata, **parent.get("metadata", {})},
            "source": metadata["source"],
        })
        # Child chunks
        for child in children:
            result.append({
                "text": child["text"],
                "metadata": {**metadata, **child.get("metadata", {})},
                "source": metadata["source"],
            })

        return result

    def _process_pdf(self, path: Path, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        处理 PDF 文件（Parent-Child 双层分块，先全局分 Child 再按页码聚合 Parent）。
        
        **核心改进**：
        - 先收集所有页面文本，全局分 Child chunk（跨页段落不会被切断）
        - 再按页码聚合 Parent chunk（每页一个 Parent，用于引用溯源）
        
        策略：
        1. 逐页提取文本，检测页面类型
        2. 扫描件页面 OCR 处理
        3. 公式密集型页面标记待处理
        4. 所有页面文本收集后，调用 chunk_document 全局分块
        """
        doc = fitz.open(str(path))
        total_pages = len(doc)
        ocr_pages = []
        formula_pages = []  # (img_bytes, metadata)
        vlm_pages = []      # (img_bytes, metadata, page_type)
        
        # Step 1: 收集所有页面文本，同时渲染需要 VLM 的页面为图片
        pages = []
        
        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text().strip()
            page_meta = {
                **metadata,
                "page_number": page_num + 1,
                "total_pages": total_pages,
                "document_name": path.name,
            }
            
            # 检测页面类型
            page_type = self._detect_page_type(page, text)
            
            if page_type == "scan":
                # 扫描件，需要 OCR
                ocr_pages.append((page_num, page, page_meta))
            elif page_type == "formula_heavy":
                # 公式密集型页面，先渲染为图片，再 VLM 提取
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                formula_pages.append((img_bytes, page_meta))
            elif page_type in ("table", "chart", "diagram", "mixed"):
                # 表格/图表/流程图/混合页面，先渲染为图片，再 VLM 分析
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                vlm_pages.append((img_bytes, page_meta, page_type))
            else:
                # 文字型页面，直接加入
                pages.append({"text": text, "metadata": page_meta})
        
        doc.close()
        
        # Step 2: 处理 OCR 页面（扫描件）
        if ocr_pages:
            ocr_results = self._ocr_pdf_pages(ocr_pages)
            for ocr_text, ocr_meta in ocr_results:
                pages.append({"text": ocr_text, "metadata": ocr_meta})
        
        # Step 3: 处理公式密集型页面（VLM）
        if formula_pages:
            formula_results = self._vlm_formula_pages(formula_pages)
            for text, meta in formula_results:
                pages.append({"text": text, "metadata": meta})
        
        # Step 4: 处理表格/图表/流程图页面（VLM）
        if vlm_pages:
            vlm_results = self._vlm_pdf_pages(vlm_pages)
            for text, meta in vlm_results:
                if text:
                    pages.append({"text": text, "metadata": meta})
        
        # 按页码排序
        pages.sort(key=lambda p: p["metadata"].get("page_number", 0))
        
        # Step 4: 全局 Parent-Child 双层分块
        # 先全局分 Child（跨页段落不会被切断），再按页码聚合 Parent
        chunker = DocumentChunker()
        parent_chunks, child_chunks = chunker.chunk_document(
            pages,
            document_name=metadata.get("source", path.name)  # 使用原始文件名，而非临时路径
        )
        
        # Step 5: 统一输出格式
        result = []
        
        # Parent chunks
        for parent in parent_chunks:
            result.append({
                "text": parent["text"],
                "metadata": {**metadata, **parent.get("metadata", {})},
                "source": metadata["source"],
            })
        
        # Child chunks（每个子 chunk 包含 parent_ids 用于溯源）
        for child in child_chunks:
            result.append({
                "text": child["text"],
                "metadata": {**metadata, **child.get("metadata", {})},
                "source": metadata["source"],
            })
        
        return result

    def _detect_page_type(self, page: fitz.Page, text: str) -> str:
        """
        检测页面类型。

        Returns:
            "text": 文字型页面（文字充足）
            "scan": 扫描件（文字极少）
            "formula_heavy": 公式密集型（大量特殊字符/数学符号）
            "table": 表格页面（大量单元格结构）
            "chart": 图表页面（数据可视化）
            "diagram": 流程图/架构图
            "mixed": 混合页面（文字+图片）
        """
        text_len = len(text.strip())
        
        # 文字极少 → 扫描件或纯图片页
        if text_len < 50:
            return "scan"

        # 检测公式密度
        formula_chars = len(re.findall(r'[\u0370-\u03FF\u2200-\u22FF\^\_\$\\]', text))
        formula_ratio = formula_chars / max(text_len, 1)
        if formula_ratio > 0.05:
            return "formula_heavy"

        # 检测表格密度：大量 | 或制表符，或特定表格关键词
        table_markers = len(re.findall(r'[|+─━┌┐└┘├┤┬┴┼]', text))
        if table_markers > 10 or text.count('\t') > 20:
            return "table"

        # 获取页面图像
        images = page.get_images()
        
        # 图片数量多但文字少 → 可能是图表/流程图
        if len(images) >= 1:
            # 检查是否有图表特征文字
            chart_keywords = ["图", "fig", "figure", "chart", "graph", "plot", "趋势", "增长", "下降", "%"]
            chart_score = sum(1 for kw in chart_keywords if kw.lower() in text.lower())
            if chart_score >= 2 and text_len < 800:
                return "chart"
            
            # 检查是否有流程图特征
            diagram_keywords = ["流程", "步骤", "stage", "process", "workflow", "架构", "系统", "模块"]
            diagram_score = sum(1 for kw in diagram_keywords if kw.lower() in text.lower())
            if diagram_score >= 2 and text_len < 600:
                return "diagram"
            
            # 文字+图片混合
            if len(images) > 2 and text_len < 500:
                return "mixed"

        return "text"

    def _ocr_pdf_pages(self, pages: List[Tuple[int, fitz.Page, Dict[str, Any]]]) -> List[Tuple[str, Dict[str, Any]]]:
        """对扫描件 PDF 页面进行 OCR，返回 [(text, metadata)] 列表"""
        ocr = self._get_ocr()
        if ocr is None:
            print("[DocumentProcessor] OCR not available, falling back to VLM for scan pages")
            return self._vlm_scan_pages(pages)

        results = []
        for page_num, page, meta in pages:
            # 将页面渲染为图片
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))

            # 保存临时图片
            temp_path = KNOWLEDGE_BASE_DIR / f"temp_ocr_page_{page_num}.png"
            img.save(str(temp_path))

            # OCR
            try:
                ocr_result = ocr.ocr(str(temp_path), cls=True)
                texts = []
                if ocr_result and ocr_result[0]:
                    for line in ocr_result[0]:
                        if line:
                            texts.append(line[1][0])  # text content
                extracted_text = "\n".join(texts)
                results.append((extracted_text, {**meta, "ocr_used": True}))
            except Exception as e:
                print(f"[DocumentProcessor] OCR failed for page {page_num}: {e}")
                results.append(("[OCR 失败]", {**meta, "ocr_failed": True}))
            finally:
                # 清理临时文件
                if temp_path.exists():
                    temp_path.unlink()

        return results

    def _vlm_scan_pages(self, pages: List[Tuple[int, fitz.Page, Dict[str, Any]]]) -> List[Tuple[str, Dict[str, Any]]]:
        """
        OCR 不可用时，使用 VLM 处理扫描件页面。
        """
        from core.vlm_client import VLMClient
        vlm = VLMClient()
        
        if not vlm.available:
            print("[DocumentProcessor] VLM not available either, scan pages will be empty")
            return [("[扫描件，OCR 和 VLM 均不可用]", meta) for _, _, meta in pages]

        results = []
        for page_num, page, meta in pages:
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            
            result = vlm.analyze_pdf_page(img_bytes, "scan", page_num + 1)
            
            if result:
                combined = f"[第{page_num + 1}页 扫描件识别]\n{result}"
                results.append((combined, {**meta, "vlm_scan": True, "page_type": "scan"}))
            else:
                results.append(("[扫描件，VLM 识别失败]", {**meta, "vlm_scan": False, "page_type": "scan"}))
        
        return results

    def _vlm_formula_pages(self, pages: List[Tuple[bytes, Dict[str, Any]]]) -> List[Tuple[str, Dict[str, Any]]]:
        """
        使用 VLM 处理公式密集型页面，提取 LaTeX 公式。
        
        Args:
            pages: [(img_bytes, metadata), ...]
        """
        from core.vlm_client import VLMClient
        vlm = VLMClient()
        
        if not vlm.available:
            print("[DocumentProcessor] VLM not available, falling back to original text")
            return []

        results = []
        for img_bytes, meta in pages:
            page_num = meta.get("page_number", 0)
            
            # 调用 VLM 识别公式
            result = vlm.analyze_pdf_page(img_bytes, "formula", page_num)
            
            if result:
                combined = f"[第{page_num}页 公式识别]\n{result}"
                results.append((combined, {**meta, "vlm_formula": True, "page_type": "formula"}))
        
        return results

    def _vlm_pdf_pages(self, pages: List[Tuple[bytes, Dict[str, Any], str]]) -> List[Tuple[str, Dict[str, Any]]]:
        """
        使用 VLM 处理表格/图表/流程图页面，返回 [(text, metadata)] 列表。
        
        Args:
            pages: [(img_bytes, metadata, page_type), ...]
        """
        from core.vlm_client import VLMClient
        vlm = VLMClient()
        
        if not vlm.available:
            print("[DocumentProcessor] VLM not available, skipping visual pages")
            return []

        results = []
        for img_bytes, meta, ptype in pages:
            page_num = meta.get("page_number", 0)
            
            # 调用 VLM 分析
            result = vlm.analyze_pdf_page(img_bytes, ptype, page_num)
            
            if result:
                type_labels = {
                    "table": "表格提取",
                    "chart": "图表分析",
                    "diagram": "流程图分析",
                    "mixed": "图片内容分析",
                }
                label = type_labels.get(ptype, "视觉内容分析")
                combined = f"[第{page_num}页 {label}]\n{result}"
                results.append((combined, {**meta, "vlm_processed": True, "page_type": ptype}))
        
        return results

    def _process_formula_pages(self, pages: List[Tuple[int, str, Dict[str, Any]]]) -> List[Tuple[str, Dict[str, Any]]]:
        """
        处理公式密集型页面（已废弃，改用 _vlm_formula_pages）。
        保留此方法用于兼容和降级。
        """
        return [(text, {**meta, "formula_ocr_attempted": False}) for _, text, meta in pages]

    def _process_image(self, path: Path, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        处理图片文件。
        策略：
        1. 尝试 OCR 提取文字
        2. 如果检测到公式区域，使用 pix2tex 提取
        3. 返回结构化文本
        """
        ocr = self._get_ocr()
        if ocr is None:
            return [{"text": "[图片，OCR 不可用]", "metadata": {**metadata, "ocr_failed": True}, "source": metadata["source"]}]

        try:
            ocr_result = ocr.ocr(str(path), cls=True)
            texts = []
            if ocr_result and ocr_result[0]:
                for line in ocr_result[0]:
                    if line:
                        texts.append(line[1][0])
            extracted_text = "\n".join(texts)

            # 检测是否包含公式
            if re.search(r'[\u0370-\u03FF\u2200-\u22FF\^\_\$\\]', extracted_text):
                metadata["has_formula"] = True

            chunks = self.chunker.chunk(extracted_text, metadata)
            return [{"text": c["text"], "metadata": {**metadata, **c.get("metadata", {}), "ocr_used": True}, "source": metadata["source"]} for c in chunks]
        except Exception as e:
            print(f"[DocumentProcessor] Image OCR failed: {e}")
            return [{"text": "[图片 OCR 失败]", "metadata": {**metadata, "ocr_failed": True}, "source": metadata["source"]}]

    def extract_formula_from_image(self, image_path: str) -> Optional[str]:
        """
        从图片中提取公式（LaTeX）。
        使用 pix2tex 将图片中的公式转换为 LaTeX 代码。

        Args:
            image_path: 图片路径（包含公式的截图）

        Returns:
            LaTeX 字符串 或 None（提取失败）
        """
        formula_ocr = self._get_formula_ocr()
        if formula_ocr is None:
            return None

        try:
            img = Image.open(image_path)
            latex = formula_ocr(img)
            return latex
        except Exception as e:
            print(f"[DocumentProcessor] Formula extraction failed: {e}")
            return None


# 便捷函数

def process_document(file_path: str, subject: str = "generic", metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """便捷函数：处理单个文档"""
    processor = DocumentProcessor()
    return processor.process_file(file_path, subject=subject, metadata=metadata)


def batch_process_documents(file_paths: List[str], subject: str = "generic", metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """便捷函数：批量处理文档"""
    processor = DocumentProcessor()
    return processor.process_batch(file_paths, subject=subject, metadata=metadata)
