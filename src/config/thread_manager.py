import concurrent.futures
import threading
from typing import Optional


class ThreadManager:
    def __init__(self) -> None:
        # 创建一个线程池，这里只使用一个线程作为示例，可以根据需要调整
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.target: Optional[callable] = None
        # 使用Future对象来跟踪线程池中的任务
        self.future = None
        # 创建一个Event来控制模拟的停止
        self.stop_event = threading.Event()

    def setTarget(self, target: callable):
        self.target = target

    # 开启随机数据模拟
    def start(self):
        # 如果已经有任务在运行，先取消它
        if self.future and not self.future.cancelled():
            self.future.cancel()
            # 提交新的任务到线程池
        self.future = self.executor.submit(self.target)

    def stop(self):
        # 设置事件来停止模拟
        self.stop_event.set()
        # 如果任务还在运行，等待它完成
        if self.future:
            self.future.cancel()  # 尝试取消任务，但不一定能成功取消正在执行的任务

    def isRunning(self):
        # 检查Future对象是否仍在运行
        if self.future:
            return not self.future.cancelled()
        return False
