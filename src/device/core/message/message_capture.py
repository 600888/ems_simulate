import threading
import time
from collections import deque
from datetime import datetime
from typing import List, Dict, Any, Optional

class MessageRecord:
    """单条报文记录"""
    def __init__(self, direction: str, data: bytes, sequence_id: int = 0):
        self.direction = direction
        self.data = data
        self.timestamp = time.time()
        self.sequence_id = sequence_id
        self.hex_string = self._bytes_to_spaced_hex(data)

    def _bytes_to_spaced_hex(self, data: bytes) -> str:
        """将字节转换为带空格的16进制字符串"""
        if not data:
            return ""
        return " ".join([f"{b:02x}" for b in data])

    @property
    def formatted_time(self) -> str:
        """获取格式化时间"""
        dt = datetime.fromtimestamp(self.timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def to_dict(self) -> Dict[str, Any]:
        """转为字典格式"""
        return {
            "sequence_id": self.sequence_id,
            "direction": self.direction,
            "data": self.data.hex(),
            "hex_string": self.hex_string,
            "timestamp": self.timestamp,
            "time": self.formatted_time,
            "length": len(self.data)
        }

class MessageCapture:
    """报文捕获器"""
    def __init__(self, max_size: int = 200):
        self._max_size = max_size
        self._queue = deque(maxlen=max_size)
        self._lock = threading.Lock()
        self._enabled = True
        self._sequence_counter = 0

        # 平均收发时间统计：追踪 TX→RX 配对的延迟
        self._tx_count: int = 0
        self._rx_count: int = 0
        self._pending_tx_time: float = 0.0   # 最近一次 TX 的时间戳，等待配对 RX
        self._pair_count: int = 0             # 已配对的 TX→RX 次数
        self._total_latency: float = 0.0      # 所有配对延迟的累计（秒）

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def _get_next_sequence(self) -> int:
        self._sequence_counter += 1
        return self._sequence_counter

    def add_tx(self, data: bytes):
        """添加发送报文"""
        if not self._enabled: return
        with self._lock:
            self._tx_count += 1
            # 记录 TX 时间，等待下一个 RX 配对
            self._pending_tx_time = time.time()

            seq = self._get_next_sequence()
            self._queue.append(MessageRecord("TX", data, seq))

    def add_rx(self, data: bytes):
        """添加接收报文"""
        if not self._enabled: return
        with self._lock:
            now = time.time()
            self._rx_count += 1

            # 如果有待配对的 TX，计算本次收发延迟
            if self._pending_tx_time > 0:
                latency = now - self._pending_tx_time
                self._total_latency += latency
                self._pair_count += 1
                self._pending_tx_time = 0.0  # 清除，避免重复配对

            seq = self._get_next_sequence()
            self._queue.append(MessageRecord("RX", data, seq))

    def get_avg_time(self) -> Dict[str, Any]:
        """获取平均收发时间

        计算 TX→RX 配对的平均延迟（即请求到响应的平均耗时）。

        Returns:
            统计字典，包含报文数量和平均收发延迟（毫秒）
        """
        with self._lock:
            avg_latency_ms = 0.0
            if self._pair_count > 0:
                avg_latency_ms = round(
                    (self._total_latency / self._pair_count) * 1000, 2
                )

            return {
                "tx_count": self._tx_count,
                "rx_count": self._rx_count,
                "total_count": self._tx_count + self._rx_count,
                "pair_count": self._pair_count,
                "avg_latency_ms": avg_latency_ms,
            }

    def get_messages(self, count: int = 0) -> List[Dict[str, Any]]:
        """获取报文列表"""
        with self._lock:
            messages = list(self._queue)
            if count > 0:
                messages = messages[-count:]
            return [msg.to_dict() for msg in messages]

    def clear(self):
        """清空报文"""
        with self._lock:
            self._queue.clear()
            # 重置统计数据
            self._tx_count = 0
            self._rx_count = 0
            self._pending_tx_time = 0.0
            self._pair_count = 0
            self._total_latency = 0.0
