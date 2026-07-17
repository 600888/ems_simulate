#!/bin/bash
# Tauri Linux 打包脚本
# 构建前端 + PyInstaller 打包 Python 后端 + Tauri 打包桌面应用
#
# 前提条件:
#   1. 安装 Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
#   2. 安装 Tauri 系统依赖:
#      sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev libgdk-pixbuf2.0-dev libpango1.0-dev libatk1.0-dev libayatana-appindicator3-dev librsvg2-dev libssl-dev patchelf pkg-config build-essential squashfs-tools
#   3. 安装 Tauri CLI: cargo install tauri-cli --version "^2"
#   4. 安装 Node.js (>=18)
#   5. 安装 Python 3.11+

set -Eeuo pipefail

# 解析命令行参数
SKIP_BUILD=false
SKIP_BACKEND=false
HELP=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-build)   SKIP_BUILD=true; shift ;;
        --skip-backend) SKIP_BACKEND=true; shift ;;
        --help|-h)      HELP=true; shift ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

if $HELP; then
    cat <<'EOF'
用法: ./build_tauri_linux.sh [选项]

选项:
  --skip-build    跳过前端构建
  --skip-backend  跳过 Python 后端构建
  --help, -h      显示此帮助信息
EOF
    exit 0
fi

APP_NAME="ems-simulate"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 从 pyproject.toml 读取版本号（单一真相源）
VERSION=$(grep -oP '^version\s*=\s*"\K[^"]+' "$SCRIPT_DIR/../pyproject.toml")
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TAURI_DIR="${PROJECT_ROOT}/src-tauri"
BUILD_DIR="${PROJECT_ROOT}/build"
BINARIES_DIR="${TAURI_DIR}/binaries"
# 获取 Rust 目标平台三元组，用于 Tauri sidecar 命名
RUST_TARGET_TRIPLE=$(rustc -vV | grep "^host:" | awk '{print $2}')
BE_SIDECAR_BINARY="${BINARIES_DIR}/ems_simulate_backend-${RUST_TARGET_TRIPLE}"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

function WriteStep() { echo -e "${CYAN}[STEP] $*${NC}"; }
function WriteOk()   { echo -e "${GREEN}[SUCCESS] $*${NC}"; }
function WriteSkip() { echo -e "${YELLOW}[SKIP] $*${NC}"; }
function WriteErr()  { echo -e "${RED}[ERROR] $*${NC}"; exit 1; }

# 判断目标是否比所有参考文件都新
# 返回 0 (true) 表示已是最新，1 (false) 表示需要重新构建
function IsUpToDate() {
    local target="$1"; shift
    if [ ! -f "$target" ]; then return 1; fi
    for ref in "$@"; do
        if [ ! -e "$ref" ]; then continue; fi
        if [ -d "$ref" ]; then
            # Directory mtimes do not change when an existing nested file is
            # edited. Check the contents so changes to Python sources or the
            # seed database cannot leave a stale sidecar in the installer.
            if find "$ref" -type f -newer "$target" -print -quit | grep -q .; then
                return 1
            fi
        elif [ "$ref" -nt "$target" ]; then
            return 1
        fi
    done
    return 0
}

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  EMS Simulate Tauri Linux Packaging${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

cd "$PROJECT_ROOT"

# Sync version to tauri.conf.json, Cargo.toml, package.json, etc.
WriteStep "同步版本号到配置文件..."
python "$SCRIPT_DIR/sync_version.py"
WriteOk "版本号已同步"

# Check prerequisites
WriteStep "检查构建环境..."
if ! command -v rustc &>/dev/null; then
    WriteErr "未找到 Rust，请安装: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
fi
WriteOk "Rust: $(rustc --version)"

if ! command -v node &>/dev/null; then
    WriteErr "未找到 Node.js"
fi
WriteOk "Node.js: $(node --version)"

if ! command -v mksquashfs &>/dev/null; then
    WriteErr "未找到 mksquashfs，请安装 squashfs-tools"
fi
WriteOk "mksquashfs: $(mksquashfs -version 2>&1 | head -n 1)"

# Generate Tauri icons (skip if already up-to-date)
ICON_SOURCE="${PROJECT_ROOT}/resources/icon.png"
ICONS_UP_TO_DATE=true
TAURI_ICONS=(
    "${TAURI_DIR}/icons/32x32.png"
    "${TAURI_DIR}/icons/128x128.png"
    "${TAURI_DIR}/icons/128x128@2x.png"
    "${TAURI_DIR}/icons/icon.png"
)
for icon in "${TAURI_ICONS[@]}"; do
    if ! IsUpToDate "$icon" "$ICON_SOURCE"; then
        ICONS_UP_TO_DATE=false
        break
    fi
done

if $ICONS_UP_TO_DATE; then
    WriteSkip "Tauri 图标已是最新"
else
    WriteStep "生成 Tauri 图标..."
    python scripts/generate_tauri_icons.py
    WriteOk "Tauri 图标已生成"
fi

# Build frontend
if ! $SKIP_BUILD; then
    FRONT_DIST="${PROJECT_ROOT}/www"
    FRONT_SRC_DIR="${PROJECT_ROOT}/front/src"

    if [ -d "$FRONT_DIST" ] && IsUpToDate "$FRONT_DIST" "$FRONT_SRC_DIR"; then
        WriteSkip "前端构建已是最新"
    else
        WriteStep "构建前端..."
        cd "${PROJECT_ROOT}/front"
        if [ ! -d "node_modules" ]; then
            npm install
        fi
        npm run build:fast
        cd "$PROJECT_ROOT"
        WriteOk "前端构建完成"
    fi
else
    WriteSkip "前端构建 (已通过 --skip-build 跳过)"
fi

# Kill any running backend process that may lock www/ files
BE_PROCESS_PID=$(pgrep -f "ems_simulate_backend" 2>/dev/null || true)
if [ -n "$BE_PROCESS_PID" ]; then
    WriteStep "停止运行中的后端进程 (可能锁定 www/ 文件)..."
    kill "$BE_PROCESS_PID" 2>/dev/null || true
    sleep 1
    WriteOk "后端进程已停止"
fi

# 构建 Python 后端（Tauri sidecar 单文件模式，与 Windows 对齐）
if ! $SKIP_BACKEND; then
    # 检查后端是否已是最新
    BE_SOURCES=(
        "${PROJECT_ROOT}/start_back_end.py"
        "${PROJECT_ROOT}/src"
        "${PROJECT_ROOT}/config.ini"
        "${PROJECT_ROOT}/data"
        "${PROJECT_ROOT}/pyproject.toml"
    )

    BE_UP_TO_DATE=false
    if [ -f "$BE_SIDECAR_BINARY" ]; then
        BE_UP_TO_DATE=true
        for src in "${BE_SOURCES[@]}"; do
            if ! IsUpToDate "$BE_SIDECAR_BINARY" "$src"; then
                BE_UP_TO_DATE=false
                break
            fi
        done
    fi

    if $BE_UP_TO_DATE; then
        WriteSkip "Python 后端已是最新"
    else
        WriteStep "构建 Python 后端 (PyInstaller --onefile for Tauri Sidecar)..."

        # 清理旧 sidecar 目录
        rm -rf "$BINARIES_DIR"
        mkdir -p "$BINARIES_DIR"
        mkdir -p "$BUILD_DIR"

        pyinstaller --noconfirm --onefile \
            --name "ems_simulate_backend" \
            --clean \
            --distpath "$BINARIES_DIR" \
            --workpath "${BUILD_DIR}/build_pyinstaller_tauri" \
            --specpath "$BUILD_DIR" \
            --add-data "${PROJECT_ROOT}/config.ini:." \
            --add-data "${PROJECT_ROOT}/www:www" \
            --add-data "${PROJECT_ROOT}/data:data" \
            --hidden-import="uvicorn.logging" \
            --hidden-import="uvicorn.loops" \
            --hidden-import="openpyxl" \
            --hidden-import="uvicorn.loops.auto" \
            --hidden-import="uvicorn.loops.asyncio" \
            --hidden-import="uvicorn.protocols" \
            --hidden-import="uvicorn.protocols.http" \
            --hidden-import="uvicorn.protocols.http.auto" \
            --hidden-import="uvicorn.lifespan" \
            --hidden-import="uvicorn.lifespan.on" \
            --hidden-import="pymodbus" \
            --hidden-import="fastapi" \
            --hidden-import="sqlalchemy" \
            --hidden-import="pydantic" \
            --hidden-import="loguru" \
            --hidden-import="c104" \
            start_back_end.py

        # PyInstaller --onefile 直接输出到 distpath，需重命名为 sidecar 格式
        PYINSTALLER_OUTPUT="${BINARIES_DIR}/ems_simulate_backend"
        if [ -f "$PYINSTALLER_OUTPUT" ]; then
            mv "$PYINSTALLER_OUTPUT" "$BE_SIDECAR_BINARY"
            chmod +x "$BE_SIDECAR_BINARY"
            if ! pyi-archive_viewer -l "$BE_SIDECAR_BINARY" | grep '_c104' >/dev/null; then
                WriteErr "PyInstaller sidecar 缺少 c104 原生扩展"
            fi
            WriteOk "Python 后端已打包: ${BE_SIDECAR_BINARY}"
            WriteOk "c104 原生扩展检查通过"
        else
            WriteErr "PyInstaller 输出未找到: $PYINSTALLER_OUTPUT"
        fi
    fi
else
    WriteSkip "Python 后端构建 (已通过 --skip-backend 跳过)"
fi

# 清理旧的 onedir 构建产物（如果存在）
if [ -d "${TAURI_DIR}/ems_simulate_backend" ]; then
    rm -rf "${TAURI_DIR}/ems_simulate_backend"
    WriteOk "已清理旧的 onedir 构建产物"
fi

# 构建 Tauri 桌面应用。这里不能仅根据主程序时间戳跳过：上一次可能已经
# 编译出主程序，但在 linuxdeploy 阶段失败，安装包仍然是不完整的。
WriteStep "构建 Tauri 桌面应用..."
cd "$TAURI_DIR"

# Install Tauri CLI if needed
if ! cargo tauri --version &>/dev/null; then
    echo "安装 Tauri CLI..."
    cargo install tauri-cli --version "^2"
fi

# Sidecar 二进制必须在构建前到位且可执行。
if [ ! -f "$BE_SIDECAR_BINARY" ]; then
    WriteErr "Sidecar 二进制未找到: ${BE_SIDECAR_BINARY}。请去掉 --skip-backend 后重新构建。"
fi
if [ ! -x "$BE_SIDECAR_BINARY" ]; then
    chmod +x "$BE_SIDECAR_BINARY"
fi

# Tauri 会把 externalBin 复制到 target/release 并去掉 target triple。
# 删除旧副本，防止增量构建误打包上一次的 sidecar。
rm -f "${TAURI_DIR}/target/release/ems_simulate_backend"

# 分开构建便于定位故障；AppImage 失败时，已经成功的 deb 仍然清晰可见。
echo "运行: cargo tauri build --bundles deb --verbose"
cargo tauri build --bundles deb --verbose

# linuxdeploy 会 strip AppDir 中的所有 ELF。PyInstaller --onefile 在 ELF 尾部
# 附加了 Python 归档，不能直接参与 strip；但全局 NO_STRIP=1 又会让 WebKitGTK、
# GTK 等所有运行库保留符号，导致 AppImage 体积膨胀到数百 MB。
#
# AppImage 构建时先用同名 shell 占位 sidecar，让 linuxdeploy 正常裁剪其他 ELF；
# 生成后再解包 AppImage、注入真实 sidecar，并重建 SquashFS。
mkdir -p "$BUILD_DIR"
SIDECAR_BACKUP=$(mktemp "${BUILD_DIR}/ems-sidecar.XXXXXX")
mv "$BE_SIDECAR_BINARY" "$SIDECAR_BACKUP"

restore_sidecar() {
    if [ -f "$SIDECAR_BACKUP" ]; then
        mv -f "$SIDECAR_BACKUP" "$BE_SIDECAR_BINARY"
        chmod +x "$BE_SIDECAR_BINARY"
    fi
}
trap restore_sidecar EXIT

printf '%s\n' '#!/bin/sh' 'echo "EMS backend sidecar placeholder must be replaced during AppImage packaging" >&2' 'exit 127' > "$BE_SIDECAR_BINARY"
chmod +x "$BE_SIDECAR_BINARY"
rm -f "${TAURI_DIR}/target/release/ems_simulate_backend"
rm -rf "${TAURI_DIR}/target/release/bundle/appimage"

echo "运行: cargo tauri build --bundles appimage --verbose"
cargo tauri build --bundles appimage --verbose

restore_sidecar
trap - EXIT
rm -f "${TAURI_DIR}/target/release/ems_simulate_backend"

shopt -s nullglob
APPIMAGE_FILES=("${TAURI_DIR}/target/release/bundle/appimage/"*.AppImage)
shopt -u nullglob
if [ "${#APPIMAGE_FILES[@]}" -ne 1 ]; then
    WriteErr "预期生成 1 个 AppImage，实际找到 ${#APPIMAGE_FILES[@]} 个"
fi
APPIMAGE_PATH="${APPIMAGE_FILES[0]}"
APPIMAGE_REPACK_DIR=$(mktemp -d "${BUILD_DIR}/appimage-repack.XXXXXX")

cleanup_appimage_repack() {
    rm -rf "$APPIMAGE_REPACK_DIR"
}
trap cleanup_appimage_repack EXIT

WriteStep "重新封装 AppImage（注入未被 strip 的 Python sidecar）..."
(
    cd "$APPIMAGE_REPACK_DIR"
    "$APPIMAGE_PATH" --appimage-extract >/dev/null
)

mapfile -d '' PACKAGED_SIDECARS < <(find "$APPIMAGE_REPACK_DIR/squashfs-root" -type f -name 'ems_simulate_backend' -print0)
if [ "${#PACKAGED_SIDECARS[@]}" -ne 1 ]; then
    WriteErr "AppImage 中预期找到 1 个 sidecar，实际找到 ${#PACKAGED_SIDECARS[@]} 个"
fi
install -m 755 "$BE_SIDECAR_BINARY" "${PACKAGED_SIDECARS[0]}"

APPIMAGE_OFFSET=$("$APPIMAGE_PATH" --appimage-offset)
if ! [[ "$APPIMAGE_OFFSET" =~ ^[0-9]+$ ]] || [ "$APPIMAGE_OFFSET" -le 0 ]; then
    WriteErr "无法读取 AppImage runtime offset: $APPIMAGE_OFFSET"
fi

head -c "$APPIMAGE_OFFSET" "$APPIMAGE_PATH" > "$APPIMAGE_REPACK_DIR/runtime"
mksquashfs "$APPIMAGE_REPACK_DIR/squashfs-root" "$APPIMAGE_REPACK_DIR/filesystem.squashfs" \
    -noappend \
    -comp zstd \
    -Xcompression-level 19 \
    -b 1M >/dev/null
cat "$APPIMAGE_REPACK_DIR/runtime" "$APPIMAGE_REPACK_DIR/filesystem.squashfs" > "$APPIMAGE_REPACK_DIR/repacked.AppImage"
chmod +x "$APPIMAGE_REPACK_DIR/repacked.AppImage"
mv -f "$APPIMAGE_REPACK_DIR/repacked.AppImage" "$APPIMAGE_PATH"

cleanup_appimage_repack
trap - EXIT
WriteOk "AppImage 已重新封装: $APPIMAGE_PATH ($(du -h "$APPIMAGE_PATH" | cut -f1))"

cd "$PROJECT_ROOT"

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Tauri 构建完成!${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${YELLOW}安装包位置:${NC}"
echo -e "  - deb:  ${TAURI_DIR}/target/release/bundle/deb/"
echo -e "  - AppImage: ${TAURI_DIR}/target/release/bundle/appimage/"
echo ""
