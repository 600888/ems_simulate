#!/bin/bash
# Tauri Linux 打包脚本
# 构建前端 + PyInstaller 打包 Python 后端 + Tauri 打包桌面应用
#
# 前提条件:
#   1. 安装 Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
#   2. 安装 Tauri 系统依赖:
#      sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev
#   3. 安装 Tauri CLI: cargo install tauri-cli --version "^2"
#   4. 安装 Node.js (>=18)
#   5. 安装 Python 3.11+

set -e

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
VERSION=$(grep -oP 'version\s*=\s*"\K[^"]+' "$SCRIPT_DIR/../pyproject.toml")
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
    local target_time
    target_time=$(stat -c %Y "$target" 2>/dev/null) || return 1
    for ref in "$@"; do
        if [ ! -e "$ref" ]; then continue; fi
        local ref_time
        ref_time=$(stat -c %Y "$ref" 2>/dev/null) || return 1
        if [ "$ref_time" -gt "$target_time" ]; then return 1; fi
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
            start_back_end.py

        # PyInstaller --onefile 直接输出到 distpath，需重命名为 sidecar 格式
        PYINSTALLER_OUTPUT="${BINARIES_DIR}/ems_simulate_backend"
        if [ -f "$PYINSTALLER_OUTPUT" ]; then
            mv "$PYINSTALLER_OUTPUT" "$BE_SIDECAR_BINARY"
            chmod +x "$BE_SIDECAR_BINARY"
            WriteOk "Python 后端已打包: ${BE_SIDECAR_BINARY}"
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

# 构建 Tauri 桌面应用
TAURI_EXE="${TAURI_DIR}/target/release/ems-simulate"
TAURI_SRC="${TAURI_DIR}/src"
TAURI_CARGO="${TAURI_DIR}/Cargo.toml"

TAURI_UP_TO_DATE=false
if [ -f "$TAURI_EXE" ]; then
    TAURI_UP_TO_DATE=true
    for ref in "$TAURI_SRC" "$TAURI_CARGO" "$BE_SIDECAR_BINARY"; do
        if ! IsUpToDate "$TAURI_EXE" "$ref"; then
            TAURI_UP_TO_DATE=false
            break
        fi
    done
fi

if $TAURI_UP_TO_DATE; then
    WriteSkip "Tauri 构建已是最新"
else
    WriteStep "构建 Tauri 桌面应用..."
    cd "$TAURI_DIR"

    # Install Tauri CLI if needed
    if ! cargo tauri --version &>/dev/null; then
        echo "安装 Tauri CLI..."
        cargo install tauri-cli --version "^2"
    fi

    # Sidecar 二进制必须在构建前到位
    if [ ! -f "$BE_SIDECAR_BINARY" ]; then
        WriteErr "Sidecar 二进制未找到: ${BE_SIDECAR_BINARY}。请先运行 --skip-backend 构建后端。"
    fi

    echo "运行: cargo tauri build"
    cargo tauri build

    cd "$PROJECT_ROOT"
fi

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Tauri 构建完成!${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${YELLOW}安装包位置:${NC}"
echo -e "  - deb:  ${TAURI_DIR}/target/release/bundle/deb/"
echo -e "  - AppImage: ${TAURI_DIR}/target/release/bundle/appimage/"
echo ""
