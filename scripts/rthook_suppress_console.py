# PyInstaller runtime hook: 在 Python 初始化后第一时间抑制控制台输出
# 必须在其他 runtime hook 之前加载，避免 python3xx.dll 引导阶段的 stderr 输出触发控制台闪现
import os
import sys

if sys.platform.startswith("win"):
    # 将 stdout/stderr 重定向到 os.devnull，后续 start_back_end.py 会重新定向到日志文件
    try:
        devnull = open(os.devnull, "wb")
        # 使用文件描述符级别的重定向，更底层、更早生效
        os.dup2(devnull.fileno(), sys.stdout.fileno())
        os.dup2(devnull.fileno(), sys.stderr.fileno())
        devnull.close()
    except OSError:
        # 回退：直接替换 sys.stdout/stderr 对象
        devnull = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = devnull
        sys.stderr = devnull
