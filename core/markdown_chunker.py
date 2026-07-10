"""
Markdown 分块器 (MarkdownChunker)
基于 Markdown 标题层级进行树形分块，替代/补充 DocumentChunker。

与 DocumentChunker 的区别:
    - DocumentChunker: 基于页面和段落长度分块（适合 PyMuPDF 纯文本）
    - MarkdownChunker: 基于 Markdown 标题层级分块（适合 MinerU 结构化输出）

分块策略:
    Level 1 (TitleChunk): 按 ## 二级标题分割 → 主题概念聚合单元
    Level 2 (ParagraphChunk): 在 TitleChunk 内按段落/### 分割 → 细粒度概念提取单元

使用方式:
    from core.markdown_chunker import MarkdownChunker
    
    chunker = MarkdownChunker()
    parent_chunks, child_chunks = chunker.chunk_markdown(
        markdown_text=md_text,
        source_metadata={"source": "doc.pdf", "subject": "generic"}
    )
"""

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class MarkdownChunker:
    """
    Markdown 树形分块器。
    
    将结构化 Markdown 按标题层级分割为多层 chunk，支持语义聚合。
    """
    
    # 分块配置
    MAX_CHUNK_CHARS = 2000      # L2 ParagraphChunk 最大字符数
    MIN_CHUNK_CHARS = 100       # L2 ParagraphChunk 最小字符数
    OVERLAP_CHARS = 100         # 相邻 chunk 重叠字符数
    
    def __init__(self, max_chunk_chars: int = 2000, overlap_chars: int = 100):
        self.max_chunk_chars = max_chunk_chars
        self.overlap_chars = overlap_chars
    
    def chunk_markdown(
        self,
        markdown_text: str,
        source_metadata: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        将 Markdown 文本分块为 Parent (TitleChunk) + Child (ParagraphChunk)。
        
        Args:
            markdown_text: MinerU 输出的 Markdown 文本
            source_metadata: 基础元数据（source, subject, raw_path 等）
        
        Returns:
            (parent_chunks, child_chunks)
            
            parent_chunks: TitleChunk 列表（按 ## 分割）
            child_chunks: ParagraphChunk 列表（在 TitleChunk 内按段落分割）
        
        输出格式:
            parent_chunk = {
                "id": str,
                "text": str,           # 标题 + 该标题下所有内容（摘要用）
                "metadata": {
                    "chunk_type": "title",
                    "heading_path": str,     # "## 标题名"
                    "heading_level": 1,       # 1=##, 2=###
                    "parent_id": None,        # TitleChunk 无父级
                    "child_ids": [str, ...],  # 子 ParagraphChunk IDs
                    "page_number": int,       # 估算页码（如有）
                    ...source_metadata
                },
                "source": str
            }
            
            child_chunk = {
                "id": str,
                "text": str,           # 段落文本
                "metadata": {
                    "chunk_type": "paragraph",
                    "heading_path": str,     # "## 标题名"
                    "heading_level": 2,       # paragraph 层级
                    "parent_id": str,         # 所属 TitleChunk ID
                    "paragraph_index": int,   # 在同标题内的段落序号
                    ...source_metadata
                },
                "source": str
            }
        """
        source_name = source_metadata.get("source", "unknown")
        
        # 1. 解析 Markdown 标题结构，生成标题树
        title_tree = self._parse_heading_tree(markdown_text)
        
        parent_chunks = []
        child_chunks = []
        
        for title_idx, title_node in enumerate(title_tree):
            # 2. 生成 TitleChunk (L1 Parent)
            title_chunk_id = self._generate_chunk_id(source_name, "title", title_idx, title_node["heading"])
            
            # 收集该标题下所有子内容（用于 Parent 的 text）
            title_full_text = title_node["heading_line"] + "\n\n" + title_node["content"]
            
            # 提取图片引用
            image_refs = self._extract_image_refs(title_node["content"])
            
            # 提取公式
            formula_count = len(re.findall(r'\$\$(.*?)\$\$', title_node["content"], re.DOTALL))
            formula_count += len(re.findall(r'(?<!\$)\$(?!\$)([^\$]+)\$(?!\$)', title_node["content"]))
            
            # 检测表格
            table_lines = [l for l in title_node["content"].split("\n") if l.strip().startswith("|")]
            
            title_chunk = {
                "id": title_chunk_id,
                "text": title_full_text.strip(),
                "metadata": {
                    **source_metadata,
                    "chunk_type": "title",
                    "heading_path": title_node["heading"],
                    "heading_level": 1,  # ## 级别
                    "parent_id": None,
                    "child_ids": [],  # 稍后填充
                    "image_refs": image_refs,
                    "formula_count": formula_count,
                    "table_lines": len(table_lines),
                    "aggregated": False,
                    "theme_concepts": [],  # 语义聚合后填充
                },
                "source": source_name,
            }
            parent_chunks.append(title_chunk)
            
            # 3. 在 TitleChunk 内按段落分割 L2 Child
            paragraphs = self._split_to_paragraphs(title_node["content"])
            
            for para_idx, paragraph in enumerate(paragraphs):
                if len(paragraph.strip()) < self.MIN_CHUNK_CHARS:
                    # 太短的段落合并到下一个
                    continue
                
                child_chunk_id = self._generate_chunk_id(
                    source_name, "para", title_idx, f"{title_node['heading']}_{para_idx}"
                )
                
                child_chunk = {
                    "id": child_chunk_id,
                    "text": paragraph.strip(),
                    "metadata": {
                        **source_metadata,
                        "chunk_type": "paragraph",
                        "heading_path": title_node["heading"],
                        "heading_level": 2,  # paragraph 级别
                        "parent_id": title_chunk_id,
                        "paragraph_index": para_idx,
                        "image_refs": self._extract_image_refs(paragraph),
                        "formula_count": len(re.findall(r'\$\$(.*?)\$\$', paragraph, re.DOTALL)),
                    },
                    "source": source_name,
                }
                child_chunks.append(child_chunk)
                title_chunk["metadata"]["child_ids"].append(child_chunk_id)
        
        return parent_chunks, child_chunks
    
    # ========== 内部方法 ==========
    
    def _parse_heading_tree(self, markdown_text: str) -> List[Dict[str, Any]]:
        """
        解析 Markdown 标题结构，生成标题树。
        
        按 ## 二级标题分割，每个节点包含：
        - heading: 标题文本（不含 #）
        - heading_line: 原始标题行（含 #）
        - content: 标题下的内容（不含子标题）
        - level: 标题层级
        
        Returns:
            [{"heading": str, "heading_line": str, "content": str, "level": int}, ...]
        """
        lines = markdown_text.split("\n")
        
        # 找到所有 ## 标题的位置
        title_positions = []
        for idx, line in enumerate(lines):
            # 匹配 ## 标题（不包括 ### 等更深的标题）
            if re.match(r'^#{2}\s+', line) and not re.match(r'^#{3,}\s+', line):
                heading_text = line.lstrip("#").strip()
                title_positions.append({
                    "line_idx": idx,
                    "heading": heading_text,
                    "heading_line": line,
                    "level": 2,
                })
        
        # 按位置分割内容
        tree = []
        for i, title_info in enumerate(title_positions):
            start_idx = title_info["line_idx"]
            end_idx = title_positions[i + 1]["line_idx"] if i + 1 < len(title_positions) else len(lines)
            
            # 提取内容（标题行之后到下一个标题之前）
            content_lines = lines[start_idx + 1:end_idx]
            content = "\n".join(content_lines).strip()
            
            tree.append({
                "heading": title_info["heading"],
                "heading_line": title_info["heading_line"],
                "content": content,
                "level": title_info["level"],
            })
        
        # 如果没有找到 ## 标题，把整个文档作为一个节点
        if not tree:
            tree.append({
                "heading": "前言",
                "heading_line": "## 前言",
                "content": markdown_text,
                "level": 2,
            })
        
        return tree
    
    def _split_to_paragraphs(self, content: str) -> List[str]:
        """
        将标题下的内容分割为段落。
        
        分割策略:
        1. 按空行分割为自然段落
        2. 如果段落过长（> MAX_CHUNK_CHARS），按句子分割
        3. 如果段落过短（< MIN_CHUNK_CHARS），与下一个段落合并
        
        Args:
            content: 标题下的 Markdown 内容
        
        Returns:
            段落文本列表
        """
        # 先按空行分割
        raw_paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        
        paragraphs = []
        current_para = ""
        
        for para in raw_paragraphs:
            # 跳过纯图片行
            if para.startswith("![") and len(para) < 200:
                # 图片引用行，合并到当前段落
                if current_para:
                    current_para += "\n\n" + para
                else:
                    current_para = para
                continue
            
            # 检测是否是 ### 子标题
            if re.match(r'^#{3}\s+', para):
                # 子标题作为独立段落
                if current_para:
                    paragraphs.append(current_para)
                    current_para = ""
                paragraphs.append(para)
                continue
            
            # 普通段落
            if current_para:
                # 检查合并后长度
                if len(current_para) + len(para) < self.max_chunk_chars:
                    current_para += "\n\n" + para
                else:
                    paragraphs.append(current_para)
                    current_para = para
            else:
                current_para = para
        
        # 处理最后一个段落
        if current_para:
            paragraphs.append(current_para)
        
        # 后处理：超长段落按句子分割
        final_paragraphs = []
        for para in paragraphs:
            if len(para) > self.max_chunk_chars:
                # 按句子分割（中文句号、英文句号、问号、感叹号）
                sentences = re.split(r'(?<=[。\.\?\!])\s+', para)
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) < self.max_chunk_chars:
                        current += sent
                    else:
                        if current:
                            final_paragraphs.append(current)
                        current = sent
                if current:
                    final_paragraphs.append(current)
            else:
                final_paragraphs.append(para)
        
        return final_paragraphs
    
    def _extract_image_refs(self, text: str) -> List[Dict[str, Any]]:
        """从文本中提取 Markdown 图片引用。"""
        refs = []
        for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', text):
            refs.append({
                "alt": match.group(1),
                "path": match.group(2),
            })
        return refs
    
    def _generate_chunk_id(self, source_name: str, chunk_type: str, index: int, content_hint: str) -> str:
        """生成唯一 chunk ID。"""
        safe_name = re.sub(r'[^\w\-_.]', '_', Path(source_name).stem)[:20]
        hint_hash = hashlib.md5(content_hint.encode()).hexdigest()[:6]
        return f"md_{safe_name}_{chunk_type}_{index}_{hint_hash}"


# ========== 便捷函数 ==========

def chunk_markdown_to_standard(
    markdown_text: str,
    source_metadata: Dict[str, Any],
    max_chunk_chars: int = 2000,
) -> List[Dict[str, Any]]:
    """
    一键将 Markdown 转换为标准 chunk 列表（合并 parent + child）。
    
    用于与现有 pipeline 兼容（DocumentProcessor 输出统一格式）。
    """
    chunker = MarkdownChunker(max_chunk_chars=max_chunk_chars)
    parent_chunks, child_chunks = chunker.chunk_markdown(markdown_text, source_metadata)
    
    # 合并为单一列表（保持顺序：先 parent，后其 children）
    result = []
    for parent in parent_chunks:
        result.append(parent)
        parent_id = parent["id"]
        for child in child_chunks:
            if child["metadata"].get("parent_id") == parent_id:
                result.append(child)
    
    return result
