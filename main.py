#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LearnAnything Desktop App
PyQt5 + WebView 封装 FastAPI 后端

打包命令：
    cd <LearnAnything-Dev 项目目录>
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

_PROCESS_STARTED_AT = time.monotonic()

import uvicorn
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QMessageBox
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineProfile
from PyQt5.QtCore import QUrl, Qt, QTimer, QThread, pyqtSignal

from app.backend_api import app as fastapi_app
from app.startup_monitor import monitor_backend_startup


# ========== 配置 ==========
BACKEND_PORT = 5001
BACKEND_HOST = "127.0.0.1"
# FRONTEND_URL 指向 FastAPI 静态文件服务
# FastAPI 将 web/ 目录挂载到根路径，/ 自动返回 index.html
FRONTEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/"
# FRONTEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/simple.html"
HEALTH_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/health"
SLOW_START_SECONDS = 30
MAX_WAIT_SECONDS = 180
_startup_log_lock = threading.Lock()


def get_startup_log_path() -> Path:
    from config.settings import DATA_ROOT
    return DATA_ROOT / "logs" / "desktop_startup.log"


def startup_log(message: str) -> None:
    """Write a small persistent phase log for packaged-startup diagnostics."""
    elapsed = time.monotonic() - _PROCESS_STARTED_AT
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} +{elapsed:7.2f}s {message}"
    print(f"[Desktop] {line}")
    try:
        log_path = get_startup_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with _startup_log_lock:
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(line + "\n")
    except Exception as exc:
        print(f"[Desktop] 启动日志写入失败（非阻塞）: {exc}")


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
            startup_log(f"后端线程开始，监听 {BACKEND_HOST}:{BACKEND_PORT}")
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
            if not server.started:
                self._error = "Uvicorn 已退出，但没有成功绑定后端端口。"
                startup_log(self._error)
        except BaseException as e:
            self._error = f"{type(e).__name__}: {e}"
            startup_log(f"后端线程异常：{self._error}")
            print(f"[BackendThread] 错误: {e}")
            _traceback.print_exc()

    @property
    def error(self):
        return self._error


class BackendMonitorThread(QThread):
    """异步监测后端，避免阻塞 Qt 主界面和误判首次冷启动。"""

    ready = pyqtSignal(float)
    slow = pyqtSignal(float)
    failed = pyqtSignal(str, float)

    def __init__(self, backend_thread):
        super().__init__()
        self.backend_thread = backend_thread

    def run(self):
        result = monitor_backend_startup(
            self.backend_thread,
            HEALTH_URL,
            slow_after=SLOW_START_SECONDS,
            timeout=MAX_WAIT_SECONDS,
            on_slow=self.slow.emit,
            should_stop=self.isInterruptionRequested,
        )
        if result.state == "ready":
            self.ready.emit(result.elapsed)
        elif result.state == "failed":
            self.failed.emit(result.detail, result.elapsed)


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
    startup_log(f"桌面进程启动，frozen={getattr(sys, 'frozen', False)}")
    # 全局异常捕获，确保所有未捕获异常都被打印到控制台
    def global_exception_handler(exc_type, exc_value, exc_traceback):
        print("[FATAL] 未捕获异常:")
        print("".join(_traceback.format_exception(exc_type, exc_value, exc_traceback)))
        # 写入日志文件以便排查
        try:
            from config.settings import DATA_ROOT
            log_path = DATA_ROOT / "crash.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"Crash at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("".join(_traceback.format_exception(exc_type, exc_value, exc_traceback)))
            print(f"[FATAL] 崩溃日志已保存到: {log_path}")
        except Exception:
            pass
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
    startup_log("Qt 主窗口已显示")

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

    startup_log(
        f"异步等待后端，{SLOW_START_SECONDS}s 后提示冷启动，"
        f"硬超时 {MAX_WAIT_SECONDS}s"
    )
    monitor = BackendMonitorThread(backend_thread)
    window.backend_monitor = monitor
    startup_finished = False

    def on_backend_ready(elapsed):
        nonlocal startup_finished
        if startup_finished:
            return
        startup_finished = True
        startup_log(f"后端健康检查通过，用时 {elapsed:.2f}s；开始加载页面")
        window.status_label.setText("后端就绪，正在加载页面...")
        window.load_url(FRONTEND_URL)

    def on_backend_slow(elapsed):
        if startup_finished:
            return
        startup_log(f"后端冷启动已耗时 {elapsed:.2f}s，继续等待")
        window.status_label.setText("首次启动初始化时间较长，仍在继续，请稍候...")
        window.status_label.setStyleSheet(
            "QLabel { background-color: #f39c12; color: white; padding: 8px; }"
        )

    def on_backend_failed(error_detail, elapsed):
        nonlocal startup_finished
        if startup_finished:
            return
        startup_finished = True
        startup_log(f"后端启动失败，用时 {elapsed:.2f}s：{error_detail}")
        window.status_label.setText("❌ 后端启动失败")
        window.status_label.setStyleSheet("QLabel { background-color: #e74c3c; color: white; padding: 8px; }")
        show_error_dialog(
            "后端启动失败",
            f"后端服务未能启动。\n\n{error_detail}",
            f"启动日志：{get_startup_log_path()}",
        )

    monitor.ready.connect(on_backend_ready)
    monitor.slow.connect(on_backend_slow)
    monitor.failed.connect(on_backend_failed)
    monitor.start()

    def on_app_exit():
        startup_log("桌面应用关闭")
        monitor.requestInterruption()
        monitor.wait(3000)

    app.aboutToQuit.connect(on_app_exit)
    
    # 进入主事件循环
    exit_code = app.exec_()
    print(f"[Desktop] 退出码: {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
