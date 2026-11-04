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

# 本地 site-packages：用于把 pydnp3_pure 这类纯 Python 可选依赖并入包内
SITE_PACKAGES=""
for candidate in "$ROOT/.venv/Lib/site-packages" "$ROOT/.venv/lib/python3.10/site-packages" "$ROOT/.venv/lib/python3.11/site-packages"; do
    if [ -d "$candidate" ]; then
        SITE_PACKAGES="$candidate"
        break
    fi
done
if [ -z "$SITE_PACKAGES" ]; then
    echo "[WARN] 未找到 .venv/site-packages，DNP3 对象解析会降级（缺 pydnp3_pure）" >&2
fi

mkdir -p "$OUT" "$(dirname "$PY_CACHE")"

if [ ! -f "$PY_CACHE" ]; then
    echo "[STEP] 下载便携 Python"
    echo "       $PY_URL"
    curl -fSL --retry 3 --max-time 900 -o "$PY_CACHE" "$PY_URL"
else
    echo "[STEP] 使用缓存的便携 Python：$PY_CACHE"
fi

# --gui：额外打包 PySide2(Qt5)，给装不了 Qt6 的老系统出图形版
GUI_ARGS=()
if [ "${1:-}" = "--gui" ] || [ "${PA_GUI:-0}" = "1" ]; then
    WHEEL_DIR="${WHEEL_DIR:-$ROOT/build/cache/wheels}"
    LIBDBUS="${LIBDBUS:-$ROOT/build/cache/libdbus-1.so.3}"
    PYSIDE2_WHEEL=$(ls "$WHEEL_DIR"/PySide2-*.whl 2>/dev/null | head -1 || true)
    SHIBOKEN_WHEEL=$(ls "$WHEEL_DIR"/shiboken2-*.whl 2>/dev/null | head -1 || true)
    if [ -z "$PYSIDE2_WHEEL" ] || [ -z "$SHIBOKEN_WHEEL" ]; then
        echo "错误：$WHEEL_DIR 下缺少 PySide2/shiboken2 的 manylinux wheel" >&2
        echo "  参考 README-linux.md「图形界面」一节的下载说明" >&2
        exit 1
    fi
    ARCHIVE="$OUT/packet-analyzer-linux-x86_64-gui.tar.gz"
    GUI_ARGS=(--qt5-wheels "$SHIBOKEN_WHEEL" "$PYSIDE2_WHEEL" --gui)
    if [ -f "$LIBDBUS" ]; then
        GUI_ARGS+=(--libdbus "$LIBDBUS")
    fi
    echo "[STEP] 图形版：PySide2 = $(basename "$PYSIDE2_WHEEL")"
fi

"$PY_BIN" "$PKG/scripts/build_linux_bundle.py" \
    --package-dir "$PKG" \
    --cache "$PY_CACHE" \
    --output "$ARCHIVE" \
    ${SITE_PACKAGES:+--site-packages "$SITE_PACKAGES"} \
    "${GUI_ARGS[@]}"

echo "[INFO] 部署：scp 到目标机后 tar xzf，然后 ./install.sh"
if [ ${#GUI_ARGS[@]} -gt 0 ]; then
    echo "[INFO] 图形版启动：./pa-gui.sh（命令行仍用 ./pa.sh）"
fi
