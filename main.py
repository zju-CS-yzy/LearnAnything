#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LearnAnything Desktop App
PyQt5 + WebView 封装 FastAPI 后端

打包命令：
    cd D:\MyCS\AI\Project\LearnAnything
    rmdir /s /q build dist
    pyinstaller app.spec --noconfirm
"""

import faulthandler
faulthandler.enable()

import sys
import os
import ctypes
from pathlib import Path

# 项目根目录
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ========== PyInstaller 环境初始化 ==========
if getattr(sys, 'frozen', False):
    base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    
    # 确保 DLL 搜索路径包含 _internal 目录
    if hasattr(os, 'add_dll_directory'):
        try:
            os.add_dll_directory(base)
        except Exception:
            pass

# ========== 模块顶层导入 ==========
import time
import threading
import traceback as _traceback

import uvicorn
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QMessageBox
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineProfile
from PyQt5.QtCore import QUrl, Qt, QTimer

from app.backend_api import app as fastapi_app


# ========== 配置 ==========
BACKEND_PORT = 5001
BACKEND_HOST = "127.0.0.1"
# FRONTEND_URL 指向 FastAPI 静态文件服务
# FastAPI 将 web/ 目录挂载到根路径，/ 自动返回 index.html
FRONTEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/"
# FRONTEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/simple.html"
HEALTH_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/health"
MAX_WAIT_SECONDS = 30


class DebugWebPage(QWebEnginePage):
    """自定义 WebPage，捕获 JavaScript 控制台消息和异常"""

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        level_names = {0: "DEBUG", 1: "INFO", 2: "WARNING", 3: "ERROR"}
        level_name = level_names.get(level, "UNKNOWN")
        print(f"[JS-{level_name}] {message} (line {lineNumber}, {sourceID})")

    def javaScriptAlert(self, frame, msg):
        print(f"[JS-ALERT] {msg}")
        return True

    def javaScriptConfirm(self, frame, msg):
        print(f"[JS-CONFIRM] {msg}")
        return True

    def javaScriptPrompt(self, frame, msg, defaultValue):
        print(f"[JS-PROMPT] {msg}")
        return True, defaultValue


class BackendThread(threading.Thread):
    """后台线程：运行 uvicorn 服务器"""

    def __init__(self):
        super().__init__(daemon=True)
        self._error = None

    def run(self):
        try:
            config = uvicorn.Config(
                fastapi_app,
                host=BACKEND_HOST,
                port=BACKEND_PORT,
                log_level="info",
                access_log=False,
                reload=False,
            )
            server = uvicorn.Server(config)
            server.run()
        except Exception as e:
            self._error = str(e)
            print(f"[BackendThread] 错误: {e}")
            _traceback.print_exc()

    @property
    def error(self):
        return self._error


class MainWindow(QMainWindow):
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
            QLabel { background-color: #3498db; color: white; padding: 8px; font-size: 13px; }
        """)
        layout.addWidget(self.status_label)

        self.browser = QWebEngineView()

        # 清除 WebView 缓存，确保加载最新前端（每次启动都刷新）
        try:
            profile = self.browser.page().profile()
            profile.clearHttpCache()
            profile.setHttpCacheType(QWebEngineProfile.NoCache)
            print("[Desktop] WebView 缓存已清除")
        except Exception as e:
            print(f"[Desktop] 清除 WebView 缓存失败（非阻塞）: {e}")

        self.browser.setPage(DebugWebPage())
        self.browser.setContextMenuPolicy(Qt.NoContextMenu)
        layout.addWidget(self.browser)

        self.browser.loadFinished.connect(self._on_page_loaded)

    def _on_page_loaded(self, ok):
        if ok:
            self.status_label.setText("✅ 系统就绪")
            self.status_label.setStyleSheet("QLabel { background-color: #27ae60; color: white; padding: 8px; }")
            QTimer.singleShot(3000, self._hide_status_bar)
        else:
            self.status_label.setText("❌ 页面加载失败")
            self.status_label.setStyleSheet("QLabel { background-color: #e74c3c; color: white; padding: 8px; }")

    def _hide_status_bar(self):
        self.status_label.hide()

    def load_url(self, url):
        self.browser.load(QUrl(url))

    def closeEvent(self, event):
        event.accept()


def wait_for_backend(timeout=MAX_WAIT_SECONDS):
    import urllib.request
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


def main():
    # 全局异常捕获，确保所有未捕获异常都被打印到控制台
    def global_exception_handler(exc_type, exc_value, exc_traceback):
        print("[FATAL] 未捕获异常:")
        print("".join(_traceback.format_exception(exc_type, exc_value, exc_traceback)))
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = global_exception_handler

    app = QApplication(sys.argv)
    app.setApplicationName("LearnAnything")
    app.setApplicationDisplayName("LearnAnything 知识学习系统")

    try:
        _ = fastapi_app
    except Exception as e:
        show_error_dialog("启动错误", "FastAPI 应用加载失败", _traceback.format_exc())
        sys.exit(1)

    window = MainWindow()
    window.show()
    app.processEvents()

    # 预加载 jieba 字典，避免后台线程中首次加载触发 Qt 线程冲突
    print("[Desktop] 预加载 jieba 分词字典...")
    try:
        import jieba
        list(jieba.cut("预加载分词字典"))
        print("[Desktop] jieba 预加载完成")
    except Exception as e:
        print(f"[Desktop] jieba 预加载失败（非致命）: {e}")

    print(f"[Desktop] 启动后端服务（{HEALTH_URL}）...")
    backend_thread = BackendThread()
    backend_thread.start()

    print(f"[Desktop] 等待后端就绪...")
    ready = wait_for_backend(timeout=MAX_WAIT_SECONDS)

    if ready:
        print(f"[Desktop] 后端已就绪，加载页面...")
        window.status_label.setText("后端就绪，正在加载页面...")
        window.load_url(FRONTEND_URL)
    else:
        error_detail = backend_thread.error or "后端未启动，可能原因：端口被占用 / 依赖缺失 / 知识库路径错误"
        window.status_label.setText("❌ 后端启动超时")
        window.status_label.setStyleSheet("QLabel { background-color: #e74c3c; color: white; padding: 8px; }")
        show_error_dialog("后端启动失败", f"后端服务启动超时。\n\n{error_detail}", _traceback.format_exc())

    def on_app_exit():
        print("[Desktop] 应用关闭")

    app.aboutToQuit.connect(on_app_exit)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
