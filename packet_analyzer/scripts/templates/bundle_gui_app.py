"""通用打包器：把任意 Python GUI 程序做成自包含离线包（供 glibc 较老、无网络的 Linux 使用）。

与项目结构解耦，只依赖命令行参数。产物解压即可运行，不需要目标机装 Python 或 Qt。

用法示例::

    python bundle_gui_app.py \
        --app-dir ./myapp \
        --package myapp \
        --python-cache ~/cache/python310.tar.gz \
        --qt5-wheels ~/cache/wheels/shiboken2-*.whl ~/cache/wheels/PySide2-*.whl \
        --libdbus ~/cache/libdbus-1.so.3 \
        --output dist/myapp-linux-x86_64.tar.gz

为什么不用 shell 拼 tar：Windows 上 ``chmod`` 对 NTFS 常静默失效，打出的包里
``python/bin/python3`` 会丢掉可执行位，到 Linux 直接跑不起来。``tarfile`` 能精确写权限位。
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path
import shutil
import sys
import tarfile
import time
import zipfile

FIXED_MTIME = 1609459200  # 2021-01-01 UTC，避免目标机时钟偏慢时刷一屏警告
DIR_MODE = 0o755
FILE_MODE = 0o644
EXEC_MODE = 0o755

# 源码里不需要进包的东西
SKIP_DIRS = {
    "__pycache__", ".git", ".idea", ".vscode", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "build", "dist", "node_modules", ".venv", "venv", "tests",
}
SKIP_SUFFIXES = {".pyc", ".pyo", ".pyd", ".so", ".dylib", ".log", ".tmp"}

# -- PySide2 裁剪白名单 ---------------------------------------------------
# 完整 PySide2 装完约 446MB，其中 362MB 是 Qt 库。只留界面真正用到的。
PYSIDE2_KEEP_SO = {"QtCore.abi3.so", "QtGui.abi3.so", "QtWidgets.abi3.so"}
QT_LIB_KEEP_PREFIXES = (
    "libQt5Core.so",
    "libQt5Gui.so",
    "libQt5Widgets.so",
    "libQt5XcbQpa.so",
    "libQt5DBus.so",
    "libQt5PrintSupport.so",
    "libQt5Svg.so",
    "libQt5Qml.so",      # Qt5Core 依赖，删掉会 ImportError
    "libQt5Network.so",  # 系统常是 Qt5.3，混用会符号不匹配
    "libicudata.so",
    "libicuuc.so",
    "libicui18n.so",
)
QT_PLUGIN_DIRS = {"platforms", "imageformats", "styles"}
QT_PLATFORM_PLUGINS = {"libqxcb.so", "libqoffscreen.so"}
DROP_DIR_MARKERS = ("/examples/", "/include/", "/typesystems/", "/qml/", "/translations/")


# ---------------------------------------------------------------- 归档写入
def _add_bytes(archive: tarfile.TarFile, name: str, data: bytes, mode: int) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = FIXED_MTIME
    info.mode = mode
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    archive.addfile(info, io.BytesIO(data))


def _add_dir(archive: tarfile.TarFile, name: str) -> None:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE
    info.mtime = FIXED_MTIME
    info.mode = DIR_MODE
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    archive.addfile(info)


def _add_source_tree(archive: tarfile.TarFile, root: Path, prefix: str) -> int:
    """把一个源码目录写进包，跳过缓存与构建产物。"""
    count = 0
    for item in sorted(root.rglob("*")):
        rel = item.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        arcname = f"{prefix}/{rel.as_posix()}"
        if item.is_dir():
            _add_dir(archive, arcname)
        elif item.is_file():
            if item.suffix in SKIP_SUFFIXES:
                continue
            _add_bytes(archive, arcname, item.read_bytes(), FILE_MODE)
            count += 1
    return count


def _add_python(archive: tarfile.TarFile, cache: Path, prefix: str) -> int:
    """把便携 Python 的成员流式搬进归档。

    不解压到磁盘再打包——Windows 上那样会丢可执行位。保留原始 mode。
    """
    count = 0
    with tarfile.open(cache, "r:gz") as source:
        for member in source.getmembers():
            rel = member.name.split("/", 1)[1] if "/" in member.name else ""
            if not rel:
                continue
            member.name = f"{prefix}/{rel}"
            member.mtime = FIXED_MTIME
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            if member.isdir():
                member.mode = DIR_MODE
            elif member.isfile():
                member.mode = member.mode | 0o600  # 保住 bin/python3 的可执行位
                count += 1
            payload = source.extractfile(member) if member.isfile() else None
            archive.addfile(member, payload)
    return count


def _keep_qt(name: str) -> bool:
    if name.endswith("/") or name.endswith(".pyi"):
        return False
    if any(marker in f"/{name}" for marker in DROP_DIR_MARKERS):
        return False

    parts = name.split("/")
    top = parts[0]
    if top == "shiboken2":
        return True  # 需要其中的 libshiboken2
    if top != "PySide2":
        return False
    if len(parts) == 2:
        if name.endswith(".abi3.so"):
            return parts[1] in PYSIDE2_KEEP_SO
        return True
    if parts[1] != "Qt":
        return False
    if len(parts) == 3:
        return parts[2] in ("lib", "plugins", "qs")
    if parts[2] == "lib":
        return parts[-1].startswith(QT_LIB_KEEP_PREFIXES)
    if parts[2] == "plugins":
        if parts[3] not in QT_PLUGIN_DIRS:
            return False
        if parts[3] == "platforms":
            return parts[-1] in QT_PLATFORM_PLUGINS
        return True
    return False


def _add_wheel(archive: tarfile.TarFile, wheel: Path, prefix: str, keep=None) -> tuple[int, int]:
    added = skipped = 0
    with zipfile.ZipFile(wheel) as zf:
        for info in zf.infolist():
            name = info.filename
            if not name or name.endswith("/"):
                continue
            if keep is not None and not keep(name):
                skipped += 1
                continue
            # zip 记录不了 exec 位；.so 只需读权限，644 足够 dlopen
            _add_bytes(archive, f"{prefix}/{name}", zf.read(name), FILE_MODE)
            added += 1
    return added, skipped


# ---------------------------------------------------------------- 启动脚本
RUN_CLI_TEMPLATE = """#!/bin/sh
# {app_title} 启动脚本（自动生成）
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
if [ ! -x "$DIR/python/bin/python3" ]; then
    echo "错误：包内缺少 Python（python/bin/python3），请重新解压完整分发包。" >&2
    exit 1
fi
PYTHONPATH="$DIR:${{PYTHONPATH:-}}" exec "$DIR/python/bin/python3" -m {module} "$@"
"""

RUN_GUI_TEMPLATE = """#!/bin/sh
# {app_title} 图形版启动脚本（自动生成）
#
# 关键：包内 Qt 库必须排在 LD_LIBRARY_PATH 最前面，
# 否则会撞上系统自带的老 Qt（常见 Qt5.3），报符号未定义。
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
SP="$DIR/python/lib/python3.10/site-packages"
QT_LIB="$SP/PySide2/Qt/lib"

if [ ! -x "$DIR/python/bin/python3" ]; then
    echo "错误：包内缺少 Python（python/bin/python3），请重新解压完整分发包。" >&2
    exit 1
fi
if [ ! -d "$SP/PySide2" ] && [ ! -d "$SP/PySide6" ]; then
    echo "错误：包内没有 Qt 绑定，无法启动图形界面。" >&2
    exit 1
fi

if [ -d "$QT_LIB" ]; then
    LD_LIBRARY_PATH="$QT_LIB${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}"
    export LD_LIBRARY_PATH
fi

if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ] && [ -z "$QT_QPA_PLATFORM" ]; then
    echo "提示：当前没有 DISPLAY，无法弹出窗口。" >&2
    echo "  · 在服务器桌面上运行，或 ssh -X 转发显示" >&2
    echo "  · 只跑命令行功能时用 ./run-cli.sh" >&2
    exit 1
fi

PYTHONPATH="$SP:$DIR${{PYTHONPATH:+:$PYTHONPATH}}" exec "$DIR/python/bin/python3" -m {module} "$@"
"""


def build(
    app_dir: Path,
    package: str,
    python_cache: Path,
    output: Path,
    *,
    app_title: str = "",
    cli_module: str = "",
    qt5_wheels: tuple[Path, ...] = (),
    libdbus: Path | None = None,
    vendor_dirs: tuple[Path, ...] = (),
    extra_files: tuple[Path, ...] = (),
    python_version: str = "3.10",
) -> int:
    title = app_title or package
    staging = output.parent / output.name.replace(".tar.gz", "")
    if staging.exists():
        shutil.rmtree(staging)

    total = 0
    with tarfile.open(output, "w:gz") as archive:
        root_name = staging.name
        _add_dir(archive, root_name)

        print(f"[STEP] 打包源码：{app_dir}")
        total += _add_source_tree(archive, app_dir, root_name)

        for extra in extra_files:
            if extra.is_file():
                _add_bytes(archive, f"{root_name}/{extra.name}", extra.read_bytes(), FILE_MODE)
                total += 1

        print(f"[STEP] 并入便携 Python：{python_cache.name}")
        if not python_cache.is_file():
            print(f"       错误：找不到 {python_cache}")
            return 1
        count = _add_python(archive, python_cache, f"{root_name}/python")
        print(f"       {count} 个文件")

        sitepkg = f"{root_name}/python/lib/python{python_version}/site-packages"

        if vendor_dirs:
            print("[STEP] 并入纯 Python 依赖")
            for src in vendor_dirs:
                if not src.is_dir():
                    print(f"       跳过 {src}（不存在）")
                    continue
                _add_dir(archive, f"{sitepkg}/{src.name}")
                added = _add_source_tree(archive, src, f"{sitepkg}/{src.name}")
                print(f"       {src.name}: {added} 个文件")

        if qt5_wheels:
            print("[STEP] 并入 Qt5（按白名单裁剪）")
            for wheel in qt5_wheels:
                if not wheel.is_file():
                    print(f"       错误：找不到 {wheel}")
                    return 1
                added, skipped = _add_wheel(archive, wheel, sitepkg, keep=_keep_qt)
                print(f"       {wheel.name.split('-')[0]}: 加入 {added}，跳过 {skipped}")
            if libdbus is not None and libdbus.is_file():
                # 目标机系统的 libdbus 常是 1.8，Qt5.15 需要 >=1.10
                _add_bytes(
                    archive,
                    f"{sitepkg}/PySide2/Qt/lib/libdbus-1.so.3",
                    libdbus.read_bytes(),
                    FILE_MODE,
                )
                print(f"       并入 libdbus：{libdbus.name}")
            else:
                print("       警告：未提供 libdbus，目标机 dbus 过旧时 xcb 会启动失败")

        print("[STEP] 生成启动脚本")
        _add_bytes(
            archive,
            f"{root_name}/run-gui.sh",
            RUN_GUI_TEMPLATE.format(module=package, app_title=title).encode("utf-8"),
            EXEC_MODE,
        )
        if cli_module:
            _add_bytes(
                archive,
                f"{root_name}/run-cli.sh",
                RUN_CLI_TEMPLATE.format(module=cli_module, app_title=title).encode("utf-8"),
                EXEC_MODE,
            )
        print("       run-gui.sh" + (" / run-cli.sh" if cli_module else ""))

    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把 Python GUI 程序打成自包含 Linux 离线包",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
        "  python bundle_gui_app.py --app-dir ./myapp --package myapp \\\n"
        "      --python-cache ~/cache/python310.tar.gz \\\n"
        "      --qt5-wheels ~/cache/wheels/shiboken2-*.whl ~/cache/wheels/PySide2-*.whl \\\n"
        "      --libdbus ~/cache/libdbus-1.so.3 --output dist/myapp.tar.gz\n",
    )
    parser.add_argument("--app-dir", required=True, help="源码目录（会被整体打进包）")
    parser.add_argument("--package", required=True, help="Python 包名（启动时 python -m <package>）")
    parser.add_argument("--python-cache", required=True, help="便携 Python 的 tar.gz")
    parser.add_argument("--output", required=True, help="输出 tar.gz")
    parser.add_argument("--title", default="", help="显示在脚本注释里的程序名")
    parser.add_argument("--cli-module", default="", help="命令行入口模块（提供则额外生成 run-cli.sh）")
    parser.add_argument("--qt5-wheels", nargs="*", default=[], help="PySide2 + shiboken2 的 manylinux wheel")
    parser.add_argument("--libdbus", default="", help="较新的 libdbus-1.so.3（Qt5.15 需要 >=1.10）")
    parser.add_argument("--vendor", nargs="*", default=[], help="要一并打包的纯 Python 包目录")
    parser.add_argument("--extra", nargs="*", default=[], help="额外文件（README、配置示例等）")
    parser.add_argument("--python-version", default="3.10", help="便携 Python 的 X.Y 版本（默认 3.10）")
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    output = Path(args.output).resolve()
    if not app_dir.is_dir():
        print(f"错误：源码目录不存在 {app_dir}")
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    count = build(
        app_dir,
        args.package,
        Path(args.python_cache).resolve(),
        output,
        app_title=args.title,
        cli_module=args.cli_module,
        qt5_wheels=tuple(Path(p).resolve() for p in (args.qt5_wheels or [])),
        libdbus=Path(args.libdbus).resolve() if args.libdbus else None,
        vendor_dirs=tuple(Path(p).resolve() for p in (args.vendor or [])),
        extra_files=tuple(Path(p).resolve() for p in (args.extra or [])),
        python_version=args.python_version,
    )
    if not output.exists():
        return 1
    size = output.stat().st_size / 1024 / 1024
    print(f"[SUCCESS] {output}（{size:.1f} MB，{count} 个源文件，用时 {time.time() - started:.1f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
