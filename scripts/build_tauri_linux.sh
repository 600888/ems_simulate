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

APP_NAME="ems-simulate"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 从 pyproject.toml 读取版本号（单一真相源）
VERSION=$(grep -oP 'version\s*=\s*"\K[^"]+' "$SCRIPT_DIR/../pyproject.toml")
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TAURI_DIR="${PROJECT_ROOT}/src-tauri"
BUILD_DIR="${PROJECT_ROOT}/build"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  EMS Simulate Tauri Linux Packaging${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

cd "$PROJECT_ROOT"

# Sync version to tauri.conf.json and package.json
echo -e "${CYAN}[STEP] 同步版本号到配置文件...${NC}"
python3 "$SCRIPT_DIR/sync_version.py"
echo -e "${GREEN}[SUCCESS] 版本号已同步${NC}"

# Check prerequisites
echo -e "${CYAN}[STEP] 检查构建环境...${NC}"
if ! command -v rustc &>/dev/null; then
    echo -e "${RED}[ERROR] 未找到 Rust，请安装: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh${NC}"
    exit 1
fi
echo -e "${GREEN}[SUCCESS] Rust: $(rustc --version)${NC}"

if ! command -v node &>/dev/null; then
    echo -e "${RED}[ERROR] 未找到 Node.js${NC}"
    exit 1
fi
echo -e "${GREEN}[SUCCESS] Node.js: $(node --version)${NC}"

# Generate Tauri icons
echo -e "${CYAN}[STEP] 生成 Tauri 图标...${NC}"
python3 scripts/generate_tauri_icons.py

# Build frontend
echo -e "${CYAN}[STEP] 构建前端...${NC}"
cd "${PROJECT_ROOT}/front"
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run build:fast
cd "$PROJECT_ROOT"
echo -e "${GREEN}[SUCCESS] 前端构建完成${NC}"

# Build Python backend with PyInstaller
BACKEND_BINARY_DIR="${TAURI_DIR}/ems_simulate_backend"

echo -e "${CYAN}[STEP] 构建 Python 后端 (PyInstaller --onedir)...${NC}"
mkdir -p "$BACKEND_BINARY_DIR"
mkdir -p "$BUILD_DIR"

pyinstaller --noconfirm --onedir \
    --name "ems_simulate_backend" \
    --clean \
    --distpath "${BUILD_DIR}/dist" \
    --workpath "${BUILD_DIR}/build_pyinstaller_tauri" \
    --specpath "$BUILD_DIR" \
    --add-data "${PROJECT_ROOT}/config.ini:." \
    --add-data "${PROJECT_ROOT}/www:www" \
    --hidden-import="uvicorn.logging" \
    --hidden-import="uvicorn.loops" \
    --hidden-import="openpyxl" \
    --hidden-import="uvicorn.loops.auto" \
    --hidden-import="uvicorn.protocols" \
    --hidden-import="uvicorn.protocols.http" \
    --hidden-import="uvicorn.protocols.http.auto" \
    --hidden-import="uvicorn.lifespan" \
    --hidden-import="uvicorn.lifespan.on" \
    --hidden-import="uvicorn.loops.asyncio" \
    --hidden-import="pymodbus" \
    --hidden-import="fastapi" \
    --hidden-import="sqlalchemy" \
    --hidden-import="pydantic" \
    --hidden-import="loguru" \
    start_back_end.py

# Copy PyInstaller output to Tauri resources
PYINSTALLER_OUTPUT="${BUILD_DIR}/dist/ems_simulate_backend"
if [ -d "$PYINSTALLER_OUTPUT" ]; then
    cp -r "$PYINSTALLER_OUTPUT"/* "$BACKEND_BINARY_DIR/"
    # Fix permissions
    chmod +x "${BACKEND_BINARY_DIR}/ems_simulate_backend" 2>/dev/null || true
fi
echo -e "${GREEN}[SUCCESS] Python 后端已打包${NC}"

# Build Tauri desktop app
echo -e "${CYAN}[STEP] 构建 Tauri 桌面应用...${NC}"
cd "$TAURI_DIR"

# Install Tauri CLI if needed
if ! cargo tauri --version &>/dev/null; then
    echo "安装 Tauri CLI..."
    cargo install tauri-cli --version "^2"
fi

echo "运行: cargo tauri build"
cargo tauri build

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
