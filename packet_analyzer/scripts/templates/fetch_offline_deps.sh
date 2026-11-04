#!/usr/bin/env bash
# 一次性备齐离线部署所需的全部外部依赖（在能上网的开发机上运行）。
#
# 产物（默认放在 ./cache）：
#   cache/python310.tar.gz      便携 CPython 3.10（glibc 2.17+，解压即用）
#   cache/wheels/PySide2-*.whl  Qt5 绑定
#   cache/wheels/shiboken2-*.whl
#   cache/libdbus-1.so.3        较新的 libdbus（Qt5.15 需要 >=1.10）
#
# 用法：
#   bash fetch_offline_deps.sh              # 全部下载
#   bash fetch_offline_deps.sh --no-qt      # 只要 Python（纯命令行程序）
#   CACHE_DIR=/data/cache bash fetch_offline_deps.sh
set -euo pipefail

# 默认放在「当前工作目录/cache」，可用 CACHE_DIR 覆盖。
# 不默认放在脚本旁边，避免污染源码树。
CACHE_DIR="${CACHE_DIR:-$(pwd)/cache}"
PY_VER="${PY_VER:-3.10}"          # 3.10 / 3.11 / 3.12 都可以；3.9 及以下不行
PBS_TAG="${PBS_TAG:-20240726}"    # python-build-standalone 的发布标签
WANT_QT=1
for arg in "$@"; do
    [ "$arg" = "--no-qt" ] && WANT_QT=0
done

mkdir -p "$CACHE_DIR/wheels"
cd "$CACHE_DIR"

# PySide2 5.15.2.1 的 abi3 wheel 只覆盖 cp35–cp310，Python 3.11+ 没有 Qt5 绑定。
# 所以「老系统 + 图形界面」这条路线锁定 3.10。
if [ "$WANT_QT" = "1" ] && [ "$PY_VER" != "3.10" ]; then
    cat >&2 <<EOF
错误：PySide2(Qt5) 的 wheel 只支持到 Python 3.10（abi3 cp35-cp310）。
当前 PY_VER=$PY_VER，请改用：
  PY_VER=3.10 bash fetch_offline_deps.sh
若一定要用 Python $PY_VER，图形界面只能选 Qt6(PySide6)，
而 Qt6 要求 glibc >= 2.28 —— 老系统上不可行。
EOF
    exit 2
fi

# 清华镜像比 files.pythonhosted.org 快很多，且支持同一个 packages/ 路径
MIRROR="${MIRROR:-https://pypi.tuna.tsinghua.edu.cn/packages}"

say() { echo "[$(date +%H:%M:%S)] $*"; }

# ---------------------------------------------------------------- 1. 便携 Python
# 文件名格式固定，改 PY_VER 时把版本号一起改（需三者一致）
case "$PY_VER" in
    3.10) PY_FULL="3.10.14" ;;
    3.11) PY_FULL="3.11.9"  ;;
    3.12) PY_FULL="3.12.4"  ;;
    *) echo "暂不支持 PY_VER=$PY_VER（用 3.10 / 3.11 / 3.12）" >&2; exit 2 ;;
esac
PY_TGZ="python${PY_VER/./}.tar.gz"
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/cpython-${PY_FULL}%2B${PBS_TAG}-x86_64-unknown-linux-gnu-install_only.tar.gz"

if [ -s "$PY_TGZ" ]; then
    say "已存在 $PY_TGZ，跳过下载"
else
    say "下载便携 Python ${PY_FULL}"
    say "  $PY_URL"
    # GitHub 直连有时很慢；失败时给出可操作的替代方案
    if ! curl -fSL --retry 3 --connect-timeout 20 --max-time 1800 -o "$PY_TGZ.part" "$PY_URL"; then
        rm -f "$PY_TGZ.part"
        cat >&2 <<'EOF'
下载失败。可选方案：
  1) 用代理重试：  HTTPS_PROXY=http://127.0.0.1:7890 bash fetch_offline_deps.sh
  2) 浏览器手动下载上面的 URL，改名放进 cache 目录
  3) 换 PY_VER（如 PY_VER=3.11）再试
EOF
        exit 1
    fi
    mv "$PY_TGZ.part" "$PY_TGZ"
fi
say "便携 Python：$(du -h "$PY_TGZ" | cut -f1)"

# ---------------------------------------------------------------- 2. Qt5 wheel
if [ "$WANT_QT" = "1" ]; then
    PY_TAG="cp${PY_VER/./}"   # cp310 / cp311 / cp312
    # PySide2 5.15.2.1 是最后一个支持 Qt5 的版本，abi3 wheel 覆盖 cp35–cp310
    PYSIDE_WHL="PySide2-5.15.2.1-5.15.2-cp35.cp36.cp37.cp38.cp39.cp310-abi3-manylinux1_x86_64.whl"
    SHIBOKEN_WHL="shiboken2-5.15.2.1-5.15.2-cp35.cp36.cp37.cp38.cp39.cp310-abi3-manylinux1_x86_64.whl"

    fetch_wheel() {
        whl="$1"
        if [ -s "wheels/$whl" ]; then
            say "已存在 $whl，跳过"
            return
        fi
        # 先问 PyPI 要真实下载地址，再换成镜像域名，避免硬编码哈希路径
        url=$(curl -sS --max-time 60 "https://pypi.org/pypi/$(echo "$whl" | cut -d- -f1)/5.15.2.1/json" \
              | grep -o "https://files.pythonhosted.org/packages/[^\"]*$(echo "$whl" | sed 's/+/%2B/g')" \
              | head -1)
        if [ -z "$url" ]; then
            say "无法解析 $whl 的下载地址，请手动从 PyPI 下载后放入 wheels/"
            return 1
        fi
        path=${url#https://files.pythonhosted.org/}
        say "下载 $whl"
        if ! curl -fSL --retry 2 --max-time 1800 -o "wheels/$whl.part" "$MIRROR/$path"; then
            say "  镜像失败，回退官方源"
            curl -fSL --retry 2 --max-time 1800 -o "wheels/$whl.part" "$url"
        fi
        mv "wheels/$whl.part" "wheels/$whl"
        say "  $(du -h "wheels/$whl" | cut -f1)"
    }

    fetch_wheel "$SHIBOKEN_WHL"
    fetch_wheel "$PYSIDE_WHL"

    # ------------------------------------------------------------ 3. libdbus
    # 老系统的 libdbus 常是 1.8，Qt5.15 需要 LIBDBUS_1_3（>=1.10）。
    # 取 Debian 11 的 1.12.28，只抽 .so 文件，不动系统。
    if [ -s "libdbus-1.so.3" ]; then
        say "已存在 libdbus-1.so.3，跳过"
    else
        say "下载 libdbus 1.12.28（Debian 11）"
        deb="libdbus-1-3_1.12.28-0+deb11u1_amd64.deb"
        if curl -fSL --max-time 600 -o "$deb" "http://deb.debian.org/debian/pool/main/d/dbus/$deb"; then
            here=$(pwd)
            tmp=$(mktemp -d)
            # 用绝对路径，不依赖 $OLDPWD（有些环境会清空它）
            if (cd "$tmp" && ar x "$here/$deb" && tar xf data.tar.* 2>/dev/null) ; then
                found=$(find "$tmp" -name "libdbus-1.so.3.*" | head -1)
                if [ -n "$found" ]; then
                    cp "$found" libdbus-1.so.3
                    say "  $(du -h libdbus-1.so.3 | cut -f1)"
                else
                    say "  未找到 libdbus-1.so.3.*，请手动解压 deb 取该文件"
                fi
            else
                say "  解包失败（可能缺 ar/tar），请手动解压 deb"
            fi
            rm -rf "$tmp" "$deb"
        else
            say "  libdbus 下载失败；若目标机 dbus 已 ≥1.10 可忽略"
            rm -f "$deb"
        fi
    fi

    # ------------------------------------------------------------ 4. libxcb-util
    # Qt5.15 的 xcb 插件要 libxcb-util.so.1，而 Debian ≤10 只给 .so.0（包名 libxcb-util0）。
    # 缺了会报 "Could not load the Qt platform plugin xcb ... even though it was found"。
    # 这个库只有 27KB，直接带进包里最省事。
    if [ -s "libxcb-util.so.1" ]; then
        say "已存在 libxcb-util.so.1，跳过"
    else
        say "下载 libxcb-util1"
        deb="libxcb-util1_0.4.0-1+b1_amd64.deb"
        if curl -fSL --max-time 600 -o "$deb" "http://deb.debian.org/debian/pool/main/x/xcb-util/$deb"; then
            here=$(pwd)
            tmp=$(mktemp -d)
            if (cd "$tmp" && ar x "$here/$deb" && tar xf data.tar.* 2>/dev/null); then
                found=$(find "$tmp" -name "libxcb-util.so.1.*" | head -1)
                if [ -n "$found" ]; then
                    # 统一改名为 SONAME，打包器会据此写进 Qt 库目录
                    cp "$found" libxcb-util.so.1
                    say "  $(du -h libxcb-util.so.1 | cut -f1)"
                else
                    say "  未找到库文件，请手动解压 deb"
                fi
            fi
            rm -rf "$tmp" "$deb"
        else
            say "  libxcb-util 下载失败；Debian ≤10 的图形界面会启动失败"
            rm -f "$deb"
        fi
    fi
fi

say "完成。cache 目录：$CACHE_DIR"
ls -1sh "$CACHE_DIR" "$CACHE_DIR/wheels" 2>/dev/null | sed 's/^/  /'
