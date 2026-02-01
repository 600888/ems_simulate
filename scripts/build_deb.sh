#!/bin/bash
set -e

# 配置
APP_NAME="ems-simulate"
VERSION="1.0.0"
BUILD_DIR="build_deb"
OUTPUT_DIR="dist"
DEB_DIR="${BUILD_DIR}/${APP_NAME}_${VERSION}_amd64"
# 修改为 /usr/share (对应 onedir 资源+二进制)
INSTALL_DIR="${DEB_DIR}/usr/share/${APP_NAME}"

# 切换到项目根目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

echo ">>> 开始构建 ${APP_NAME} v${VERSION}..."

# 1. 清理旧构建 (在 build/ 目录下)
# 2. 构建前端
echo ">>> 构建前端..."
cd front
npm install
npm run build:fast
cd ..

# 检查前端构建结果
if [ ! -d "www" ]; then
    echo "错误: 前端构建失败，找不到 www 目录"
    exit 1
fi

# 3. 准备 Debian 包结构 (直接复制骨架)
echo ">>> 准备 Debian 包结构..."
# 复制 debian 下的所有内容到构建目录
cp -r debian/* "build/${DEB_DIR}/"

# 4. 构建后端 (PyInstaller)
echo ">>> 构建后端 (PyInstaller)..."
# 注意: 在 Windows 上运行此命令会生成 .exe，在 Linux 上运行会生成 elf
# 使用 --onedir 模式，方便包含依赖文件
# 输出目录修改为 build/dist
# 获取项目根目录的绝对路径
PROJECT_ROOT=$(pwd)

pyinstaller --noconfirm --onedir --name "${APP_NAME//-/_}" --clean \
    --distpath "build/dist" \
    --workpath "build/build_pyinstaller" \
    --specpath "build" \
    --add-data "${PROJECT_ROOT}/config.ini:etc" \
    --add-data "${PROJECT_ROOT}/www:www" \
    --hidden-import="uvicorn.logging" \
    --hidden-import="uvicorn.loops" \
    --hidden-import="uvicorn.loops.auto" \
    --hidden-import="uvicorn.protocols" \
    --hidden-import="uvicorn.protocols.http" \
    --hidden-import="uvicorn.protocols.http.auto" \
    --hidden-import="uvicorn.lifespan" \
    --hidden-import="uvicorn.lifespan.on" \
    start_back_end.py

# 5. 组装内容
echo ">>> 组装 Debian 包..."
# 复制 PyInstaller 生成的内容到 /usr/share/ems-simulate
cp -r "build/dist/${APP_NAME//-/_}/"* "build/$INSTALL_DIR/"

# 创建 /usr/bin 下的软链接
ln -sf "../share/${APP_NAME}/ems_simulate" "build/${DEB_DIR}/usr/bin/${APP_NAME}"

# 权限设置和 Control 更新在后面...
# 更新 Control 文件中的 Installed-Size
# INSTALLED_SIZE=$(du -s "$INSTALL_DIR" | cut -f1)
# echo "Installed-Size: $INSTALLED_SIZE" >> "${DEB_DIR}/DEBIAN/control"

# 5. 设置权限
chmod 755 "build/${DEB_DIR}/DEBIAN/postinst" 2>/dev/null || true
chmod 755 "build/${DEB_DIR}/DEBIAN/prerm" 2>/dev/null || true
chmod 755 "build/${DEB_DIR}/DEBIAN/postrm" 2>/dev/null || true

# 6. 生成 .deb
echo ">>> 生成 .deb 文件..."
mkdir -p build/dist_deb
dpkg-deb --build "build/$DEB_DIR" "build/dist_deb/${APP_NAME}_${VERSION}_amd64.deb"

echo ">>> 打包完成！文件位于 build/dist_deb/"

