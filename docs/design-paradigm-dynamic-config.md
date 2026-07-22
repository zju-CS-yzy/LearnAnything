# LA-052: 范式配置动态获取方案设计

> 目标：消除前端对关系类型的硬编码，通过 API 从后端获取当前学科的范式配置，实现前后端范式定义统一。

---

## 1. 问题分析

### 当前状态

| 层级 | 硬编码位置 | 内容 |
|:---|:---|:---|
| 后端 | `semantic_linker.py` | `PARADIGM_LEVELS` 硬编码（已修复为 YAML 优先） |
| 后端 | `graph_store.py` | `SCHEMA_DEFINITIONS` 硬编码关系表 |
| 前端 | `GraphLayout.js` | `SOLUTION`/`DEPENDS_ON`/`IMPLEMENTS`/`DEPEND_ON` 判断 |
| 前端 | `GraphStyles.js` | CSS selector 硬编码 `edge[type="SOLUTION"]` |
| 前端 | `GraphView.vue` | legend 文字硬编码 |
| 前端 | `NodeDetailPanel.vue` | CSS class 硬编码 |

### 根本问题

1. **范式配置分散**：YAML → 后端代码 → 前端代码，任何修改需要改 3 处
2. **前端无法感知新范式**：如果用户新增自定义范式（如 `medical`），前端完全不支持
3. **样式与数据耦合**：边颜色、label 映射写死在 CSS 和 JS 中

---

## 2. 设计方案

### 2.1 后端 API 扩展

#### 新增 API: 获取范式配置

```
GET /api/knowledge-graph/{subject}/paradigm
```

**响应格式**:
```json
{
  "paradigm_id": "engineering",
  "name": "工程分解",
  "levels": ["requirement", "technology"],
  "types": {
    "requirement": "需求",
    "technology": "技术"
  },
  "relations": {
    "IMPLEMENTS": "实现",
    "DEPEND_ON": "依赖"
  },
  "relation_map": {
    "requirement": {
      "IMPLEMENTS": ["technology"]
    },
    "technology": {
      "DEPEND_ON": ["requirement"]
    }
  },
  "cyclic": true,
  "cycle_pattern": ["requirement", "technology"],
  "styles": {
    "IMPLEMENTS": {
      "color": "#e67e22",
      "lineStyle": "solid",
      "width": 2
    },
    "DEPEND_ON": {
      "color": "#9b59b6",
      "lineStyle": "dashed",
      "width": 1.5
    }
  }
}
```

#### 扩展 API: 获取概念链接

已有的 `/concept-links` 返回的 edge.type 保持不变（即实际关系名），前端根据 paradigm 配置进行 label 映射。

### 2.2 数据流

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ paradigms   │────▶│ 后端 API     │────▶│ 前端缓存    │
│ .yaml       │     │ /paradigm    │     │ paradigm    │
└─────────────┘     └──────────────┘     │ Config      │
                                         └──────┬──────┘
                                                │
                       ┌────────────────────────┼────────────────────────┐
                       ▼                        ▼                        ▼
              ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
              │ GraphLayout.js  │    │ GraphStyles.js  │    │ GraphView.vue   │
              │ 动态语义边判断  │    │ 动态CSS生成     │    │ 动态图例渲染    │
              └─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 2.3 前端架构调整

#### 新增模块: `ParadigmConfig.js`

```javascript
// ParadigmConfig.js — 范式配置管理

let cachedConfig = null
let currentSubject = null

/**
 * 加载当前学科的范式配置
 */
export async function loadParadigmConfig(subject) {
  if (cachedConfig && currentSubject === subject) {
    return cachedConfig
  }
  
  const resp = await fetch(
    `${window.location.origin}/api/knowledge-graph/${subject}/paradigm`
  )
  if (!resp.ok) {
    console.warn('[ParadigmConfig] 加载失败，使用 fallback')
    cachedConfig = getFallbackConfig()
    return cachedConfig
  }
  
  cachedConfig = await resp.json()
  currentSubject = subject
  return cachedConfig
}

/**
 * 判断是否为语义边（基于当前范式配置）
 */
export function isSemanticEdge(edgeType, config = null) {
  const cfg = config || cachedConfig
  if (!cfg) return false
  return cfg.relations && cfg.relations[edgeType] !== undefined
}

/**
 * 获取关系类型的中文标签
 */
export function getRelationLabel(type, config = null) {
  const cfg = config || cachedConfig
  if (!cfg || !cfg.relations) return type
  return cfg.relations[type] || type
}

/**
 * 获取关系类型的样式配置
 */
export function getRelationStyle(type, config = null) {
  const cfg = config || cachedConfig
  if (!cfg || !cfg.styles) return null
  return cfg.styles[type] || cfg.styles['default'] || null
}

/**
 * 获取所有语义边类型列表
 */
export function getSemanticEdgeTypes(config = null) {
  const cfg = config || cachedConfig
  if (!cfg || !cfg.relations) return []
  return Object.keys(cfg.relations)
}

/**
 * Fallback 配置（向后兼容）
 */
function getFallbackConfig() {
  return {
    relations: {
      'SOLUTION': '解决',
      'DEPENDS_ON': '依赖',
      'IMPLEMENTS': '实现',
      'DEPEND_ON': '依赖',
    },
    styles: {
      'SOLUTION': { color: '#e67e22', lineStyle: 'solid', width: 2 },
      'DEPENDS_ON': { color: '#9b59b6', lineStyle: 'dashed', width: 1.5 },
      'IMPLEMENTS': { color: '#e67e22', lineStyle: 'solid', width: 2 },
      'DEPEND_ON': { color: '#9b59b6', lineStyle: 'dashed', width: 1.5 },
    }
  }
}
```

#### GraphLayout.js 改造

```javascript
// 移除硬编码的 SOLUTION/DEPENDS_ON/IMPLEMENTS/DEPEND_ON 判断
// 使用导入的 isSemanticEdge() / getRelationLabel()

import { isSemanticEdge, getRelationLabel } from './ParadigmConfig.js'

// 改造前:
const semanticEdges = cy.edges().filter(e => {
  const t = e.data('type')
  return t === 'SOLUTION' || t === 'DEPENDS_ON' || t === 'IMPLEMENTS' || t === 'DEPEND_ON'
})

// 改造后:
const semanticEdges = cy.edges().filter(e => {
  return isSemanticEdge(e.data('type'))
})
```

#### GraphStyles.js 改造

```javascript
// 移除硬编码的 edge[type="SOLUTION"] CSS selector
// 改为动态生成样式

import { getSemanticEdgeTypes, getRelationStyle } from './ParadigmConfig.js'

export function buildDynamicStyles(config) {
  const styles = [...baseStyles]
  
  const edgeTypes = getSemanticEdgeTypes(config)
  for (const type of edgeTypes) {
    const style = getRelationStyle(type, config)
    if (style) {
      styles.push({
        selector: `edge[type="${type}"]`,
        style: {
          'line-color': style.color,
          'target-arrow-color': style.color,
          'line-style': style.lineStyle,
          'width': style.width,
          'target-arrow-shape': 'triangle',
          'arrow-scale': 0.8,
        }
      })
    }
  }
  
  return styles
}
```

#### GraphView.vue 改造

```vue
<!-- 图例动态渲染 -->
<div class="legend-section">
  <div v-for="(label, type) in paradigmConfig.relations" :key="type" class="legend-item">
    <span class="legend-line" :style="getLegendStyle(type)"></span>
    <span>{{ label }} ({{ type }})</span>
  </div>
</div>
```

---

## 3. 后端实现要点

### 3.1 新增 API 路由

```python
@app.get("/api/knowledge-graph/{subject}/paradigm")
def get_paradigm_config(subject: str):
    """获取指定学科的范式配置"""
    from core.semantic_linker import _PARADIGMS_YAML
    
    # 从 YAML 读取范式配置
    paradigm_id = get_subject_paradigm(subject)  # 从学科配置或数据库读取
    config = _PARADIGMS_YAML.get(paradigm_id)
    
    if not config:
        raise HTTPException(404, f"范式配置未找到: {paradigm_id}")
    
    # 组装响应（增加 styles 字段）
    return {
        "paradigm_id": paradigm_id,
        "name": config.get("name", paradigm_id),
        "levels": list(config.get("types", {}).keys()),
        "types": config.get("types", {}),
        "relations": config.get("relations", {}),
        "relation_map": config.get("relation_map", {}),
        "cyclic": config.get("cyclic", False),
        "cycle_pattern": config.get("cycle_pattern", []),
        "styles": build_relation_styles(config.get("relations", {}).keys()),
    }

def build_relation_styles(relation_types):
    """为每种关系类型分配默认样式"""
    default_styles = {
        'SOLUTION': {'color': '#e67e22', 'lineStyle': 'solid', 'width': 2},
        'DEPENDS_ON': {'color': '#9b59b6', 'lineStyle': 'dashed', 'width': 1.5},
        'IMPLEMENTS': {'color': '#e67e22', 'lineStyle': 'solid', 'width': 2},
        'DEPEND_ON': {'color': '#9b59b6', 'lineStyle': 'dashed', 'width': 1.5},
    }
    result = {}
    for rt in relation_types:
        result[rt] = default_styles.get(rt, {
            'color': '#95a5a6',
            'lineStyle': 'solid',
            'width': 1.5,
        })
    return result
```

### 3.2 学科配置扩展

```json
// config/subjects/rag.json
{
  "id": "rag",
  "name": "RAG技术",
  "paradigm": "engineering",
  "description": "检索增强生成技术"
}
```

---

## 4. 实施计划

| 步骤 | 内容 | 文件 |
|:---|:---|:---|
| 1 | 后端：新增 `/paradigm` API | `app/main.py` 或新增 router |
| 2 | 后端：YAML 配置增加 `styles` 字段 | `config/paradigms.yaml` |
| 3 | 前端：新增 `ParadigmConfig.js` | `web-vue/src/components/graph/ParadigmConfig.js` |
| 4 | 前端：`GraphLayout.js` 使用动态配置 | 替换硬编码判断 |
| 5 | 前端：`GraphStyles.js` 动态生成样式 | 替换硬编码 CSS |
| 6 | 前端：`GraphView.vue` 动态渲染图例 | 替换硬编码 legend |
| 7 | 前端：`NodeDetailPanel.vue` 动态样式 | 替换硬编码 CSS |
| 8 | 测试：切换不同范式学科验证 | engineering/theory/hierarchical |

---

## 5. 向后兼容

- `ParadigmConfig.js` 提供 fallback 配置（支持旧类型 SOLUTION/DEPENDS_ON）
- API 失败时前端使用 fallback，不影响现有功能
- `graph_store.py` 的 `_ensure_paradigm_rel_tables()` 继续确保关系表存在

---

## 6. 长期收益

1. **新增范式零前端修改**：只需更新 YAML + 重启后端
2. **自定义范式支持**：用户可定义自己的范式，前端自动适配
3. **样式集中管理**：边颜色、线型在 YAML 中配置
4. **多范式并存**：不同学科使用不同范式，前端动态切换
