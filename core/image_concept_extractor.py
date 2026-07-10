"""
图片概念提取器 (ImageConceptExtractor)
LA-035 Phase 2.2: 图片 → VLM 描述 → 伪文本 chunk → 概念提取 → 融合到 CanonicalConcept

核心流程:
    1. 从 Markdown chunks 中识别含图片的 TitleChunk
    2. 对每个图片，结合 TitleChunk 上下文调用 VLM 生成描述
    3. 将图片描述作为"伪文本 chunk"输入 SemanticExtractor
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

from config.settings import KNOWLEDGE_BASE_DIR
from core.vlm_client import VLMClient


class ImageConceptExtractor:
    """
    图片概念提取器。
    
    对 Markdown chunks 中的图片进行 VLM 分析，生成描述文本，
    使图片内容能够参与概念提取流程。
    """
    
    def __init__(self, vlm_client: Optional[VLMClient] = None):
        """
        Args:
            vlm_client: VLM 客户端实例，None 则自动创建
        """
        self.vlm = vlm_client or VLMClient()
        self._description_cache: Dict[str, str] = {}  # 图片路径 → 描述缓存
    
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
            
            # 只处理 TitleChunk（图片通常嵌入在标题下）
            if chunk.get("metadata", {}).get("chunk_type") != "title":
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
                
                # 检查缓存
                cache_key = str(img_path)
                if cache_key in self._description_cache:
                    description = self._description_cache[cache_key]
                    print(f"[ImageConceptExtractor] 使用缓存描述: {img_path.name}")
                else:
                    # 调用 VLM 生成描述
                    description = self._describe_image_with_context(img_path, context)
                    if description:
                        self._description_cache[cache_key] = description
                
                if not description:
                    continue
                
                # 创建"伪文本 chunk"
                pseudo_chunk = self._create_pseudo_chunk(
                    parent_chunk=chunk,
                    img_ref=img_ref,
                    description=description,
                    img_idx=img_idx,
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
    ) -> Optional[str]:
        """调用 VLM 分析图片，结合上下文生成更准确的描述。"""
        print(f"[ImageConceptExtractor] 分析图片: {img_path.name}")
        start = time.time()
        
        try:
            description = self.vlm.analyze_image(str(img_path), task="describe")
            elapsed = time.time() - start
            
            if description:
                print(f"[ImageConceptExtractor] 描述生成完成 ({elapsed:.1f}s): {description[:100]}...")
                return description.strip()
            else:
                print(f"[ImageConceptExtractor] VLM 返回空描述")
                return None
                
        except Exception as e:
            print(f"[ImageConceptExtractor] VLM 调用失败: {e}")
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
        description: str,
        img_idx: int,
    ) -> Dict[str, Any]:
        """创建图片"伪文本 chunk"。"""
        parent_id = parent_chunk["id"]
        heading = parent_chunk.get("metadata", {}).get("heading_path", "")
        source = parent_chunk.get("source", "")
        
        # 生成 ID
        img_hash = hashlib.md5(description.encode()).hexdigest()[:6]
        pseudo_id = f"img_pseudo_{parent_id}_{img_idx}_{img_hash}"
        
        # 构建伪文本：图片描述 + 元信息
        pseudo_text = f"[图片 - {heading}]\n{description}"
        
        return {
            "id": pseudo_id,
            "text": pseudo_text,
            "metadata": {
                **parent_chunk.get("metadata", {}),
                "chunk_type": "image_pseudo",
                "parent_id": parent_id,
                "heading_path": heading,
                "media_refs": [img_ref],
                "description_source": "vlm",
                "description_length": len(description),
            },
            "source": source,
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
