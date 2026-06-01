"""
测点变化追溯模块
使用现代 Python 设计模式追踪测点值变化的原因

设计模式:
    - Enum: ChangeSource 标准化变更原因
    - dataclass(frozen): ChangeRecord 不可变变更记录
    - ContextVar: 线程/协程安全地传递当前变更原因
    - contextmanager: track_change 便捷设置/还原
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import time
from typing import Any


class ChangeSource(Enum):
    """变更原因枚举"""

    MANUAL = "manual"  # 手动置值（前端/API）
    SIMULATION = "simulation"  # 自动模拟
    MAPPING = "mapping"  # 关联测点更新（映射计算）
    PROTOCOL = "protocol"  # 通过协议远程修改（Modbus/IEC104/DLT645 服务端被写入）
    CLIENT_READ = "client_read"  # 客户端读取远程数据变化
    INTERNAL = "internal"  # 内部默认（未明确指定来源）

    @property
    def label(self) -> str:
        """返回中文标签"""
        labels = {
            "manual": "手动置值",
            "simulation": "自动模拟",
            "mapping": "关联测点更新",
            "protocol": "协议远程修改",
            "client_read": "客户端读取",
            "internal": "内部默认",
        }
        return labels.get(self.value, self.value)


@dataclass(frozen=True)
class ChangeRecord:
    """
    不可变的测点变更记录

    Attributes:
        source: 变更原因
        old_value: 变更前的值
        new_value: 变更后的值
        timestamp: 变更时间戳 (Unix epoch)
        detail: 可选的补充描述
    """

    source: ChangeSource
    old_value: Any
    new_value: Any
    old_real_value: Any = None
    new_real_value: Any = None
    timestamp: float = field(default_factory=time.time)
    detail: str = ""
    client_info: str = ""

    def to_dict(self) -> dict:
        """序列化为字典，便于 API 返回"""
        # 将 Unix 时间戳转为可读时间字符串（精确到毫秒）
        dt = datetime.fromtimestamp(self.timestamp)
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d}"
        return {
            "source": self.source.value,
            "source_label": self.source.label,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "old_real_value": self.old_real_value if self.old_real_value is not None else self.old_value,
            "new_real_value": self.new_real_value if self.new_real_value is not None else self.new_value,
            "timestamp": self.timestamp,
            "time": time_str,
            "detail": self.detail,
            "client_info": self.client_info,
        }


# ===== 线程安全的上下文变量 =====

# 当前变更原因，默认为 INTERNAL
change_source_ctx: ContextVar[ChangeSource] = ContextVar("change_source_ctx", default=ChangeSource.INTERNAL)

# 当前变更详情描述
change_detail_ctx: ContextVar[str] = ContextVar("change_detail_ctx", default="")

# 当前变更机器信息(IP或串口)
change_client_info_ctx: ContextVar[str] = ContextVar("change_client_info_ctx", default="")


@contextmanager
def track_change(source: ChangeSource, detail: str = "", client_info: str = ""):
    """
    上下文管理器: 在代码块内设置变更原因

    用法:
        with track_change(ChangeSource.MANUAL, "手动设置电压=220", "192.168.1.100:502"):
            point.set_real_value(220)

    线程安全: 基于 ContextVar，不同线程/协程互不影响
    """
    source_token = change_source_ctx.set(source)
    detail_token = change_detail_ctx.set(detail)
    client_info_token = change_client_info_ctx.set(client_info)
    try:
        yield
    finally:
        change_source_ctx.reset(source_token)
        change_detail_ctx.reset(detail_token)
        change_client_info_ctx.reset(client_info_token)


def get_current_source() -> ChangeSource:
    """获取当前上下文中的变更原因"""
    return change_source_ctx.get()


def get_current_detail() -> str:
    """获取当前上下文中的变更详情"""
    return change_detail_ctx.get()


def get_current_client_info() -> str:
    """获取当前上下文中的客户端信息"""
    return change_client_info_ctx.get()


@dataclass
class ChangeContext:
    """用于跨线程传递的变更上下文快照"""

    source: ChangeSource
    detail: str
    client_info: str


def capture_context() -> ChangeContext:
    """捕获当前变更上下文快照"""
    return ChangeContext(
        source=change_source_ctx.get(), detail=change_detail_ctx.get(), client_info=change_client_info_ctx.get()
    )


@contextmanager
def restore_context(context: ChangeContext):
    """还原已捕获的变更上下文"""
    source_token = change_source_ctx.set(context.source)
    detail_token = change_detail_ctx.set(context.detail)
    client_info_token = change_client_info_ctx.set(context.client_info)
    try:
        yield
    finally:
        change_source_ctx.reset(source_token)
        change_detail_ctx.reset(detail_token)
        change_client_info_ctx.reset(client_info_token)
