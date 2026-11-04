# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：电力协议报文解析器（onedir 目录模式）。

用法（在 packet_analyzer 目录下）：
    python -m PyInstaller --noconfirm packet_analyzer.spec

产物：dist/PacketAnalyzer/PacketAnalyzer.exe

采用 onedir 而非 onefile：PySide6 为 LGPLv3，保留独立的 Qt 动态库文件
便于用户自行替换，符合许可证的"可替换"要求；同时启动速度更快。
"""

from pathlib import Path


PROJECT_ROOT = Path(SPECPATH).resolve()
APP_NAME = "PacketAnalyzer"

# 本工具只用到 QtCore / QtGui / QtWidgets。
# 完整 PySide6（含 Qt WebEngine、Quick、3D 等）约 655MB，必须排除未使用的模块。
EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineQuickDelegatesQml",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickTest",
    "PySide6.QtQuickWidgets",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtNetworkAuth",
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtHelp",
    "PySide6.QtDesigner",
    "PySide6.QtUiTools",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech",
    "PySide6.QtHttpServer",
    # 与桌面工具无关的标准库/第三方
    "tkinter",
    "numpy",
    "scipy",
    "pandas",
    "matplotlib",
    "IPython",
    "pytest",
    "PIL",
]

# 可选依赖：dlt645 提供 DI 数据项中文名称（缺失时仅退化为不显示名称）。
# 该导入写在函数内且被 try/except 包裹，显式声明以免打包时被漏掉。
HIDDEN_IMPORTS = [
    "dlt645.model.data.data_handler",
]

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT.parent)],
    binaries=[],
    datas=[(str(PROJECT_ROOT / "samples"), "samples")],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# PySide6 的 hook 会把 Qml/Quick 运行库和软件 OpenGL 一并带入，
# 本工具只用 Widgets，运行时完全用不到，剔除以减小体积。
DROP_BINARIES = ("qt6qml", "qt6quick", "opengl32sw")
a.binaries = [item for item in a.binaries if not any(token in item[0].lower() for token in DROP_BINARIES)]
a.datas = [item for item in a.datas if not item[0].replace("\\", "/").startswith(("PySide6/qml", "qml/"))]

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)
