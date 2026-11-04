#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# 优先使用能导入 PySide6 的解释器，避免误选空 venv
try_run() {
    local py="$1"
    if [ -x "$py" ] && "$py" -c "import PySide6" >/dev/null 2>&1; then
        exec "$py" main.py "$@"
    fi
}

try_run .venv/bin/python
try_run ../.venv/bin/python

if python3 -c "import PySide6" >/dev/null 2>&1; then
    exec python3 main.py "$@"
fi

echo "[ERROR] 找不到已安装 PySide6 的 Python 解释器。" >&2
echo "        请执行：pip install -r requirements.txt" >&2
exit 1
