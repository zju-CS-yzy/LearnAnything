# LA-035-P14: 两阶段提取优化方案讨论

## 当前问题

当前概念提取流程（单阶段）：
```
Chunk → LLM 提取概念 + 关系 → ExtractedConcept (含 relation 字段) → 去重 → 连接
```

**问题**：
1. 每个 chunk 独立提取，LLM 不知道全局概念分布，容易提取重复或冲突的概念
2. 连接建立阶段（SemanticLinker）需要遍历所有概念对，LLM 调用量大
3. 提取阶段已经输出了 `relation` 字段，但去重后这个信息被丢失，连接阶段需要重新计算

## 两阶段提取方案

### 阶段 1：Nodes-First（概念提取）

**目标**：快速提取所有候选概念，不考虑连接关系。

**流程**：
```
按 heading 分组
  ↓
提取 heading 上下文
  ↓
对每个 chunk（paragraph/image）独立提取概念
  ↓
输出：[(name, concept_type, description, source_chunk), ...]
```

**特点**：
- 不输出 `relation` 字段（不需要）
- 不输出 `parent_hint`（阶段 2 统一计算）
- 只关注概念本身的语义质量
- 可以使用更轻量的 prompt（不需要连接相关的指令）

### 阶段 2：Edges-With-Context（连接建立）

**目标**：在全局概念上下文中，建立概念间的语义关系。

**流程**：
```
收集阶段 1 的所有概念（按 heading 分组）
  ↓
构建全局上下文：heading 文本 + 同组所有概念列表
  ↓
LLM 判断：这组概念之间应该建立哪些连接？
  ↓
输出：[(from_concept, to_concept, relation_type), ...]
```

**特点**：
- LLM 知道"这组概念都在同一主题下"，判断更准确
- 可以建立跨 chunk 的连接（当前 SemanticLinker 只能连接已去重的 CanonicalConcept）
- 可以直接生成语义关系类型（SOLUTION/DEPENDS_ON/HAS_DETAIL），不需要后续再分类

## 与现有架构的整合

### 方案 A：最小改动（在现有 SemanticLinker 基础上增强）

```python
# 阶段 1：提取概念（已存在）
extracted_concepts = []
for chunk in chunks:
    concepts = extractor.extract_concepts_batch_v2([chunk])  # 不返回 relation
    extracted_concepts.extend(concepts)

# 去重合并（已存在）
canonical_concepts = deduper.dedupe(extracted_concepts)

# 阶段 2：在 heading 组级别建立连接（增强）
for heading_path, heading_concepts in group_by_heading_path(canonical_concepts):
    links = linker.extract_concept_links_with_context(
        heading_concepts,
        heading_context=heading_text,
    )
    # 写入 KùzuDB
```

**优点**：改动最小，兼容现有流程
**缺点**：阶段 2 的输入是 CanonicalConcept（已去重），可能丢失原始 chunk 的上下文

### 方案 B：更彻底的分离（推荐）

```python
# 阶段 1：提取概念（去重前）
for heading_path, chunks in heading_groups.items():
    heading_context = extract_heading_text(chunks)
    batch_concepts = extractor.extract_concepts_batch_v2(
        chunks,
        heading_context=heading_context,
        output_mode="nodes_only",  # 只输出概念，不输出关系
    )
    all_concepts.extend(batch_concepts)

# 去重合并
canonical_concepts = deduper.dedupe(all_concepts)

# 阶段 2：在 heading 组级别建立连接（去重后）
# 但保留 heading 分组信息
for heading_path, concept_ids in heading_group_concepts.items():
    group_concepts = [c for c in canonical_concepts if c.id in concept_ids]
    links = linker.extract_concept_links_with_context(
        group_concepts,
        heading_context=heading_texts[heading_path],
    )
    # 写入 KùzuDB
```

**优点**：
- 阶段 2 输入是 CanonicalConcept + heading 上下文，质量更高
- 可以建立跨 chunk 的连接（如 chunk A 的"检索"与 chunk B 的"向量相似度"）
- heading 上下文帮助 LLM 理解概念间的层级关系

**缺点**：需要新增 `extract_concept_links_with_context` 方法

### 方案 C：激进方案（端到端两阶段）

```python
# 阶段 1：全局概念提取（不区分 heading）
all_chunks_text = "\n\n".join([c.text for c in chunks])
all_concepts = extractor.extract_all_concepts_from_document(
    all_chunks_text,
    paradigm="theory",
)
# 输出：全局概念列表（已去重）

# 阶段 2：全局连接建立
all_links = linker.extract_all_links_from_document(
    all_concepts,
    all_chunks_text,  # 全局上下文
)
# 输出：全局连接列表
```

**优点**：LLM 有全局视野，概念提取和连接建立质量最高
**缺点**：
- 需要一次性发送所有 chunk 文本，可能超出 token 限制
- 与当前按 heading 分组的架构冲突

## 推荐方案：B（平衡）

**理由**：
1. 与现有 heading 分组架构兼容
2. 阶段 2 的上下文明确（同一 heading 下的概念）
3. 阶段 1 的 token 消耗降低（不需要输出 relation）
4. 连接质量提升（LLM 知道同组概念的全貌）

## 实现步骤

1. **修改 `semantic_extractor.py`**：
   - `extract_concepts_batch_v2` 新增 `output_mode` 参数（`"nodes_only"` / `"full"`）
   - `"nodes_only"` 时，prompt 不输出 `relation` 和 `parent_hint`

2. **新增 `semantic_linker.py` 方法**：
   - `extract_concept_links_with_context(concepts, heading_context)` 
   - 接收一组概念 + heading 上下文，输出连接列表

3. **修改 `graph_builder.py`**：
   - 阶段 1：提取概念（`output_mode="nodes_only"`）
   - 去重合并
   - 阶段 2：按 heading 组建立连接

## 预期效果

| 指标 | 当前 | 两阶段优化后 |
|:---|:---|:---|
| 阶段 1 Token 消耗 | 高（包含 relation 输出） | 降低 20-30% |
| 连接质量 | 中（基于 embedding 相似度） | 高（LLM 全局判断） |
| 跨 chunk 连接 | 弱（去重后丢失 chunk 关联） | 强（heading 组内全局判断） |
| 实现复杂度 | 低 | 中（新增方法） |

## 风险与注意事项

1. **Token 预算**：阶段 2 需要同时发送多个概念，可能超出 token 限制。需要限制每组概念数量（如最多 20 个）。
2. **LLM 一致性**：阶段 2 的 LLM 可能与阶段 1 使用不同模型（如阶段 1 用 DeepSeek，阶段 2 用更强的模型）。
3. **错误传播**：阶段 1 提取的概念质量直接影响阶段 2 的连接质量。如果阶段 1 提取了错误概念，阶段 2 会建立错误连接。

## 下一步

建议先实现方案 B 的简化版本：
1. 在 `extract_concepts_batch_v2` 中支持 `output_mode="nodes_only"`
2. 实现 `extract_concept_links_with_context` 的 prototype
3. 用一个 heading 组（如"检索"主题）测试两阶段效果
4. 对比单阶段和两阶段的连接质量
