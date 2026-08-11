/**
 * LA-UI-001 M4: CommandExecutor —— 解析 Agent 返回的 CommandMessage，
 * 通过 EventBus 驱动左侧视图联动（设计文档 §3.2）。
 *
 * CommandMessage: { type:'command', command, target, payload }
 * 目前已接线：navigate/highlight → target 'graph'（GraphView 监听 'graph-command'）
 */
import { busEmit } from './eventBus.js'

export function executeCommand(cmd) {
  if (!cmd || typeof cmd !== 'object' || !cmd.command) return
  const payload = cmd.payload || {}

  switch (`${cmd.command}:${cmd.target}`) {
    case 'navigate:graph':
    case 'highlight:graph':
      busEmit('graph-command', { command: cmd.command, ...payload })
      break
    default:
      console.warn('[CommandExecutor] 未支持的命令:', cmd.command, cmd.target)
  }
}
