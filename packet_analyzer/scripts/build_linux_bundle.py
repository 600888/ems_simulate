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
import shutil
import sys
import tarfile
import time

# 统一 mtime，避免目标机时钟偏慢时刷一屏 "timestamp in the future" 警告
FIXED_MTIME = 1609459200  # 2021-01-01 00:00:00 UTC
DIR_MODE = 0o755
FILE_MODE = 0o644
EXEC_MODE = 0o755

# 包内 Python 模块文件（进 packet-analyzer/packet_analyzer/）
PACKAGE_FILES = ("__init__.py", "cli.py")
PACKAGE_DIRS = ("core", "samples")
# 包根目录下的脚本与文档（进 packet-analyzer/）
ROOT_FILES = ("pa.sh", "install.sh")
EXECUTABLES = {"pa.sh", "install.sh"}
EXTRA_FILES = {"docs/README-linux.md": "README-linux.md"}


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


def _add_tree(archive: tarfile.TarFile, root: Path, prefix: str) -> int:
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


def build(package_dir: Path, cache: Path, output: Path) -> int:
    staging_root = output.parent / "packet-analyzer"
    if staging_root.exists():
        shutil.rmtree(staging_root)

    print("[STEP] 写归档")
    total = 0
    with tarfile.open(output, "w:gz") as archive:
        _add_dir_entry(archive, "packet-analyzer")
        _add_dir_entry(archive, "packet-analyzer/packet_analyzer")
        for name in PACKAGE_DIRS:
            source = package_dir / name
            if not source.is_dir():
                print(f"       跳过不存在的目录 {name}")
                continue
            _add_dir_entry(archive, f"packet-analyzer/packet_analyzer/{name}")
            total += _add_tree(archive, source, f"packet-analyzer/packet_analyzer/{name}")

        for name in PACKAGE_FILES:
            source = package_dir / name
            if not source.is_file():
                print(f"       跳过不存在的文件 {name}")
                continue
            _add_file(archive, source, f"packet-analyzer/packet_analyzer/{name}", FILE_MODE)
            total += 1

        for name in ROOT_FILES:
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

        print("[STEP] 并入便携 Python（保留原始权限位）")
        if not cache.is_file():
            print(f"       错误：缺少 {cache}，请先下载（见 build_linux_bundle.sh）")
            return 1
        python_files = _add_python(archive, cache, "packet-analyzer/python")
        print(f"       加入 {python_files} 个文件")
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Linux 离线部署包")
    parser.add_argument("--package-dir", required=True, help="packet_analyzer 目录")
    parser.add_argument("--cache", required=True, help="便携 Python 的 tar.gz")
    parser.add_argument("--output", required=True, help="输出 tar.gz 路径")
    args = parser.parse_args()

    package_dir = Path(args.package_dir).resolve()
    cache = Path(args.cache).resolve()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    count = build(package_dir, cache, output)
    if count == 0 and not output.exists():
        return 1
    size_mb = output.stat().st_size / 1024 / 1024
    print(f"[SUCCESS] {output}（{size_mb:.1f} MB，用时 {time.time() - started:.1f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
