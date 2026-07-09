"""
文档处理模块 (DocumentProcessor)
支持多格式输入：文本、Markdown、PDF（文字型/扫描件）、图片、手写笔记、公式

处理流程:
  输入文件 → 格式检测 → 预处理 → 文本提取 → 结构化输出 → 分块 → 导入知识库

支持的格式:
  - .txt, .md: 直接读取
  - .pdf: PyMuPDF 提取文字型 / PaddleOCR 提取扫描件 / LA-035 图片提取
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
                    lang="ch",
                    show_log=False,
                )
            except Exception as e:
                print(f"[DocumentProcessor] OCR init failed: {e}")
                self._ocr = None
        return self._ocr

    def _get_formula_ocr(self):
        """延迟加载公式识别引擎"""
        if self._formula_ocr is None:
            try:
                from pix2tex.cli import LatexOCR
                self._formula_ocr = LatexOCR()
            except Exception as e:
                print(f"[DocumentProcessor] Formula OCR init failed: {e}")
                self._formula_ocr = None
        return self._formula_ocr

    def process_file(self, path: str, subject: str = "generic", source_name: str = None, raw_path: str = None) -> List[Dict[str, Any]]:
        """
        处理单个文件，返回 chunk 列表。

        Args:
            path: 文件路径
            subject: 学科名称
            source_name: 原始文件名（用于溯源）
            raw_path: 原始文件保存路径

        Returns:
            [{"id": str, "text": str, "metadata": dict, "source": str}, ...]
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        if source_name is None:
            source_name = path.name

        metadata = {
            "source": source_name,
            "raw_path": raw_path or str(path),
            "subject": subject,
        }

        ext = path.suffix.lower()
        if ext in (".txt", ".md"):
            return self._process_text(path, metadata)
        elif ext == ".pdf":
            return self._process_pdf(path, metadata, subject=subject)
        elif ext in (".png", ".jpg", ".jpeg"):
            return self._process_image(path, metadata)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")

    def _process_text(self, path: Path, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """处理文本/Markdown 文件"""
        text = path.read_text(encoding="utf-8")

        chunker = DocumentChunker()
        parent_chunks, child_chunks = chunker.chunk_document(
            [{"text": text, "metadata": metadata}],
            document_name=metadata["source"]
        )

        result = []
        for parent in parent_chunks:
            result.append({
                "id": parent["id"],
                "text": parent["text"],
                "metadata": {**metadata, **parent.get("metadata", {})},
                "source": metadata["source"],
            })
        for child in child_chunks:
            result.append({
                "id": child["id"],
                "text": child["text"],
                "metadata": {**metadata, **child.get("metadata", {})},
                "source": metadata["source"],
            })
        return result

    def _process_pdf(self, path: Path, metadata: Dict[str, Any], subject: str = "generic") -> List[Dict[str, Any]]:
        """
        处理 PDF 文件（Parent-Child 双层分块，先全局分 Child 再按页码聚合 Parent）。
        LA-035: 同时提取页面中的图片为独立 chunk。
        
        **核心改进**：
        - 先收集所有页面文本，全局分 Child chunk（跨页段落不会被切断）
        - 再按页码聚合 Parent chunk（每页一个 Parent，用于引用溯源）
        - 提取标题结构（从书签/文本特征），填充 heading_path
        - 提取页面图片为 image chunk
        """
        doc = fitz.open(str(path))
        total_pages = len(doc)
        ocr_pages = []
        formula_pages = []  # (img_bytes, metadata)
        vlm_pages = []      # (img_bytes, metadata, page_type)
        
        # === LA-035: 图片提取结果 ===
        image_chunks = []
        
        # === Step 1: 收集所有页面文本，同时提取标题结构 ===
        pages = []
        # page_headings: {page_num: heading_path_string}
        page_headings = self._extract_page_headings(doc)
        
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
            
            # LA-035: 提取页面中的图片
            page_image_chunks = self._extract_pdf_page_images(
                doc, page, page_num + 1, page_meta, subject, path.name
            )
            image_chunks.extend(page_image_chunks)
            
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
        
        # Step 2: 处理 OCR 页面（扫描件）
        # 注意：doc 必须在 OCR/VLM 处理完成后才关闭，因为 page 对象需要有效的 doc 引用
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
        
        # 所有 page 对象处理完成后，关闭 doc
        doc.close()
        
        # 按页码排序
        pages.sort(key=lambda p: p["metadata"].get("page_number", 0))
        
        # Step 5: 全局 Parent-Child 双层分块
        chunker = DocumentChunker()
        parent_chunks, child_chunks = chunker.chunk_document(
            pages,
            document_name=metadata.get("source", path.name)
        )
        
        # Step 6: 统一输出格式，填充 heading_path 和 page_number
        result = []
        
        # Parent chunks: page_number 单值，heading_path 来自 page_headings
        for parent in parent_chunks:
            page_num = parent["metadata"].get("page_number", 0)
            heading_path = page_headings.get(page_num, "")
            parent_meta = {
                **parent.get("metadata", {}),
                "page_number": page_num,
                "heading_path": heading_path,
            }
            result.append({
                "id": parent.get("id", ""),
                "text": parent["text"],
                "metadata": {**metadata, **parent_meta},
                "source": metadata["source"],
            })
        
        # Child chunks: 取第一个页码作为 page_number，heading_path 来自该页
        for child in child_chunks:
            page_nums = child["metadata"].get("page_numbers", [1])
            first_page = page_nums[0] if page_nums else 1
            heading_path = page_headings.get(first_page, "")
            child_meta = {
                **child.get("metadata", {}),
                "page_number": first_page,
                "heading_path": heading_path,
                # 移除 page_numbers 列表，统一使用 page_number 单值
            }
            # 清理掉旧的 page_numbers 字段（如果存在）
            child_meta.pop("page_numbers", None)
            result.append({
                "id": child.get("id", ""),
                "text": child["text"],
                "metadata": {**metadata, **child_meta},
                "source": metadata["source"],
            })
        
        # LA-035: 将图片 chunk 加入结果
        result.extend(image_chunks)
        
        return result

    # ==================== LA-035: PDF 图片提取 ====================

    def _extract_pdf_page_images(
        self,
        doc: fitz.Document,
        page: fitz.Page,
        page_num: int,
        page_meta: Dict[str, Any],
        subject: str,
        doc_name: str,
    ) -> List[Dict[str, Any]]:
        """
        提取 PDF 页面中的内嵌图片，保存为文件并生成 image chunk。
        
        Args:
            doc: PyMuPDF Document 对象
            page: 当前页面
            page_num: 页码（1-based）
            page_meta: 页面元数据
            subject: 学科名称
            doc_name: 文档名称
        
        Returns:
            图片 chunk 列表
        """
        image_list = page.get_images(full=True)
        if not image_list:
            return []
        
        # 准备存储目录
        safe_doc_name = re.sub(r'[^\w\-_.]', '_', Path(doc_name).stem)
        img_dir = KNOWLEDGE_BASE_DIR / f"{subject}_v1_images"
        thumb_dir = KNOWLEDGE_BASE_DIR / f"{subject}_v1_thumbnails"
        img_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        
        chunks = []
        for img_idx, img_info in enumerate(image_list):
            xref = img_info[0]
            
            try:
                # 提取图片
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue
                
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)
                
                # 生成唯一文件名
                img_hash = hashlib.md5(image_bytes).hexdigest()[:8]
                base_name = f"{safe_doc_name}_p{page_num}_img{img_idx}_{img_hash}"
                
                # 保存原始图片（统一转换为 PNG）
                img_path = img_dir / f"{base_name}.png"
                try:
                    pil_img = Image.open(io.BytesIO(image_bytes))
                    # 转换为 RGB（处理 CMYK 等模式）
                    if pil_img.mode in ('CMYK', 'RGBA', 'P'):
                        pil_img = pil_img.convert('RGB')
                    pil_img.save(str(img_path), 'PNG')
                except Exception as e:
                    print(f"[ImageExtract] Failed to save image {base_name}: {e}")
                    continue
                
                # 生成缩略图
                thumb_path = thumb_dir / f"{base_name}.png"
                try:
                    thumb = pil_img.copy()
                    thumb.thumbnail((200, 200), Image.LANCZOS)
                    thumb.save(str(thumb_path), 'PNG')
                except Exception as e:
                    print(f"[ImageExtract] Failed to create thumbnail {base_name}: {e}")
                    thumb_path = img_path  # 回退到原图
                
                # 构建 chunk ID
                chunk_id = f"img_{subject}_{safe_doc_name}_p{page_num}_i{img_idx}_{img_hash}"
                
                # 构建图片 chunk
                chunk = {
                    "id": chunk_id,
                    "text": f"[图片] PDF第{page_num}页内嵌图片 #{img_idx + 1} ({width}x{height})",
                    "metadata": {
                        **page_meta,
                        "chunk_type": "image",
                        "image_path": str(img_path.relative_to(KNOWLEDGE_BASE_DIR)),
                        "thumbnail_path": str(thumb_path.relative_to(KNOWLEDGE_BASE_DIR)),
                        "width": width,
                        "height": height,
                        "heading_path": page_meta.get("heading_path", ""),
                    },
                    "source": page_meta.get("source", doc_name),
                }
                chunks.append(chunk)
                
                print(f"[ImageExtract] Extracted image: {img_path.name} ({width}x{height})")
                
            except Exception as e:
                print(f"[ImageExtract] Failed to extract image {img_idx} on page {page_num}: {e}")
                continue
        
        return chunks

    # ==================== 原有方法保持不变 ====================

    def _extract_page_headings(self, doc: fitz.Document) -> Dict[int, str]:
        """
        提取 PDF 每页对应的标题路径。
        
        优先使用 PDF 书签（TOC），否则从文本特征推断。
        返回: {page_number: heading_path}
        """
        # 先尝试从 TOC 获取标题结构
        toc = doc.get_toc()
        if toc:
            return self._build_headings_from_toc(toc)
        
        # 无 TOC，从每页文本推断标题
        page_headings = {}
        for page_num in range(len(doc)):
            page = doc[page_num]
            heading = self._infer_page_heading(page)
            if heading:
                page_headings[page_num + 1] = heading
        
        return page_headings

    def _build_headings_from_toc(self, toc: List[tuple]) -> Dict[int, str]:
        """
        从 PDF TOC（书签）构建每页的标题路径。
        
        TOC 格式: [(level, title, page), ...]
        返回: {page_number: "一级标题 > 二级标题 > ..."}
        """
        # 构建标题层级栈
        heading_stack = []
        page_headings = {}
        
        for level, title, page in toc:
            # 维护层级栈：当前 level 时，弹出比它深的层级
            while len(heading_stack) >= level:
                heading_stack.pop()
            heading_stack.append(title)
            
            # 该页及后续页（直到下一个标题页）都使用这个标题路径
            heading_path = " > ".join(heading_stack)
            page_headings[page] = heading_path
        
        # 填充空白页：没有明确标题的页，继承最近的标题
        if page_headings:
            max_page = max(page_headings.keys())
            last_heading = ""
            for p in range(1, max_page + 1):
                if p in page_headings:
                    last_heading = page_headings[p]
                elif last_heading:
                    page_headings[p] = last_heading
        
        return page_headings

    def _infer_page_heading(self, page: fitz.Page) -> str:
        """
        从页面文本推断标题（无 TOC 时的回退策略）。
        
        策略：
        1. 查找页面中最大的字体文本
        2. 优先使用加粗文本
        3. 限制长度（< 100 字符）
        """
        blocks = page.get_text("dict").get("blocks", [])
        candidates = []
        
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text or len(text) > 100:
                        continue
                    size = span["size"]
                    flags = span["flags"]
                    # 加粗文本权重更高
                    is_bold = bool(flags & 2**4)
                    score = size + (5 if is_bold else 0)
                    candidates.append((score, text))
        
        if candidates:
            # 返回得分最高的文本
            candidates.sort(reverse=True)
            return candidates[0][1]
        
        return ""

    def _detect_page_type(self, page: fitz.Page, text: str) -> str:
        """
        检测 PDF 页面类型，返回类型标签。
        
        类型：
            "text": 文字型页面
            "scan": 扫描件（文字极少）
            "formula_heavy": 公式密集型
            "table": 表格型
            "chart": 图表
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
        """
        对扫描件 PDF 页面进行 OCR，返回 [(text, metadata)] 列表
        """
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
                
                if extracted_text.strip():
                    results.append((extracted_text, {**meta, "page_type": "scan", "ocr": True}))
                else:
                    results.append(("[扫描件，OCR 未识别出文字]", {**meta, "page_type": "scan", "ocr": False}))
            except Exception as e:
                print(f"[DocumentProcessor] OCR failed for page {page_num}: {e}")
                results.append(("[扫描件，OCR 失败]", {**meta, "page_type": "scan", "ocr_error": str(e)}))
            finally:
                # 清理临时文件
                if temp_path.exists():
                    temp_path.unlink()

        return results

    def _vlm_scan_pages(self, pages: List[Tuple[int, fitz.Page, Dict[str, Any]]]) -> List[Tuple[str, Dict[str, Any]]]:
        """
        OCR 不可用时使用 VLM 处理扫描件页面。
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

    def _process_image(self, path: Path, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        处理图片文件（OCR + 公式识别）。
        """
        # 使用 OCR 提取文字
        ocr = self._get_ocr()
        if ocr:
            result = ocr.ocr(str(path), cls=True)
            texts = []
            if result and result[0]:
                for line in result[0]:
                    if line:
                        texts.append(line[1][0])
            extracted_text = "\n".join(texts)
        else:
            extracted_text = ""
        
        # 使用公式识别
        formula_ocr = self._get_formula_ocr()
        if formula_ocr:
            try:
                img = Image.open(str(path))
                formula_result = formula_ocr(img)
                if formula_result:
                    extracted_text += f"\n[公式] {formula_result}"
            except Exception as e:
                print(f"[DocumentProcessor] Formula OCR failed: {e}")
        
        if not extracted_text.strip():
            extracted_text = "[图片，未识别出文字或公式]"
        
        return [{
            "id": f"img_{hashlib.md5(str(path).encode()).hexdigest()[:12]}",
            "text": extracted_text,
            "metadata": {
                **metadata,
                "chunk_type": "image",
            },
            "source": metadata["source"],
        }]

    def process_image_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        处理图片 chunk（OCR 识别）。
        
        Args:
            chunks: 包含图片的 chunk 列表
        
        Returns:
            处理后的 chunk 列表
        """
        results = []
        for chunk in chunks:
            if chunk.get("metadata", {}).get("chunk_type") == "image":
                # 图片 chunk 已经处理过
                results.append(chunk)
            else:
                results.append(chunk)
        return results
