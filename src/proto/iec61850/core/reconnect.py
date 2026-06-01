"""IEC 61850 重连与重试策略

提供指数退避重连、重试装饰器等鲁棒性增强功能。
"""

from collections.abc import Callable
import functools
import time

from ..log import log
from .exceptions import ConnectionError, ConnectionLostError


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (ConnectionError, ConnectionLostError),
    on_retry: Callable | None = None,
):
    """指数退避重试装饰器

    Args:
        max_retries: 最大重试次数
        base_delay: 初始延迟 (秒)
        max_delay: 最大延迟 (秒)
        exponential_base: 指数基数
        exceptions: 触发重试的异常类型
        on_retry: 重试回调 (attempt, exception)
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (exponential_base**attempt), max_delay)
                        log.warning(
                            f"{func.__name__} 失败 (尝试 {attempt + 1}/{max_retries + 1}), {delay:.1f}s 后重试: {e}"
                        )
                        if on_retry:
                            on_retry(attempt, e)
                        time.sleep(delay)
                    else:
                        log.error(f"{func.__name__} 失败，已达最大重试次数 {max_retries + 1}: {e}")
            raise last_exception

        return wrapper

    return decorator


class ReconnectionManager:
    """重连管理器

    管理自动重连逻辑，支持指数退避和最大重试次数。
    """

    def __init__(
        self,
        max_retries: int = 5,
        base_delay: float = 5.0,
        max_delay: float = 300.0,
        exponential_base: float = 2.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self._retry_count = 0

    @property
    def retry_count(self) -> int:
        return self._retry_count

    def reset(self):
        """重置重试计数"""
        self._retry_count = 0

    def get_delay(self, attempt: int) -> float:
        """计算第 N 次重试的延迟时间"""
        return min(self.base_delay * (self.exponential_base**attempt), self.max_delay)

    def attempt_reconnect(self, connect_func: Callable[[], bool]) -> bool:
        """尝试重连

        Args:
            connect_func: 连接函数，返回 True 表示成功

        Returns:
            是否重连成功
        """
        for attempt in range(self.max_retries):
            delay = self.get_delay(attempt)
            log.info(f"重连尝试 {attempt + 1}/{self.max_retries}, 等待 {delay:.1f}s...")
            time.sleep(delay)

            try:
                if connect_func():
                    self._retry_count = attempt + 1
                    log.info(f"重连成功 (第 {attempt + 1} 次尝试)")
                    return True
            except Exception as e:
                log.error(f"重连异常 (尝试 {attempt + 1}): {e}")

        log.error(f"重连失败，已达最大重试次数 {self.max_retries}")
        return False
