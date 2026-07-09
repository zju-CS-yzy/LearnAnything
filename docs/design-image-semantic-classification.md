# LA-035 Phase 2: 图片语义分类策略设计

## 背景

PDF 提取出的图片 chunk 目前孤立存在，未与知识图谱的其他节点建立语义连接。这些图片包含多种类型：
- **流程图/架构图**：独立的系统结构描述
- **公式截图**：其他概念节点的数学表达
- **代码截图**：算法实现的可视化
- **表格/图表**：数据关系的可视化
- **示意图**：概念的可视化说明

## 目标

为每个图片 chunk 决定：
1. **自成独立语义节点**：图片本身代表一个独立的知识概念
2. **合并到现有概念节点**：图片是某个现有概念的说明/例证

## 策略分类方案

### Step 1: VLM 图片分析

使用 VLM（如 GPT-4V/Qwen-VL）对图片进行结构化分析，输出包含以下字段的描述：

```json
{
  "content_type": "flowchart|architecture|formula|code|table|chart|diagram|illustration|screenshot",
  "description": "图片内容的自然语言描述（100-300字）",
  "entities": ["图中出现的核心概念/实体列表"],
  "relationships": "图中表达的关系类型（如：流程顺序、层次结构、因果关系）",
  "complexity_score": 1-10,
  "standalone_assessment": "这张图片是否可以独立表达一个完整的知识概念？"
}
```

### Step 2: 分类决策树

```
                    ┌─────────────────────────────────────┐
                    │  VLM 分析结果                        │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────┴───────────────────┐
                    │ content_type 判断                    │
                    └─────────────────┬───────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          │                           │                           │
    【独立节点类型】              【需进一步判断】              【附属类型】
    flowchart                    architecture                  formula
    diagram (系统架构)            table                         code
    chart (复杂图表)              illustration                  screenshot
          │                           │                           │
          │                    ┌──────┴──────┐                    │
          │                    │ complexity  │                    │
          │                    │   score     │                    │
          │                    └──────┬──────┘                    │
          │                           │                           │
          │              ┌────────────┼────────────┐              │
          │              │            │            │              │
          │           >= 7          4-6         <= 3             │
          │              │            │            │              │
          │           【独立】    【检查关联】   【附属】         │
          │              │            │            │              │
          │              │    ┌───────┴───────┐    │              │
          │              │    │ 上下文匹配    │    │              │
          │              │    │ 找到关联概念?  │    │              │
          │              │    └───────┬───────┘    │              │
          │              │            │            │              │
          │              │      Yes / No          │              │
          │              │       /    \           │              │
          │              │   【合并】 【独立】    │              │
          └──────────────┴────────────┴──────────┴──────────────┘
```

### Step 3: 分类规则详解

#### 3.1 强制独立类型（无需判断，直接成节点）

| content_type | 原因 | 节点命名示例 |
|-------------|------|------------|
| `flowchart` | 表达完整流程/算法 | "XX流程图" |
| `architecture` | 系统/模块结构 | "XX系统架构" |
| `diagram` + complexity >= 7 | 复杂关系图 | "XX关系图" |
| `chart` + complexity >= 7 | 数据趋势/对比 | "XX趋势分析图" |

#### 3.2 强制附属类型（直接合并到最近的概念节点）

| content_type | 合并目标 | 合并方式 |
|-------------|---------|---------|
| `formula` | 公式相关的概念节点（如数学定义） | 将图片路径加入目标节点的 `metadata.image_refs` |
| `code` | 代码相关的概念节点（如算法实现） | 同上 |
| `screenshot` | 上下文最近的 chunk/concept | 同上 |
| `table` + complexity <= 3 | 简单数据表 | 同上 |

#### 3.3 模糊地带（需要上下文匹配判断）

**判断条件**：检查图片所在 PDF 页的邻近文本 chunk 中提取的 CanonicalConcept

```python
def find_best_merge_target(image_chunk, nearby_concepts, threshold=0.6):
    """
    找到图片最适合合并到的概念节点
    
    匹配策略：
    1. 实体重叠度：VLM 提取的 entities 与 concept.name 的相似度
    2. 描述语义相似度：VLM description 与 concept.description 的 embedding 余弦相似度
    3. 位置邻近度：图片页码与 concept 来源 chunk 页码的接近程度
    
    返回：最佳匹配 concept_id，如果最大相似度 < threshold 则返回 None（表示应独立）
    """
    pass
```

### Step 4: 边的建立

#### 4.1 独立图片节点

- 创建 `CanonicalConcept`（或专用 `ImageConcept`）节点
- 节点字段：
  ```
  name: "XX流程图" 或 "XX架构图"
  description: VLM 生成的详细描述
  concept_type: "visual_flowchart" / "visual_architecture" / ...
  image_path: 原图路径
  thumbnail_path: 缩略图路径
  ```
- 建立与邻近概念节点的语义边（如 `ILLUSTRATES` / `DEPENDS_ON`）

#### 4.2 附属图片（合并）

- 不创建新节点
- 在目标概念节点的 metadata 中增加：
  ```
  image_refs: ["path/to/image1.png", "path/to/image2.png"]
  ```
- 前端展示时，在概念节点详情面板中显示关联图片

## 关键问题讨论

### Q1: 如何判断图片是否"独立表达完整知识概念"？

**当前方案**：基于 `content_type` + `complexity_score` 的组合判断

**替代方案**：让 VLM 直接输出 `standalone_assessment` 字段（是/否），作为最终判断

**建议**：采用组合方案 — `content_type` 做初步分类，VLM 的 `standalone_assessment` 做复核，不一致时以 VLM 判断为准。

### Q2: 附属图片合并时，如果找不到匹配的概念节点怎么办？

**方案 A**：降级为独立节点（保守策略）
**方案 B**：创建一个通用的 "未分类图片说明" 节点聚合（可能导致节点膨胀）
**方案 C**：保持为孤立的图片 chunk，等待人工标注

**建议**：采用方案 A，避免信息丢失。

### Q3: 公式图片的特殊处理

公式图片通常有两种情况：
1. **定义公式**：如 "熵的定义式 H(X) = -Σp(x)log p(x)" → 属于"熵"概念节点
2. **推导公式**：仅在某一步骤中出现的中间公式 → 属于对应的推导/证明概念

**建议**：对 `formula` 类型，使用 VLM 提取公式中的关键变量名，与概念节点的 embedding 进行匹配。

### Q4: 性能考虑

VLM 调用成本较高，对于大量图片的 PDF 可能耗时较长。

**优化方案**：
1. 缩略图（200x200）送 VLM 分析，降低 token 消耗
2. 相同/相似图片（hash 去重）只分析一次
3. 异步处理：图片分析放入后台任务，不阻塞导入流程

## 实施步骤

### Phase 2.1: VLM 图片分析模块
- 新增 `ImageAnalyzer` 类，封装 VLM 调用
- 输出标准化的 JSON 分析结果
- 支持缓存（相同图片不重复分析）

### Phase 2.2: 分类决策引擎
- 实现 `classify_image_chunk()` 函数
- 实现 `find_best_merge_target()` 匹配算法
- 单元测试覆盖各种图片类型

### Phase 2.3: 节点创建/合并逻辑
- 独立图片 → 创建 `CanonicalConcept` 节点
- 附属图片 → 更新目标节点的 `image_refs`
- 建立图片节点与其他概念节点的语义边

### Phase 2.4: 前端展示优化
- 概念节点详情面板显示关联图片
- 图片节点详情面板显示 VLM 描述
- 支持图片点击查看大图

## 待决策点

请确认以下问题，以便进入实现阶段：

1. **VLM 选型**：使用现有 VLMClient（基于哪个模型？）还是需要接入新的多模态模型？
2. **分类阈值**：`complexity_score` 的分界点（当前草案：>=7 独立，<=3 附属，4-6 需判断）
3. **公式处理**：是否优先使用 pix2tex 提取 LaTeX，再结合文本匹配？
4. **独立图片节点类型**：是否创建新的节点类型（如 `ImageConcept`），还是复用现有 `CanonicalConcept`？
