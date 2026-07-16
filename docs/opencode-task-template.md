# OpenCode 任务协作规范

> 版本: v1.0
> 创建: 2026-07-16
> 用途: 规范 OpenClaw 与 OpenCode 之间的任务委派流程

---

## 一、工作流

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   用户      │────→│  OpenClaw   │────→│ OpenCode    │────→│  OpenClaw   │
│  提出任务   │     │ 生成prompt  │     │ 执行并输出  │     │ 审查结果    │
└─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                    │
                              ┌─────────────────────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   结果判断          │
                    ├─────────────────────┤
                    │ 成功 → 更新文档     │
                    │ 失败 → 自行修复     │
                    │ 不确定 → 向用户汇报 │
                    └─────────────────────┘
```

**OpenClaw 职责**:
- 读取项目上下文（代码、文档、遗留问题）
- 生成完整的任务 Prompt（含必读文档、参考文件、约束条件）
- 调用 `opencode run` 执行
- 审查返回的 diff / 输出
- 更新项目文档、记录决策

**OpenCode 职责**:
- 按 Prompt 读取指定的本地文件
- 执行代码修改
- 返回执行结果（成功 / 失败 + 变更摘要）

**用户职责**:
- 提出需求和目标
- 确认 OpenCode 产出的重大变更
- 验收最终效果

---

## 二、OpenCode 任务 Prompt 模板

```markdown
# 任务：[LA-编号-名称]

## 项目上下文
- **项目名称**: LearnAnything
- **项目路径**: D:\MyCS\AI\Project\LearnAnything
- **前端路径**: web-vue/src/
- **后端路径**: core/

## 必读项目文档（执行前先读取）
- D:\MyCS\AI\Project\LearnAnything\docs\design.md — 项目架构设计
- D:\MyCS\AI\Project\LearnAnything\docs\effective-decisions.md — 有效决策记录
- D:\MyCS\AI\Project\LearnAnything\AGENTS.md — 项目规范
- D:\MyCS\AI\Project\LearnAnything\docs\leftover-problem.md — 遗留问题列表

## 问题描述
[清晰描述当前问题和期望行为]

## 当前状态
[相关文件路径、当前实现的关键代码片段]

## 期望行为
[描述修复/实现后应该达到的效果]

## 约束条件
- [ ] 不破坏现有功能
- [ ] 逐行注释新添加的代码
- [ ] 仅在必要时修改后端 API 结构
- [ ] 保持向后兼容
- [ ] 不泄露 API Key 等敏感信息

## 参考文件
- 文件1: [绝对路径] — [说明]
- 文件2: [绝对路径] — [说明]

## 验收标准
- [ ] 功能正确性: [具体验证方式]
- [ ] 代码质量: [审查要点]

## 建议实现步骤
1. [步骤1]
2. [步骤2]
3. [步骤3]
```

---

## 三、OpenCode 调用规范

### 基础命令
```powershell
cd D:\MyCS\AI\Project\LearnAnything; opencode run "[prompt内容]" --model deepseek/deepseek-chat --auto
```

### 关键参数
| 参数 | 说明 |
|------|------|
| `--auto` | 自动批准工具调用，无需人工确认 |
| `--model deepseek/deepseek-chat` | 指定 DeepSeek 模型 |
| `--continue` | 继续上一轮会话（手动管理 session ID） |

### 注意事项
1. **每次 `run` 都是独立会话**，上下文不保留
2. **OpenCode 不会反问**，遇到歧义会按自身理解执行
3. **失败时不会自动重试**，需要我（OpenClaw）分析后决定是否重新生成 prompt
4. **输出是文本格式**，需要解析关键信息

---

## 四、任务状态记录

每次 OpenCode 任务完成后，OpenClaw 需要更新以下文档：

1. `docs/leftover-problem.md` — 如果任务修复了某个遗留问题
2. `memory/YYYY-MM-DD.md` — 记录今日完成的任务
3. `docs/effective-decisions.md` — 如果产生了新的设计决策

---

## 五、版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-07-16 | 初始版本 |
