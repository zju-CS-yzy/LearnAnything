"""
文档分块策略
支持 Markdown 标题分块、固定长度分块、学科专用分块、Parent-Child 双层分块
"""

import re
import hashlib
from typing import List, Dict, Any, Tuple


class ChunkingStrategy:
    """分块策略基类"""

    def chunk(self, text: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """分块接口，返回 [{"text": str, "metadata": dict}]"""
        raise NotImplementedError


class MarkdownHeaderChunker(ChunkingStrategy):
    """
    Markdown 标题分块器。
    按 # 和 ## 标题分割，保留标题路径作为上下文。
    """

    def __init__(self, max_chunk_size: int = 3000, min_chunk_size: int = 100, overlap: int = 200):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap = overlap

    def chunk(self, text: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        metadata = metadata or {}
        source = metadata.get("source", "")

        # 移除 YAML front matter
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                text = parts[2]

        chunks = []
        lines = text.split("\n")
        current_chunk = ""
        header_path = ""
        current_level = 0
        paragraph_buffer = []

        for line in lines:
            header_match = re.match(r"^(#{1,3})\s+(.+)$", line)
            if header_match:
                # 提交段落缓冲区
                if paragraph_buffer:
                    current_chunk += "\n".join(paragraph_buffer) + "\n"
                    paragraph_buffer = []

                level = len(header_match.group(1))
                title = header_match.group(2).strip()

                if level <= 2:
                    # 标题层级分块
                    if len(current_chunk.strip()) >= self.min_chunk_size:
                        chunks.append(self._make_chunk(current_chunk, header_path, source, current_level))
                    current_chunk = ""
                    header_path = title
                    current_level = level
                else:
                    # 三级标题在块内
                    if len(current_chunk.strip()) >= self.max_chunk_size:
                        chunks.append(self._make_chunk(current_chunk, header_path, source, current_level))
                        current_chunk = title + "\n"
                    else:
                        current_chunk += title + "\n"
            else:
                paragraph_buffer.append(line)
                if line.strip() == "" or len("\n".join(paragraph_buffer)) > 500:
                    current_chunk += "\n".join(paragraph_buffer) + "\n"
                    paragraph_buffer = []
                    if len(current_chunk.strip()) >= self.max_chunk_size:
                        chunks.append(self._make_chunk(current_chunk, header_path, source, current_level))
                        current_chunk = ""

        # 提交剩余内容
        if paragraph_buffer:
            current_chunk += "\n".join(paragraph_buffer) + "\n"
        if len(current_chunk.strip()) >= self.min_chunk_size:
            chunks.append(self._make_chunk(current_chunk, header_path, source, current_level))

        return chunks

    def _make_chunk(self, text: str, header_path: str, source: str, level: int) -> Dict[str, Any]:
        return {
            "text": (header_path + "\n" + text).strip() if header_path else text.strip(),
            "metadata": {
                "source": source,
                "header_path": header_path,
                "level": level,
                "type": "markdown",
            },
        }


class FallbackChunker(ChunkingStrategy):
    """
    回退分块器：固定长度分块，保留段落边界。
    """

    def __init__(self, chunk_size: int = 1500, overlap: int = 200, min_chunk_size: int = 100):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size

    def chunk(self, text: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        metadata = metadata or {}
        source = metadata.get("source", "")
        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + self.chunk_size, text_len)
            if end < text_len:
                # 在句子边界截断
                for sep in ["\n\n", "\n", "。", "．", ". ", "? ", "! ", "；", ";"]:
                    pos = text.rfind(sep, start + self.chunk_size // 2, end)
                    if pos != -1:
                        end = pos + len(sep)
                        break

            chunk = text[start:end].strip()
            if len(chunk) >= self.min_chunk_size:
                chunks.append({
                    "text": f"[文档: {source}]\n{chunk}" if source else chunk,
                    "metadata": {
                        "source": source,
                        "type": "fallback",
                        "level": 0,
                    },
                })

            if end >= text_len:
                break
            start = end - self.overlap

        return chunks


# ==================== 语义解析与合并（复用 IWork 逻辑） ====================

def parse_page_sections(text: str) -> List[Tuple[List[str], str, str, int]]:
    """
    按文本结构解析段落/语义块。
    
    复用 IWork 项目 rebuild_semantic_chunks.py 的 parse_markdown_sections 逻辑，
    适配为通用文本解析（不限于 Markdown）。
    
    返回: [(heading_path, content, block_type, heading_level)]
    block_type: heading, paragraph, code_block, list, table
    heading_level: 标题层级（1-6），非标题为 0
    """
    lines = text.split('\n')
    sections = []
    current_heading = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        heading_level = 0
        
        # 标题检测（支持 Markdown 和常见标题格式）
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if not heading_match:
            # 尝试检测 "1. 标题" 或 "一、标题" 这类格式
            heading_match = re.match(r'^(\d+\.\s+|\d+\.\s*[\d\.]+\s+|第[一二三四五六七八九十\d]+[章节篇]\s+|\([\d一二三四五六七八九十]+\)\s+|[一二三四五六七八九十]+[、．]\s*)(.+)$', line)
        
        if heading_match:
            if len(heading_match.groups()) >= 2:
                title = heading_match.group(2).strip()
                level = len(heading_match.group(1)) if heading_match.group(1).startswith('#') else 2
            else:
                title = line.strip()
                level = 2
            heading_level = level
            # 更新当前标题路径
            while len(current_heading) >= level:
                current_heading.pop()
            current_heading.append(title)
            sections.append((
                list(current_heading),
                title,
                "heading",
                heading_level
            ))
            i += 1
            continue
        
        # 代码块检测
        if line.startswith('```') or line.startswith('    '):
            code_lines = []
            lang = line[3:].strip() if line.startswith('```') else "indent"
            i += 1
            while i < len(lines):
                if line.startswith('```') and lines[i].startswith('```'):
                    break
                if not line.startswith('```') and not lines[i].startswith('    '):
                    break
                code_lines.append(lines[i])
                i += 1
            code_content = '\n'.join(code_lines)
            if code_content.strip():
                sections.append((
                    list(current_heading),
                    f"[代码块: {lang}]\n{code_content}",
                    "code_block",
                    0
                ))
            if line.startswith('```'):
                i += 1  # 跳过 ```
            continue
        
        # 列表检测
        if re.match(r'^(\s*[-*+]\s|\s*\d+\.\s)', line):
            list_lines = [line]
            i += 1
            while i < len(lines):
                if lines[i].strip() == '' or lines[i].startswith('#') or lines[i].startswith('```'):
                    break
                # 列表续行: 缩进或空行后缩进
                if re.match(r'^(\s*[-*+]\s|\s*\d+\.\s|\s+\S)', lines[i]):
                    list_lines.append(lines[i])
                    i += 1
                else:
                    break
            list_content = '\n'.join(list_lines)
            if list_content.strip():
                sections.append((
                    list(current_heading),
                    list_content,
                    "list",
                    0
                ))
            continue
        
        # 表格检测（Markdown 表格格式）
        if '|' in line:
            table_lines = [line]
            i += 1
            while i < len(lines) and '|' in lines[i]:
                table_lines.append(lines[i])
                i += 1
            table_content = '\n'.join(table_lines)
            if table_content.strip():
                sections.append((
                    list(current_heading),
                    table_content,
                    "table",
                    0
                ))
            continue
        
        # 普通段落 - 合并连续非空行
        if line.strip():
            para_lines = [line]
            i += 1
            while i < len(lines):
                if lines[i].strip() == '' or lines[i].startswith('#') or lines[i].startswith('```'):
                    break
                para_lines.append(lines[i])
                i += 1
            para_content = '\n'.join(para_lines)
            if para_content.strip():
                sections.append((
                    list(current_heading),
                    para_content,
                    "paragraph",
                    0
                ))
            continue
        
        i += 1
    
    return sections


def merge_sections_to_chunks(sections, max_chunk_size: int = 1000, min_chunk_size: int = 50) -> List[Dict[str, Any]]:
    """
    将语义块合并为检索 chunk。
    
    复用 IWork 项目 chunk_sections 逻辑：
    - 同标题下的连续块合并，不超过 max_chunk_size
    - 代码块/表格/列表保持完整（即使超过 max_chunk_size 也不切）
    - 每个 chunk 包含上下文路径（标题路径）
    - **跨章节边界强制分块**：遇到一级标题（level=1）时，当前 chunk 立即终止
    """
    chunks = []
    chunk_id = 0
    
    i = 0
    while i < len(sections):
        heading_path, content, btype, heading_level = sections[i]
        
        # 标题本身：不单独建 chunk（作为上下文路径使用）
        if btype == "heading":
            i += 1
            continue
        
        # 代码块/表格/列表: 保持完整
        if btype in ("code_block", "table", "list"):
            prefix = ' > '.join(heading_path) if heading_path else ""
            full_text = f"[上下文: {prefix}]\n{content}" if prefix else content
            
            chunk_id += 1
            chunks.append({
                "chunk_id": chunk_id,
                "heading_path": heading_path,
                "content": content,
                "type": btype,
                "text": full_text,
                "size": len(full_text),
            })
            i += 1
            continue
        
        # 段落: 合并同标题下连续段落，直到接近 max_chunk_size
        # 或遇到章节边界（heading）
        current_chunks_content = [content]
        current_size = len(content)
        j = i + 1
        
        while j < len(sections):
            h2, c2, t2, hl2 = sections[j]
            
            # 遇到 heading 立即终止合并（章节边界）
            if t2 == "heading":
                break
            
            # heading_path 不同，停止合并（标题层级变化）
            if h2 != heading_path:
                break
            
            # 遇到独立块，停止合并
            if t2 in ("code_block", "table", "list"):
                break
            
            # 超过最大 chunk 大小，停止合并
            if current_size + len(c2) > max_chunk_size:
                break
            
            current_chunks_content.append(c2)
            current_size += len(c2) + 1
            j += 1
        
        merged = '\n'.join(current_chunks_content)
        prefix = ' > '.join(heading_path) if heading_path else ""
        full_text = f"[上下文: {prefix}]\n{merged}" if prefix else merged
        
        # 如果合并后太小，跳过（避免超小块污染检索）
        if len(full_text.strip()) < min_chunk_size:
            i = j
            continue
        
        chunk_id += 1
        chunks.append({
            "chunk_id": chunk_id,
            "heading_path": heading_path,
            "content": merged,
            "type": "paragraph_group",
            "text": full_text,
            "size": len(full_text),
        })
        
        i = j
    
    return chunks


# ==================== Parent-Child 双层分块器 ====================

class ParentChildChunker(ChunkingStrategy):
    """
    Parent-Child 双层分块器。
    
    **核心设计**：先全局分 Child（段落级语义块），再按页码聚合 Parent（页面级上下文）。
    
    这解决了传统"先分页再分段"方案中跨页段落被切断的问题：
    - 如果一个段落跨第1页末尾和第2页开头，它会被识别为同一个 Child chunk
    - 该 Child 的 page_numbers 会同时包含 [1, 2]
    - 第1页和第2页的 Parent 都会引用这个 Child
    
    使用方式:
        # 单页/单文件
        chunker = ParentChildChunker(max_child_size=1000, min_child_size=50)
        parent, children = chunker.chunk_page(page_text, metadata={"page_number": 1, "source": "doc.pdf"})
        
        # 多页文档（推荐用于 PDF）
        pages = [
            {"text": "第1页文本...", "metadata": {"page_number": 1, "source": "doc.pdf"}},
            {"text": "第2页文本...", "metadata": {"page_number": 2, "source": "doc.pdf"}},
        ]
        parents, children = chunker.chunk_document(pages, document_name="doc.pdf")
    """

    def __init__(self, max_child_size: int = 1000, min_child_size: int = 50, overlap: int = 100):
        self.max_child_size = max_child_size
        self.min_child_size = min_child_size
        self.overlap = overlap

    def chunk(self, text: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        统一分块接口（单层调用）。
        对于 Parent-Child 场景，建议直接使用 chunk_page 或 chunk_document 方法。
        """
        metadata = metadata or {}
        source = metadata.get("source", "")
        page_number = metadata.get("page_number", 0)
        
        # 先按语义解析段落
        sections = parse_page_sections(text)
        if not sections:
            # 无结构化内容，回退到固定长度分块
            fallback = FallbackChunker(self.max_child_size, self.overlap, self.min_child_size)
            return fallback.chunk(text, metadata)
        
        # 合并为语义 chunk
        child_chunks = merge_sections_to_chunks(
            sections, 
            max_chunk_size=self.max_child_size, 
            min_chunk_size=self.min_child_size
        )
        
        # 统一输出格式（单层模式，保留页码信息）
        result = []
        for c in child_chunks:
            result.append({
                "text": c["text"],
                "metadata": {
                    "source": source,
                    "page_number": page_number,
                    "chunk_type": c["type"],
                    "heading_path": ' > '.join(c["heading_path"]) if c["heading_path"] else "",
                    "type": "semantic_child",
                },
            })
        return result

    def chunk_page(self, text: str, metadata: Dict[str, Any] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        单页 Parent-Child 双层分块（兼容旧接口）。
        
        对于单页场景，先分 Child 再建 Parent 与先建 Parent 再分 Child 效果等价。
        内部调用 chunk_document 实现统一逻辑。
        """
        metadata = metadata or {}
        pages = [{"text": text, "metadata": metadata}]
        document_name = metadata.get("document_name", metadata.get("source", "doc"))
        
        parents, children = self.chunk_document(pages, document_name=document_name)
        
        if parents and children:
            return parents[0], children
        elif parents:
            return parents[0], []
        else:
            # 空内容，返回空 Parent + 空 Children
            empty_parent = {
                "id": f"parent_{hashlib.md5(document_name.encode()).hexdigest()[:12]}",
                "text": "",
                "metadata": {
                    "source": metadata.get("source", ""),
                    "document_name": document_name,
                    "page_number": metadata.get("page_number", 1),
                    "chunk_type": "parent_page",
                    "type": "parent",
                    "child_count": 0,
                },
            }
            return empty_parent, []

    def chunk_document(self, pages: List[Dict[str, Any]], document_name: str = "") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        多页文档 Parent-Child 双层分块（推荐用于 PDF）。
        
        **核心逻辑**：
        1. 合并所有页面文本，在每页之间插入页码标记 `<!--PAGE:N-->`
        2. 全局解析 section（跨页段落会被识别为一个整体）
        3. 全局合并为 Child chunks
        4. 解析每个 Child 的页码标记，确定来源页码
        5. 按页码分组建立 Parent chunks
        
        Args:
            pages: [{"text": str, "metadata": {"page_number": int, "source": str}}, ...]
            document_name: 文档名称
        
        Returns:
            (parent_chunks, child_chunks)
        """
        if not pages:
            return [], []
        
        # 获取文档名
        if not document_name:
            document_name = pages[0].get("metadata", {}).get("source", "doc")
        
        # === Step 1: 合并所有页面文本，插入页码标记 ===
        full_text_parts = []
        page_number_map = {}  # 记录每个页码标记在合并文本中的位置
        
        for page in pages:
            page_text = page.get("text", "")
            page_num = page.get("metadata", {}).get("page_number", 1)
            source = page.get("metadata", {}).get("source", "")
            
            if not page_text.strip():
                continue
            
            # 插入页码标记（用于后续解析 Child 的来源页码）
            marker = f"\n\n<!--PAGE:{page_num}-->\n\n"
            page_number_map[page_num] = len("".join(full_text_parts)) + len(marker)
            full_text_parts.append(marker + page_text)
        
        full_text = "".join(full_text_parts)
        
        if not full_text.strip():
            return [], []
        
        # === Step 2: 全局解析 section（跨页段落会被识别为一个整体）===
        sections = parse_page_sections(full_text)
        
        if not sections:
            # 无结构化内容，回退到固定长度分块
            fallback = FallbackChunker(self.max_child_size, self.overlap, self.min_child_size)
            fallback_chunks = fallback.chunk(full_text, {"source": document_name})
            
            # 包装为 Parent-Child 格式（单页情况）
            parent_id = f"parent_{hashlib.md5(f'{document_name}_fallback'.encode()).hexdigest()[:12]}"
            parent = {
                "id": parent_id,
                "text": full_text.strip(),
                "metadata": {
                    "source": document_name,
                    "document_name": document_name,
                    "page_numbers": list(page_number_map.keys()),
                    "chunk_type": "parent_page",
                    "type": "parent",
                    "child_count": len(fallback_chunks),
                },
            }
            
            children = []
            for i, c in enumerate(fallback_chunks):
                child_id = f"{parent_id}_child_{i:04d}"
                # 解析该 Child 的页码
                child_page_nums = self._extract_page_numbers(c["text"])
                children.append({
                    "id": child_id,
                    "text": c["text"],
                    "metadata": {
                        "source": document_name,
                        "document_name": document_name,
                        "page_numbers": child_page_nums if child_page_nums else [1],
                        "parent_id": parent_id,
                        "chunk_type": "fallback_child",
                        "type": "child",
                    },
                })
            
            return [parent], children
        
        # === Step 3: 全局合并为 Child chunks ===
        child_chunks_raw = merge_sections_to_chunks(
            sections,
            max_chunk_size=self.max_child_size,
            min_chunk_size=self.min_child_size
        )
        
        # === Step 4: 为每个 Child 确定页码，移除页码标记 ===
        children = []
        for i, c in enumerate(child_chunks_raw):
            child_id = f"child_{hashlib.md5(f'{document_name}_{i}'.encode()).hexdigest()[:12]}"
            
            # 解析页码标记
            page_nums = self._extract_page_numbers(c["text"])
            
            # 移除页码标记，清理文本
            clean_text = self._remove_page_markers(c["text"])
            
            children.append({
                "id": child_id,
                "text": clean_text,
                "metadata": {
                    "source": document_name,
                    "document_name": document_name,
                    "page_numbers": page_nums if page_nums else [1],
                    "chunk_type": c["type"],
                    "heading_path": ' > '.join(c["heading_path"]) if c["heading_path"] else "",
                    "type": "child",
                },
            })
        
        # === Step 5: 按页码分组建立 Parent chunks ===
        # 每个页码对应一个 Parent，包含该页的所有 Child
        all_page_nums = sorted(page_number_map.keys())
        
        parents = []
        for page_num in all_page_nums:
            parent_id = f"parent_{hashlib.md5(f'{document_name}_page_{page_num}'.encode()).hexdigest()[:12]}"
            
            # 找到属于该页的所有 Child（Child 的 page_numbers 包含该页）
            page_children = [c for c in children if page_num in c["metadata"].get("page_numbers", [])]
            
            # Parent 的文本是该页原始内容（从 page 中提取）
            page_text = ""
            for page in pages:
                if page.get("metadata", {}).get("page_number") == page_num:
                    page_text = page.get("text", "")
                    break
            
            parents.append({
                "id": parent_id,
                "text": page_text.strip(),
                "metadata": {
                    "source": document_name,
                    "document_name": document_name,
                    "page_number": page_num,
                    "page_numbers": [page_num],
                    "chunk_type": "parent_page",
                    "type": "parent",
                    "child_count": len(page_children),
                },
            })
            
            # 更新 Child 的 parent_id
            for c in page_children:
                # 一个 Child 可能跨多页，需要关联到所有相关 Parent
                existing_parents = c["metadata"].get("parent_ids", [])
                if parent_id not in existing_parents:
                    existing_parents.append(parent_id)
                c["metadata"]["parent_ids"] = existing_parents
                # 保留第一个 parent_id 作为主引用
                if "parent_id" not in c["metadata"]:
                    c["metadata"]["parent_id"] = parent_id
        
        return parents, children
    
    def _extract_page_numbers(self, text: str) -> List[int]:
        """从文本中提取页码标记 `<!--PAGE:N-->`，返回页码列表"""
        matches = re.findall(r'<!--PAGE:(\d+)-->', text)
        page_nums = sorted(set(int(m) for m in matches))
        return page_nums
    
    def _remove_page_markers(self, text: str) -> str:
        """移除文本中的页码标记 `<!--PAGE:N-->`"""
        return re.sub(r'\n*<!--PAGE:\d+-->\n*', '\n\n', text).strip()


class DocumentChunker:
    """
    文档分块统一入口。
    先尝试 Markdown 标题分块，失败时回退到固定长度分块。
    支持 Parent-Child 双层分块模式。
    """

    def __init__(self, max_chunk_size: int = 3000, min_chunk_size: int = 100, overlap: int = 200):
        self.markdown_chunker = MarkdownHeaderChunker(max_chunk_size, min_chunk_size, overlap)
        self.fallback_chunker = FallbackChunker(max_chunk_size, overlap, min_chunk_size)
        self.parent_child_chunker = ParentChildChunker(max_chunk_size, min_chunk_size, overlap)

    def chunk(self, text: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """分块入口（单层模式），返回 [{"text": str, "metadata": dict}]"""
        # 先尝试 Markdown 分块
        chunks = self.markdown_chunker.chunk(text, metadata)
        # 如果 Markdown 分块为空或结果太少，回退到固定长度分块
        if not chunks or (len(text) > 1000 and len(chunks) < 2):
            chunks = self.fallback_chunker.chunk(text, metadata)
        return chunks
    
    def chunk_page(self, text: str, metadata: Dict[str, Any] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Parent-Child 双层分块入口（单页）。
        
        返回: (parent_chunk, child_chunks)
        - parent_chunk: 整页文本，用于引用溯源
        - child_chunks: 页内语义分块，用于精确检索
        """
        return self.parent_child_chunker.chunk_page(text, metadata)
    
    def chunk_document(self, pages: List[Dict[str, Any]], document_name: str = "") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Parent-Child 双层分块入口（多页文档，推荐用于 PDF）。
        
        返回: (parent_chunks, child_chunks)
        - parent_chunks: 每页一个，用于引用溯源
        - child_chunks: 全局语义分块，用于精确检索（支持跨页段落）
        """
        return self.parent_child_chunker.chunk_document(pages, document_name=document_name)
