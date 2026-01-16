from loguru import logger
import os
import sys
import traceback
from typing import Optional, Union

LOG_COLORS = {
    "DEBUG": "\033[1;36m",  # CYAN
    "INFO": "\033[1;32m",  # GREEN
    "WARNING": "\033[1;33m",  # YELLOW
    "ERROR": "\033[1;31m",  # RED
    "CRITICAL": "\033[1;31m",  # RED
    "EXCEPTION": "\033[1;31m",  # RED
}
COLOR_RESET = "\033[1;0m"


class Log:
    def __init__(
        self,
        filename: Optional[str] = None,
        cmdlevel: str = "DEBUG",
        filelevel: str = "INFO",
        backup_count: int = 7,  # 默认保留7天/7个文件
        limit: Union[int, str] = "20 MB",  # 支持字符串格式
        when: Optional[str] = None,
        colorful: bool = True,
        compression: Optional[str] = None,  # 新增压缩功能
    ):
        # 设置日志文件路径
        if filename is None:
            filename = getattr(sys.modules["__main__"], "__file__", "log.py")
            filename = os.path.basename(filename.replace(".py", ".log"))

        # 确保日志目录存在
        log_dir = os.path.abspath(os.path.dirname(filename))
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 移除默认handler
        logger.remove()

        # 控制台输出配置
        logger.add(
            sys.stderr,
            level=cmdlevel,
            format=self._formatter,
            colorize=colorful,
            enqueue=True,
        )

        # 文件输出配置
        rotation_config = self._get_rotation_config(when, limit)
        logger.add(
            filename,
            level=filelevel,
            format=self._formatter,
            rotation=rotation_config,
            retention=f"{backup_count} days",
            compression=compression,
            enqueue=True,
        )

    def _formatter(self, record):
        level_color = LOG_COLORS.get(record["level"].name, "")
        return (
            f"{level_color}[{record['time'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] "
            f"[{record['file']}] [line:{record['line']}] "
            f"[{record['level']}] {record['message']}{COLOR_RESET}\n"
        )

    def _get_rotation_config(self, when: Optional[str], limit: Union[int, str]):
        if when:  # 时间轮转
            return when  # "D"（天）、"H"（小时）、"midnight"等
        else:  # 大小轮转
            if isinstance(limit, int):
                return f"{limit / 1024 / 1024} MB"
            return limit  # 直接支持"10 MB"、"1 GB"等字符串格式

    def trace(self):
        """Log exception trace."""
        info = sys.exc_info()
        for file, lineno, function, text in traceback.extract_tb(info[2]):
            logger.error(f"{file} line:{lineno} in {function}:{text}")
        logger.error(f"{info[0].__name__}: {info[1]}")

    # 代理loguru的日志方法（保持与原类完全相同的接口）
    debug = logger.debug
    info = logger.info
    warning = logger.warning
    error = logger.error
    critical = logger.critical
    exception = logger.exception

    @staticmethod
    def set_logger(**kwargs) -> bool:
        """For backward compatibility."""
        return True


# 保持原有接口
__all__ = ["set_logger", "debug", "info", "warning", "error", "critical", "exception"]
