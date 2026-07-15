"""
Markdown 分块器 v2.0 (MarkdownChunker)
基于自然段分块 + 树形标题结构，替代/补充 DocumentChunker。

核心策略:
    1. 按自然段（空行分隔）分块 → ParagraphChunk（最小单位）
    2. 按 #/##/###/####/#####/###### 标题层级构建树形结构
    3. 每个自然段归属到包含它的最深层标题
    4. 每个标题节点生成 HeadingChunk（标题 + 直接段落 + 子节点引用）
    5. 文档根生成 DocumentChunk（可选）

与 DocumentChunker 的区别:
    - DocumentChunker: 基于页面和段落长度分块（适合 PyMuPDF 纯文本）
    - MarkdownChunker: 基于 Markdown 标题层级 + 自然段分块（适合 MinerU 结构化输出）

与 v1.0 的区别:
    - v1.0: 仅按 ## 分块，两层扁平结构（TitleChunk + ParagraphChunk）
    - v2.0: 按自然段分块，树形递归结构（DocumentChunk + HeadingChunk L1~N + ParagraphChunk）

使用方式:
    from core.markdown_chunker import MarkdownChunker
    
    chunker = MarkdownChunker()
    chunks = chunker.chunk_markdown(
        markdown_text=md_text,
        source_metadata={"source": "doc.pdf", "subject": "generic"}
    )
    # chunks: List[Dict] — 包含 heading + paragraph + document 类型的 chunk
"""

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class MarkdownChunker:
    """
    Markdown 树形分块器 v2.0。
    
    核心策略:
    1. 按自然段（\n\n+ 分隔）分块 → ParagraphChunk
    2. 按 #~###### 标题层级构建树形结构
    3. 每个自然段归属到包含它的最深层标题
    4. 每个标题节点 → HeadingChunk（标题 + 直接段落）
    5. 文档根 → DocumentChunk（前言段落 + 一级标题引用）
    """
    
    # 分块配置
    MAX_PARA_CHARS = 4000  # 单个自然段的最大字符数，超过则按句子切分
    MIN_PARA_CHARS = 50    # LA-035: 极短段落合并阈值（小于此值尝试合并到相邻段落）
    
    # 合并方向判断用的连词/标点规则
    MERGE_FORWARD_MARKERS = [  # 倾向于合并到下一段的标记
        "此外", "但是", "然而", "不过", "另外", "其次", "接着",
        "然后", "最后", "总之", "因此", "所以", "于是", "从而",
        "另一方面", "除此之外", "不仅如此", "更重要的是",
        "but", "however", "therefore", "thus", "moreover", "furthermore",
    ]
    
    MERGE_BACKWARD_MARKERS = [  # 倾向于合并到上一段的标记（句末标点已在代码中处理）
    ]
    
    def __init__(self, max_para_chars: int = 4000, min_para_chars: int = 50):
        self.max_para_chars = max_para_chars
        self.min_para_chars = min_para_chars
    
    def chunk_markdown(
        self,
        markdown_text: str,
        source_metadata: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        将 Markdown 文本分块为树形结构的 chunk 列表。
        
        Args:
            markdown_text: MinerU 输出的 Markdown 文本
            source_metadata: 基础元数据（source, subject, raw_path 等）
        
        Returns:
            扁平 chunk 列表（按文档顺序排列），包含三种 chunk_type:
            - "document": 文档根（Level 0，可选）
            - "heading": 标题级 chunk（Level 1~N）
            - "paragraph": 段落级 chunk（自然段，最小单位）
            
            每个 chunk 包含:
            - id: 唯一标识
            - text: 文本内容
            - metadata: 元数据（chunk_type, heading_path, heading_level, parent_id, child_ids 等）
            - source: 来源文件名
        """
        source_name = source_metadata.get("source", "unknown")
        lines = markdown_text.split("\n")
        
        # Stage 1: 解析标题树
        headings = self._parse_headings(lines)
        
        # Stage 2: 构建标题树（计算每个标题的区间）
        root_node, all_nodes = self._build_heading_tree(headings, len(lines))
        
        # Stage 3: 分割自然段并归属到标题
        self._assign_paragraphs_to_nodes(root_node, all_nodes, lines, markdown_text)
        
        # Stage 4: 生成 chunk
        chunks = self._generate_chunks(root_node, all_nodes, source_metadata)
        
        return chunks
    
    # ========== Stage 1: 标题解析 ==========
    
    def _parse_headings(self, lines: List[str]) -> List[Dict[str, Any]]:
        """
        解析 Markdown 中的所有标题行。
        
        匹配 #~###### 标题，返回列表:
        [{"level": int, "text": str, "raw": str, "line_idx": int}, ...]
        """
        headings = []
        for idx, line in enumerate(lines):
            match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if match:
                level = len(match.group(1))
                text = match.group(2).strip()
                headings.append({
                    "level": level,
                    "text": text,
                    "raw": line,
                    "line_idx": idx,
                })
        return headings
    
    # ========== Stage 2: 标题树构建 ==========
    
    def _build_heading_tree(
        self,
        headings: List[Dict[str, Any]],
        total_lines: int,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        构建标题树。
        
        算法:
        1. 计算每个标题的"区间结束位置"（下一个同级或更高级标题的行号）
        2. 使用栈构建父子关系
        
        Returns:
            (root_node, all_nodes) — 根节点和所有节点列表（含根）
        """
        n = len(headings)
        
        # 计算每个标题的区间结束位置
        # 对第 i 个标题，结束位置 = 第 j 个标题的行号，其中 j 是满足 level[j] <= level[i] 的最小 j > i
        end_line_indices = [total_lines] * n
        for i in range(n):
            for j in range(i + 1, n):
                if headings[j]["level"] <= headings[i]["level"]:
                    end_line_indices[i] = headings[j]["line_idx"]
                    break
        
        # 创建根节点（文档级，level=0）
        root = {
            "id": None,
            "level": 0,
            "text": "",
            "raw": "",
            "line_idx": -1,
            "end_line_idx": total_lines,
            "parent": None,
            "children": [],
            "paragraphs": [],  # 直接段落（字符串列表）
            "para_line_ranges": [],  # 每个段落的 [start_line, end_line)
        }
        
        # 构建树
        stack = [root]
        all_nodes = [root]
        
        for i, h in enumerate(headings):
            node = {
                "id": None,
                "level": h["level"],
                "text": h["text"],
                "raw": h["raw"],
                "line_idx": h["line_idx"],
                "end_line_idx": end_line_indices[i],
                "parent": None,
                "children": [],
                "paragraphs": [],
                "para_line_ranges": [],
            }
            
            # 找到父节点：最近的一个层级更小的节点
            while stack[-1]["level"] >= h["level"]:
                stack.pop()
            
            parent = stack[-1]
            node["parent"] = parent
            parent["children"].append(node)
            stack.append(node)
            all_nodes.append(node)
        
        return root, all_nodes
    
    # ========== Stage 3: 自然段分割与归属 ==========
    
    def _assign_paragraphs_to_nodes(
        self,
        root: Dict[str, Any],
        all_nodes: List[Dict[str, Any]],
        lines: List[str],
        full_text: str,
    ):
        """
        将 Markdown 内容按自然段分割，并归属到对应的最深层标题节点。
        
        算法:
        1. 对每个节点，计算其"直接内容区间"
           - 起始 = line_idx + 1
           - 结束 = min(end_line_idx, 第一个子标题的行号)
        2. 从直接内容区间提取文本，按 \n\n+ 分割为自然段
        3. 记录每个自然段的行号范围
        """
        for node in all_nodes:
            # 计算直接内容区间
            start_line = node["line_idx"] + 1
            end_line = node["end_line_idx"]
            
            # 如果节点有子节点，直接内容只到第一个子节点之前
            if node["children"]:
                first_child_line = min(child["line_idx"] for child in node["children"])
                end_line = min(end_line, first_child_line)
            
            if start_line >= end_line:
                continue
            
            # 提取直接内容文本
            content_lines = lines[start_line:end_line]
            content = "\n".join(content_lines)
            
            # LA-035-P21 FIX: 从原始内容提取图片引用，防止纯图片行被过滤后丢失
            # 纯图片段落（如 ![formula](path)）会被 _is_image_only_paragraph 过滤，
            # 但图片引用信息必须保留，供 ImageConceptExtractor 后续处理
            node["image_refs"] = self._extract_image_refs(content)
            
            # 按自然段分割
            paragraphs = self._split_to_paragraphs(content)
            
            # 计算每个自然段在原文件中的行号范围
            current_line = start_line
            for para in paragraphs:
                para_start_line = current_line
                # 找到该自然段在 content_lines 中的结束位置
                para_lines = para.split("\n")
                para_end_line = current_line + len(para_lines)
                
                node["paragraphs"].append(para)
                node["para_line_ranges"].append([para_start_line, para_end_line])
                
                # 更新 current_line（跳过自然段 + 空行）
                current_line = para_end_line
                while current_line < end_line and not lines[current_line].strip():
                    current_line += 1
    
    def _split_to_paragraphs(self, content: str) -> List[str]:
        """
        按自然段分割文本，并执行后处理优化。
        
        规则:
        - 分隔符: 一个或多个空行（\n\n+）
        - 每个自然段 strip() 处理
        - 过滤空字符串
        - 过滤纯图片引用行（LA-035: MinerU 会将图片提取为独立行）
        - 合并极短段落（< MIN_PARA_CHARS）到相邻段落
        - 如果自然段超过 MAX_PARA_CHARS，按句子边界切分
        
        Returns:
            优化后的段落列表
        """
        if not content.strip():
            return []
        
        # 按一个或多个空行分割
        raw_paras = [p.strip() for p in re.split(r'\n\s*\n', content) if p.strip()]
        
        # LA-035: Step 1 — 过滤纯图片引用行
        filtered_paras = []
        for para in raw_paras:
            # 如果段落只包含图片引用（无其他文本内容），跳过
            if self._is_image_only_paragraph(para):
                continue
            filtered_paras.append(para)
        
        # LA-035: Step 2 — 合并极短段落
        merged_paras = self._merge_short_paragraphs(filtered_paras)
        
        # Step 3 — 处理超长段落
        paragraphs = []
        for para in merged_paras:
            if len(para) > self.max_para_chars:
                sentences = self._split_to_sentences(para)
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) < self.max_para_chars:
                        current += sent
                    else:
                        if current.strip():
                            paragraphs.append(current.strip())
                        current = sent
                if current.strip():
                    paragraphs.append(current.strip())
            else:
                paragraphs.append(para)
        
        return paragraphs
    
    def _is_image_only_paragraph(self, para: str) -> bool:
        """
        判断段落是否只包含图片引用（无其他语义内容）。
        
        MinerU 输出的 Markdown 中，图片可能被提取为独立段落：
        ![](path/to/image.png)
        
        这些段落没有文本语义，应该被过滤（图片内容会在 image_pseudo chunk 中处理）。
        """
        # 移除所有 Markdown 图片引用
        text_without_images = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', para).strip()
        # 如果移除图片后为空或只剩空白，则认为是纯图片段落
        return not text_without_images
    
    def _merge_short_paragraphs(self, paragraphs: List[str]) -> List[str]:
        """
        合并极短段落（< MIN_PARA_CHARS）到相邻段落。
        
        合并方向判断策略（优先级从高到低）：
        1. 句末标点：以句号/问号/感叹号结尾 → 合并到下一段（作为开头补充）
        2. 连词开头：以"此外"/"但是"/"因此"等开头 → 合并到下一段（承接上文）
        3. 列表标记：以 "- "/"* "/"数字. " 开头 → 合并到上一段（列表延续）
        4. 位置优先：第一个段落 → 合并到下一段；最后一个段落 → 合并到上一段
        5. 默认：合并到上一段（中文阅读流自上而下）
        
        Args:
            paragraphs: 原始段落列表
            
        Returns:
            合并后的段落列表
        """
        if not paragraphs:
            return []
        
        result = []
        i = 0
        while i < len(paragraphs):
            para = paragraphs[i]
            
            # 如果段落长度 >= 阈值，直接保留
            if len(para) >= self.min_para_chars:
                result.append(para)
                i += 1
                continue
            
            # 极短段落，需要合并
            # 判断合并方向
            merge_direction = self._determine_merge_direction(
                para, i, len(paragraphs), result[-1] if result else None, paragraphs[i + 1] if i + 1 < len(paragraphs) else None
            )
            
            if merge_direction == "forward" and i + 1 < len(paragraphs):
                # 合并到下一段
                paragraphs[i + 1] = para + "\n" + paragraphs[i + 1]
                i += 1  # 跳过当前段落（已合并到下一段）
            elif merge_direction == "backward" and result:
                # 合并到上一段
                result[-1] = result[-1] + "\n" + para
                i += 1
            else:
                # 无法合并，保留（作为独立段落）
                result.append(para)
                i += 1
        
        return result
    
    def _determine_merge_direction(
        self,
        para: str,
        index: int,
        total: int,
        prev_para: Optional[str],
        next_para: Optional[str],
    ) -> str:
        """
        判断极短段落的合并方向。
        
        Returns:
            "forward" — 合并到下一段
            "backward" — 合并到上一段
            "keep" — 无法合并，保持独立
        """
        # 规则 1：句末标点检查
        # 如果短段落以句号/问号/感叹号结尾，可能是上一句的结尾，应合并到下一段作为开头补充
        if re.search(r'[。！？\.\!\?]$', para.strip()):
            # 但如果这是最后一个段落，只能合并到上一段
            if index == total - 1:
                return "backward" if prev_para else "keep"
            return "forward"
        
        # 规则 2：连词开头检查
        # 如果以"此外"/"但是"/"因此"等开头，说明是承接上文，应合并到下一段
        para_start = para.strip()[:10]  # 取前10个字符判断
        for marker in self.MERGE_FORWARD_MARKERS:
            if para_start.startswith(marker):
                if index == total - 1:
                    return "backward" if prev_para else "keep"
                return "forward"
        
        # 规则 3：列表标记检查
        # 如果以列表标记开头，说明是列表延续，应合并到上一段
        if re.match(r'^\s*[-\*•]\s', para) or re.match(r'^\s*\d+[\.\)]\s', para):
            return "backward" if prev_para else "keep"
        
        # 规则 4：位置优先
        # 第一个段落 → 合并到下一段
        if index == 0:
            return "forward" if next_para else "keep"
        
        # 最后一个段落 → 合并到上一段
        if index == total - 1:
            return "backward" if prev_para else "keep"
        
        # 规则 5：默认合并到上一段（中文阅读流自上而下）
        return "backward" if prev_para else "keep"
    
    def _split_to_sentences(self, text: str) -> List[str]:
        """
        按句子边界分割文本。
        
        支持中英文句子边界:
        - 中文: 。！？；
        - 英文: .!?
        """
        # 使用正则匹配句子结束符，保留结束符
        pattern = r'[^。！？；.!?]*[。！？；.!?]+'
        sentences = re.findall(pattern, text)
        
        # 处理没有结束符的剩余文本
        remaining = re.sub(pattern, '', text)
        if remaining.strip():
            sentences.append(remaining.strip())
        
        return sentences
    
    # ========== Stage 4: Chunk 生成 ==========
    
    def _generate_chunks(
        self,
        root: Dict[str, Any],
        all_nodes: List[Dict[str, Any]],
        source_metadata: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        将标题树节点转换为标准 chunk 列表。
        
        输出顺序:
        1. DocumentChunk（根，如果有前言段落）
        2. 按文档顺序遍历树: HeadingChunk → 其 ParagraphChunks → 子 HeadingChunks → ...
        """
        source_name = source_metadata.get("source", "unknown")
        safe_name = re.sub(r'[^\w\-_.]', '_', Path(source_name).stem)[:20]
        
        chunks = []
        chunk_id_map = {}  # node -> chunk_id
        
        # 为每个节点生成 ID
        heading_counters = {}  # level -> counter
        para_counter = [0]
        
        for node in all_nodes:
            if node["level"] == 0:
                # 文档根
                hint = f"doc_{safe_name}"
                node["id"] = self._generate_chunk_id(safe_name, "doc", 0, hint)
            else:
                # 标题节点
                level = node["level"]
                heading_counters[level] = heading_counters.get(level, 0) + 1
                idx = heading_counters[level] - 1
                hint = f"h{level}_{node['text'][:30]}"
                node["id"] = self._generate_chunk_id(safe_name, f"h{level}", idx, hint)
        
        # 先为所有段落节点生成 ID（它们会被挂在 HeadingChunk 下）
        para_ids = {}  # (node_idx, para_idx) -> para_id
        for node in all_nodes:
            for pidx, para in enumerate(node["paragraphs"]):
                para_counter[0] += 1
                hint = f"p{para_counter[0]}_{para[:30]}"
                para_id = self._generate_chunk_id(safe_name, "p", para_counter[0], hint)
                para_ids[(id(node), pidx)] = para_id
        
        # 按文档顺序生成 chunk（前序遍历）
        def traverse(node):
            # 生成 HeadingChunk / DocumentChunk
            chunk_type = "document" if node["level"] == 0 else "heading"
            heading_path = self._build_heading_path(node)
            
            # 构建 text: 标题行 + 直接段落
            if node["level"] == 0:
                text = "\n\n".join(node["paragraphs"]) if node["paragraphs"] else ""
            else:
                parts = [node["raw"]]
                parts.extend(node["paragraphs"])
                text = "\n\n".join(parts)
            
            # 子节点 IDs
            child_ids = [child["id"] for child in node["children"]]
            
            # 段落 IDs
            paragraph_ids = [para_ids[(id(node), pidx)] for pidx in range(len(node["paragraphs"]))]
            
            # 提取图片引用
            # LA-035-P21 FIX: 从节点预先提取的原始图片引用读取（防止纯图片行被过滤后丢失）
            # 同时兼容从段落提取的旧逻辑
            image_refs = list(node.get("image_refs", []))
            for para in node["paragraphs"]:
                image_refs.extend(self._extract_image_refs(para))
            
            # 去重（基于 path）
            seen_paths = set()
            deduped_refs = []
            for ref in image_refs:
                path = ref.get("path", "")
                if path and path not in seen_paths:
                    seen_paths.add(path)
                    deduped_refs.append(ref)
            image_refs = deduped_refs
            
            # 检测公式和表格
            all_para_text = "\n".join(node["paragraphs"])
            formula_count = self._count_formulas(all_para_text)
            table_lines = self._count_table_lines(all_para_text)
            
            # LA-035-P21 FIX: 提取公式为 media_refs，供 SemanticExtractor 识别
            heading_formulas = self._extract_formulas(all_para_text)
            heading_media_refs = self._build_media_refs(image_refs, heading_formulas)
            
            chunk = {
                "id": node["id"],
                "text": text,
                "metadata": {
                    **source_metadata,
                    "chunk_type": chunk_type,
                    "heading_path": heading_path,
                    "heading_level": node["level"],
                    "parent_id": node["parent"]["id"] if node["parent"] else None,
                    "child_ids": child_ids,
                    "paragraph_ids": paragraph_ids,
                    "line_range": [node["line_idx"], node["end_line_idx"]],
                    "image_refs": image_refs,
                    "media_refs": heading_media_refs,
                    "formula_count": formula_count,
                    "table_lines": table_lines,
                },
                "source": source_name,
            }
            chunks.append(chunk)
            
            # 生成 ParagraphChunks（紧跟在父 HeadingChunk 后面）
            for pidx, para in enumerate(node["paragraphs"]):
                para_id = para_ids[(id(node), pidx)]
                para_image_refs = self._extract_image_refs(para)
                
                # LA-035-P21 FIX: 提取段落中的公式为 media_refs
                para_formulas = self._extract_formulas(para)
                para_media_refs = self._build_media_refs(para_image_refs, para_formulas)
                
                para_chunk = {
                    "id": para_id,
                    "text": para,
                    "metadata": {
                        **source_metadata,
                        "chunk_type": "paragraph",
                        "heading_path": heading_path,
                        "heading_level": node["level"],
                        "parent_id": node["id"],
                        "paragraph_index": pidx,
                        "line_range": node["para_line_ranges"][pidx] if pidx < len(node["para_line_ranges"]) else [0, 0],
                        "image_refs": para_image_refs,
                        "media_refs": para_media_refs,
                        "formula_count": self._count_formulas(para),
                        "table_lines": self._count_table_lines(para),
                    },
                    "source": source_name,
                }
                chunks.append(para_chunk)
            
            # 递归遍历子节点
            for child in node["children"]:
                traverse(child)
        
        traverse(root)
        
        # 过滤掉空的 DocumentChunk（如果没有前言段落且没有子节点）
        if chunks and chunks[0]["metadata"]["chunk_type"] == "document":
            doc_chunk = chunks[0]
            if not doc_chunk["text"] and not doc_chunk["metadata"].get("child_ids"):
                chunks = chunks[1:]  # 移除空的文档根
            elif not doc_chunk["text"]:
                # 有子节点但无前言，保留文档根但标记
                doc_chunk["text"] = f"[文档: {source_name}]"
        
        return chunks
    
    def _build_heading_path(self, node: Dict[str, Any]) -> str:
        """
        构建标题路径：从根到当前标题的文本链。
        
        示例: "一级标题 > 二级标题 > 三级标题"
        """
        parts = []
        current = node
        while current and current["level"] > 0:
            if current["text"]:
                parts.append(current["text"])
            current = current["parent"]
        
        parts.reverse()
        return " > ".join(parts) if parts else ""
    
    def _extract_image_refs(self, text: str) -> List[Dict[str, Any]]:
        """从文本中提取 Markdown 图片引用。"""
        refs = []
        for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', text):
            refs.append({
                "alt": match.group(1),
                "path": match.group(2),
            })
        return refs
    
    def _count_formulas(self, text: str) -> int:
        """统计文本中的公式数量（LaTeX 行内 + 块级）。"""
        block = len(re.findall(r'\$\$(.*?)\$\$', text, re.DOTALL))
        inline = len(re.findall(r'(?<!\$)\$(?!\$)([^\$]+)\$(?!\$)', text))
        return block + inline
    
    def _extract_formulas(self, text: str) -> List[Dict[str, Any]]:
        """
        从文本中提取 LaTeX 公式，返回 media_refs 格式列表。
        
        支持的格式:
        - 块级公式: $$...$$
        - 行内公式: $...$ (不包含 $$)
        
        Returns:
            [{"type": "formula", "latex": str, "display": "block"|"inline"}, ...]
        """
        formulas = []
        # 块级公式 $$...$$
        for match in re.finditer(r'\$\$(.*?)\$\$', text, re.DOTALL):
            formulas.append({
                "type": "formula",
                "latex": match.group(1).strip(),
                "display": "block",
            })
        # 行内公式 $...$ — 使用负向回顾/前瞻避免匹配 $$
        for match in re.finditer(r'(?<!\$)\$(?!\$)([^\$]+)\$(?!\$)', text):
            formulas.append({
                "type": "formula",
                "latex": match.group(1).strip(),
                "display": "inline",
            })
        return formulas
    
    def _build_media_refs(self, image_refs: List[Dict[str, Any]], formulas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将图片引用和公式合并为统一的 media_refs 列表。
        
        Args:
            image_refs: _extract_image_refs 返回的列表
            formulas: _extract_formulas 返回的列表
        
        Returns:
            统一的 media_refs，供 SemanticExtractor.media_context 使用
        """
        media_refs = []
        for ref in image_refs:
            media_refs.append({
                "type": ref.get("type", "image"),
                "path": ref.get("path", ""),
                "caption": ref.get("alt", ""),
            })
        media_refs.extend(formulas)
        return media_refs
    
    def _count_table_lines(self, text: str) -> int:
        """统计文本中的 Markdown 表格行数。"""
        return len([l for l in text.split("\n") if l.strip().startswith("|")])
    
    def _generate_chunk_id(self, source_name: str, chunk_type: str, index: int, content_hint: str) -> str:
        """生成唯一 chunk ID。"""
        hint_hash = hashlib.md5(content_hint.encode()).hexdigest()[:6]
        return f"md_{source_name}_{chunk_type}_{index}_{hint_hash}"


# ========== 便捷函数 ==========

def chunk_markdown_to_standard(
    markdown_text: str,
    source_metadata: Dict[str, Any],
    max_para_chars: int = 4000,
    min_para_chars: int = 50,
) -> List[Dict[str, Any]]:
    """
    一键将 Markdown 转换为标准 chunk 列表。
    
    用于与现有 pipeline 兼容。
    
    Args:
        min_para_chars: 极短段落合并阈值（小于此值尝试合并到相邻段落，默认 50）
    """
    chunker = MarkdownChunker(max_para_chars=max_para_chars, min_para_chars=min_para_chars)
    return chunker.chunk_markdown(markdown_text, source_metadata)


# ========== 向后兼容的 v1.0 接口 ==========

def chunk_markdown_v1_compat(
    markdown_text: str,
    source_metadata: Dict[str, Any],
    max_para_chars: int = 4000,
    min_para_chars: int = 50,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    v1.0 兼容接口：返回 (parent_chunks, child_chunks) 元组。
    
    用于兼容旧的调用代码（如未更新的 mineru_client.py）。
    
    Returns:
        (heading_chunks, paragraph_chunks) — 模拟 v1.0 的 parent/child 结构
    """
    chunker = MarkdownChunker(max_para_chars=max_para_chars, min_para_chars=min_para_chars)
    chunks = chunker.chunk_markdown(markdown_text, source_metadata)
    
    heading_chunks = [c for c in chunks if c["metadata"]["chunk_type"] in ("heading", "document")]
    paragraph_chunks = [c for c in chunks if c["metadata"]["chunk_type"] == "paragraph"]
    
    return heading_chunks, paragraph_chunks
