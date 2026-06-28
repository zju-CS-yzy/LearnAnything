#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DesktopApp - LearnAnything 桌面封装器（PyInstaller 6 兼容版）

关键设计：
  - 所有导入在模块顶层，不放在 try/except 中（PyInstaller 静态分析可追踪）
  - 在 main() 中处理运行时错误，而非导入时
  - 路径解析兼容 PyInstaller 6 one-dir 模式（_internal/）

打包后运行：
    dist/LearnAnything.exe
"""

import sys
import os
import time
import threading
import traceback
from pathlib import Path

# ========== 路径设置（必须在任何导入之前） ==========
if getattr(sys, 'frozen', False):
    # PyInstaller 打包环境
    exe_dir = Path(sys.executable).parent
    internal_dir = exe_dir / '_internal'
    # 确保 _internal 在 sys.path 最前面（PyInstaller 6 的 PYZ 和模块在这里）
    if str(internal_dir) not in sys.path:
        sys.path.insert(0, str(internal_dir))
    # exe 目录也加入 sys.path
    if str(exe_dir) not in sys.path:
        sys.path.insert(0, str(exe_dir))
    # 设置 QtWebEngineProcess 路径（确保打包后能找到）
    qwebengine_path = internal_dir / 'PyQt5' / 'Qt5' / 'bin' / 'QtWebEngineProcess.exe'
    if qwebengine_path.exists():
        os.environ['QTWEBENGINEPROCESS_PATH'] = str(qwebengine_path)
        print(f"[Desktop] QtWebEngineProcess: {qwebengine_path}")
    else:
        print(f"[Desktop] WARNING: QtWebEngineProcess not found at {qwebengine_path}")
    print(f"[Desktop] exe_dir: {exe_dir}")
    print(f"[Desktop] internal_dir: {internal_dir}")
else:
    # 开发环境：项目根目录
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    print(f"[Desktop] dev mode, project_root: {project_root}")

# ========== 模块顶层导入（PyInstaller 可追踪） ==========
import uvicorn
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QMessageBox
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile
from PyQt5.QtCore import QUrl, Qt, QTimer

# 导入后端（必须在顶层，PyInstaller 6 的静态分析器才能追踪）
from app.backend_api import app as fastapi_app

# ========== 配置 ==========
BACKEND_PORT = 5000
BACKEND_HOST = "127.0.0.1"
FRONTEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
HEALTH_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/health"
MAX_WAIT_SECONDS = 30


class BackendThread(threading.Thread):
    """后台线程：运行 uvicorn 服务器"""

    def __init__(self):
        super().__init__(daemon=True)
        self._error = None

    def run(self):
        """启动 uvicorn"""
        try:
            config = uvicorn.Config(
                fastapi_app,
                host=BACKEND_HOST,
                port=BACKEND_PORT,
                log_level="warning",
                access_log=False,
                reload=False,
            )
            server = uvicorn.Server(config)
            server.run()
        except Exception as e:
            self._error = str(e)
            print(f"[BackendThread] 错误: {e}")
            traceback.print_exc()

    @property
    def error(self):
        return self._error


class MainWindow(QMainWindow):
    """主窗口：WebView 加载前端页面"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LearnAnything - 知识学习系统")
        self.setGeometry(200, 100, 1280, 800)
        self.setMinimumSize(800, 600)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.status_label = QLabel("正在启动后端服务...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #3498db;
                color: white;
                padding: 8px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.status_label)

        self.browser = QWebEngineView()

        # 清除 WebView 缓存，确保加载最新前端（每次启动都刷新）
        try:
            profile = self.browser.page().profile()
            profile.clearHttpCache()
            # 禁用磁盘缓存，防止旧文件被复用
            profile.setHttpCacheType(QWebEngineProfile.NoCache)
            print("[Desktop] WebView 缓存已清除")
        except Exception as e:
            print(f"[Desktop] 清除 WebView 缓存失败（非阻塞）: {e}")

        self.browser.setContextMenuPolicy(Qt.NoContextMenu)
        layout.addWidget(self.browser)

        self.browser.loadFinished.connect(self._on_page_loaded)

    def load_url(self, url):
        print(f"[Desktop] Loading URL: {url}")
        self.browser.load(QUrl(url))

    def _on_page_loaded(self, ok):
        print(f"[Desktop] Page load finished: ok={ok}, url={self.browser.url().toString()}")
        if ok:
            self.status_label.setText("✅ 系统就绪")
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #27ae60;
                    color: white;
                    padding: 8px;
                    font-size: 13px;
                }
            """)
            QTimer.singleShot(3000, self._hide_status_bar)
        else:
            self.status_label.setText("❌ 页面加载失败")
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #e74c3c;
                    color: white;
                    padding: 8px;
                    font-size: 13px;
                }
            """)
            # 尝试显示错误信息
            self.browser.page().toHtml(lambda html: print(f"[Desktop] Loaded HTML length: {len(html)}") if html else None)

    def _hide_status_bar(self):
        self.status_label.hide()

    def closeEvent(self, event):
        event.accept()


def wait_for_backend(timeout=MAX_WAIT_SECONDS):
    """轮询后端健康检查"""
    import urllib.request
    import urllib.error

    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(HEALTH_URL, method='GET')
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def show_error_dialog(title, message, detailed=None):
    """显示错误弹窗"""
    try:
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
        msg = QMessageBox()
        msg.setWindowTitle(title)
        msg.setText(message)
        if detailed:
            msg.setDetailedText(detailed)
        msg.setIcon(QMessageBox.Critical)
        msg.exec_()
    except Exception:
        print(f"[ERROR] {title}: {message}")
        if detailed:
            print(f"[DETAIL] {detailed}")


def main():
    """主入口"""
    print("[Desktop] Starting LearnAnything Desktop App...")
    print(f"[Desktop] sys.frozen={getattr(sys, 'frozen', False)}")
    print(f"[Desktop] sys.executable={sys.executable}")

    # 1. 检查 fastapi_app 是否已加载（导入时异常会在顶层抛出）
    try:
        _ = fastapi_app
        print("[Desktop] fastapi_app loaded OK")
    except Exception as e:
        show_error_dialog(
            "启动错误",
            "FastAPI 应用加载失败。请检查依赖是否安装。",
            traceback.format_exc()
        )
        sys.exit(1)

    # 2. 创建 Qt 应用
    app = QApplication(sys.argv)
    app.setApplicationName("LearnAnything")
    app.setApplicationDisplayName("LearnAnything 知识学习系统")

    # 3. 创建窗口
    window = MainWindow()
    window.show()
    app.processEvents()

    # 4. 启动后端线程
    print(f"[Desktop] 启动后端服务（{HEALTH_URL}）...")
    backend_thread = BackendThread()
    backend_thread.start()

    # 5. 等待后端就绪
    print(f"[Desktop] 等待后端就绪... (timeout={MAX_WAIT_SECONDS}s)")
    ready = wait_for_backend(timeout=MAX_WAIT_SECONDS)
    print(f"[Desktop] Backend ready={ready}")

    if ready:
        print(f"[Desktop] 后端已就绪，加载页面: {FRONTEND_URL}")
        window.status_label.setText("后端就绪，正在加载页面...")
        window.load_url(FRONTEND_URL)
    else:
        print(f"[Desktop] 后端启动超时！")
        error_detail = backend_thread.error or "后端未在 30 秒内启动，可能的原因：\n1. 端口 5000 被占用\n2. 依赖库缺失\n3. 知识库路径错误"
        window.status_label.setText("❌ 后端启动超时")
        window.status_label.setStyleSheet("""
            QLabel {
                background-color: #e74c3c;
                color: white;
                padding: 8px;
                font-size: 13px;
            }
        """)
        show_error_dialog(
            "后端启动失败",
            f"后端服务启动超时或失败。\n\n{error_detail}",
            traceback.format_exc()
        )

    # 6. 退出清理
    def on_app_exit():
        print("[Desktop] 应用关闭")

    app.aboutToQuit.connect(on_app_exit)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
