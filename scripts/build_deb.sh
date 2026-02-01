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
rm -rf "build/$BUILD_DIR" "build/$OUTPUT_DIR"
mkdir -p "build/$INSTALL_DIR"
mkdir -p "build/${DEB_DIR}/DEBIAN"
# 修改为 /lib/systemd/system
mkdir -p "build/${DEB_DIR}/lib/systemd/system"

# 2. 构建前端
echo ">>> 构建前端..."
cd front
npm install
npm run build
cd ..

# 检查前端构建结果
if [ ! -d "www" ]; then
    echo "错误: 前端构建失败，找不到 www 目录"
    exit 1
fi

# 3. 构建后端 (PyInstaller)
echo ">>> 构建后端 (PyInstaller)..."
# 注意: 在 Windows 上运行此命令会生成 .exe，在 Linux 上运行会生成 elf
# 使用 --onedir 模式，方便包含依赖文件
# 输出目录修改为 build/dist
pyinstaller --noconfirm --onedir --name "${APP_NAME//-/_}" --clean \
    --distpath "build/dist" \
    --workpath "build/build_pyinstaller" \
    --specpath "build" \
    --add-data "config.ini:." \
    --add-data "www:www" \
    --hidden-import="uvicorn.logging" \
    --hidden-import="uvicorn.loops" \
    --hidden-import="uvicorn.loops.auto" \
    --hidden-import="uvicorn.protocols" \
    --hidden-import="uvicorn.protocols.http" \
    --hidden-import="uvicorn.protocols.http.auto" \
    --hidden-import="uvicorn.lifespan" \
    --hidden-import="uvicorn.lifespan.on" \
    start_back_end.py

# 4. 复制文件到打包目录
echo ">>> 组装 Debian 包..."
# 复制 PyInstaller 生成的内容到 /usr/share/ems-simulate
cp -r "build/dist/${APP_NAME//-/_}/"* "build/$INSTALL_DIR/"

# 复制 Systemd 服务文件 (移至 /lib/systemd/system)
cp debian/ems_simulate.service "build/${DEB_DIR}/lib/systemd/system/"

# 复制 Control 文件及 maintainer 脚本
cp debian/control "build/${DEB_DIR}/DEBIAN/"
if [ -f "debian/postinst" ]; then cp "debian/postinst" "build/${DEB_DIR}/DEBIAN/"; fi
if [ -f "debian/prerm" ]; then cp "debian/prerm" "build/${DEB_DIR}/DEBIAN/"; fi
if [ -f "debian/postrm" ]; then cp "debian/postrm" "build/${DEB_DIR}/DEBIAN/"; fi
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

