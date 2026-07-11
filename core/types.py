"""
核心数据类型定义 (Pydantic v2)

LearnAnything 项目所有模块共享的类型定义。
迁移目标：将核心数据结构从 Dict[str, Any] 改为 Pydantic BaseModel，
提升类型安全、IDE 补全、运行时校验能力。

兼容策略：
- 所有模型默认支持 dict() 转换（通过 model_dump()）
- 新增字段均有默认值，不影响现有数据反序列化
- 保持与前端 API 的 JSON 格式完全一致
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, field_validator


# ========== 多媒体引用 ==========

class MediaRef(BaseModel):
    """多媒体引用（图片、公式、表格）。"""
    
    type: str = Field(default="image", pattern="^(image|formula|table|audio|video)$")
    path: str = Field(default="", description="原始文件路径")
    thumbnail_path: Optional[str] = Field(default=None, description="缩略图路径")
    description: str = Field(default="", description="VLM 生成的描述或 alt 文本")
    width: Optional[int] = Field(default=None, ge=0)
    height: Optional[int] = Field(default=None, ge=0)
    page_number: Optional[int] = Field(default=None, ge=0, description="所在页码")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")

    # 兼容旧代码的 dict 访问
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)
    
    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)


class ImageRef(MediaRef):
    """图片引用（MediaRef 的别名，兼容旧代码）。"""
    
    type: str = "image"
    alt: str = Field(default="", description="图片 alt 文本（兼容旧格式）")
    
    @field_validator("alt")
    @classmethod
    def sync_alt_to_description(cls, v: str, info) -> str:
        # 如果 alt 有值但 description 为空，同步到 description
        data = info.data
        if v and not data.get("description"):
            data["description"] = v
        return v
    
    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


# ========== Chunk 元数据 ==========

class ChunkMetadata(BaseModel):
    """Chunk 的元数据。兼容 markdown_chunker v2.0、DocumentChunker 和旧版格式。"""
    
    source: str = Field(default="unknown", description="来源文件名")
    subject: str = Field(default="generic", description="学科分类")
    
    # 分块类型（兼容新旧格式）
    chunk_type: str = Field(
        default="paragraph",
        pattern="^(heading|paragraph|document|image_pseudo|parent|title|child|text)$",
        description="分块类型",
    )
    
    # 标题路径（MarkdownChunker v2.0）
    heading_path: str = Field(default="", description="标题层级路径，如 '一级 > 二级'")
    heading_level: int = Field(default=0, ge=0, le=6, description="标题层级 0=document, 1=#, ..., 6=######")
    
    # 树形关系
    parent_id: Optional[str] = Field(default=None, description="父节点 chunk_id")
    child_ids: List[str] = Field(default_factory=list, description="子节点 chunk_id 列表")
    paragraph_ids: List[str] = Field(default_factory=list, description="直接子段落 chunk_id 列表")
    
    # 行号范围
    line_range: List[int] = Field(default_factory=list, description="[起始行, 结束行)")
    
    # 多媒体
    image_refs: List[ImageRef] = Field(default_factory=list, description="图片引用列表")
    media_refs: List[MediaRef] = Field(default_factory=list, description="所有多媒体引用（图片/公式/表格）")
    
    # 文档特征
    formula_count: int = Field(default=0, ge=0)
    table_lines: int = Field(default=0, ge=0)
    page_number: Optional[int] = Field(default=None, ge=0)
    
    # 旧版兼容字段
    type: str = Field(default="child", description="旧版类型兼容（parent/child）")
    
    # 图像概念提取（v1.0 兼容）
    image_path: Optional[str] = Field(default=None, description="图片路径（旧版兼容）")
    thumbnail_path: Optional[str] = Field(default=None, description="缩略图路径（旧版兼容）")
    width: Optional[int] = Field(default=None, ge=0)
    height: Optional[int] = Field(default=None, ge=0)
    
    # VLM 描述
    description_source: Optional[str] = Field(default=None, description="描述来源（vlm/ocr/manual）")
    
    # 段落序号
    paragraph_index: int = Field(default=0, ge=0, description="在同父 heading 下的段落序号")
    
    # 通用扩展字段（兼容任意旧字段）
    model_config = {"extra": "allow"}
    
    @field_validator("chunk_type")
    @classmethod
    def normalize_chunk_type(cls, v: str) -> str:
        """兼容旧版 chunk_type 命名。"""
        mapping = {
            "title": "heading",
            "text": "paragraph",
            "child": "paragraph",
            "parent": "document",
        }
        return mapping.get(v.lower(), v.lower())
    
    @field_validator("line_range")
    @classmethod
    def normalize_line_range(cls, v) -> List[int]:
        """兼容 Tuple 和 List 格式。"""
        if isinstance(v, tuple):
            return list(v)
        if not isinstance(v, list):
            return []
        return v
    
    @field_validator("image_refs", mode="before")
    @classmethod
    def parse_image_refs(cls, v) -> List[ImageRef]:
        """兼容 dict list 和 ImageRef list。"""
        if not v:
            return []
        if isinstance(v, list):
            return [ImageRef(**item) if isinstance(item, dict) else item for item in v]
        return []
    
    @field_validator("media_refs", mode="before")
    @classmethod
    def parse_media_refs(cls, v) -> List[MediaRef]:
        """兼容 dict list 和 MediaRef list。"""
        if not v:
            return []
        if isinstance(v, list):
            return [MediaRef(**item) if isinstance(item, dict) else item for item in v]
        return []


# ========== Chunk 主体 ==========

class Chunk(BaseModel):
    """文档分块（ParagraphChunk / HeadingChunk / DocumentChunk / ImagePseudoChunk）。"""
    
    id: str = Field(..., description="唯一 chunk ID")
    text: str = Field(default="", description="文本内容")
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)
    source: str = Field(default="", description="来源文件名")
    
    # 通用扩展字段
    model_config = {"extra": "allow"}
    
    # 兼容旧代码的 dict 访问
    def __getitem__(self, key: str) -> Any:
        if key == "metadata":
            return self.metadata
        return getattr(self, key)
    
    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)
    
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（兼容旧代码）。"""
        return self.model_dump(mode="json", by_alias=True)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Chunk":
        """从字典创建（兼容旧代码）。"""
        return cls.model_validate(d)


# ========== 概念提取 ==========

class ExtractedConcept(BaseModel):
    """从单个 chunk 中提取的原始概念。"""
    
    id: str = Field(..., description="唯一提取概念 ID（chunk_id + hash）")
    name: str = Field(..., description="概念名称")
    concept_type: str = Field(default="definition", description="概念类型")
    extract_role: str = Field(default="DEFINES", description="提取角色（DEFINES/SOLUTION/APPLIED_TO 等）")
    description: str = Field(default="", description="概念描述")
    parent_hint: str = Field(default="", description="上层父概念提示（用于连接阶段）")
    source_chunk: str = Field(default="", description="来源 chunk ID")
    media_refs: List[MediaRef] = Field(default_factory=list, description="关联的多媒体引用")
    
    # 兼容旧代码
    model_config = {"extra": "allow"}
    
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)
    
    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)
    
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExtractedConcept":
        return cls.model_validate(d)


class CanonicalConcept(BaseModel):
    """去重合并后的规范概念。"""
    
    canonical_id: str = Field(..., description="唯一规范概念 ID")
    name: str = Field(..., description="概念名称（最频繁出现的原始名称）")
    concept_type: str = Field(default="definition", description="概念类型（投票胜出）")
    description: str = Field(default="", description="合并后的描述")
    parent_hint: str = Field(default="", description="父概念提示")
    
    # 去重信息
    aliases: List[str] = Field(default_factory=list, description="所有别名（合并的原始名称）")
    alias_count: int = Field(default=0, ge=0, description="别名数量")
    source_chunk_count: int = Field(default=0, ge=0, description="来源 chunk 数量")
    source_chunks: List[str] = Field(default_factory=list, description="来源 chunk ID 列表")
    type_votes: Dict[str, int] = Field(default_factory=dict, description="类型投票统计")
    
    # 多媒体
    media_refs: List[MediaRef] = Field(default_factory=list, description="合并后的多媒体引用")
    
    # embedding（可选，用于语义搜索）
    embedding: Optional[List[float]] = Field(default=None, description="embedding 向量")
    
    # 兼容旧代码
    model_config = {"extra": "allow"}
    
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)
    
    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)
    
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CanonicalConcept":
        return cls.model_validate(d)
    
    @field_validator("aliases", mode="before")
    @classmethod
    def parse_aliases(cls, v) -> List[str]:
        """兼容 JSON 字符串和 list。"""
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except:
                return [v] if v else []
        return v or []
    
    @field_validator("source_chunks", mode="before")
    @classmethod
    def parse_source_chunks(cls, v) -> List[str]:
        """兼容 JSON 字符串和 list。"""
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except:
                return [v] if v else []
        return v or []
    
    @field_validator("type_votes", mode="before")
    @classmethod
    def parse_type_votes(cls, v) -> Dict[str, int]:
        """兼容 JSON 字符串和 dict。"""
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except:
                return {}
        return v or {}
    
    @field_validator("media_refs", mode="before")
    @classmethod
    def parse_media_refs(cls, v) -> List[MediaRef]:
        """兼容 JSON 字符串和 list。"""
        if isinstance(v, str):
            import json
            try:
                v = json.loads(v)
            except:
                return []
        if isinstance(v, list):
            return [MediaRef(**item) if isinstance(item, dict) else item for item in v]
        return []


# ========== 关系边 ==========

class RelationEdge(BaseModel):
    """概念之间的关系边。"""
    
    source: str = Field(default="", description="源节点 ID（canonical_id 或 chunk_id）")
    target: str = Field(default="", description="目标节点 ID")
    type: str = Field(default="", description="关系类型（HAS_CONCEPT/DERIVED_FROM/HAS_DETAIL/SOLUTION/DEPENDS_ON/BELONGS_TO）")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    reason: str = Field(default="", description="关系建立原因（LLM 判断依据）")
    stage: str = Field(default="", description="建立阶段（parent_hint/embedding_llm/semantic_aggregator）")
    
    # 兼容旧代码
    model_config = {"extra": "allow"}
    
    # 别名：parent_id / child_id（兼容 SemanticLinker 输出）
    parent_id: Optional[str] = Field(default=None, description="父节点 ID（兼容旧名）")
    child_id: Optional[str] = Field(default=None, description="子节点 ID（兼容旧名）")
    relation_type: Optional[str] = Field(default=None, description="关系类型（兼容旧名）")
    
    @field_validator("source", mode="before")
    @classmethod
    def map_source_from_parent_id(cls, v, info) -> str:
        if v:
            return v
        return info.data.get("parent_id", "")
    
    @field_validator("target", mode="before")
    @classmethod
    def map_target_from_child_id(cls, v, info) -> str:
        if v:
            return v
        return info.data.get("child_id", "")
    
    @field_validator("type", mode="before")
    @classmethod
    def map_type_from_relation_type(cls, v, info) -> str:
        if v:
            return v
        return info.data.get("relation_type", "")
    
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)
    
    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)
    
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RelationEdge":
        return cls.model_validate(d)


# ========== 语义聚合结果 ==========

class AggregationResult(BaseModel):
    """SemanticAggregator 的聚合结果。"""
    
    status: str = Field(default="success")
    heading_count: int = Field(default=0, ge=0)
    theme_concepts: List[str] = Field(default_factory=list, description="主题概念 canonical_id 列表")
    has_detail_edges: int = Field(default=0, ge=0)
    details: List[Dict[str, Any]] = Field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


# ========== 前后端 API 响应模型 ==========

class GraphNodeResponse(BaseModel):
    """知识图谱节点 API 响应。"""
    
    id: str
    label: str = Field(default="", description="显示标签")
    type: str = Field(default="", description="节点类型")
    description: str = Field(default="")
    media_refs: List[MediaRef] = Field(default_factory=list)
    source_chunks: List[str] = Field(default_factory=list)
    alias_count: int = Field(default=0)
    # Cytoscape.js 兼容性字段
    data: Optional[Dict[str, Any]] = Field(default=None)


class GraphEdgeResponse(BaseModel):
    """知识图谱边 API 响应。"""
    
    id: str = Field(default="", description="边 ID")
    source: str
    target: str
    label: str = Field(default="", description="关系标签")
    type: str = Field(default="", description="关系类型")
    confidence: float = Field(default=0.85)
    # Cytoscape.js 兼容性字段
    data: Optional[Dict[str, Any]] = Field(default=None)


class GraphDataResponse(BaseModel):
    """知识图谱数据 API 响应。"""
    
    nodes: List[GraphNodeResponse]
    edges: List[GraphEdgeResponse]
    stats: Dict[str, Any] = Field(default_factory=dict)


class ChunkResponse(BaseModel):
    """Chunk 列表 API 响应。"""
    
    id: str
    text: str = Field(default="")
    metadata: ChunkMetadata
    source: str = Field(default="")
    # 前端展示字段
    heading_path: str = Field(default="")
    chunk_type: str = Field(default="")
    media_refs: List[MediaRef] = Field(default_factory=list)
    page_number: Optional[int] = Field(default=None)


class ConceptExtractResponse(BaseModel):
    """概念提取 API 响应。"""
    
    subject: str
    chunk_id: str
    paradigm: str
    status: str = Field(default="success")
    concepts_extracted: int = Field(default=0, ge=0)
    concepts_added: int = Field(default=0, ge=0)
    concepts: List[ExtractedConcept] = Field(default_factory=list)


# ========== 便捷导出 ==========

__all__ = [
    # 多媒体
    "MediaRef",
    "ImageRef",
    # Chunk
    "ChunkMetadata",
    "Chunk",
    # 概念
    "ExtractedConcept",
    "CanonicalConcept",
    # 关系
    "RelationEdge",
    # 聚合
    "AggregationResult",
    # API 响应
    "GraphNodeResponse",
    "GraphEdgeResponse",
    "GraphDataResponse",
    "ChunkResponse",
    "ConceptExtractResponse",
]
