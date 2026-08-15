# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec 文件 — LearnAnything 桌面应用
打包方式：
    cd <LearnAnything-Dev 项目目录>
    rmdir /s /q build dist
    python -m PyInstaller app.spec --noconfirm

输出：
    dist/LearnAnything/LearnAnything.exe
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

# LA-DEPLOY: 使用 SPECPATH（PyInstaller 内置变量，指向 .spec 文件所在目录）
# 这样无论项目放在哪里，打包都能正确找到资源
project_root = Path(SPECPATH)

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

# 前端文件（确保构建产物存在）
web_dist_dir = str(project_root / "web" / "dist")
if os.path.exists(web_dist_dir):
    added_files.extend(collect_files(web_dist_dir, "web/dist"))
    print(f"[spec] 前端文件已收集: {web_dist_dir}")
else:
    print(f"[spec] 警告: 前端构建目录不存在: {web_dist_dir}")
    # 回退：尝试收集 web/ 根目录
    web_dir = str(project_root / "web")
    if os.path.exists(web_dir):
        added_files.extend(collect_files(web_dir, "web"))
        print(f"[spec] 回退收集 web/ 目录")

# 配置文件（排除敏感文件：api_config.ini、api_keys.ini，只保留模板和学科配置）
config_whitelist = {
    "api_keys.ini.example",
    "paradigms.yaml",
    "__init__.py",
}
for root, dirs, files in os.walk(str(project_root / "config")):
    # 排除运行时生成的 __pycache__
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for file in files:
        if file in config_whitelist:
            src = os.path.join(root, file)
            rel_dir = os.path.relpath(root, str(project_root / "config"))
            if rel_dir == '.':
                dest = "config"
            else:
                dest = os.path.join("config", rel_dir).replace('\\', '/')
            added_files.append((src, dest))
# 学科配置目录完整保留
added_files.extend(collect_files(str(project_root / "config" / "subjects"), "config/subjects"))

# LA-DEPLOY: MinerU CLI 工具（打包进压缩包，用户无需额外安装）
added_files.extend(collect_files(str(project_root / "tools" / "mineru"), "tools/mineru"))

# LA-DEPLOY-SECURITY: 知识库目录 —— 完全排除，所有内容均为运行时生成
# 包括: graph_db, vector_db, cache, *.db 数据库、用户上传的文档等
# 程序首次运行时会自动创建所需目录结构
print("[spec] LA-DEPLOY: knowledge_base/ 已排除（纯运行时数据）")

# 如果需要保留知识库的空目录结构（让程序知道目录位置），可以创建一个 .gitkeep 类似的标记
# 但当前设计下，settings.py 中的路径定义已经足够，程序会自动 mkdir


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

# 收集必要数据文件（PIL、certifi、PyQt5 等）
for pkg in ['PIL', 'certifi']:
    try:
        pkg_data = collect_data_files(pkg)
        added_files.extend(pkg_data)
        print(f"[spec] collect_data_files('{pkg}') -> {len(pkg_data)} files")
    except Exception as e:
        print(f"[spec] collect_data_files('{pkg}') failed: {e}")

# LA-DEPLOY: 收集 PyQt5 的动态库和数据文件（QtWebEngine 需要）
try:
    qt5_binaries = collect_dynamic_libs('PyQt5')
    qt5_data = collect_data_files('PyQt5')
    added_files.extend(qt5_data)
    print(f"[spec] collect_dynamic_libs('PyQt5') -> {len(qt5_binaries)} binaries")
    print(f"[spec] collect_data_files('PyQt5') -> {len(qt5_data)} files")

    # LA-DEPLOY-FIX: 显式收集 QtWebEngineProcess.exe
    import PyQt5
    qt5_dir = Path(PyQt5.__file__).parent
    qtwebengine_exe = qt5_dir / "Qt5" / "bin" / "QtWebEngineProcess.exe"
    if qtwebengine_exe.exists():
        added_files.append((str(qtwebengine_exe), "PyQt5/Qt5/bin"))
        print(f"[spec] QtWebEngineProcess.exe -> {qtwebengine_exe}")
    else:
        print(f"[spec] 警告: QtWebEngineProcess.exe 未找到")

    # LA-DEPLOY-FIX: 显式收集 Qt 资源文件（translations, resources）
    qt_resources_dir = qt5_dir / "Qt5" / "resources"
    if qt_resources_dir.exists():
        added_files.extend(collect_files(str(qt_resources_dir), "PyQt5/Qt5/resources"))
        print(f"[spec] Qt resources -> {qt_resources_dir}")

    qt_translations_dir = qt5_dir / "Qt5" / "translations"
    if qt_translations_dir.exists():
        added_files.extend(collect_files(str(qt_translations_dir), "PyQt5/Qt5/translations"))
        print(f"[spec] Qt translations -> {qt_translations_dir}")

except Exception as e:
    print(f"[spec] collect PyQt5 failed: {e}")

# LA-DEPLOY: 收集 PyYAML 数据文件（libyaml 等）
try:
    yaml_data = collect_data_files('yaml')
    added_files.extend(yaml_data)
    print(f"[spec] collect_data_files('yaml') -> {len(yaml_data)} files")
except Exception as e:
    print(f"[spec] collect yaml failed: {e}")

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
        'core.gap_detector', 'core.gap_store', 'core.gap_service',
        'core.gap_migration', 'core.gap_proposal_store',
        'core.gap_completion_advisor', 'core.gap_completion_service',
        'core.knowledge_search',
        'app.gap_api',
        'core.subject_analyzer', 'core.vector_store',
        'config', 'config.settings',
        'interfaces', 'interfaces.cli',
        'kuzu',  # LA-DEPLOY: KùzuDB 图数据库
        'yaml',  # LA-DEPLOY: PyYAML 配置解析
        'PyQt5', 'PyQt5.QtWidgets', 'PyQt5.QtWebEngineWidgets', 'PyQt5.QtCore',  # LA-DEPLOY: 桌面窗口
        'pydantic_core',  # LA-DEPLOY: pydantic v2 原生扩展
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
