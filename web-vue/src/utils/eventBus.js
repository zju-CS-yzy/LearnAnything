/**
 * LA-UI-001 M4: 轻量 EventBus —— window CustomEvent 的规范化封装。
 *
 * busOn 返回解绑函数，组件卸载时必须调用以避免泄漏。
 * 事件命名约定：<域>-<动作>，如 'graph-command'、'share-to-chat'。
 */
export function busOn(name, callback) {
  const handler = (e) => callback(e.detail)
  window.addEventListener(name, handler)
  return () => window.removeEventListener(name, handler)
}

export function busEmit(name, detail) {
  window.dispatchEvent(new CustomEvent(name, { detail }))
}
