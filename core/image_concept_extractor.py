"""
图片概念提取器 (ImageConceptExtractor)
LA-035 Phase 2.2: 图片 → VLM 描述/公式识别 → 伪文本 chunk → 概念提取 → 融合到 CanonicalConcept

核心流程:
    1. 从 Markdown chunks 中识别含图片的 TitleChunk
    2. 对每个图片，判断类型（公式图片 vs 普通图片）
       - 公式图片: 调用 VLM task="formula" 识别 LaTeX
       - 普通图片: 结合 TitleChunk 上下文调用 VLM task="describe" 生成描述
    3. 将处理结果作为"伪文本 chunk"输入 SemanticExtractor
    4. 提取的概念携带 media_refs，参与去重融合

使用方式:
    from core.image_concept_extractor import ImageConceptExtractor
    
    extractor = ImageConceptExtractor()
    enhanced_chunks = extractor.enrich_chunks_with_image_descriptions(
        chunks,
        subject="generic",
        base_dir=Path("/path/to/mineru/output")  # MinerU 输出目录，用于解析相对路径
    )
"""

import hashlib
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image as PILImage

from config.settings import KNOWLEDGE_BASE_DIR
from core.vlm_client import VLMClient


class ImageConceptExtractor:
    """
    图片概念提取器。
    
    对 Markdown chunks 中的图片进行智能分析：
    - 公式图片 → VLM formula 识别 → LaTeX 文本
    - 普通图片 → VLM describe 生成描述文本
    
    使图片内容能够参与概念提取流程。
    """
    
    # LA-035-P21: 公式图片检测阈值
    FORMULA_ASPECT_RATIO_MIN = 1.5   # 宽高比最小值（公式通常是宽而矮的）
    FORMULA_HEIGHT_MAX = 120         # 高度最大值（像素）
    FORMULA_WIDTH_MIN = 50           # 宽度最小值（像素）
    
    def __init__(self, vlm_client: Optional[VLMClient] = None):
        """
        Args:
            vlm_client: VLM 客户端实例，None 则自动创建
        """
        self.vlm = vlm_client or VLMClient()
        self._description_cache: Dict[str, str] = {}  # 图片路径 → 描述缓存
        self._formula_cache: Dict[str, str] = {}      # LA-035-P21: 图片路径 → LaTeX 缓存
    
    def enrich_chunks_with_image_descriptions(
        self,
        chunks: List[Dict[str, Any]],
        subject: str = "generic",
        base_dir: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """
        对 chunks 中的图片进行 VLM 描述，增强 chunk 文本内容。
        
        Args:
            chunks: MarkdownChunker 输出的 chunk 列表
            subject: 学科名称（用于图片路径解析）
            base_dir: 基础目录（用于解析相对路径，如 MinerU 输出目录）
        
        Returns:
            增强后的 chunk 列表（新增了图片伪文本 chunks）
        """
        result = []
        
        for chunk in chunks:
            result.append(chunk)
            
            # 处理 heading / document 类型的 chunk 中的图片（v2.0 用 "heading"，兼容旧数据 "title"）
            chunk_type = chunk.get("metadata", {}).get("chunk_type", "")
            if chunk_type not in ("heading", "document", "title"):
                continue
            
            image_refs = chunk.get("metadata", {}).get("image_refs", [])
            if not image_refs:
                continue
            
            # 获取上下文（标题 + 该标题下的文本摘要）
            context = self._build_context(chunk)
            
            # 处理每个图片
            for img_idx, img_ref in enumerate(image_refs):
                img_path = self._resolve_image_path(img_ref, subject, base_dir)
                if not img_path or not img_path.exists():
                    print(f"[ImageConceptExtractor] 图片不存在: {img_ref}")
                    continue
                
                # LA-035-P21: 调用智能图片分析（自动判断公式 vs 普通图片）
                analyze_result = self._describe_image_with_context(img_path, context)
                
                if not analyze_result:
                    continue
                
                text, source = analyze_result  # text=LaTeX 或描述, source="vlm_formula" 或 "vlm_describe"
                
                # 创建"伪文本 chunk"
                pseudo_chunk = self._create_pseudo_chunk(
                    parent_chunk=chunk,
                    img_ref=img_ref,
                    text=text,
                    source=source,
                    img_idx=img_idx,
                    kb_path=img_path,
                )
                result.append(pseudo_chunk)
        
        return result
    
    def _build_context(self, title_chunk: Dict[str, Any]) -> str:
        """从 TitleChunk 构建 VLM 提示的上下文。"""
        heading = title_chunk.get("metadata", {}).get("heading_path", "")
        text = title_chunk.get("text", "")
        
        # 取文本前 500 字符作为摘要
        text_summary = text[:500].replace("\n", " ")
        
        context_parts = []
        if heading:
            context_parts.append(f"章节标题: {heading}")
        if text_summary:
            context_parts.append(f"章节内容摘要: {text_summary}")
        
        return "\n".join(context_parts) if context_parts else ""
    
    def _describe_image_with_context(
        self,
        img_path: Path,
        context: str,
    ) -> Optional[Tuple[str, str]]:
        """
        调用 VLM 分析图片，自动判断图片类型并选择合适的分析策略。
        
        LA-035-P21: 对疑似公式图片调用 task="formula" 识别 LaTeX，
        对普通图片调用 task="describe" 生成描述。
        
        Args:
            img_path: 图片文件路径
            context: 标题/章节上下文
        
        Returns:
            (text, source) 元组:
            - text: 识别出的 LaTeX 代码（公式）或描述文本（普通图片）
            - source: "vlm_formula" | "vlm_describe" | None
        """
        print(f"[ImageConceptExtractor] 分析图片: {img_path.name}")
        start = time.time()
        
        # LA-035-P21: Step 1 — 检测是否为公式图片
        is_formula = self._is_formula_image(img_path)
        
        if is_formula:
            print(f"[ImageConceptExtractor] 检测到公式图片特征，尝试 LaTeX 识别...")
            latex = self._recognize_formula(img_path)
            elapsed = time.time() - start
            
            if latex:
                print(f"[ImageConceptExtractor] 公式识别完成 ({elapsed:.1f}s): {latex[:80]}...")
                return (latex, "vlm_formula")
            else:
                print(f"[ImageConceptExtractor] 公式识别失败，回退到图片描述...")
        
        # 普通图片: 调用 VLM describe
        try:
            description = self.vlm.analyze_image(str(img_path), task="describe")
            elapsed = time.time() - start
            
            if description:
                print(f"[ImageConceptExtractor] 描述生成完成 ({elapsed:.1f}s): {description[:80]}...")
                return (description.strip(), "vlm_describe")
            else:
                print(f"[ImageConceptExtractor] VLM 返回空描述")
                return None
                
        except Exception as e:
            print(f"[ImageConceptExtractor] VLM 调用失败: {e}")
            return None
    
    def _is_formula_image(self, img_path: Path) -> bool:
        """
        判断图片是否为公式图片（基于视觉特征）。
        
        公式图片的典型特征:
        - 宽高比大（宽而矮）
        - 高度较小（通常 < 120px）
        - 宽度适中（通常 > 50px）
        
        Args:
            img_path: 图片文件路径
        
        Returns:
            True 如果疑似公式图片
        """
        try:
            with PILImage.open(img_path) as img:
                width, height = img.size
                aspect_ratio = width / height if height > 0 else 0
                
                is_formula = (
                    aspect_ratio >= self.FORMULA_ASPECT_RATIO_MIN
                    and height <= self.FORMULA_HEIGHT_MAX
                    and width >= self.FORMULA_WIDTH_MIN
                )
                
                if is_formula:
                    print(f"[ImageConceptExtractor] 公式图片检测: {img_path.name} "
                          f"({width}x{height}, 宽高比={aspect_ratio:.2f}) → 疑似公式")
                
                return is_formula
                
        except Exception as e:
            print(f"[ImageConceptExtractor] 公式检测失败 {img_path.name}: {e}")
            return False
    
    def _recognize_formula(self, img_path: Path) -> Optional[str]:
        """
        调用 VLM 识别公式图片中的 LaTeX 代码。
        
        Args:
            img_path: 公式图片路径
        
        Returns:
            LaTeX 代码字符串，失败返回 None
        """
        # 检查缓存
        cache_key = str(img_path)
        if cache_key in self._formula_cache:
            print(f"[ImageConceptExtractor] 使用缓存公式: {img_path.name}")
            return self._formula_cache[cache_key]
        
        try:
            result = self.vlm.analyze_image(str(img_path), task="formula")
            
            if result:
                # 清理结果：去除多余的 $$ 包裹（如果 VLM 返回了）
                latex = result.strip()
                # 去除可能的 markdown 代码块标记
                latex = latex.replace("```latex", "").replace("```", "").strip()
                # 如果 VLM 用 $$ 包裹，去除外层
                if latex.startswith("$$") and latex.endswith("$$"):
                    latex = latex[2:-2].strip()
                
                if latex:
                    self._formula_cache[cache_key] = latex
                    return latex
            
            return None
            
        except Exception as e:
            print(f"[ImageConceptExtractor] 公式识别失败: {e}")
            return None
    
    def _resolve_image_path(
        self,
        img_ref: Dict[str, Any],
        subject: str,
        base_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        """
        解析图片引用为绝对路径。
        
        搜索顺序:
            1. base_dir / path（MinerU 输出目录下的相对路径）
            2. 绝对路径
            3. KNOWLEDGE_BASE_DIR / path
            4. KNOWLEDGE_BASE_DIR / {subject}_v1_images / path.name
        """
        path_candidates = [
            img_ref.get("path"),
            img_ref.get("relative_path"),
            img_ref.get("full_path"),
        ]
        
        for path_str in path_candidates:
            if not path_str:
                continue
            
            path = Path(path_str)
            
            # 1. base_dir / path（MinerU 输出目录下的相对路径）
            if base_dir and not path.is_absolute():
                full_path = base_dir / path
                if full_path.exists():
                    return full_path
            
            # 2. 绝对路径
            if path.is_absolute() and path.exists():
                return path
            
            # 3. 知识库根目录下的相对路径
            kb_path = KNOWLEDGE_BASE_DIR / path_str
            if kb_path.exists():
                return kb_path
            
            # 4. 学科图片目录
            img_dir = KNOWLEDGE_BASE_DIR / f"{subject}_v1_images"
            img_path = img_dir / path.name if path.name else img_dir / path_str
            if img_path.exists():
                return img_path
        
        return None
    
    def _create_pseudo_chunk(
        self,
        parent_chunk: Dict[str, Any],
        img_ref: Dict[str, Any],
        text: str,
        source: str,
        img_idx: int,
        kb_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        创建图片"伪文本 chunk"。
        
        LA-035-P21: 支持公式图片和普通图片两种类型。
        - 公式图片: text=LaTeX 代码, chunk_type="image_pseudo", 额外添加 formula media_refs
        - 普通图片: text=描述文本, chunk_type="image_pseudo"
        """
        parent_id = parent_chunk["id"]
        heading = parent_chunk.get("metadata", {}).get("heading_path", "")
        chunk_source = parent_chunk.get("source", "")
        
        # 生成 ID
        img_hash = hashlib.md5(text.encode()).hexdigest()[:6]
        pseudo_id = f"img_pseudo_{parent_id}_{img_idx}_{img_hash}"
        
        # LA-035-P21: 根据图片类型构建不同的伪文本
        is_formula = source == "vlm_formula"
        if is_formula:
            # 公式图片: 伪文本为 LaTeX 代码，便于 SemanticExtractor 提取概念
            pseudo_text = f"[公式 - {heading}]\n{text}"
        else:
            # 普通图片: 伪文本为 VLM 描述
            pseudo_text = f"[图片 - {heading}]\n{text}"
        
        # LA-035: 使用 KB 中的实际路径，保留原始信息
        media_ref = dict(img_ref)  # 复制，避免修改原始
        if kb_path and kb_path.exists():
            media_ref["path"] = str(kb_path)
            # 推断缩略图路径
            thumb_path = str(kb_path).replace("_v1_images/", "_v1_thumbnails/")
            media_ref["thumbnail_path"] = thumb_path
        
        # LA-035-P21: 构建 media_refs
        media_refs = [media_ref]
        # 如果是公式图片，额外添加 formula 类型的 media_ref
        if is_formula:
            media_refs.append({
                "type": "formula",
                "latex": text,
                "display": "block" if "\n" in text else "inline",
            })
        
        return {
            "id": pseudo_id,
            "text": pseudo_text,
            "metadata": {
                **parent_chunk.get("metadata", {}),
                "chunk_type": "image_pseudo",
                "parent_id": parent_id,
                "heading_path": heading,
                "media_refs": media_refs,
                "description_source": source,  # "vlm_formula" 或 "vlm_describe"
                "description_length": len(text),
                "is_formula_image": is_formula,
            },
            "source": chunk_source,
        }


# ========== 与 SemanticExtractor 的整合 ==========

def prepare_chunks_for_extraction(
    chunks: List[Dict[str, Any]],
    subject: str = "generic",
    use_vlm: bool = True,
    base_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    预处理 chunks，为概念提取做准备。
    
    如果 use_vlm=True:
        - 调用 ImageConceptExtractor 为图片生成描述
        - 返回增强后的 chunks（含 image_pseudo chunks）
    
    Args:
        chunks: MarkdownChunker 输出的 chunk 列表
        subject: 学科名称
        use_vlm: 是否使用 VLM 分析图片
        base_dir: MinerU 输出目录（用于解析相对路径）
    
    Returns:
        预处理后的 chunk 列表
    """
    if not use_vlm:
        return chunks
    
    extractor = ImageConceptExtractor()
    return extractor.enrich_chunks_with_image_descriptions(chunks, subject, base_dir)
