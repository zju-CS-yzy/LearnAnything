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
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image as PILImage

from config.settings import KNOWLEDGE_BASE_DIR, get_subject_images_dir, get_subject_thumbnails_dir, get_user_subject_dir, get_share_subject_dir
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
        self.last_rename_map: Dict[str, str] = {}
    
    def enrich_chunks_with_image_descriptions(
        self,
        chunks: List[Dict[str, Any]],
        subject: str = "generic",
        base_dir: Optional[Path] = None,
        rename_callback: Optional[Callable[[str, str], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        对 chunks 中的图片进行 VLM 描述，增强 chunk 文本内容。
        同时基于 VLM 描述对图片进行总结性命名，重命名文件并同步更新所有路径引用。
        
        Args:
            chunks: MarkdownChunker 输出的 chunk 列表
            subject: 学科名称（用于图片路径解析）
            base_dir: 基础目录（用于解析相对路径，如 MinerU 输出目录）
            rename_callback: 图片成功重命名后的持久化回调（旧相对路径，新相对路径）
        
        Returns:
            增强后的 chunk 列表（新增了图片伪文本 chunks）
        """
        result = []
        rename_map = {}  # old_relative_path -> new_relative_path
        self.last_rename_map = {}
        
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
                
                # LA-IMG-NAMING: 调用 VLM 获取标题和描述（JSON 格式）
                analyze_result = self._analyze_image_with_title(img_path, context)
                
                if not analyze_result:
                    continue
                
                title, description, source = analyze_result
                
                # LA-IMG-NAMING: 基于 VLM 生成的标题重命名图片
                user_id = chunk.get("metadata", {}).get("user_id")
                file_name = self._generate_filename_from_title(title, img_path)
                rename_result = self._rename_image_file(img_path, file_name, subject, user_id)
                if rename_result:
                    old_rel = img_ref.get("relative_path", "")
                    if old_rel:
                        new_rel = rename_result["relative_path"]
                        rename_map[old_rel] = new_rel
                        self.last_rename_map[old_rel] = new_rel
                        if rename_callback:
                            rename_callback(old_rel, new_rel)
                    # 更新 img_ref 指向新路径（直接修改原 chunk 的引用）
                    img_ref.update(rename_result)
                
                # 创建"伪文本 chunk"（使用更新后的路径）
                kb_path = rename_result["full_path"] if rename_result else img_path
                pseudo_chunk = self._create_pseudo_chunk(
                    parent_chunk=chunk,
                    img_ref=img_ref,
                    text=description,  # 使用完整描述作为 chunk 文本
                    source=source,
                    img_idx=img_idx,
                    kb_path=kb_path,
                )
                result.append(pseudo_chunk)
        
        # 统一更新所有 chunk 中的图片路径引用
        if rename_map:
            self._update_all_media_refs(result, rename_map)
            print(f"[ImageConceptExtractor] 已重命名 {len(rename_map)} 张图片")
        
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
    
    def _analyze_image_with_title(
        self,
        img_path: Path,
        context: str,
        ) -> Optional[Tuple[str, str, str]]:
        """
        LA-IMG-NAMING: 调用 VLM 获取图片标题和描述（JSON 格式）。
    
        增强鲁棒性：
        - max_tokens=8192 防止截断
        - 清理控制字符后再解析 JSON
        - 检测并修复截断的 JSON
        - 回退时清理 markdown 标记
    
        Returns:
            (title, description, source) 三元组，失败返回 None
        """
        print(f"[ImageConceptExtractor] 分析图片（含标题生成）: {img_path.name}")
        start = time.time()
    
        # Step 1: 检测是否为公式图片
        is_formula = self._is_formula_image(img_path)
    
        if is_formula:
            latex = self._recognize_formula(img_path)
            if latex:
                title = f"数学公式-{hashlib.md5(latex.encode()).hexdigest()[:6]}"
                return (title, latex, "vlm_formula")
    
        # Step 2: 普通图片 — 调用 VLM 返回 JSON
        try:
            import base64
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
        
            system_prompt = (
                "你是一位专业的文档图片分析助手。请仔细分析图片内容，"
                "然后用 JSON 格式返回结果。\n\n"
                "要求：\n"
                "1. title: 用 3-5 个中文词概括图片核心内容，作为标题\n"
                "2. description: 对图片进行详细描述（200-500字）\n"
                "3. title 必须简洁、概括性强，不含 markdown 格式\n"
                "4. 只输出 JSON，不要有其他文字\n"
                "5. JSON 字符串中的换行符必须使用 \\n 转义\n\n"
                "JSON 格式：\n"
                '{\"title\": "概括性标题\", "description\": "详细描述...\"}'
            )
        
            user_text = "请分析这张图片。"
            if context:
                user_text += f"\n\n上下文信息：\n{context}"
        
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": user_text},
                    ],
                },
            ]
        
            # LA-FIX: 增加 max_tokens 防止截断
            result = self.vlm._call_api(messages, max_tokens=8192)
            elapsed = time.time() - start
        
            if not result:
                print(f"[ImageConceptExtractor] VLM 返回空结果")
                return None
        
            # 尝试解析 JSON（多层防护）
            parsed = self._safe_parse_json(result)
            if parsed:
                title = parsed.get("title", "").strip()
                description = parsed.get("description", "").strip()
            
                # 清理 title
                title = re.sub(r"[^\w\s\u4e00-\u9fff\-]", "", title).strip("-")
            
                if title and description:
                    print(f"[ImageConceptExtractor] 标题+描述生成完成 ({elapsed:.1f}s): title={title[:40]}")
                    return (title, description, "vlm_describe")
        
            # 回退：清理后把返回内容当描述
            print(f"[ImageConceptExtractor] JSON 解析失败，回退到纯描述")
            return self._fallback_title_from_text(result)
        
        except Exception as e:
            print(f"[ImageConceptExtractor] VLM 调用失败: {e}")
            return None
    
    def _safe_parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        安全解析可能包含控制字符或被截断的 JSON。
    
        防护策略：
        1. 提取 JSON 块（处理 markdown 代码块包裹）
        2. 修复截断（补全缺少的 }）
        3. 清理非法控制字符（原始换行符 → 转义 \\n）
        4. 修复未转义的双引号
        """
        import json
    
        # 1. 提取 JSON 块
        # 处理被 markdown 代码块包裹的情况
        code_block_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if code_block_match:
            json_str = code_block_match.group(1).strip()
        else:
            # 直接找 { ... }
            brace_match = re.search(r"\{.*\}", text, re.DOTALL)
            if not brace_match:
                return None
            json_str = brace_match.group().strip()
    
        # 2. 修复截断：如果缺少闭合的 }，尝试补全
        open_count = json_str.count("{")
        close_count = json_str.count("}")
        if open_count > close_count:
            json_str += "}" * (open_count - close_count)
    
        # 3. 清理非法控制字符
        # 将原始换行符（JSON 字符串值内部的）替换为转义的 \\n
        cleaned = []
        in_string = False
        escape_next = False
        for char in json_str:
            if escape_next:
                cleaned.append(char)
                escape_next = False
                continue
            if char == "\\":
                cleaned.append(char)
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                cleaned.append(char)
                continue
            if in_string and char == "\n":
                # 字符串值内部的原始换行符 → 转义
                cleaned.append("\\n")
            elif in_string and ord(char) < 32 and char not in "\t\r":
                # 其他控制字符 → 空格
                cleaned.append(" ")
            else:
                cleaned.append(char)
    
        json_str_clean = "".join(cleaned)
    
        # 4. 尝试解析
        try:
            return json.loads(json_str_clean)
        except json.JSONDecodeError:
            # 5. 尝试修复未转义的双引号（字符串值内部）
            try:
                fixed = self._fix_unescaped_quotes(json_str_clean)
                return json.loads(fixed)
            except:
                return None
    
    def _fix_unescaped_quotes(self, s: str) -> str:
        """
        修复 JSON 字符串值内部未转义的双引号。
        简单策略：假设 key 的引号是正确转义的，只修复 value 中的。
        """
        result = []
        in_string = False
        escape_next = False
        for i, char in enumerate(s):
            if escape_next:
                result.append(char)
                escape_next = False
                continue
            if char == "\\":
                result.append(char)
                escape_next = True
                continue
            if char == '"' and not escape_next:
                if in_string:
                    # 检查下一个非空白字符
                    j = i + 1
                    while j < len(s) and s[j] in " \t\n":
                        j += 1
                    if j < len(s) and s[j] in ",}]:":
                        # 字符串正常结束
                        in_string = False
                        result.append(char)
                    else:
                        # 可能是未转义的引号
                        result.append('\\"')
                else:
                    in_string = True
                    result.append(char)
            else:
                result.append(char)
        return "".join(result)
    
    def _fallback_title_from_text(self, text: str) -> Tuple[str, str, str]:
        """
        从 VLM 原始输出中提取标题和描述（回退策略）。
        清理 markdown 标记，生成合理的文件名。
        """
        import re as _re
    
        # 1. 清理 markdown 代码块标记
        cleaned = _re.sub(r"```\w*\s*\n?|```", "", text).strip()
        # 2. 清理其他 markdown
        cleaned = cleaned.replace("**", "").replace("#", "").strip()
    
        # 3. 尝试从中提取 title 和 description
        title_match = _re.search(r'"title"\s*:\s*"([^"]*)"', cleaned)
        desc_match = _re.search(r'"description"\s*:\s*"([^"]*)"', cleaned)
    
        if title_match:
            title = title_match.group(1).strip()
            title = _re.sub(r"[^\w\s\u4e00-\u9fff\-]", "", title).strip("-")
        else:
            # 从文本前部取词
            words = _re.sub(r"[^\w\s\u4e00-\u9fff]", " ", cleaned[:50]).split()
            title = "-".join(words[:5]) if words else "图片"
    
        description = desc_match.group(1) if desc_match else cleaned
    
        return (title, description, "vlm_describe")

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
        
        LA-051-DIR: 搜索顺序更新为新目录结构。
        
        搜索顺序:
            1. base_dir / path（MinerU 输出目录下的相对路径）
            2. 绝对路径
            3. KNOWLEDGE_BASE_DIR / path（相对路径）
            4. get_subject_images_dir(subject) / path.name（新结构）
            5. KNOWLEDGE_BASE_DIR / {subject}_v1_images / path.name（旧结构兼容）
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
            
            # 4. LA-051-DIR: 新结构 - 学科图片目录
            img_dir = get_subject_images_dir(subject)
            img_path = img_dir / path.name if path.name else img_dir / path_str
            if img_path.exists():
                return img_path
            
            # 5. 旧结构兼容
            legacy_img_dir = KNOWLEDGE_BASE_DIR / f"{subject}_v1_images"
            legacy_path = legacy_img_dir / path.name if path.name else legacy_img_dir / path_str
            if legacy_path.exists():
                return legacy_path
        
        return None
    
    # ========== LA-IMG-NAMING: 图片命名与路径同步 ==========

    def _generate_filename_from_title(self, title: str, img_path: Path) -> str:
        """
        LA-IMG-NAMING: 基于 VLM 生成的标题生成合法文件名。
        
        1. 清理标题中的非法字符和 markdown 格式
        2. 空格转为连字符
        3. 限制长度
        4. 加上原文件 hash 后缀避免冲突
        """
        import re
        
        # 1. 清理非法字符和 markdown
        name = re.sub(r"[#*\"'<>|:/?\\]", "", title)
        name = re.sub(r"\s+", "-", name).strip("-")
        
        # 2. 限制长度
        if len(name) > 40:
            name = name[:40].rsplit("-", 1)[0] if "-" in name[:40] else name[:40]
        
        # 3. 如果为空，回退到 hash
        if not name:
            name = hashlib.md5(title.encode()).hexdigest()[:8]
        
        # 4. 加上 hash 后缀避免冲突
        orig_hash = img_path.stem.split("_")[-1] if "_" in img_path.stem else hashlib.md5(str(img_path).encode()).hexdigest()[:4]
        
        return f"{name}-{orig_hash}.png"

    def _rename_image_file(
        self,
        old_path: Path,
        new_name: str,
        subject: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        重命名图片文件及其缩略图。
        
        Returns:
            新的路径信息字典，失败返回 None
        """
        if not old_path.exists():
            return None
        
        # 确定目录
        img_dir = get_subject_images_dir(subject, user_id)
        thumb_dir = get_subject_thumbnails_dir(subject, user_id)
        
        new_img_path = img_dir / new_name
        
        # 避免冲突：如果目标已存在，添加序号
        counter = 1
        stem = Path(new_name).stem
        suffix = Path(new_name).suffix
        while new_img_path.exists():
            new_img_path = img_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        
        try:
            # 重命名图片
            old_path.rename(new_img_path)
            print(f"[ImageConceptExtractor] 图片重命名: {old_path.name} -> {new_img_path.name}")
            
            # 重命名缩略图
            old_thumb_path = thumb_dir / old_path.name
            new_thumb_path = thumb_dir / new_img_path.name
            if old_thumb_path.exists():
                old_thumb_path.rename(new_thumb_path)
            
            return {
                "full_path": str(new_img_path),  # 转为字符串，避免 JSON 序列化失败
                "relative_path": str(new_img_path.relative_to(KNOWLEDGE_BASE_DIR)).replace("\\", "/"),
                "thumbnail_path": str(new_thumb_path.relative_to(KNOWLEDGE_BASE_DIR)).replace("\\", "/") if old_thumb_path.exists() else "",
                "width": None,
                "height": None,
            }
        except Exception as e:
            print(f"[ImageConceptExtractor] 图片重命名失败: {e}")
            return None

    def _update_all_media_refs(self, chunks: List[Dict[str, Any]], rename_map: Dict[str, str]):
        """
        统一更新所有 chunk 中的图片路径引用。
        处理 image_refs、media_refs 以及 concepts 中的 media_refs 三种路径存储位置。
        LA-035-P27-fix: 修复 concept 级别 media_refs 未被更新的问题，导致知识图谱节点引用旧文件名。
        """
        normalized_renames = {
            str(old).replace("\\", "/"): str(new).replace("\\", "/")
            for old, new in rename_map.items()
        }

        def update_ref(ref: Dict[str, Any]) -> None:
            """Update refs that store the old location in any supported path field."""
            if not isinstance(ref, dict):
                return
            values = [
                str(ref.get(key) or "").replace("\\", "/")
                for key in ("relative_path", "path", "full_path", "thumbnail_path")
            ]
            for old_rel, new_rel in normalized_renames.items():
                old_name, new_name = Path(old_rel).name, Path(new_rel).name
                if not any(
                    value == old_rel or (value and Path(value).name == old_name)
                    for value in values
                ):
                    continue
                ref["relative_path"] = new_rel
                for key in ("path", "full_path", "thumbnail_path"):
                    value = ref.get(key)
                    if not isinstance(value, str) or not value:
                        continue
                    normalized = value.replace("\\", "/")
                    if Path(normalized).name == old_name:
                        ref[key] = normalized[: -len(old_name)] + new_name
                # A paragraph-level Markdown ref often has only ``path``.
                # Store the canonical KB-relative path as well as updating it.
                if not ref.get("path") or str(ref.get("path")).replace("\\", "/") == old_rel:
                    ref["path"] = new_rel
                return

        for chunk in chunks:
            # Markdown text itself can contain image links; metadata-only updates
            # leave stale paths in vector storage and in later document rebuilds.
            chunk_text = chunk.get("text")
            if isinstance(chunk_text, str):
                for old_rel, new_rel in normalized_renames.items():
                    chunk_text = chunk_text.replace(
                        str(old_rel).replace("\\", "/"),
                        str(new_rel).replace("\\", "/"),
                    )
                chunk["text"] = chunk_text

            # 1. 更新 image_refs
            for ref in chunk.get("metadata", {}).get("image_refs", []):
                update_ref(ref)
            
            # 2. 更新 chunk 级别的 media_refs
            for ref in chunk.get("metadata", {}).get("media_refs", []):
                if ref.get("type") != "image":
                    continue
                update_ref(ref)
            
            # LA-035-P27-fix: 3. 更新 concepts 中的 media_refs（知识图谱节点引用）
            for concept in chunk.get("metadata", {}).get("concepts", []):
                for ref in concept.get("media_refs", []):
                    if ref.get("type") != "image":
                        continue
                    update_ref(ref)

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
        # LA-054-FIX: 清除可能包含错误原始文件名的 relative_path
        media_ref = dict(img_ref)  # 复制，避免修改原始
        # LA-051-DIR: 从 parent_chunk metadata 提取 subject
        subject = parent_chunk.get("metadata", {}).get("subject", "generic")
        user_id = parent_chunk.get("metadata", {}).get("user_id")
        # LA-FIX: kb_path 可能是 str（来自 rename_result），转为 Path
        if kb_path:
            kb_path = Path(kb_path)
        if kb_path and kb_path.exists():
            # LA-054-FIX: 设置正确的相对路径（相对于 KNOWLEDGE_BASE_DIR）
            try:
                rel_path = str(kb_path.relative_to(KNOWLEDGE_BASE_DIR)).replace('\\', '/')
            except ValueError:
                rel_path = str(kb_path).replace('\\', '/')
            media_ref["path"] = str(kb_path)
            media_ref["relative_path"] = rel_path  # 覆盖旧的 MinerU 文件名
            # LA-051-DIR: 正确推断缩略图路径（新结构）
            thumb_dir = get_subject_thumbnails_dir(subject, user_id)
            thumb_path = thumb_dir / kb_path.name
            if thumb_path.exists():
                try:
                    thumb_rel = str(thumb_path.relative_to(KNOWLEDGE_BASE_DIR)).replace('\\', '/')
                except ValueError:
                    thumb_rel = str(thumb_path).replace('\\', '/')
                media_ref["thumbnail_path"] = thumb_rel
            else:
                # 旧结构兼容
                thumb_path_legacy = KNOWLEDGE_BASE_DIR / f"{subject}_v1_thumbnails" / kb_path.name
                if thumb_path_legacy.exists():
                    media_ref["thumbnail_path"] = str(thumb_path_legacy.relative_to(KNOWLEDGE_BASE_DIR)).replace('\\', '/')
        
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
