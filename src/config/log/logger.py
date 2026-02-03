import inspect
import json
from loguru import logger
import os
import sys
from typing import Any, Dict, Optional, Union
from src.config.env import log_path

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
    # 静态标记：确保只移除一次默认 handler
    _default_handler_removed = False

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
        is_backtrace: bool = True,
        enqueue: bool = True,
    ):
        # 移除 loguru 默认的 stderr handler，避免日志重复打印
        if not Log._default_handler_removed:
            logger.remove()
            Log._default_handler_removed = True

        self.is_backtrace = is_backtrace
        self.logger = logger.bind(task=filename)
        # 设置日志文件路径
        if filename is None:
            filename = getattr(sys.modules["__main__"], "__file__", "log.py")
            filename = os.path.basename(filename.replace(".py", ".log"))

        # 确保日志目录存在
        log_dir = os.path.abspath(os.path.dirname(filename))
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 控制台输出配置
        self.logger.add(
            sys.stderr,
            level=cmdlevel,
            format=self._formatter,
            colorize=colorful,
            backtrace=True,
            enqueue=enqueue,
            filter=lambda record: record["extra"]["task"] == filename,
        )

        # 文件输出配置
        rotation_config = self._get_rotation_config(when, limit)
        self.logger.add(
            filename,
            level=filelevel,
            format=self._formatter,
            backtrace=True,
            rotation=rotation_config,
            retention=f"{backup_count} days",
            compression=compression,
            enqueue=enqueue,
            filter=self._create_filter(filename),
        )

    def _create_filter(self, filename):
        def filter_func(record):
            task = record["extra"].get("task")
            
            # Normalize paths for comparison
            task_norm = os.path.normpath(os.path.abspath(task)).lower() if task else ""
            filename_norm = os.path.normpath(os.path.abspath(filename)).lower() if filename else ""
            
            is_match = task_norm == filename_norm
            
            # Debugging for web.log issues
            if "web.log" in str(filename) and not is_match:
                 # Only print if it looks like it SHOULD match (e.g. both are web.log variants)
                 if "web.log" in str(task):
                     print(f"DEBUG: Log Filter Mismatch! Record Task: '{task}' (norm: {task_norm}) vs Handler Filename: '{filename}' (norm: {filename_norm})")
            return is_match
        return filter_func

    def _formatter(self, record):
        # 处理消息内容
        message = str(record["message"]).replace("{", "{{").replace("}", "}}")
        if isinstance(message, (dict, list)):
            try:
                message = json.dumps(message, ensure_ascii=False)
            except TypeError:
                message = str(message)

        # 处理调用栈和颜色
        if self.is_backtrace:
            frame = inspect.currentframe()
            while frame:
                if (
                    "loguru" not in frame.f_code.co_filename
                    and "logger.py" not in frame.f_code.co_filename
                ):
                    break
                frame = frame.f_back
            file_info = (
                f"[{os.path.basename(frame.f_code.co_filename)}:{frame.f_code.co_name}:{frame.f_lineno}]"
                if frame
                else f"[{record['file']}:{record['function']}:{record['line']}]"
            )
        else:
            file_info = f"[{record['file']}:{record['line']}]"
        
        # Escape Loguru tags in file_info and message
        file_info = file_info.replace("<", "\\<").replace(">", "\\>")
        message = message.replace("<", "\\<").replace(">", "\\>")

        level_color = LOG_COLORS.get(record["level"].name, "")
        return (
            f"{level_color}[{record['time'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] "
            + file_info
            + f"[{record['level']}] {message}{COLOR_RESET}\n"
        )

    def _get_rotation_config(self, when: Optional[str], limit: Union[int, str]):
        if when:  # 时间轮转
            return when  # "D"（天）、"H"（小时）、"midnight"等
        else:  # 大小轮转
            if isinstance(limit, int):
                return f"{limit / 1024 / 1024} MB"
            return limit  # 直接支持"10 MB"、"1 GB"等字符串格式

    @staticmethod
    def set_logger(**kwargs) -> bool:
        """For backward compatibility."""
        return True

    def debug(self, *args, **kwargs):
        self.logger.debug(*args, **kwargs)

    def info(self, *args, **kwargs):
        self.logger.info(*args, **kwargs)

    def warning(self, *args, **kwargs):
        self.logger.warning(*args, **kwargs)

    def error(self, *args, **kwargs):
        self.logger.error(*args, **kwargs)

    def critical(self, *args, **kwargs):
        self.logger.critical(*args, **kwargs)

    def exception(self, *args, **kwargs):
        self.logger.exception(*args, **kwargs)