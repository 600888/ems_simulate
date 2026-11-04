"""生成 Linux 离线部署包（在 Windows 或任意平台运行）。

之所以用 Python 而不是 shell 拼 tar：

* Windows 上 ``chmod`` 对 NTFS 文件常常静默失效，打出的包里 python3 会丢掉
  可执行位，到 Linux 上直接跑不起来（"未找到 python/bin/python3"）；
* ``tarfile`` 能把权限位、符号链接、mtime 精确写进归档，跨平台结果一致。

产物：build/linux/packet-analyzer-linux-x86_64.tar.gz
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path
import re
import shutil
import sys
import tarfile
import time
import zipfile

# 统一 mtime，避免目标机时钟偏慢时刷一屏 "timestamp in the future" 警告
FIXED_MTIME = 1609459200  # 2021-01-01 00:00:00 UTC
DIR_MODE = 0o755
FILE_MODE = 0o644
EXEC_MODE = 0o755

# 包内 Python 模块文件（进 packet-analyzer/packet_analyzer/）
PACKAGE_FILES = ("__init__.py", "cli.py")
PACKAGE_DIRS = ("core", "samples")
# 图形版额外需要界面代码与入口
GUI_PACKAGE_FILES = ("main.py",)
GUI_PACKAGE_DIRS = ("ui",)
# 包根目录下的脚本与文档（进 packet-analyzer/）
ROOT_FILES = ("pa.sh", "install.sh", "pa-gui.sh")
EXECUTABLES = {"pa.sh", "install.sh", "pa-gui.sh"}
EXTRA_FILES = {"docs/README-linux.md": "README-linux.md"}
# 查缺失库的工具：图形版才需要，放进包内 tools/ 供目标机现场排查
TOOL_FILES = {"scripts/templates/find_missing_lib.py": "tools/find_missing_lib.py",
              "scripts/templates/lib-packages.tsv": "tools/lib-packages.tsv"}

# -- Qt5(PySide2) 裁剪名单 -------------------------------------------------
# 只保留界面真正用到的三个模块。整包 446MB 里 362MB 是 Qt 库，
# 剪掉不用的部分后约 167MB（实测在目标机可正常启动 xcb 界面）。
SITE_PACKAGES_PREFIX = "packet-analyzer/python/lib/python3.10/site-packages"

PYSIDE2_KEEP_SO = {"QtCore.abi3.so", "QtGui.abi3.so", "QtWidgets.abi3.so"}
QT_LIB_KEEP_PREFIXES = (
    "libQt5Core.so",
    "libQt5Gui.so",
    "libQt5Widgets.so",
    "libQt5XcbQpa.so",
    "libQt5DBus.so",
    "libQt5PrintSupport.so",
    "libQt5Svg.so",
    "libQt5Qml.so",       # libQt5Core/Gui 依赖它，删掉会 ImportError
    "libQt5Network.so",   # 系统自带的是 Qt5.3，必须用包内的 5.15
    "libicudata.so",
    "libicuuc.so",
    "libicui18n.so",
)
QT_PLUGIN_DIRS = {"platforms", "imageformats", "styles"}
QT_PLATFORM_PLUGINS = {"libqxcb.so", "libqoffscreen.so"}
DROP_DIR_MARKERS = ("/examples/", "/include/", "/typesystems/", "/qml/", "/translations/")


def _add_bytes(archive: tarfile.TarFile, name: str, data: bytes, mode: int) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = FIXED_MTIME
    info.mode = mode
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    archive.addfile(info, io.BytesIO(data))


def _add_file(archive: tarfile.TarFile, source: Path, name: str, mode: int) -> None:
    data = source.read_bytes()
    _add_bytes(archive, name, data, mode)


def _add_tree(archive: tarfile.TarFile, root: Path, prefix: str, *, skip_compiled: bool = False) -> int:
    """递归加入目录，返回文件数。空目录也会保留。"""
    count = 0
    for item in sorted(root.rglob("*")):
        relative = item.relative_to(root).as_posix()
        arcname = f"{prefix}/{relative}"
        if item.is_dir():
            info = tarfile.TarInfo(arcname)
            info.type = tarfile.DIRTYPE
            info.mtime = FIXED_MTIME
            info.mode = DIR_MODE
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info)
        elif item.is_file():
            if "__pycache__" in item.parts or item.suffix == ".pyc":
                continue
            if skip_compiled and item.suffix in (".so", ".pyd", ".dll"):
                continue
            _add_file(archive, item, arcname, FILE_MODE)
            count += 1
    return count


def _add_dir_entry(archive: tarfile.TarFile, name: str) -> None:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE
    info.mtime = FIXED_MTIME
    info.mode = DIR_MODE
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    archive.addfile(info)


def _keep_qt_member(name: str) -> bool:
    """判断 wheel 里的成员是否要打进包（裁剪逻辑集中在这里）。"""
    if name.endswith("/"):
        return False
    # 存根、头文件、示例、QML 资源一律不要
    if name.endswith(".pyi"):
        return False
    if any(marker in f"/{name}" for marker in DROP_DIR_MARKERS):
        return False

    parts = name.split("/")
    if parts[0] == "shiboken2":
        return True  # 整个 shiboken2 都要（含 libshiboken2）
    if parts[0] != "PySide2":
        return False

    if len(parts) == 2:  # PySide2/xxx
        if name.endswith(".abi3.so"):
            return parts[1] in PYSIDE2_KEEP_SO
        return True  # __init__.py 等

    if len(parts) == 3 and parts[1] == "Qt":
        if parts[2] in ("lib", "plugins"):
            return True
        return parts[2] in ("qs",)  # 其它目录丢弃

    if len(parts) == 4 and parts[1] == "Qt" and parts[2] == "lib":
        return parts[3].startswith(QT_LIB_KEEP_PREFIXES)

    if len(parts) >= 5 and parts[1] == "Qt" and parts[2] == "plugins":
        plugin_dir = parts[3]
        if plugin_dir not in QT_PLUGIN_DIRS:
            return False
        if plugin_dir == "platforms":
            return parts[-1] in QT_PLATFORM_PLUGINS
        return True

    # PySide2/Qt/lib 之下的其它层级（版本化文件名）交给前缀规则处理
    if len(parts) > 4 and parts[1] == "Qt" and parts[2] == "lib":
        return parts[-1].startswith(QT_LIB_KEEP_PREFIXES)

    return False


def _add_wheel(
    archive: tarfile.TarFile,
    wheel: Path,
    prefix: str,
    *,
    keep=None,
) -> tuple[int, int]:
    """把 wheel 中的（符合条件的）文件写进归档。

    返回 (加入文件数, 跳过文件数)。文件权限按 zip 里的记录保留，
    这样 .so 与 bin 脚本在 Linux 上仍然可用。
    """
    added = skipped = 0
    with zipfile.ZipFile(wheel) as zf:
        for info in zf.infolist():
            name = info.filename
            if keep is not None and not keep(name):
                skipped += 1
                continue
            if not name or name.endswith("/"):
                continue
            # zip 无 exec 位信息，.so 给 644 即可（dlopen 不需要可执行位）
            data = zf.read(name)
            _add_bytes(archive, f"{prefix}/{name}", data, FILE_MODE)
            added += 1
    return added, skipped


def _add_python(archive: tarfile.TarFile, cache: Path, prefix: str) -> int:
    """把便携 Python 的成员原样搬进新归档，保留其原始权限位。

    不解压到磁盘再打包——那样在 Windows 上会丢可执行位。
    """
    count = 0
    with tarfile.open(cache, "r:gz") as source:
        for member in source.getmembers():
            relative = member.name
            # 归档顶层目录名可能是 python/ 或其它，统一剥掉第一段
            if "/" in relative:
                relative = relative.split("/", 1)[1]
            if not relative:
                continue
            member.name = f"{prefix}/{relative}"
            member.mtime = FIXED_MTIME
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            if member.isdir():
                member.mode = DIR_MODE
            elif member.isfile():
                # 原始可执行位必须保留（bin/python3.10 等）
                member.mode = member.mode | 0o600
                count += 1
            archive.addfile(member, source.extractfile(member) if member.isfile() else None)
    return count


def _lib_names(filename: str) -> list[str]:
    """由带完整版本号的库名推出它可能被引用的名字。

    libxcb-util.so.1.0.0 -> ["libxcb-util.so.1.0.0", "libxcb-util.so.1"]
    动态加载器按 SONAME 查找，缓存文件名常常带三段版本号，两个都要有。
    """
    names = [filename]
    stem = re.match(r"^(lib[^.]+\.so\.\d+)", filename)
    if stem and stem.group(1) != filename:
        names.append(stem.group(1))
    return names


# 纯 Python 的可选依赖：打进包内 site-packages，避免运行时缺模块导致功能降级
VENDOR_PACKAGES = ("pydnp3_pure",)


def build(
    package_dir: Path,
    cache: Path,
    output: Path,
    *,
    site_packages: Path | None = None,
    vendor: tuple[str, ...] = (),
    qt5_wheels: tuple[Path, ...] = (),
    libdbus: Path | None = None,
    extra_libs: tuple[Path, ...] = (),
) -> int:
    staging_root = output.parent / "packet-analyzer"
    if staging_root.exists():
        shutil.rmtree(staging_root)

    print("[STEP] 写归档")
    total = 0
    package_dirs = PACKAGE_DIRS + (GUI_PACKAGE_DIRS if qt5_wheels else ())
    package_files = PACKAGE_FILES + (GUI_PACKAGE_FILES if qt5_wheels else ())

    with tarfile.open(output, "w:gz") as archive:
        _add_dir_entry(archive, "packet-analyzer")
        _add_dir_entry(archive, "packet-analyzer/packet_analyzer")
        for name in package_dirs:
            source = package_dir / name
            if not source.is_dir():
                print(f"       跳过不存在的目录 {name}")
                continue
            _add_dir_entry(archive, f"packet-analyzer/packet_analyzer/{name}")
            total += _add_tree(archive, source, f"packet-analyzer/packet_analyzer/{name}")

        for name in package_files:
            source = package_dir / name
            if not source.is_file():
                print(f"       跳过不存在的文件 {name}")
                continue
            _add_file(archive, source, f"packet-analyzer/packet_analyzer/{name}", FILE_MODE)
            total += 1

        for name in ROOT_FILES:
            if name == "pa-gui.sh" and not qt5_wheels:
                continue  # 命令行版不带图形启动脚本
            source = package_dir / name
            if not source.is_file():
                print(f"       跳过不存在的文件 {name}")
                continue
            mode = EXEC_MODE if name in EXECUTABLES else FILE_MODE
            _add_file(archive, source, f"packet-analyzer/{name}", mode)
            total += 1

        for source_name, target_name in EXTRA_FILES.items():
            source = package_dir / source_name
            if source.is_file():
                _add_file(archive, source, f"packet-analyzer/{target_name}", FILE_MODE)
                total += 1

        if qt5_wheels:
            for source_name, target_name in TOOL_FILES.items():
                source = package_dir / source_name
                if source.is_file():
                    mode = EXEC_MODE if target_name.endswith(".py") else FILE_MODE
                    _add_file(archive, source, f"packet-analyzer/{target_name}", mode)
                    total += 1
            print("       附带 tools/find_missing_lib.py（现场查缺失库用）")

        print("[STEP] 并入便携 Python（保留原始权限位）")
        if not cache.is_file():
            print(f"       错误：缺少 {cache}，请先下载（见 build_linux_bundle.sh）")
            return 1
        python_files = _add_python(archive, cache, "packet-analyzer/python")
        print(f"       加入 {python_files} 个文件")

        if vendor and site_packages is not None:
            print("[STEP] 并入纯 Python 依赖")
            for name in vendor:
                source = site_packages / name
                if not source.is_dir():
                    print(f"       跳过 {name}（本地未安装）")
                    continue
                # 直接放进包内 site-packages，运行时不改 sys.path
                prefix = f"{SITE_PACKAGES_PREFIX}/{name}"
                _add_dir_entry(archive, prefix)
                added = _add_tree(archive, source, prefix, skip_compiled=True)
                print(f"       {name}: {added} 个文件")

        if qt5_wheels:
            print("[STEP] 并入 Qt5（PySide2，按需裁剪）")
            for wheel in qt5_wheels:
                if not wheel.is_file():
                    print(f"       错误：缺少 {wheel}")
                    return 1
                added, skipped = _add_wheel(archive, wheel, SITE_PACKAGES_PREFIX, keep=_keep_qt_member)
                print(f"       {wheel.name.split('-')[0]}: 加入 {added} 个，跳过 {skipped} 个")

            if libdbus is not None and libdbus.is_file():
                # 目标机系统的 libdbus 往往太旧（如 1.8），Qt5.15 需要 >=1.10
                target = f"{SITE_PACKAGES_PREFIX}/PySide2/Qt/lib/libdbus-1.so.3"
                _add_bytes(archive, target, libdbus.read_bytes(), FILE_MODE)
                print(f"       并入 libdbus：{libdbus.name}")
            else:
                print("       警告：未提供 libdbus，目标机若 dbus 过旧会导致 xcb 启动失败")

        if extra_libs:
            print("[STEP] 并入补充运行库")
            lib_dir = f"{SITE_PACKAGES_PREFIX}/PySide2/Qt/lib"
            for lib in extra_libs:
                if not lib.is_file():
                    print(f"       跳过 {lib.name}（不存在）")
                    continue
                data = lib.read_bytes()
                # 目标机可能按 SONAME 找库，而缓存文件名带完整版本号，
                # 两个名字都写一份，省得再纠结软链接。
                for name in _lib_names(lib.name):
                    _add_bytes(archive, f"{lib_dir}/{name}", data, FILE_MODE)
                print(f"       {lib.name} -> {', '.join(_lib_names(lib.name))}")
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Linux 离线部署包")
    parser.add_argument("--package-dir", required=True, help="packet_analyzer 目录")
    parser.add_argument("--cache", required=True, help="便携 Python 的 tar.gz")
    parser.add_argument("--output", required=True, help="输出 tar.gz 路径")
    parser.add_argument(
        "--site-packages",
        help="本地 site-packages 目录（用于并入纯 Python 可选依赖）",
        default="",
    )
    parser.add_argument(
        "--vendor",
        nargs="*",
        default=list(VENDOR_PACKAGES),
        help=f"要并入的纯 Python 包名（默认：{' '.join(VENDOR_PACKAGES)}）",
    )
    parser.add_argument(
        "--qt5-wheels",
        nargs="*",
        default=[],
        help="PySide2 与 shiboken2 的 manylinux wheel（给老系统出图形版时提供）",
    )
    parser.add_argument("--libdbus", default="", help="较新的 libdbus-1.so.3（Qt5.15 需要 >=1.10）")
    parser.add_argument(
        "--extra-libs",
        nargs="*",
        default=[],
        help="目标机可能缺失的运行库（如 libxcb-util.so.1），统一放进包内 Qt 库目录",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="同时包含图形界面启动脚本（需要 --qt5-wheels）",
    )
    args = parser.parse_args()

    package_dir = Path(args.package_dir).resolve()
    cache = Path(args.cache).resolve()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    site_packages = Path(args.site_packages).resolve() if args.site_packages else None
    qt5_wheels = tuple(Path(item).resolve() for item in (args.qt5_wheels or []))
    libdbus = Path(args.libdbus).resolve() if args.libdbus else None
    extra_libs = tuple(Path(item).resolve() for item in (args.extra_libs or []))
    started = time.time()
    count = build(
        package_dir,
        cache,
        output,
        site_packages=site_packages,
        vendor=tuple(args.vendor or ()),
        qt5_wheels=qt5_wheels,
        libdbus=libdbus,
        extra_libs=extra_libs,
    )
    if count == 0 and not output.exists():
        return 1
    size_mb = output.stat().st_size / 1024 / 1024
    print(f"[SUCCESS] {output}（{size_mb:.1f} MB，用时 {time.time() - started:.1f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
