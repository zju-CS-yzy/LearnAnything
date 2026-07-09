# LA-035 Phase 2: CanonicalConcept 多媒体扩展设计

## 1. 核心设计原则

> **图片、表格、公式不是独立的节点类型，而是 CanonicalConcept 原始信息的扩展形式。**

与 Phase 1 设计的区别：
- Phase 1: 图片作为独立节点（ImageConcept）或附属引用（image_refs）
- Phase 2: 图片的 VLM 描述作为文本，与文字 chunk 一样参与概念提取；图片路径作为 CanonicalConcept 的原始信息引用存储

**最终目标**：CanonicalConcept 的语义连接基于其原始信息（文字 + 图片 + 表格 + 公式）的语义，而非信息载体类型。

## 2. 扩展后的 CanonicalConcept Schema

```python
# KùzuDB Schema（向后兼容）
"""CREATE NODE TABLE CanonicalConcept (
    canonical_id STRING,
    name STRING,
    concept_type STRING,
    description STRING,           # 概念描述（文字摘要）
    parent_hint STRING,
    aliases STRING,
    source_chunks STRING,         # 来源 chunk IDs（逗号分隔）
    type_votes STRING,            # 类型投票（JSON）
    # === 新增字段：多媒体原始信息引用 ===
    media_refs STRING,            # 关联的多媒体资源（JSON 数组字符串）
    PRIMARY KEY(canonical_id)
)"""
```

### media_refs 字段格式

```json
[
  {
    "type": "image",
    "path": "generic_v1_images/doc_p2_img0_abc123.png",
    "thumbnail_path": "generic_v1_thumbnails/doc_p2_img0_abc123.png",
    "description": "VLM 生成的图片描述",
    "width": 800,
    "height": 600,
    "page_number": 2
  },
  {
    "type": "table",
    "path": "",
    "description": "VLM 提取的 Markdown 表格",
    "markdown": "| 列1 | 列2 |\n| --- | --- |\n| A | B |",
    "page_number": 3
  },
  {
    "type": "formula",
    "path": "",
    "description": "数学公式",
    "latex": "H(X) = -\\sum_{x} p(x) \\log p(x)",
    "page_number": 5
  }
]
```

## 3. 概念提取流程（扩展版）

```
┌─────────────────────────────────────────────────────────────────────┐
│                     文档导入流程（扩展版）                              │
└─────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │   Step 1: PDF 解析与分块（已有）    │
                    │   - 文字 chunk → 正常流程           │
                    │   - 图片 chunk → 保存图片 + 记录元数据 │
                    │   - 表格 chunk → 保存图片 + 记录元数据 │
                    │   - 公式 chunk → 保存图片 + 记录元数据 │
                    └─────────────────┬─────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │   Step 2: 多媒体预处理（新增）        │
                    │                                     │
                    │   ┌──────────┐  ┌──────────┐       │
                    │   │ 图片 chunk│  │ 表格 chunk│       │
                    │   └────┬─────┘  └────┬─────┘       │
                    │        │              │              │
                    │   ┌────┴─────┐  ┌────┴─────┐       │
                    │   │ VLM 描述  │  │ VLM 提取   │       │
                    │   │ (describe)│  │ (table)   │       │
                    │   └────┬─────┘  └────┬─────┘       │
                    │        │              │              │
                    │   ┌────┴─────┐  ┌────┴─────┐       │
                    │   │ 图片文字   │  │ Markdown  │       │
                    │   │ 描述     │  │ 表格      │       │
                    │   └────┬─────┘  └────┬─────┘       │
                    │        │              │              │
                    │   ┌────┴────────────────┐          │
                    │   │  公式 chunk          │          │
                    │   └────┬────────────────┘          │
                    │        │                         │
                    │   ┌────┴─────┐                    │
                    │   │ pix2tex    │                    │
                    │   │ 提取 LaTeX │                    │
                    │   └────┬─────┘                    │
                    │        │                         │
                    │   ┌────┴─────┐                    │
                    │   │ LaTeX 文本 │                    │
                    │   └──────────┘                    │
                    └─────────────────┬─────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │   Step 3: 概念提取（扩展）          │
                    │                                     │
                    │   输入：文字 chunk 文本             │
                    │        + 图片描述                  │
                    │        + Markdown 表格             │
                    │        + LaTeX 公式                │
                    │                                     │
                    │   SemanticExtractor.extract()      │
                    │   → 返回概念列表                   │
                    │   → 每个概念关联 source_chunks     │
                    │   → 每个概念关联 media_refs        │
                    └─────────────────┬─────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │   Step 4: 去重与融合（已有）         │
                    │   → ConceptDeduper                │
                    │   → 生成 CanonicalConcept          │
                    │   → media_refs 随概念合并          │
                    └─────────────────┬─────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │   Step 5: 存储到 KùzuDB             │
                    │   → 文字概念：正常存储               │
                    │   → 图片/表格/公式概念：             │
                    │     description = VLM 描述          │
                    │     media_refs = JSON 数组         │
                    │     语义边基于 description 建立    │
                    └─────────────────────────────────────┘
```

## 4. 关键模块修改

### 4.1 graph_store.py — Schema 扩展

```python
# CanonicalConcept 节点增加 media_refs 字段
"""CREATE NODE TABLE CanonicalConcept (
    canonical_id STRING,
    name STRING,
    concept_type STRING,
    description STRING,
    parent_hint STRING,
    aliases STRING,
    source_chunks STRING,
    type_votes STRING,
    media_refs STRING,  # NEW: JSON 数组字符串
    PRIMARY KEY(canonical_id)
)"""
```

### 4.2 semantic_extractor.py — 扩展输入

```python
class SemanticExtractor:
    def extract_concepts(self, chunk_text: str, media_context: List[Dict] = None) -> List[Dict]:
        """
        提取 chunk 中的概念。
        
        Args:
            chunk_text: chunk 的文本内容
            media_context: 关联的多媒体信息（图片描述、表格、公式）
                [
                    {"type": "image", "description": "..."},
                    {"type": "table", "markdown": "..."},
                    {"type": "formula", "latex": "..."},
                ]
        
        修改：prompt 中增加多媒体上下文
        """
        # 构建增强后的文本输入
        enhanced_text = chunk_text
        if media_context:
            for media in media_context:
                if media["type"] == "image":
                    enhanced_text += f"\n\n[图片描述] {media['description']}"
                elif media["type"] == "table":
                    enhanced_text += f"\n\n[表格数据]\n{media['markdown']}"
                elif media["type"] == "formula":
                    enhanced_text += f"\n\n[数学公式] {media['latex']}"
        
        # 调用 LLM 提取概念（基于增强后的文本）
        return self._call_llm(enhanced_text)
```

### 4.3 document_processor.py — 图片概念化

```python
def _process_image_chunks(self, chunks: List[Dict]) -> List[Dict]:
    """
    将图片 chunk 转化为可参与概念提取的形式。
    
    返回：每个图片 chunk 附带 VLM 描述，作为"伪文本 chunk"参与后续流程
    """
    vlm = VLMClient()
    result = []
    
    for chunk in chunks:
        if chunk.get("metadata", {}).get("chunk_type") == "image":
            img_path = KNOWLEDGE_BASE_DIR / chunk["metadata"]["image_path"]
            
            # VLM 分析图片
            description = vlm.analyze_image(str(img_path), task="describe")
            
            # 创建"伪文本 chunk"（用于概念提取）
            pseudo_chunk = {
                "id": chunk["id"],
                "text": f"[图片] {description}",  # 图片描述作为文本
                "metadata": {
                    **chunk["metadata"],
                    "media_refs": [{
                        "type": "image",
                        "path": chunk["metadata"]["image_path"],
                        "thumbnail_path": chunk["metadata"]["thumbnail_path"],
                        "description": description,
                        "width": chunk["metadata"].get("width"),
                        "height": chunk["metadata"].get("height"),
                    }]
                }
            }
            result.append(pseudo_chunk)
        else:
            result.append(chunk)
    
    return result
```

### 4.4 concept_deduper.py — media_refs 合并

```python
def merge_media_refs(self, refs_a: List[Dict], refs_b: List[Dict]) -> List[Dict]:
    """
    合并两个概念的 media_refs，去重。
    
    去重依据：type + path（或 description 前 50 字符的 hash）
    """
    seen = set()
    merged = []
    
    for ref in (refs_a or []) + (refs_b or []):
        key = f"{ref['type']}:{ref.get('path', ref.get('description', '')[:50])}"
        if key not in seen:
            seen.add(key)
            merged.append(ref)
    
    return merged
```

## 5. 图片分类策略（与 Phase 2 设计合并）

### 5.1 分类决策（简化版）

由于图片已融入 CanonicalConcept，分类策略简化为：

```
图片 chunk → VLM 分析 → 获取描述
                    │
                    ├─ 描述能提取出明确概念 → 参与概念提取，成为 CanonicalConcept
                    │                        （如：流程图 → "XX流程"概念）
                    │
                    └─ 描述无法提取独立概念 → 作为附属引用，关联到邻近概念
                                               （如：公式截图 → 关联到数学定义概念）
```

**判断标准**：VLM 描述是否能被 SemanticExtractor 提取出至少一个概念。

### 5.2 流程图

```
PDF 图片提取
    │
    ├─ 保存原图 + 缩略图
    ├─ 创建 image chunk（chunk_type='image'）
    │
    VLM 分析（describe）
    │
    ├─ 图片描述文本
    │
    SemanticExtractor 尝试提取概念
    │
    ├─ 能提取概念 → 创建/合并 CanonicalConcept
    │              → media_refs 包含图片引用
    │              → 语义边基于描述建立
    │
    └─ 无法提取概念 → 查找邻近文本 chunk 提取的概念
                     → 将图片关联到最佳匹配概念
                     → 更新该概念的 media_refs
```

## 6. 前端展示方案

### 6.1 概念节点详情面板

```
┌────────────────────────────────────┐
│  概念名称：Transformer 架构        │
├────────────────────────────────────┤
│  类型：definition                   │
├────────────────────────────────────┤
│  描述：一种基于自注意力...          │
├────────────────────────────────────┤
│  📎 关联资源（2）                   │
│  ├─ [📷] 架构图（点击查看）        │
│  │    来源：PDF第3页               │
│  ├─ [📊] 性能对比表                │
│  │    来源：PDF第5页               │
│  └─ [📐] 注意力公式                │
│       H = -Σp(x)log p(x)           │
├────────────────────────────────────┤
│  语义关联：                          │
│  → DEPENDS_ON 自注意力机制         │
│  → SOLUTION 机器翻译任务            │
└────────────────────────────────────┘
```

### 6.2 知识图谱中的展示

- 概念节点保持现有 UML 卡片样式
- 有关联 media 的概念节点，在卡片右下角显示 📎 图标
- 点击 📎 图标，展开关联资源列表（图片/表格/公式）
- 图片资源：点击显示缩略图，再点击全屏查看

## 7. 向后兼容性

### 7.1 数据库 Schema 兼容

```python
def init_schema(self, force: bool = False):
    # 检查现有 schema 是否包含 media_refs 字段
    # 如果不包含，执行 ALTER（KùzuDB 支持 ALTER TABLE ADD COLUMN）
    # 或重建 schema（将数据迁移到新 schema）
    pass
```

### 7.2 API 兼容

```python
# list_graph_concepts 返回时，media_refs 为空的节点保持原有格式
# 有 media_refs 的节点，前端可选展示 📎 图标
```

## 8. 实施计划

### Phase 2.1: Schema 与数据层（1-2 天）
- [ ] 修改 graph_store.py：CanonicalConcept 增加 media_refs 字段
- [ ] 修改 semantic_extractor.py：支持多媒体上下文输入
- [ ] 修改 document_processor.py：图片 chunk VLM 预处理
- [ ] 修改 concept_deduper.py：media_refs 合并逻辑

### Phase 2.2: 概念提取与融合（1-2 天）
- [ ] 实现图片 → VLM 描述 → 概念提取流程
- [ ] 实现公式 → pix2tex → LaTeX → 概念提取流程
- [ ] 实现表格 → VLM Markdown → 概念提取流程
- [ ] 测试：导入含图片/表格/公式的 PDF，验证概念提取结果

### Phase 2.3: 前端展示（1 天）
- [ ] 修改 NodeDetailPanel.vue：概念节点展示关联媒体
- [ ] 修改 GraphStyles.js：有关联媒体的概念节点显示 📎 图标
- [ ] 实现图片/表格/公式的内嵌展示

### Phase 2.4: 性能优化（可选）
- [ ] VLM 调用缓存（相同图片不重复分析）
- [ ] 异步图片处理（不阻塞导入流程）
- [ ] 缩略图懒加载

## 9. 与原有设计的对比与决策

| 决策点 | Phase 1 设计 | Phase 2 设计（当前） | 变更原因 |
|-------|-------------|-------------------|---------|
| 图片节点类型 | ImageConcept（独立） | CanonicalConcept（扩展） | 统一概念模型，避免节点类型碎片化 |
| 图片分类 | complexity_score + 类型判断 | 能否提取出概念 | 简化决策，让语义本身决定 |
| 公式处理 | 作为独立节点 | 作为概念描述的一部分 | 公式是数学概念的表达形式，不是独立概念 |
| 表格处理 | 作为独立节点 | 作为概念数据引用 | 表格是数据载体，概念是表格描述的知识 |
| 关系类型 | ILLUSTRATES/DEPENDS_ON | 复用 SOLUTION/DEPENDS_ON | 图片描述与其他概念的关系即语义关系 |
| 存储方式 | 节点属性 | media_refs JSON 字段 | 灵活扩展，支持多种媒体类型 |

**关键变更总结**：
- 删除 ImageConcept 节点类型设计
- 删除图片独立/附属的两级分类策略
- 统一使用 CanonicalConcept + media_refs 承载所有原始信息
- 语义连接基于 VLM 生成的文本描述，而非图片本身
