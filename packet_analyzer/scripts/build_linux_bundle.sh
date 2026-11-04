#!/usr/bin/env bash
# 生成 Linux 离线部署包（在 Windows / Git Bash 或任意 Linux 上运行）
#
# 产物：
#   build/linux/packet-analyzer-linux-x86_64.tar.gz
#
# 包内结构：
#   packet-analyzer/
#       packet_analyzer/       核心代码（纯 Python，无 Qt）
#       pa.sh                  启动脚本
#       install.sh             自检与权限提示
#       README-linux.md        部署与用法
#       python/                便携 CPython 3.10（兼容 glibc 2.17+）
#
# 为什么带自己的 Python：
#   目标机常见 Debian 8 / glibc 2.19 + Python 3.4，既跑不了 PySide6（需 glibc 2.28），
#   也没有 3.10。便携版由 python-build-standalone 提供，解压即用、不动系统。
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)          # 仓库根目录
PKG="$ROOT/packet_analyzer"                        # 工具目录
OUT="$ROOT/build/linux"
ARCHIVE="$OUT/packet-analyzer-linux-x86_64.tar.gz"
PY_URL="${PY_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/20240726/cpython-3.10.14%2B20240726-x86_64-unknown-linux-gnu-install_only.tar.gz}"
PY_CACHE="${PY_CACHE:-$ROOT/build/cache/python310.tar.gz}"

# 选一个可用的 Python 来跑打包器
PY_BIN=""
for candidate in "$ROOT/.venv/Scripts/python.exe" "$ROOT/.venv/bin/python" python3 python; do
    if [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1; then
        PY_BIN="$candidate"
        break
    fi
done
if [ -z "$PY_BIN" ]; then
    echo "错误：未找到 Python，无法打包。" >&2
    exit 1
fi

mkdir -p "$OUT" "$(dirname "$PY_CACHE")"

if [ ! -f "$PY_CACHE" ]; then
    echo "[STEP] 下载便携 Python"
    echo "       $PY_URL"
    curl -fSL --retry 3 --max-time 900 -o "$PY_CACHE" "$PY_URL"
else
    echo "[STEP] 使用缓存的便携 Python：$PY_CACHE"
fi

"$PY_BIN" "$PKG/scripts/build_linux_bundle.py" \
    --package-dir "$PKG" \
    --cache "$PY_CACHE" \
    --output "$ARCHIVE"

echo "[INFO] 部署：scp 到目标机后 tar xzf，然后 ./packet-analyzer/install.sh"
