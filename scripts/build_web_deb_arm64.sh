#!/usr/bin/env bash
set -Eeuo pipefail

# EMS Simulate Web Ubuntu ARM64 Deb 打包脚本。
#
# 构建必须在原生 aarch64 环境中执行。为兼容 Ubuntu 20.04 及更高版本，
# GitHub Actions 会在 Ubuntu 20.04 ARM64 容器中调用本脚本；本地也可直接运行。
# 前端静态资源需事先构建到项目根目录的 www/。
#
# 用法：
#   bash scripts/build_web_deb_arm64.sh
#   bash scripts/build_web_deb_arm64.sh --skip-backend

APP_NAME="ems-simulate-web"
BACKEND_NAME="ems_simulate_web"
ARCH="arm64"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION="$(grep -oP '^version\s*=\s*"\K[^"]+' "${PROJECT_ROOT}/pyproject.toml")"
[ -n "${VERSION}" ] || { echo "错误: 无法从 pyproject.toml 读取版本号"; exit 1; }

BUILD_DIR="${PROJECT_ROOT}/build/build_deb_web_arm64"
DEB_DIR="${BUILD_DIR}/${APP_NAME}_${VERSION}_${ARCH}"
INSTALL_DIR="${DEB_DIR}/usr/share/${APP_NAME}"
DEB_OUTPUT="${PROJECT_ROOT}/build/dist_deb/${APP_NAME}_${VERSION}_${ARCH}.deb"
PY_DIST="${BUILD_DIR}/dist"
PY_WORK="${BUILD_DIR}/build_pyinstaller_web"
VENV_DIR="${BUILD_DIR}/.venv"
VENV_PY="${VENV_DIR}/bin/python"
WWW_DIR="${PROJECT_ROOT}/www"
C104_PYPI_VERSION="${C104_PYPI_VERSION:-2.2.1}"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'
info() { echo -e "${BLUE}>>>${NC} $1"; }
ok() { echo -e "${GREEN}OK${NC} $1"; }
warn() { echo -e "${YELLOW}WARN${NC} $1"; }
die() { echo -e "${RED}ERROR${NC} $1"; exit 1; }

SKIP_BACKEND=0
for arg in "$@"; do
    case "${arg}" in
        --skip-backend) SKIP_BACKEND=1 ;;
        --help)
            echo "用法: bash scripts/build_web_deb_arm64.sh [--skip-backend]"
            exit 0
            ;;
        *) die "未知参数: ${arg}（使用 --help 查看用法）" ;;
    esac
done

case "$(uname -m)" in
    aarch64|arm64) ;;
    *) die "必须在原生 ARM64 环境中构建，当前架构: $(uname -m)" ;;
esac

command -v uv >/dev/null || die "未找到 uv: https://docs.astral.sh/uv/getting-started/installation/"
command -v dpkg-deb >/dev/null || die "未找到 dpkg-deb"

# 可用 PYTHON_BIN 指定 workflow 编译的共享库 Python；本地未指定时由 uv 查找。
PY="${PYTHON_BIN:-}"
if [ -z "${PY}" ]; then
    uv python install 3.11 >/dev/null 2>&1 || warn "uv 自动安装 Python 3.11 失败，将查找系统 Python"
    PY="$(uv python find 3.11 2>/dev/null || true)"
fi

python_has_shared_library() {
    [ -n "${1:-}" ] &&
        [ -x "$1" ] &&
        [ "$("$1" -c "import sysconfig; print(sysconfig.get_config_var('Py_ENABLE_SHARED') or 0)" 2>/dev/null)" = "1" ]
}

if ! python_has_shared_library "${PY}"; then
    for candidate in /usr/local/bin/python3.11 /usr/bin/python3.11; do
        if python_has_shared_library "${candidate}"; then
            PY="${candidate}"
            warn "uv Python 无共享库，改用 ${candidate}"
            break
        fi
    done
fi

if ! python_has_shared_library "${PY}"; then
    die "未找到带 libpython3.11.so 的 Python 3.11，PyInstaller 无法构建。可通过 PYTHON_BIN 指定解释器。"
fi
ok "Python 3.11: ${PY}（共享库可用）"

if [ "${SKIP_BACKEND}" -eq 1 ] && [ -x "${VENV_PY}" ]; then
    ok "复用打包虚拟环境: ${VENV_DIR}"
else
    uv venv --python "${PY}" --clear "${VENV_DIR}" || die "创建虚拟环境失败"
fi

if [ ! -f "${WWW_DIR}/index.html" ]; then
    die "前端产物不存在: ${WWW_DIR}/index.html，请先在 front/ 执行 npm ci && npm run build:fast"
fi
ok "前端产物: ${WWW_DIR}"

info "准备 Debian 包结构"
rm -rf "${DEB_DIR}"
mkdir -p "${INSTALL_DIR}" "${DEB_DIR}/usr/bin"
cp -r "${PROJECT_ROOT}/debian/." "${DEB_DIR}/"
sed -i "s|^Version:.*|Version: ${VERSION}|" "${DEB_DIR}/DEBIAN/control"
sed -i "s|^Architecture:.*|Architecture: ${ARCH}|" "${DEB_DIR}/DEBIAN/control"
sed -i "/^Installed-Size:/d" "${DEB_DIR}/DEBIAN/control"

if [ "${SKIP_BACKEND}" -eq 1 ]; then
    info "跳过 PyInstaller 构建"
else
    info "根据 uv.lock 安装 ARM64 后端构建依赖（排除仅供其他架构使用的 Git 版 c104）"
    UV_PROJECT_ENVIRONMENT="${VENV_DIR}" \
        uv sync \
            --project "${PROJECT_ROOT}" \
            --python "${PY}" \
            --frozen \
            --no-dev \
            --no-install-package c104 \
            --extra build || die "Python 依赖安装失败"

    info "从 PyPI 安装 ARM64 c104 ${C104_PYPI_VERSION}"
    uv pip install \
        --python "${VENV_PY}" \
        --default-index "https://pypi.org/simple" \
        --only-binary c104 \
        "c104==${C104_PYPI_VERSION}" || die "PyPI c104 安装失败"
    "${VENV_PY}" -c \
        "import importlib.metadata, platform, c104; assert importlib.metadata.version('c104') == '${C104_PYPI_VERSION}'; assert platform.machine() in {'aarch64', 'arm64'}" \
        || die "PyPI c104 ARM64 校验失败"

    info "运行 PyInstaller"
    EMS_PYINSTALLER_MODE=onedir \
    EMS_PYINSTALLER_NAME="${BACKEND_NAME}" \
    EMS_PYINSTALLER_CONTENTS_DIR=_internal \
    EMS_PYINSTALLER_DATA_SCOPE=all \
    EMS_PYINSTALLER_CONSOLE=1 \
    uv run --python "${VENV_PY}" --no-project -m PyInstaller \
        --noconfirm \
        --clean \
        --distpath "${PY_DIST}" \
        --workpath "${PY_WORK}" \
        "${PROJECT_ROOT}/ems_simulate_backend.spec" || die "PyInstaller 构建失败"
fi

PYINSTALLER_OUTPUT="${PY_DIST}/${BACKEND_NAME}"
[ -x "${PYINSTALLER_OUTPUT}/${BACKEND_NAME}" ] || die "PyInstaller 主程序不存在"

if ! find "${PYINSTALLER_OUTPUT}" -type f -name '*_c104*.so' -print -quit | grep -q .; then
    die "PyInstaller 产物缺少 c104 ARM64 原生扩展"
fi

if ! find "${PYINSTALLER_OUTPUT}" -type f -path '*/src/modeling/profile_packages/*/manifest.json' -print -quit | grep -q . ||
   ! find "${PYINSTALLER_OUTPUT}" -type f -path '*/src/modeling/standard_packages/*/manifest.json' -print -quit | grep -q .; then
    die "PyInstaller 产物缺少 modeling 包 manifest"
fi

info "组装 Debian 包"
cp -r "${PYINSTALLER_OUTPUT}/." "${INSTALL_DIR}/"
ln -sf "../share/${APP_NAME}/${BACKEND_NAME}" "${DEB_DIR}/usr/bin/${APP_NAME}"

INSTALLED_SIZE="$(du -s "${INSTALL_DIR}" | cut -f1)"
echo "Installed-Size: ${INSTALLED_SIZE}" >> "${DEB_DIR}/DEBIAN/control"

chmod 755 "${DEB_DIR}/DEBIAN/postinst" 2>/dev/null || true
chmod 755 "${DEB_DIR}/DEBIAN/prerm" 2>/dev/null || true
chmod 755 "${DEB_DIR}/DEBIAN/postrm" 2>/dev/null || true

info "生成 ARM64 Deb"
mkdir -p "$(dirname "${DEB_OUTPUT}")"
dpkg-deb --build --root-owner-group "${DEB_DIR}" "${DEB_OUTPUT}" || die "dpkg-deb 构建失败"

ok "构建完成: ${DEB_OUTPUT}"
dpkg-deb --info "${DEB_OUTPUT}"
