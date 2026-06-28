import os
import sys

from src.config.global_config import LOG_DIR
from src.config.log.logger import Log

# 打包环境下控制台只显示 INFO 及以上级别，不输出 DEBUG
_cmd_level = "INFO" if getattr(sys, "frozen", False) else "DEBUG"

log = Log(
    filename=os.path.join(LOG_DIR, "web.log"),
    cmdlevel=_cmd_level,
    filelevel="INFO",
    limit=2048000,
    backup_count=1,
    colorful=True,
    enqueue=True,  # 在异步环境中需要启用队列
)
