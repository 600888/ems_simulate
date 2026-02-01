#!/bin/bash
set -e

APP_NAME="ems-simulate"
VERSION="1.0.0"

# 切换到脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# 构件输出目录在项目根目录下的 build/dist_deb
DIST_DEB_DIR="$SCRIPT_DIR/../build/dist_deb"

if [ ! -d "$DIST_DEB_DIR" ]; then
    echo "错误: 找不到 dist_deb 目录 ($DIST_DEB_DIR)，请先运行构建脚本。"
    exit 1
fi

cd "$DIST_DEB_DIR" || exit 1
DEB_FILE="${APP_NAME}_${VERSION}_amd64.deb"

echo ">>> 开始测试 .deb 包结构..."

if [ ! -f "$DEB_FILE" ]; then
    echo "错误: 未找到 .deb 文件: $DEB_FILE"
    exit 1
fi

# 使用 dpkg -c 查看包内容
echo ">>> 包内容列表:"
CONTENTS=$(dpkg -c "$DEB_FILE")
echo "$CONTENTS"

# 验证关键文件是否存在
echo ">>> 验证关键文件..."

check_file() {
    local file=$1
    if echo "$CONTENTS" | grep -q "$file"; then
        echo "[OK] 找到: $file"
    else
        echo "[FAIL] 缺失: $file"
        failed=1
    fi
}

failed=0

# 1. 检查主程序
# 注意：PyInstaller onedir 模式下，主程序安装在 /usr/share/ems-simulate
check_file "./usr/share/ems-simulate/ems_simulate"

# 2. 检查 www 目录 (静态资源)
check_file "./usr/share/ems-simulate/www/"
check_file "./usr/share/ems-simulate/www/index.html"

# 3. 检查 Systemd 服务
check_file "./lib/systemd/system/ems_simulate.service"

if [ "$failed" -eq 1 ]; then
    echo ">>> 测试失败！包结构不完整。"
    exit 1
else
    echo ">>> 测试通过！包结构正常。"
fi
