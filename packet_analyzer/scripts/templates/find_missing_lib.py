#!/usr/bin/env python3
"""缺失运行库解析器：把 "libxxx.so.N => not found" 变成可下载的地址。

两种用法：

1) 直接查（不下载）——回答「这个库从哪来」
     python3 find_missing_lib.py libxcb-xinerama.so.0
     python3 find_missing_lib.py --ldd-output missing.txt

2) 批量取到目录（离线部署时把库塞进包内 Qt 目录）
     python3 find_missing_lib.py --download ./xcb-libs libxcb-xinerama.so.0 libxcb-util.so.1

表在本目录的 lib-packages.tsv，查不到时可编辑该文件补充。
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path
import sys
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
TABLE = HERE / "lib-packages.tsv"
MIRROR = "http://deb.debian.org/debian/pool/main"


def load_table(path: Path = TABLE) -> dict[str, dict[str, str]]:
    table: dict[str, dict[str, str]] = {}
    if not path.is_file():
        return table
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        soname, package, version, pool = parts[:4]
        note = parts[4] if len(parts) > 4 else ""
        table[soname.strip()] = {
            "package": package.strip(),
            "version": version.strip(),
            "pool": pool.strip(),
            "note": note.strip(),
        }
    return table


def deb_url(pool: str, package: str, version: str) -> str:
    return f"{MIRROR}/{pool}/{package}_{version}_amd64.deb"


def extract_so_from_deb(deb_bytes: bytes, prefix: str) -> bytes:
    """从 .deb 里取出以 prefix 开头的 .so 文件。

    .deb = ar 归档，内含 data.tar.{xz,gz,zst}。这里只处理前两种，
    Debian 的 data.tar 基本都是 xz。
    """
    # ar 全局头 8 字节，之后每项 60 字节头 + 数据（2 字节对齐）
    offset = 8
    data_blob = None
    while offset + 60 <= len(deb_bytes):
        header = deb_bytes[offset : offset + 60]
        name = header[:16].decode("ascii", "replace").strip()
        size_text = header[48:58].decode("ascii", "replace").strip()
        try:
            size = int(size_text)
        except ValueError:
            break
        body = deb_bytes[offset + 60 : offset + 60 + size]
        if name.startswith("data.tar"):
            data_blob = body
            break
        offset += 60 + size + (size % 2)

    if data_blob is None:
        raise RuntimeError("未在 deb 中找到 data.tar")

    with tarfile.open(fileobj=io.BytesIO(data_blob), mode="r:*") as tf:
        for member in tf.getmembers():
            base = member.name.rsplit("/", 1)[-1]
            # 只取真实文件（跳过 .so 软链接，软链接内容为 0 字节）
            if base.startswith(prefix) and member.isfile() and member.size > 0:
                handle = tf.extractfile(member)
                if handle:
                    return handle.read()
    raise RuntimeError(f"deb 内未找到 {prefix}*")


def soname_of(blob: bytes) -> str:
    """读 ELF 的 DT_SONAME，确认拿到的库名正确。"""
    if blob[:4] != b"\x7fELF":
        return ""
    endian = "<" if blob[5] == 1 else ">"
    is64 = blob[4] == 2
    try:
        if is64:
            shoff, = _unpack(endian + "Q", blob, 0x28)
            shentsize, shnum = _unpack(endian + "HH", blob, 0x3A)
        else:
            shoff, = _unpack(endian + "I", blob, 0x20)
            shentsize, shnum = _unpack(endian + "HH", blob, 0x2E)
        secs = []
        for i in range(shnum):
            off = shoff + i * shentsize
            sh_type, = _unpack(endian + "I", blob, off + 4)
            sh_link, = _unpack(endian + "I", blob, off + 0x28)
            if is64:
                sh_offset, sh_size = _unpack(endian + "QQ", blob, off + 0x18)
            else:
                sh_offset, sh_size = _unpack(endian + "II", blob, off + 0x10)
            secs.append((sh_type, sh_offset, sh_size, sh_link))
        dyn = next((s for s in secs if s[0] == 6), None)
        if not dyn:
            return ""
        strtab = secs[dyn[3]]
        step = 16 if is64 else 8
        for pos in range(dyn[1], dyn[1] + dyn[2], step):
            tag, val = _unpack(endian + ("Qq" if is64 else "Ii"), blob, pos)
            if tag == 0:
                break
            if tag == 14:  # DT_SONAME
                start = strtab[1] + val
                end = blob.index(b"\x00", start)
                return blob[start:end].decode("ascii", "replace")
    except (IndexError, ValueError, StopIteration):
        return ""
    return ""


def _unpack(fmt: str, blob: bytes, offset: int):
    import struct

    return struct.unpack_from(fmt, blob, offset)


def glibc_requirement(blob: bytes) -> str:
    """从字符串表里找 GLIBC_x.y，给出最高要求，便于判断能否在老系统上用。"""
    import re

    versions = {v.decode() for v in re.findall(rb"GLIBC_(\d+\.\d+(?:\.\d+)?)", blob)}
    if not versions:
        return "未知"
    newest = sorted(versions, key=lambda s: [int(x) for x in s.split(".")])[-1]
    return f"GLIBC_{newest}"


def report(names: list[str], table: dict[str, dict[str, str]], download_dir: Path | None) -> int:
    unknown = [n for n in names if n not in table]
    missing_pkg: list[tuple[str, str, str]] = []

    for name in names:
        info = table.get(name)
        if not info:
            print(f"  {name}")
            print("    ✗ 对照表里没有。可能是别的库，用下面命令查它属于哪个包：")
            print(f"        apt-file search {name}      # 需先 apt-get install apt-file && apt-file update")
            print(f"        # 或在 https://packages.debian.org/search?searchon=contents&keywords={name} 搜")
            continue
        url = deb_url(info["pool"], info["package"], info["version"])
        print(f"  {name}")
        print(f"    包名   : {info['package']}（{info['note']}）")
        print(f"    下载   : {url}")
        print(f"    deb 内 : usr/lib/x86_64-linux-gnu/{name}.*")
        missing_pkg.append((name, info["package"], url))

    if download_dir is not None and missing_pkg:
        download_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n下载到 {download_dir} ...")
        for name, _package, url in missing_pkg:
            target = download_dir / name
            if target.is_file() and target.stat().st_size > 0:
                print(f"  {name}: 已存在，跳过")
                continue
            try:
                with urllib.request.urlopen(url, timeout=120) as resp:
                    deb = resp.read()
                blob = extract_so_from_deb(deb, name)
            except Exception as exc:  # noqa: BLE001 - 单条失败不影响其余
                print(f"  {name}: 失败 - {exc}")
                continue
            target.write_bytes(blob)
            actual = soname_of(blob)
            flag = "OK" if actual == name else f"注意：SONAME={actual or '未读到'}"
            print(f"  {name}: {len(blob) / 1024:.0f}KB, {glibc_requirement(blob)}, {flag}")
    return 1 if unknown else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把缺失的 .so 名解析成 Debian 包与下载地址",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
        "  python3 find_missing_lib.py libxcb-xinerama.so.0\n"
        "  python3 find_missing_lib.py --ldd-output /tmp/missing.txt\n"
        "  python3 find_missing_lib.py --download ./xcb-libs libxcb-xinerama.so.0\n",
    )
    parser.add_argument("libs", nargs="*", help="缺失的库名，如 libxcb-xinerama.so.0")
    parser.add_argument("--ldd-output", help="ldd 输出文件（自动提取 not found 的库名）")
    parser.add_argument("--download", metavar="DIR", help="下载并解包到该目录")
    args = parser.parse_args()

    names = list(args.libs)
    if args.ldd_output:
        text = Path(args.ldd_output).read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if "not found" in line:
                candidate = line.split("=>")[0].strip()
                if candidate and candidate not in names:
                    names.append(candidate)

    if not names:
        if args.ldd_output:
            print("这次 ldd 输出里没有 not found 的库，依赖齐全。")
            return 0
        parser.error("请给出库名，或用 --ldd-output 指定 ldd 输出")

    table = load_table()
    print(f"对照表：{TABLE}（{len(table)} 条）\n")
    code = report(names, table, Path(args.download) if args.download else None)
    if args.download:
        print("\n用法：把下载到的 .so 复制进包内 Qt 库目录，例如")
        print("  cp xcb-libs/* your-app/python/lib/python3.10/site-packages/PySide2/Qt/lib/")
    return code


if __name__ == "__main__":
    sys.exit(main())
