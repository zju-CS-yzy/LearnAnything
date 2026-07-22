/**
 * ParadigmConfig.js — 范式配置管理
 * LA-052: 从后端 API 获取范式配置，消除前端对关系类型的硬编码
 */

let cachedConfig = null
let currentSubject = null
let loadPromise = null

/**
 * 加载当前学科的范式配置
 * @param {string} subject - 学科ID
 * @returns {Promise<Object>} 范式配置
 */
export async function loadParadigmConfig(subject) {
  if (cachedConfig && currentSubject === subject) {
    return cachedConfig
  }
  
  // 防止重复并发请求
  if (loadPromise && currentSubject === subject) {
    return loadPromise
  }
  
  loadPromise = fetch(`${window.location.origin}/api/knowledge-graph/${subject}/paradigm`)
    .then(async (resp) => {
      if (!resp.ok) {
        console.warn('[ParadigmConfig] 加载失败，使用 fallback:', resp.status)
        cachedConfig = getFallbackConfig()
        return cachedConfig
      }
      const data = await resp.json()
      cachedConfig = data
      currentSubject = subject
      return data
    })
    .catch((err) => {
      console.warn('[ParadigmConfig] 网络错误，使用 fallback:', err)
      cachedConfig = getFallbackConfig()
      return cachedConfig
    })
    .finally(() => {
      loadPromise = null
    })
  
  return loadPromise
}

/**
 * 判断是否为语义边（基于当前范式配置）
 * @param {string} edgeType - 边类型
 * @returns {boolean}
 */
export function isSemanticEdge(edgeType) {
  if (!cachedConfig) return false
  return cachedConfig.relations && cachedConfig.relations[edgeType] !== undefined
}

/**
 * 获取关系类型的中文标签
 * @param {string} type - 关系类型
 * @returns {string}
 */
export function getRelationLabel(type) {
  if (!cachedConfig || !cachedConfig.relations) return type
  return cachedConfig.relations[type] || type
}

/**
 * 获取关系类型的样式配置
 * @param {string} type - 关系类型
 * @returns {Object|null} { color, lineStyle, width }
 */
export function getRelationStyle(type) {
  if (!cachedConfig || !cachedConfig.styles) return null
  return cachedConfig.styles[type] || null
}

/**
 * 获取所有语义边类型列表
 * @returns {string[]}
 */
export function getSemanticEdgeTypes() {
  if (!cachedConfig || !cachedConfig.relations) return []
  return Object.keys(cachedConfig.relations)
}

/**
 * 获取当前缓存的范式配置
 * @returns {Object|null}
 */
export function getCachedConfig() {
  return cachedConfig
}

/**
 * 清除缓存（切换学科时调用）
 */
export function clearConfigCache() {
  cachedConfig = null
  currentSubject = null
  loadPromise = null
}

/**
 * Fallback 配置（向后兼容，API 失败时使用）
 */
function getFallbackConfig() {
  return {
    paradigm_id: 'fallback',
    name: '默认范式',
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
