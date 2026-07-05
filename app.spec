# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec 文件 — LearnAnything 桌面应用
打包方式：
    cd D:\MyCS\AI\Project\LearnAnything
    rmdir /s /q build dist
    pyinstaller app.spec --noconfirm

输出：
    dist/LearnAnything/LearnAnything.exe
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

project_root = Path('D:\\MyCS\\AI\\Project\\LearnAnything')

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

block_cipher = None

# ========== 收集数据文件（前端、配置、知识库） ==========

def collect_files(directory, prefix):
    """递归收集目录下所有文件，返回 (src, dest) 元组列表"""
    result = []
    if not os.path.exists(directory):
        return result
    for root, dirs, files in os.walk(directory):
        for file in files:
            src = os.path.join(root, file)
            rel_dir = os.path.relpath(root, directory)
            if rel_dir == '.':
                dest = prefix
            else:
                dest = os.path.join(prefix, rel_dir).replace('\\', '/')
            result.append((src, dest))
    return result


added_files = []

# 前端文件
added_files.extend(collect_files(str(project_root / "web"), "web"))

# 配置文件
added_files.extend(collect_files(str(project_root / "config"), "config"))

# 知识库目录（排除运行时生成的数据库目录，只保留原始资料）
def collect_files_exclude_db(directory, prefix):
    """递归收集目录下所有文件，排除 graph_db 和 vector_db 子目录"""
    result = []
    if not os.path.exists(directory):
        return result
    for root, dirs, files in os.walk(directory):
        # 排除运行时生成的数据库目录
        dirs[:] = [d for d in dirs if d not in ('graph_db', 'vector_db', 'cache')]
        for file in files:
            src = os.path.join(root, file)
            rel_dir = os.path.relpath(root, directory)
            if rel_dir == '.':
                dest = prefix
            else:
                dest = os.path.join(prefix, rel_dir).replace('\\', '/')
            result.append((src, dest))
    return result

added_files.extend(collect_files_exclude_db(str(project_root / "knowledge_base"), "knowledge_base"))


# ========== 收集本地 Python 包的子模块 ==========

local_packages = ['app', 'agents', 'core', 'config', 'interfaces']
extra_hiddenimports = []

for pkg in local_packages:
    try:
        submodules = collect_submodules(pkg)
        extra_hiddenimports.extend(submodules)
        print(f"[spec] collect_submodules('{pkg}') -> {len(submodules)} modules")
    except Exception as e:
        print(f"[spec] collect_submodules('{pkg}') failed: {e}")

# 收集必要数据文件（PIL、certifi 等）
for pkg in ['PIL', 'certifi']:
    try:
        pkg_data = collect_data_files(pkg)
        added_files.extend(pkg_data)
        print(f"[spec] collect_data_files('{pkg}') -> {len(pkg_data)} files")
    except Exception as e:
        print(f"[spec] collect_data_files('{pkg}') failed: {e}")

# ========== PyInstaller Analysis ==========
a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=added_files,
    hiddenimports=list(set([
        'app', 'app.backend_api', 'app.desktop_app',
        'agents', 'agents.base_agent', 'agents.coordinator', 'agents.coach_agent',
        'agents.quiz_agent', 'agents.tutor_agent',
        'core', 'core.chunking', 'core.document_processor', 'core.embedding',
        'core.evaluator', 'core.hallucination_detector', 'core.hybrid_retriever',
        'core.intent_router', 'core.llm_client', 'core.monitoring',
        'core.query_cache', 'core.query_rewriter', 'core.reranker',
        'core.subject_analyzer', 'core.vector_store',
        'config', 'config.settings',
        'interfaces', 'interfaces.cli',
        'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'fastapi', 'starlette', 'pydantic', 'pydantic.deprecated',
        'pydantic.json_schema', 'pydantic_core',
        'requests',
        'numpy', 'fitz', 'PIL', 'PIL.Image', 'PIL.ImageOps',
        'packaging', 'packaging.version', 'packaging.specifiers',
        'packaging.requirements', 'packaging.markers', 'packaging.utils', 'packaging.tags',
        'jsonschema', 'jsonschema.protocols',
        'anyio', 'sniffio', 'idna', 'exceptiongroup', 'h11', 'click', 'colorama',
        'python_multipart', 'jinja2', 'markupsafe',
    ] + extra_hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tensorflow', 'tensorflow_hub', 'tensorflow_text', 'tensorboard',
        'pandas', 'matplotlib', 'seaborn', 'scipy',
        'sklearn', 'scikit-learn', 'scikit-image',
        'plotly', 'bokeh',
        'jupyter', 'jupyter_core', 'jupyterlab', 'notebook', 'ipywidgets', 'IPython',
        'wandb', 'pytest',
        'nltk', 'spacy',
        'accelerate', 'diffusers', 'datasets',
        'openai', 'anthropic',
        'flask', 'flask_sqlalchemy', 'flask_wtf', 'flask_login', 'flask_migrate',
        'django', 'werkzeug',
        # 彻底移除 torch / transformers 相关
        'torch', 'torchvision', 'torchaudio',
        'transformers',
        'sentence_transformers', 'sentence_transformers.models',
        'huggingface_hub', 'huggingface_hub.file_download',
        'tqdm', 'tqdm.auto', 'tqdm.asyncio', 'tqdm.std',
        # 彻底移除 ChromaDB（Rust 扩展在 Windows 多线程下崩溃）
        'chromadb', 'chromadb_rust_bindings',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LearnAnything',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 禁用 UPX 压缩（防止 DLL 损坏）
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 设为 True 方便调试，稳定后改为 False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # 禁用 UPX 压缩
    upx_exclude=[],
    name='LearnAnything',
)
