#!/usr/bin/env python3
"""
桌面应用入口 — 打包为 .exe 后使用此入口
"""
import sys
import os
import uvicorn

# PyInstaller 打包后的路径处理
if getattr(sys, 'frozen', False):
    # 打包后的路径：sys._MEIPASS 指向 _internal 目录
    PROJECT_ROOT = os.path.dirname(sys._MEIPASS)
else:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 将项目根目录添加到 Python 路径
sys.path.insert(0, PROJECT_ROOT)

from app.backend_api import app

if __name__ == "__main__":
    # 使用 127.0.0.1:5000，避免 Windows 防火墙弹窗
    uvicorn.run(app, host="127.0.0.1", port=5000, log_level="info")
