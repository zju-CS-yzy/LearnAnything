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

### 2.1 complexity_score 计算方法

`complexity_score` 是 VLM 对图片内容复杂度的量化评估，1-10 分。评分基于以下维度：

```
complexity_score = 基础分(content_type) + 元素复杂度 + 结构复杂度 + 语义深度

其中各项权重和计算方式：
```

#### 维度 1: 基础分（由 content_type 决定）

| content_type | 基础分 | 原因 |
|-------------|--------|------|
| `screenshot` | 1-2 | 纯展示，无结构 |
| `formula` | 2-4 | 数学表达，有结构但单一 |
| `code` | 3-5 | 有语法结构，复杂度可变 |
| `illustration` | 3-5 | 示意图，结构简单 |
| `table` | 3-6 | 行列结构，复杂度取决于规模 |
| `chart` | 4-7 | 数据可视化，有坐标/图例 |
| `diagram` | 5-8 | 概念关系图，有节点和边 |
| `flowchart` | 6-9 | 流程控制，有分支和循环 |
| `architecture` | 7-10 | 系统架构，多层次多模块 |

#### 维度 2: 元素复杂度（1-3 分）

VLM 统计图片中的关键元素数量：
- 1 分: 单一元素（如一个公式、一张截图）
- 2 分: 3-10 个元素（如简单流程图、小表格）
- 3 分: >10 个元素（如复杂架构图、大型流程图）

#### 维度 3: 结构复杂度（1-3 分）

- 1 分: 线性/平铺结构（如列表、顺序流程）
- 2 分: 层次/树形结构（如分类图、模块层次）
- 3 分: 网状/复杂交互结构（如状态机、多对多关系）

#### 维度 4: 语义深度（1-2 分）

- 1 分: 纯描述性（如截图、简单示意）
- 2 分: 包含推理/判断逻辑（如决策树、条件流程）

#### 最终评分示例

| 图片类型 | 基础分 | 元素 | 结构 | 语义 | 总分 | 分类 |
|---------|--------|------|------|------|------|------|
| 简单公式 H(X)=... | 3 | 1 | 1 | 1 | 6 | 模糊(需判断) |
| 截图 | 1 | 1 | 1 | 1 | 4 | 附属 |
| 3步流程图 | 7 | 2 | 2 | 1 | 12→10(封顶) | 独立 |
| 复杂系统架构 | 8 | 3 | 3 | 2 | 16→10(封顶) | 独立 |
| 数据表格(5x3) | 4 | 2 | 1 | 1 | 8 | 模糊(需判断) |
| 决策树 | 7 | 2 | 3 | 2 | 14→10(封顶) | 独立 |

**注**: 总分超过 10 按 10 封顶。最终分类阈值：>=7 独立，<=3 附属，4-6 需上下文匹配。

---

### 2.2 分类决策树

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

## 前人方案调研与对比

### MegaRAG (2026, arXiv:2512.20626v2)

**核心思路**：使用 MLLM（如 GPT-4o）对 PDF 每页进行实体关系提取，构建多模态知识图谱（MMKG）。

**图片处理方式**：
- 使用 MinerU 预处理 PDF，提取文本、图片、表格
- 每页的图片作为**单个实体**（single entity）处理
- 通过两轮精炼（refinement）改善跨模态关联
- 图片与其他文本实体通过 `text-to-figure` 关系连接

**与我们的方案对比**：
| 维度 | MegaRAG | 我们的方案 |
|------|---------|-----------|
| 图片粒度 | 每页的图片作为一个整体实体 | 每个内嵌图片独立处理 |
| 分类策略 | 全部作为独立实体，无合并逻辑 | 根据复杂度判断独立/合并 |
| 关系类型 | `text-to-figure` | `ILLUSTRATES`/`DEPENDS_ON`/`MERGED_TO` |
| 精炼策略 | 两轮全局子图精炼 | 基于上下文匹配的局部关联 |

**借鉴点**：
- MinerU 预处理思路可以借鉴，但我们直接用 PyMuPDF + VLM 更轻量
- 图片作为实体的思路与我们"独立节点"方案一致
- **不足**：MegaRAG 未处理"图片应合并到文本概念"的场景（如公式截图）

---

### RAG-Anything (2026, NextFuture Blog)

**核心思路**：基于 LightRAG 的多模态 pipeline，使用 GPT-4o-mini 处理文本，GPT-4o 处理图片。

**图片处理方式**：
- MinerU 提取 PDF 中的图片和布局
- GPT-4o（vision）生成图片描述
- 图片描述作为文本 chunk 存入向量库
- 知识图谱中图片作为独立节点

**关键经验**（来自作者的踩坑记录）：
1. **GPT-4o-mini 不适合 vision 任务**："gpt-4o-mini accepts multimodal message payloads and returns a response without error, producing hallucinated chart descriptions with no warning. Reserve gpt-4o-mini exclusively for text-only graph queries and keep vision_func on gpt-4o."
2. **图片处理成本高**："due to the high computational and preprocessing costs associated with figures and images, the scale of our multimodal dataset is still relatively limited."

**借鉴点**：
- VLM 选型教训： vision 任务不能用便宜的模型
- 成本考虑：图片处理开销大，需要控制调用频率

---

### MMGraphRAG (GitHub: wanxueyao/MMGraphRAG)

**核心思路**：YOLO + MLLM 将图片转为**场景图**（scene graph），再与文本 KG 融合。

**图片处理方式**：
- YOLO 分割图片中的对象
- MLLM 识别对象间关系
- 生成场景图（类似：物体A -[关系]-> 物体B）
- 光谱聚类融合文本 KG 和图片场景图

**与我们的方案对比**：
- MMGraphRAG 走"细粒度场景图"路线，我们走"粗粒度语义分类"路线
- 场景图适合图片密集的应用（如视觉问答），我们的方案更适合文档知识库

**借鉴点**：
- 细粒度图片分析可以作为未来扩展
- 光谱聚类融合思路可以借鉴到我们的"模糊地带"判断

---

### 关键结论

1. **前人方案的共同特点**：
   - 所有方案都将图片作为**独立实体/节点**处理
   - **没有方案专门处理"图片应合并到文本概念"的场景**
   - 公式截图、代码截图等"附属图片"在前人方案中也被当作独立实体

2. **我们的创新点**：
   - 首次提出**图片语义分类**（独立 vs 附属）的两级策略
   - 基于 `complexity_score` 的自动化分类决策
   - 附属图片通过 `image_refs` 关联到现有概念，避免节点膨胀

3. **前人方案的不足（我们的改进机会）**：
   - MegaRAG: 图片全部独立 → 知识图谱节点过多，影响查询效率
   - RAG-Anything: 图片描述作为文本 chunk → 丢失视觉结构信息
   - MMGraphRAG: 场景图粒度太细 → 不适合文档型知识库

## 待决策点

请确认以下问题，以便进入实现阶段：

1. **VLM 选型**：使用现有 VLMClient（基于哪个模型？）还是需要接入新的多模态模型？
2. **分类阈值**：`complexity_score` 的分界点（当前草案：>=7 独立，<=3 附属，4-6 需判断）
3. **公式处理**：是否优先使用 pix2tex 提取 LaTeX，再结合文本匹配？
4. **独立图片节点类型**：是否创建新的节点类型（如 `ImageConcept`），还是复用现有 `CanonicalConcept`？
