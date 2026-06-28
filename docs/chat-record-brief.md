

---

## [2026-06-26] LearnAnything 前端 Markdown 渲染修复

**参与者：** 开发者、树状图（PM）
**时间：** 2026-06-26 23:23:59 ~ 2026-06-27 00:16:39 GMT+8

### 今日工作内容

**问题**：前端返回的 JSON 数据无法正确渲染为 Markdown 格式。

**第一轮尝试**：引入 `marked.js` v5+ 进行 Markdown 渲染
- 添加了 `marked.min.js` 引用和 Markdown CSS 样式
- 将 `apiAsk()` 从 `textContent` 改为 `innerHTML = marked.parse(data.answer)`
- **失败**：Qt WebEngine 的 Chromium 版本较老，不支持 `String.prototype.at()`（ES2022 API），前端报错 `t.at is not a function`

**第二轮尝试**：添加 `String.prototype.at()` polyfill
- 在 HTML `<head>` 中添加 polyfill 脚本
- 重新打包
- **失败**：网络下载 `marked.js` v4.3.0 超时，且 `lib/marked.min.js` 文件不存在导致打包中断

**第三轮尝试（成功）**：内联 Markdown 渲染器
- 完全移除外部的 `marked.js` 依赖
- 在 HTML 中内联实现 `renderMarkdown()` 函数
- 支持：粗体、斜体、标题、代码块、行内代码、列表、引用、水平线、链接、表格
- 重新打包成功
- **验证**：API 返回 Status 200，answer 长度 1,906，包含 Markdown 语法
- **前端测试**：自然语言回答正确显示，Markdown 格式正确渲染

### 核心变更

| 文件 | 变更 |
|:---|:---|
| `web/index.html` | 移除 `marked.js` 外部依赖，添加内联 `renderMarkdown()` 函数 |
| `web/index.html` | 添加 Markdown 渲染 CSS 样式（标题/列表/代码块/引用/表格） |
| `web/index.html` | `apiAsk()` 使用 `renderMarkdown(data.answer)` 替代 `textContent` |

### 技术要点

- Qt WebEngine（PyQt5）内置的 Chromium 版本较老，不支持 ES2022 的 `String.prototype.at()`
- 内联渲染器避免了外部依赖和网络下载问题
- 所有 Markdown 常用语法均已支持

---
