#!/bin/sh
# 电力协议报文解析器（命令行版）启动脚本
#
# 优先用随包携带的便携 Python（不依赖系统 python3），
# 这样在 glibc 2.19 这类老系统上也能直接跑。
set -e

DIR=$(cd "$(dirname "$0")" && pwd)

# 便携解释器按顺序找：包内 python/、上级目录的 packet_analyzer_deps/python/
for candidate in \
    "$DIR/python/bin/python3" \
    "$DIR/../packet_analyzer_deps/python/bin/python3" \
    "$HOME/packet_analyzer_deps/python/bin/python3"
do
    if [ -x "$candidate" ]; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PY=$(command -v python3)
        ver=$("$PY" -c 'import sys;print("%d%d"%sys.version_info[:2])' 2>/dev/null || echo 0)
        if [ "$ver" -lt 310 ]; then
            echo "错误：系统 python3 版本过低（需要 3.10+），且未找到便携 Python。" >&2
            echo "请把便携 Python 解压到 $DIR/python，或参考 README 的部署章节。" >&2
            exit 1
        fi
    else
        echo "错误：未找到 Python，请先部署便携 Python（见 README）。" >&2
        exit 1
    fi
fi

# 让包能被 import，即使当前目录不是安装目录
if [ -n "$PYTHONPATH" ]; then
    PYTHONPATH="$DIR:$PYTHONPATH"
else
    PYTHONPATH="$DIR"
fi
export PYTHONPATH

exec "$PY" -m packet_analyzer.cli "$@"
