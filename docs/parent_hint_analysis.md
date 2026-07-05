# Parent_Hint 匹配失败分析报告

## 核心发现

**270 个概念有 parent_hint，但只有 50 个成功匹配（匹配率 18.5%），最终写入 43 条边。**

这不是 bug，而是反映了提取和去重过程中的结构性问题。

---

## 匹配失败的原因分析

### 1. 去重导致名称变化（主因）

**流程回顾：**
```
提取阶段: LLM 输出 "Token"，parent_hint="大模型底层架构"
去重阶段: "Token" 被合并到 canonical 名称 "词元"（因为 "词元" 出现频率更高）
连接阶段: parent_hint="大模型底层架构" 在 requirement 列表中找不到精确匹配
```

**具体表现：**
- `sub_technology "Token"` → parent_hint: "大模型底层架构"
- 去重后 canonical 名称变为 "词元"
- 但 parent_hint 仍然是原始的 "大模型底层架构"
- 在 requirement/technology 列表中搜索 "大模型底层架构" → 找不到匹配

### 2. 概念类型标注不准确（次因）

**期望的层级链：**
```
requirement -(SOLUTION)-> technology -(DEPENDS_ON)-> sub_requirement -(SOLUTION)-> sub_technology
```

**实际提取结果：**
- LLM 经常将 `sub_requirement` 的 parent_hint 指向 `technology`（跳过一层）
- 或者将 `sub_technology` 的 parent_hint 指向 `technology`（跳两层）
- 导致在期望的上层类型列表中找不到匹配

**数据佐证：**
| Transition | 有 hint 的数量 | 匹配成功 | 匹配率 |
|------------|--------------|---------|--------|
| requirement → technology | 26 | 22 | **84.6%** ✅ |
| technology → sub_requirement | 59 | 17 | **28.8%** ⚠️ |
| sub_requirement → sub_technology | 182 | 11 | **6.0%** ❌ |

**分析：**
- 第一层（requirement→technology）匹配率最高，因为层级关系最清晰
- 第二层和第三层匹配率急剧下降，说明：
  1. LLM 对 sub_requirement / sub_technology 的区分不准确
  2. parent_hint 指向的目标可能不在期望的上层类型中

### 3. 别名丢失

**当前实现：**
- CSV 中 aliases 是分号分隔的字符串
- 但 `_load_from_csv` 解析 aliases 时，由于去重逻辑只保留了一个 canonical 名称
- 原始概念名称（被合并前的）作为别名保存
- 但 parent_hint 中的名称可能和 aliases 也不匹配

---

## 根本原因：信息在"提取→去重→连接"流程中丢失

```
[提取阶段]                    [去重阶段]                     [连接阶段]
┌─────────────┐              ┌─────────────┐              ┌─────────────┐
│ Concept A   │              │ Canonical X │              │ 搜索 parent_hint │
│ name: "A"   │ ──合并──>    │ name: "B"   │              │ 在 requirement   │
│ hint: "P"   │              │ aliases: ["A","C"] │         │ 列表中搜索 "P"   │
└─────────────┘              └─────────────┘              └─────────────┘
                                                                    ↓
                                                              找不到 "P"
                                                              因为 "P" 被合并到了 "B"
```

---

## 修复方案

### 方案 A：在去重时更新 parent_hint（推荐）

在去重阶段，将所有被合并概念的 parent_hint 也合并到 canonical 概念中：

```python
# 在 ConceptDeduper.dedupe_all 中
for canonical_name, merged_names in canonical_groups.items():
    # ... 现有逻辑 ...
    
    # 收集所有 parent_hint（去重后取最常见的非空值）
    hint_counts = defaultdict(int)
    for c in all_concepts:
        if c["name"] in merged_names and c.get("parent_hint", "").strip():
            hint_counts[c["parent_hint"].strip()] += 1
    canonical_hint = max(hint_counts, key=hint_counts.get) if hint_counts else ""
    
    # 同时建立 "原始名称 → canonical 名称" 的映射表
    # 用于连接阶段查找
```

**优点：** 简单直接，在现有架构下修复
**缺点：** 如果多个子概念指向同一个父概念的不同别名，只能保留一个

### 方案 B：用 embedding 相似度匹配 parent_hint（更鲁棒）

在连接阶段，不再用精确字符串匹配 parent_hint，而是用 embedding 相似度：

```python
def _stage1_parent_hint_match(...):
    for child in children:
        hint = child.get("parent_hint", "").strip()
        if not hint:
            continue
        
        # 用 embedding 相似度找到最匹配的 parent
        hint_emb = embedding.embed([hint])[0]
        best_match = None
        best_sim = 0
        for p in parents:
            sim = cosine_similarity(hint_emb, p["embedding"])
            if sim > best_sim and sim > 0.8:
                best_sim = sim
                best_match = p
        
        if best_match:
            edges.append(...)
```

**优点：** 能处理同义不同词的情况
**缺点：** 增加 API 调用成本；可能误匹配

### 方案 C：在提取阶段增强 parent_hint 规范

修改 prompt，要求 LLM：
1. parent_hint 必须填写 canonical 概念在**当前 chunk 中出现的原文表述**
2. 如果 parent_hint 指向的概念在当前 chunk 中没有出现，留空
3. 提供 "概念名称 → 规范名称" 的映射表

**优点：** 从源头解决问题
**缺点：** 增加 prompt 复杂度；LLM 可能不遵循

---

## 建议

**短期（推荐方案 A）：**
1. 在 ConceptDeduper 中建立 "原始名称 → canonical ID" 映射表
2. 在 SemanticLinker 中，先用精确匹配，再用映射表查找
3. 这样可以恢复大部分丢失的连接

**中期（推荐方案 B）：**
1. 对未匹配的 parent_hint 使用 embedding 相似度匹配
2. 作为精确匹配的补充（fallback）

**长期（推荐方案 C）：**
1. 优化提取 prompt，让 LLM 输出更规范的 parent_hint
2. 考虑在提取时就提供全局概念列表，让 LLM 从中选择 parent
