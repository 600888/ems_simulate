# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


PROJECT_ROOT = Path(SPECPATH).resolve()
BUILD_MODE = os.environ.get("EMS_PYINSTALLER_MODE", "onefile").lower()
APP_NAME = os.environ.get("EMS_PYINSTALLER_NAME", "ems_simulate_backend")
CONTENTS_DIRECTORY = os.environ.get("EMS_PYINSTALLER_CONTENTS_DIR", "_internal")
DATA_SCOPE = os.environ.get("EMS_PYINSTALLER_DATA_SCOPE", "point_csv").lower()
CONSOLE = os.environ.get("EMS_PYINSTALLER_CONSOLE", "0") == "1"

if BUILD_MODE not in {"onefile", "onedir"}:
    raise ValueError(f"Unsupported EMS_PYINSTALLER_MODE: {BUILD_MODE}")
if DATA_SCOPE not in {"point_csv", "all"}:
    raise ValueError(f"Unsupported EMS_PYINSTALLER_DATA_SCOPE: {DATA_SCOPE}")

datas = [
    (str(PROJECT_ROOT / "config.ini"), "."),
    (str(PROJECT_ROOT / "www"), "www"),
    (
        str(PROJECT_ROOT / "src" / "modeling" / "profile_packages"),
        "src/modeling/profile_packages",
    ),
    (
        str(PROJECT_ROOT / "src" / "modeling" / "standard_packages"),
        "src/modeling/standard_packages",
    ),
]
if DATA_SCOPE == "all":
    datas.append((str(PROJECT_ROOT / "data"), "data"))
else:
    datas.append((str(PROJECT_ROOT / "data" / "point_csv"), "data/point_csv"))

# pyiec61850 ships a Python extension and a native libiec61850 library. Keep
# their collection policy here so every packaging entry point behaves alike.
pyiec_datas, pyiec_binaries, pyiec_hiddenimports = collect_all("pyiec61850")
datas += pyiec_datas

hiddenimports = [
    "scapy.all",
    "psutil",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "openpyxl",
    "pymodbus",
    "fastapi",
    "sqlalchemy",
    "pydantic",
    "loguru",
    "c104",
    # dlt645 exposes these through an eager package initializer. Listing both
    # services explicitly keeps frozen builds from discovering either service
    # for the first time inside a device-reload worker thread.
    "dlt645",
    "dlt645.aio",
    "dlt645.service.serversvc.server_service",
    "dlt645.service.serversvc.async_server_service",
    "dlt645.service.clientsvc.client_service",
    "dlt645.service.clientsvc.async_client_service",
    "dlt645.transport.server.async_tcp_server",
    "dlt645.transport.server.async_rtu_server",
    "dlt645.transport.client.async_tcp_client",
    "dlt645.transport.client.async_rtu_client",
    *pyiec_hiddenimports,
]

a = Analysis(
    [str(PROJECT_ROOT / "start_back_end.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=pyiec_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(PROJECT_ROOT / "scripts" / "rthook_numpy_compat.py")],
    excludes=["numpy", "tkinter", "_tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if BUILD_MODE == "onefile":
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=CONSOLE,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=CONSOLE,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        contents_directory=CONTENTS_DIRECTORY,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=APP_NAME,
    )
