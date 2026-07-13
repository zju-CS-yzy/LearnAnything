# LearnAnything 四层数据模型设计 v2.0

> 基于开发者反馈：需要保留原始概念层，区分原始提取与全局去重，支持溯源。
> 创建日期：2026-07-07
> 关联：LA-028 孤立节点问题、LA-029 来源信息缺失

---

## 一、核心设计决策

### 四层模型架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Chunk 层（文档片段）                                   │
│  ├── 164 个 Chunk 节点                                          │
│  ├── BELONGS_TO: 文档层级结构                                     │
│  └── ADJACENT_TO: 页码相邻关系                                   │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: ExtractedConcept 层（原始概念）                         │
│  ├── 1489 个节点（chunk 内去重，跨 chunk 保留）                   │
│  ├── HAS_CONCEPT: Chunk → ExtractedConcept                      │
│  └── 每个节点包含提取时的完整信息（role/type/description/hint）    │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: CanonicalConcept 层（全局去重概念）                     │
│  ├── 186 个节点（跨 chunk 语义合并）                              │
│  ├── DERIVED_FROM: ExtractedConcept → CanonicalConcept            │
│  └── 每个节点保留来源索引和别名列表                               │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: 图谱层（语义连接）                                      │
│  ├── SOLUTION: canonical 需求 → canonical 技术                  │
│  └── DEPENDS_ON: canonical 技术 → canonical 需求                  │
└─────────────────────────────────────────────────────────────────┘
```

### 与单层模型的区别

| 维度 | 旧单层模型 | 新四层模型 |
|:---|:---|:---|
| 概念节点 | 1 种（Concept，混合原始+canonical） | 2 种（ExtractedConcept + CanonicalConcept） |
| Chunk→概念关系 | REQUIRES/IMPLEMENTS/HAS_SUB/HAS_IMPL（错误） | HAS_CONCEPT（统一归属） |
| 原始概念去重 | 无（每个 chunk 同名概念保留多个） | chunk 内去重（同一 chunk 只保留一个） |
| 全局去重 | CSV 文件（不写入 KùzuDB） | KùzuDB 节点 + DERIVED_FROM 边 |
| 溯源能力 | 弱（只能通过 source_chunk 字段） | 强（通过 DERIVED_FROM 边显式关联） |
| 用户视角 | 混乱（1489 个节点，1303 个"孤立"） | 清晰（186 个 canonical 节点用于图谱） |

---

## 二、KùzuDB Schema 设计

### 2.1 节点类型

#### Chunk（多媒体增强版）
```cypher
CREATE NODE TABLE Chunk (
    chunk_id STRING PRIMARY KEY,
    text STRING,                    -- 文本内容（图片 chunk 为 VLM 描述文本）
    heading_path STRING,            -- 标题路径
    source STRING,                  -- 来源文件名
    page_number INT64,             -- 页码
    chunk_type STRING,             -- 类型: document | heading | paragraph | image_pseudo
    image_path STRING,             -- 原始图片路径（图片 chunk 专用）
    thumbnail_path STRING,         -- 缩略图路径（图片 chunk 专用）
    width INT64,                   -- 图片宽度（像素，图片 chunk 专用）
    height INT64,                  -- 图片高度（像素，图片 chunk 专用）
    media_refs STRING              -- JSON 数组: [{"type": "image", "path": ..., "thumbnail_path": ..., "description": ...}]
)
```

**字段说明**：
- `image_path` / `thumbnail_path` / `width` / `height`：图片 chunk 的元数据，用于前端展示和回退查询
- `media_refs`：JSON 序列化的媒体引用列表，支持图片、公式、表格等多种媒体类型（LA-035-P18 新增）
- `chunk_type`：新增 `image_pseudo` 类型，表示 VLM 描述后的图片 chunk

#### ExtractedConcept（多媒体增强版）
```cypher
CREATE NODE TABLE ExtractedConcept (
    extracted_id STRING PRIMARY KEY,    -- 格式: {chunk_id}_{name_hash}
    name STRING,
    concept_type STRING,               -- requirement/technology/sub_requirement/sub_technology
    extract_role STRING,               -- DEFINES/HAS_LAW/APPLIES_TO/EXTENDS/REQUIRES/IMPLEMENTS/HAS_SUB/HAS_IMPL
    description STRING,
    parent_hint STRING,
    source_chunk STRING,               -- 来源 chunk_id
    media_refs STRING                  -- JSON 数组: [{"type": "image", "path": ..., "description": ...}]（LA-035-P18 新增）
)
```

**字段说明**：
- `media_refs`：从来源 chunk 的 `media_refs` 继承，用于在概念详情面板中展示关联媒体（LA-035-P18）
- 去重合并时，CanonicalConcept 的 `media_refs` 由所有来源 ExtractedConcept 的 `media_refs` 合并去重得到

#### CanonicalConcept（新增，替代原 Concept）
```cypher
CREATE NODE TABLE CanonicalConcept (
    canonical_id STRING PRIMARY KEY,   -- 格式: concept_canonical_{name_hash}
    name STRING,
    concept_type STRING,
    description STRING,
    parent_hint STRING,
    aliases STRING,                    -- JSON 数组: ["别名1", "别名2"]
    source_chunks STRING               -- JSON 数组: ["chunk_id_1", "chunk_id_2"]
)
```

### 2.2 边类型

```cypher
-- Layer 1 → Layer 2
CREATE REL TABLE HAS_CONCEPT(FROM Chunk TO ExtractedConcept, MANY_MANY)

-- Layer 2 → Layer 3
CREATE REL TABLE DERIVED_FROM(FROM ExtractedConcept TO CanonicalConcept, MANY_MANY)

-- Layer 3 → Layer 3（语义连接）
CREATE REL TABLE SOLUTION(FROM CanonicalConcept TO CanonicalConcept, MANY_MANY)
CREATE REL TABLE DEPENDS_ON(FROM CanonicalConcept TO CanonicalConcept, MANY_MANY)

-- Layer 1 → Layer 1（结构连接）
CREATE REL TABLE BELONGS_TO(FROM Chunk TO Chunk, MANY_MANY)
CREATE REL TABLE ADJACENT_TO(FROM Chunk TO Chunk, MANY_MANY)
```

---

## 三、潜在问题检查

### 3.1 ✅ 已解决的问题

| 问题 | 旧模型 | 新模型 |
|:---|:---|:---|
| Chunk→Concept 关系类型错误 | REQUIRES/IMPLEMENTS 等边类型 | 统一为 HAS_CONCEPT |
| 原始概念丢失 | 去重后只保留 canonical | 保留 ExtractedConcept 层 |
| 同名概念语义差异 | 强制合并为一个 | 各自保留，通过 DERIVED_FROM 关联 |
| 孤立概念 | 1303 个被判定为孤立 | 原始层是独立的，canonical 层有连接 |

### 3.2 ⚠️ 需要关注的新问题

#### 问题 A：ExtractedConcept 数量膨胀
- 当前 1489 个原始概念，164 个 chunk → 平均每 chunk 约 9 个概念
- 如果导入更多文档，ExtractedConcept 可能膨胀到数千个
- **影响**：KùzuDB 查询性能、前端加载速度
- **缓解**：前端默认只展示 canonical 层，ExtractedConcept 按需查询（点击溯源时加载）

#### 问题 B：CanonicalConcept 的 concept_type 冲突
- 同一概念在不同 chunk 中被提取为不同类型（如 chunk_A 判定为"requirement"，chunk_B 判定为"technology"）
- 当前投票机制（取最多的类型）可能丢失重要信息
- **建议**：在 CanonicalConcept 中增加 `type_votes` 属性记录类型分布，让用户可见

#### 问题 C：extract_role 的含义
- ExtractedConcept 的 `extract_role` 表示"这个 chunk 如何提及这个概念"
- CanonicalConcept 不需要此属性（因为 canonical 是全局抽象的，不是从某个 chunk"提取"的）
- **确认**：CanonicalConcept 不存储 extract_role，这是正确的

#### 问题 D：删除 Chunk 的级联行为
- 删除 Chunk 时，需要级联删除其关联的 ExtractedConcept
- 如果这些 ExtractedConcept 是某个 CanonicalConcept 的唯一来源，CanonicalConcept 是否保留？
- **建议**：保留但标记为 `orphan=true`，不展示在图谱中，但保留在历史/审计中

#### 问题 E：前端视图切换复杂度
- 当前前端只有"概念视图"（展示 canonical 节点）
- 新模型需要支持：
  - **Canonical 视图**：默认，展示 canonical 节点和 SOLUTION/DEPENDS_ON 边
  - **溯源视图**：点击 canonical 节点后，展示其关联的 ExtractedConcept 和来源 Chunk
- **工作量**：中等，需要新增 API 和 UI 组件

#### 问题 F：SemanticLinker 的数据来源
- 当前 SemanticLinker 从 CSV 读取 canonical 概念（`generic_v1_concepts.csv`）
- 新模型中，CanonicalConcept 写入 KùzuDB，SemanticLinker 应直接从 KùzuDB 读取
- **好处**：数据一致性更好，不需要 CSV 作为中间层
- **遗留**：CSV 可作为导出/备份格式保留

### 3.3 ❌ 不适用的问题

| 假设 | 实际 |
|:---|:---|
| "需要为每个 ExtractedConcept 建 embedding" | 不需要。CanonicalConcept 已有 embedding，ExtractedConcept 的相似度通过 DERIVED_FROM 已确定 |
| "Chunk→ExtractedConcept 需要多关系类型" | 不需要。统一 HAS_CONCEPT 即可，语义角色由 ExtractedConcept 的 extract_role 属性表达 |
| "CanonicalConcept 需要存储原始文本" | 不需要。通过 source_chunks 索引到 Chunk 即可获取原始文本 |

---

## 四、实施路径

### Phase 1：Schema 迁移（破坏性，需重建 graph DB）

```
1. 删除旧 graph DB（generic_v1_graph 等）
2. 初始化新 Schema（含 ExtractedConcept 和 CanonicalConcept）
3. 重新导入所有 chunk（Phase 1 结构层）
4. 执行概念提取（Phase 2 Step 1）→ 写入 ExtractedConcept
5. 执行概念去重（Phase 2 Step 2）→ 写入 CanonicalConcept + DERIVED_FROM 边
6. 执行语义连接（Phase 2 Step 3）→ 写入 SOLUTION/DEPENDS_ON 边
```

### Phase 2：前端适配

```
1. 修改 list_graph_concepts API：默认返回 CanonicalConcept
2. 新增溯源 API：给定 canonical_id，返回关联的 ExtractedConcept + Chunk
3. 修改 NodeDetailPanel：
   - CanonicalConcept 节点：展示名称、类型、描述、来源 chunks（可点击跳转）
   - 新增"查看原始概念"按钮：展开显示所有 ExtractedConcept
4. 保留 GraphView 的 canonical 层布局（不变）
```

### Phase 3：数据迁移脚本（可选，用于保留现有数据）

```
1. 从旧 KùzuDB 导出所有 Concept 节点
2. 按 source_chunk 区分原始概念和 canonical 概念
3. 写入新 Schema
4. 重建 BELONGS_TO/ADJACENT_TO 边
```

---

## 五、关键数据流确认

### 5.1 提取流程（SemanticExtractor → GraphStore）

```python
# 1. SemanticExtractor 从 chunk 提取概念
concepts = extractor.extract_concepts(chunk_text)
# 返回: [{"name", "concept_type", "relation", "description", "parent_hint"}, ...]

# 2. GraphStore.add_concepts 写入 ExtractedConcept
for concept in concepts:
    extracted_id = f"{chunk_id}_{hash(concept['name'])}"
    # MERGE (e:ExtractedConcept {extracted_id, name, concept_type, extract_role, description, parent_hint, source_chunk})
    # CREATE (ch:Chunk)-[:HAS_CONCEPT]->(e)

# 3. 保存到 JSONL（供去重器使用）
_save_concept_details(chunk_id, concepts)
```

### 5.2 去重流程（ConceptDeduper → GraphStore）

```python
# 1. 读取所有 ExtractedConcept
all_extracted = graph_store.get_extracted_concepts()

# 2. 基于 embedding 相似度聚类合并
# 生成 canonical_map: {original_name -> canonical_name}

# 3. 写入 CanonicalConcept
for canonical_name, group in canonical_groups:
    canonical_id = hash(canonical_name)
    # MERGE (c:CanonicalConcept {canonical_id, name, concept_type, description, parent_hint, aliases, source_chunks})
    
    # 为每个原始概念建立 DERIVED_FROM 边
    for extracted in group:
        # MATCH (e:ExtractedConcept {extracted_id}), (c:CanonicalConcept {canonical_id})
        # CREATE (e)-[:DERIVED_FROM]->(c)
```

### 5.3 连接流程（SemanticLinker → GraphStore）

```python
# 1. 从 KùzuDB 读取 CanonicalConcept（而不是 CSV）
concepts = graph_store.get_canonical_concepts()

# 2. 按范式层级分组，执行 parent_hint + embedding + LLM 推断

# 3. 写入 SOLUTION/DEPENDS_ON 边
# CREATE (p:CanonicalConcept)-[:SOLUTION]->(c:CanonicalConcept)
```

---

## 六、前端展示设计

### 6.1 CanonicalConcept 节点详情面板

```
┌─────────────────────────────────────┐
│ 📌 概念：知识图谱                        │
│ 类型：technology                        │
│ 描述：用图结构表示知识的系统...          │
│                                       │
│ 📎 来源文档（3 个）                      │
│  ├─ generic_text_42  [查看]           │
│  ├─ generic_text_88  [查看]           │
│  └─ generic_text_103  [查看]          │
│                                       │
│ 🔗 原始概念（3 个）                      │
│  ├─ 知识图谱（chunk_42）  [提取角色: DEFINES]  │
│  ├─ 知识图谱（chunk_88）  [提取角色: HAS_LAW]  │
│  └─ 知识图谱（chunk_103） [提取角色: DEFINES]  │
│                                       │
│ 📊 类型分布：technology(2), requirement(1) │
│                                       │
│ [查看关联图谱]  [在知识库中搜索]          │
└─────────────────────────────────────┘
```

### 6.2 ExtractedConcept 节点详情面板（溯源视图）

```
┌─────────────────────────────────────┐
│ 📄 原始概念：知识图谱                    │
│ 来源：chunk_42                         │
│ 提取角色：DEFINES（定义）               │
│ 类型：technology                        │
│ 描述：用图结构表示知识的系统...          │
│                                       │
│ 👆 所属全局概念                         │
│  知识图谱 → [查看 canonical]           │
│                                       │
│ 📄 来源文档片段                         │
│  ├─ 标题：技术架构                     │
│  ├─ 页码：第 3 页                      │
│  └─ 内容摘要：知识图谱是一种...         │
│                                       │
│ [定位到文档]  [查看 chunk 详情]         │
└─────────────────────────────────────┘
```

---

## 七、遗留问题状态更新

| 编号 | 问题 | 新模型下状态 | 备注 |
|:---|:---|:---:|:---|
| LA-028 | 孤立概念过多 | ✅ 解决 | 原始概念层独立，canonical 层天然有连接 |
| LA-029 | 概念节点详情缺少来源 | ✅ 解决 | CanonicalConcept 展示 source_chunks 和 DERIVED_FROM 关系 |
| — | Chunk→Concept 关系类型错误 | ✅ 解决 | 统一为 HAS_CONCEPT + extract_role 属性 |
| — | 原始概念与 canonical 概念混淆 | ✅ 解决 | 两层标签明确区分 |

---

## 八、决策点

开发者需要确认以下问题，才能开始实施：

### 1. 数据迁移策略
- **A. 重建**：删除现有 graph DB，按新 Schema 重新提取/去重/连接（推荐，数据量不大，164 chunk 重建很快）
- **B. 迁移**：写脚本将现有数据转换到新 Schema（工作量大，且旧数据有错误关系，不建议）

### 2. CanonicalConcept 的 type 冲突处理
- **A. 投票制**：取出现最多的类型（当前实现）
- **B. 多类型存储**：存储 `type_votes` JSON（如 `{"technology": 2, "requirement": 1}`），让用户在详情面板可见

### 3. 删除 Chunk 的级联行为
- **A. 级联删除**：删除 Chunk 时，级联删除 ExtractedConcept，如果 CanonicalConcept 无来源则标记为 orphan
- **B. 软删除**：Chunk 标记为 deleted，不实际删除，保留完整性

### 4. 前端默认视图
- **A. 只展示 canonical**：GraphView 默认只加载 CanonicalConcept + SOLUTION/DEPENDS_ON（当前行为，推荐）
- **B. 可切换视图**：支持"canonical 视图"和"完整视图"（含 ExtractedConcept）

---

**请确认以上决策点，我将开始实施代码修改。**
