import threading
import time
from typing import Callable, Optional


class DataUpdateThread:
    def __init__(self, task: Optional[Callable] = None, task_args: tuple = ()):
        """
        :param task: 可调用任务（函数或方法）
        :param task_args: 任务参数元组
        """
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.task = task
        self.task_args = task_args

    def _run_task(self):
        """内部线程执行逻辑，支持任务中断检查"""
        while not self.stop_event.is_set() and self.task:
            try:
                self.task(*self.task_args)  # 执行任务
                # 添加小延迟避免CPU空转
                if not self.stop_event.is_set():
                    time.sleep(0.1)  # 100毫秒延迟
            except Exception as e:
                print(f"Task execution failed: {e}")
                raise e

    def is_alive(self) -> bool:
        """检查线程是否运行中"""
        return self.thread is not None and self.thread.is_alive()

    def start(self) -> bool:
        """启动任务线程"""
        if self.task is None:
            raise ValueError("No task provided to execute")
        if not self.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run_task, daemon=True)
            self.thread.start()
            return True
        return False

    def stop(self, timeout: Optional[float] = None) -> None:
        """停止线程，支持超时控制"""
        if self.is_alive():
            self.stop_event.set()
            self.thread.join(timeout=timeout)  # 等待线程终止
            if self.thread.is_alive():  # 超时后强制清理
                self.thread = None
