# LearnAnything Phase 2.5 — 修复后构建评估报告

> 生成时间: 2026-07-02
> 学科: generic
> 范式: engineering（工程分解）

---

## 一、修复清单

### 1. ✅ 同一 chunk 内概念重复（P0）
**修复**: `graph_store.py` 的 `add_concepts` 中增加 `seen_names` 去重逻辑
**效果**: 消除 "duplicated primary key" 错误

### 2. ✅ KùzuDB 锁冲突（P0）
**修复**: 
- `concept_deduper.py` 接受可选的 `graph_store` 参数
- `graph_builder.py` 的 `dedupe_concepts` 复用 `self.graph_store`
**效果**: 去重阶段不再因锁冲突崩溃

### 3. ✅ parent_hint 为空（P1）
**修复**: `semantic_extractor.py` 的 `validated.append` 中添加 `"parent_hint": c.get("parent_hint", "").strip()`
**效果**: 270/394 个概念（68.5%）包含非空 parent_hint

### 4. ✅ EmbeddingManager.encode 缺失（P1）
**修复**: 
- `concept_deduper.py`: `self.embedding.encode` → `self.embedding.embed`
- `semantic_quality_evaluator.py`: 同上
- `concept_deduper.py` 导出 CSV 时 numpy array → list 转换
**效果**: 去重和评估阶段正常运行

### 5. ✅ SemanticLinker 概念加载（新发现）
**修复**: `_load_canonical_concepts` 改为直接从 CSV 加载（而非数据库→CSV 合并）
**效果**: parent_hint 正确读取，连接建立成功

### 6. ✅ SemanticLinker 节点创建（新发现）
**修复**: `_write_edges` 在创建关系前先用 `MERGE` 确保 canonical 节点存在
**效果**: 51 条连接边成功写入，查询到 43 条

---

## 二、最终构建结果

### 2.1 整体流程
```
提取 (98 chunks) → 去重 (394 canonical) → 连接 (43 edges)
```

### 2.2 提取结果
- **处理 chunk**: 98
- **成功提取**: 98 (100%)
- **失败**: 0
- **总概念**: 499（去重前）
- **平均质量分**: 0.648

### 2.3 去重结果
- **Canonical 概念**: 394
- **去重率**: 21% (105/499)
- **有 parent_hint**: 270 (68.5%)

### 2.4 语义连接结果
- **总连接边**: 43
- **parent_hint 精确匹配**: 42
- **embedding+LLM 二次确认**: 1
- **连接类型**: 全部为 SOLUTION（requirement→technology 或 sub_requirement→sub_technology）

### 2.5 概念类型分布
| 类型 | 数量 | 占比 |
|------|------|------|
| technology | 131 | 33.2% |
| sub_technology | 226 | 57.4% |
| requirement | 78 | 19.8% |
| sub_requirement | 64 | 16.2% |

**需求/技术比**: 1:2.1（文档偏重技术实现，符合技术文档特征）

---

## 三、评估指标

| 维度 | 值 | 状态 |
|------|-----|------|
| 概念数量 | 394 canonical | ✅ |
| 类型分布 | 技术 > 需求 | ✅ 合理 |
| 覆盖度 | 5.1 个/chunk | ✅ |
| 去重率 | 21% | ✅ 合理 |
| parent_hint 命中率 | 68.5% | ✅ |
| 连接覆盖率 | 43/394 = 10.9% | ⚠️ 偏低 |
| 平均质量分 | 0.648 | ✅ |

---

## 四、仍存在的问题

### 连接覆盖率偏低（10.9%）
- 只有 10.9% 的 concept 参与了连接
- 原因分析:
  1. 部分 requirement 没有对应的技术概念（孤立需求）
  2. 部分 technology 没有被任何需求引用（孤立技术）
  3. sub_requirement 和 sub_technology 之间的连接较少
- 改进方向:
  1. 降低 embedding 相似度阈值，扩大候选范围
  2. 增加跨层级连接（如 requirement 直接连接到 sub_technology）
  3. 人工审核孤立概念，补充连接

### 降级 Embedding
- 智谱 API 因限流（429）降级为 HashEmbedding
- 影响: embedding 相似度计算质量下降
- 建议: 增加 API 限流处理（降低并发、增加重试间隔）

---

## 五、下一步建议

1. **可视化验证**: 启动前端，查看 Concept 节点和语义连接边的渲染效果
2. **连接覆盖率优化**: 调整阈值或增加跨层级连接规则
3. **API 限流处理**: 优化 embedding 调用策略
4. **人工抽样**: 随机抽取 10-20 个连接，人工判断准确性
