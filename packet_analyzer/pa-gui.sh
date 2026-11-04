#!/bin/sh
# 电力协议报文解析器（图形版）启动脚本 —— 供缺少 Qt6 的老系统使用
#
# 包内自带 PySide2(Qt5.15) 与便携 Python，不依赖系统 Qt。
# 关键点：必须把包内 Qt 库放在动态加载器搜索路径的最前面，
# 否则会撞上系统自带的老 Qt（例如 Qt 5.3 / 5.11）导致符号不匹配。
set -e

DIR=$(cd "$(dirname "$0")" && pwd)
SP="$DIR/python/lib/python3.10/site-packages"
QT_LIB="$SP/PySide2/Qt/lib"
XCB_PLUGIN="$SP/PySide2/Qt/plugins/platforms/libqxcb.so"

if [ ! -x "$DIR/python/bin/python3" ]; then
    echo "错误：未找到内置 Python（python/bin/python3）。" >&2
    echo "请按 README-linux.md 重新解压完整分发包。" >&2
    exit 1
fi

if [ ! -d "$SP/PySide2" ]; then
    echo "错误：包内没有 PySide2，这一份是命令行版。" >&2
    echo "图形版请使用带 Qt5 的完整包，或直接用 ./pa.sh。" >&2
    exit 1
fi

# 包内 Qt 库优先；已经设置过就保持用户值在前
if [ -n "$LD_LIBRARY_PATH" ]; then
    LD_LIBRARY_PATH="$QT_LIB:$LD_LIBRARY_PATH"
else
    LD_LIBRARY_PATH="$QT_LIB"
fi
export LD_LIBRARY_PATH

if [ -n "$PYTHONPATH" ]; then
    PYTHONPATH="$SP:$DIR:$PYTHONPATH"
else
    PYTHONPATH="$SP:$DIR"
fi
export PYTHONPATH

# 没有图形环境时给出明确提示，而不是抛一堆 xcb 报错
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ] && [ -z "$QT_QPA_PLATFORM" ]; then
    echo "提示：当前没有 DISPLAY，无法弹出窗口。" >&2
    echo "  · 在服务器桌面上运行，或 ssh -X 转发显示" >&2
    echo "  · 只想抓包/解析，直接用 ./pa.sh capture|replay|parse" >&2
    exit 1
fi

# 预检 xcb 插件的依赖。
# 不查的话 Qt 只会含糊地说 "Could not load the Qt platform plugin xcb ... even though it was found"，
# 实际原因通常是缺某个 .so。这里直接点名缺什么，并给出可执行的解决路径。
if [ -f "$XCB_PLUGIN" ] && command -v ldd >/dev/null 2>&1; then
    missing=$(ldd "$XCB_PLUGIN" 2>/dev/null | awk '/not found/{print $1}' | sort -u)
    if [ -n "$missing" ]; then
        echo "错误：图形界面缺少以下运行库，Qt 的 xcb 插件因此加载失败：" >&2
        for lib in $missing; do
            echo "  · $lib" >&2
        done
        echo "" >&2
        echo "处理办法（任选其一）：" >&2
        echo "  1) 在本机查询这个库来自哪个 deb 包（联网可用）：" >&2
        if [ -f "$DIR/tools/find_missing_lib.py" ]; then
            echo "       $DIR/python/bin/python3 $DIR/tools/find_missing_lib.py $(echo $missing)" >&2
        else
            echo "       apt-file search $lib" >&2
            echo "       # 或网页查：https://packages.debian.org/search?searchon=contents&keywords=$lib" >&2
        fi
        echo "  2) 装上对应软件包：sudo apt-get install <包名>" >&2
        echo "  3) 从别的机器把该 .so 拷进包内 Qt 库目录，然后重新运行本脚本：" >&2
        echo "       $QT_LIB/" >&2
        echo "  4) 只做报文解析/抓包（不需要图形界面）：" >&2
        echo "       ./pa.sh capture|replay|parse" >&2
        exit 1
    fi
fi

exec "$DIR/python/bin/python3" -m packet_analyzer.main "$@"
