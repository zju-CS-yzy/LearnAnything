# LearnAnything Desktop App - 使用说明

## 验证结果

✅ **后端服务** (`backend_minimal.py`) — 已验证可正常启动，Flask 运行在 `http://127.0.0.1:5000`，健康检查通过。

✅ **桌面封装器** (`desktop_app.py`) — 代码结构正确，模块加载无错误。

⚠️ **GUI 窗口** — 当前环境（Kimi 桌面端后台进程）不支持 GUI 显示，这是预期行为。你需要在本地 Windows 桌面直接运行才能看到窗口。

---

## 文件结构

```
app/
├── desktop_app.py      # 桌面封装器（PyQt5 + QWebEngineView）
├── backend_minimal.py  # 最小后端（Flask，用于验证）
```

---

## 验证步骤（在本地 Windows 桌面执行）

### 1. 确保依赖已安装

```bash
cd D:\MyCS\AI\Project\LearnAnything
pip install PyQt5 PyQtWebEngine flask
```

### 2. 运行桌面应用

```bash
python app\desktop_app.py
```

预期效果：
- 弹出窗口显示 "LearnAnything - 知识学习系统"
- 顶部状态栏从 "正在启动后端服务..." 变为 "后端就绪，正在加载页面..."
- 最后显示一个绿色状态栏 "✅ 系统就绪"，然后隐藏，全屏展示前端页面

### 3. 验证内容

页面应显示：
- 标题："🎓 LearnAnything 桌面应用验证"
- 状态："✅ 后端 + WebView 运行正常"
- 三个卡片：后端服务、前端渲染、下一步

---

## 技术细节

### 启动流程

```
用户双击 desktop_app.py
    │
    ├─ 创建 QApplication + MainWindow
    ├─ 显示窗口（启动画面：状态栏 + 进度条）
    ├─ 后台线程启动 backend_minimal.py（Flask，端口 5000）
    ├─ 轮询 /api/health，最多等待 30 秒
    ├─ 后端就绪 → 加载 http://127.0.0.1:5000
    └─ QWebEngineView 渲染前端页面
```

### 关闭流程

```
用户点击关闭窗口
    │
    ├─ 触发 aboutToQuit 信号
    ├─ 调用 backend_thread.stop()
    ├─ 发送 terminate() 给后端进程
    ├─ 5 秒内未退出则 kill()
    └─ 应用退出
```

---

## 后续集成路线

验证通过后，接入现有 LearnAnything 系统的步骤：

| 步骤 | 操作 | 文件 |
|------|------|------|
| 1 | 将现有 `interfaces/cli.py` 的功能封装为 Flask API | 新建 `app/backend_api.py` |
| 2 | 前端页面替换为实际 UI（可用 Vue/React 或纯 HTML） | `web/` 目录 |
| 3 | `desktop_app.py` 指向新的后端入口 | 修改 `backend_script` 路径 |
| 4 | PyInstaller 打包为单文件 exe | `pyinstaller app/desktop_app.py` |

---

## 常见问题

**Q: 运行后窗口空白？**
A: 检查后端是否启动成功。在浏览器中访问 `http://127.0.0.1:5000/api/health`，看是否返回 JSON。

**Q: 端口被占用？**
A: 修改 `desktop_app.py` 中的 `BACKEND_PORT = 5000` 为其他端口（如 5001）。

**Q: 如何打包成 exe？**
A: 安装 PyInstaller 后执行：`pyinstaller --onefile --windowed app/desktop_app.py`

---

## 最小可行验证

如果不想运行完整 GUI，也可以单独验证后端：

```bash
python app\backend_minimal.py
```

然后在浏览器中打开 `http://127.0.0.1:5000`，看到验证页面即说明后端正常。
