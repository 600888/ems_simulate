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
            seq = self._get_next_sequence()
            self._queue.append(MessageRecord("TX", data, seq))

    def add_rx(self, data: bytes):
        """添加接收报文"""
        if not self._enabled: return
        with self._lock:
            seq = self._get_next_sequence()
            self._queue.append(MessageRecord("RX", data, seq))

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
