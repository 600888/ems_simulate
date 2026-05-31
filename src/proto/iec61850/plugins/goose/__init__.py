"""GOOSE 插件 - IEC 61850 GOOSE 功能模块

管理 GOOSE 报文的发布 (Publisher)、订阅 (Receiver)、
捕获 (Capture) 的完整生命周期。

模块结构:
- types.py        — 数据类型定义 (dataclass + enum)
- publisher.py    — GoosePublisher 发布者
- subscriber.py   — GooseReceiver 接收器 + GooseSubscription 订阅
- capture.py      — GooseCaptureEngine 报文捕获引擎
- manager.py      — GooseResourceManager 资源管理器
- persistence.py  — 持久化适配层 (DAO 调用隔离)
"""

from __future__ import annotations

from typing import Any

from ..base import Iec61850Plugin
from ...defs.constants import HAS_IEC61850
from ...log import log

from .types import (
    GooseDataSetEntry, GooseState, IecDataType,
    PublisherConfig, ReceiverConfig, MmsType,
)
from .manager import GooseResourceManager
from .persistence import PersistenceAdapter
from .publisher import GoosePublisher
from .subscriber import GooseReceiver, GooseSubscriptionInfo
from .capture import GooseCaptureEngine, CapturedPacket


class GoosePlugin:
    """GOOSE 插件 — 实现 Iec61850Plugin 协议

    作为 GOOSE 功能的门面，对外暴露 Publisher/Receiver/Capture 的
    完整管理 API，对内通过 GooseResourceManager 协调各组件。
    """

    def __init__(self):
        self._connection: Any = None
        self._manager: GooseResourceManager | None = None
        self._initialized = False

    # ===== Iec61850Plugin 协议实现 =====

    @property
    def name(self) -> str:
        return "goose"

    @property
    def available(self) -> bool:
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        """初始化 GOOSE 插件

        Args:
            connection: Iec61850Connection 实例
            **kwargs: 支持 persistence (PersistenceAdapter 实例)
        """
        self._connection = connection
        persistence = kwargs.get("persistence", PersistenceAdapter())
        self._manager = GooseResourceManager(persistence=persistence)
        self._initialized = True
        log.info("GOOSE 插件已初始化")

    def shutdown(self) -> None:
        """关闭 GOOSE 插件，停止所有资源"""
        if self._manager:
            self._manager.stop_all()
        self._connection = None
        self._manager = None
        self._initialized = False
        log.info("GOOSE 插件已关闭")

    # ===== 门面属性 =====

    @property
    def manager(self) -> GooseResourceManager | None:
        """获取资源管理器实例"""
        return self._manager

    # ===== 便捷方法 (委托给 manager) =====

    def create_publisher(self, **kwargs) -> dict[str, Any] | None:
        """创建 GOOSE Publisher"""
        if not self._manager:
            return None
        return self._manager.create_publisher(**kwargs)

    def create_subscriber(self, **kwargs) -> dict[str, Any] | None:
        """创建 GOOSE Receiver"""
        if not self._manager:
            return None
        return self._manager.create_receiver(**kwargs)


# ===== 公开导出 =====

__all__ = [
    # 插件类
    "GoosePlugin",
    # 管理器
    "GooseResourceManager",
    # 核心组件
    "GoosePublisher",
    "GooseReceiver",
    "GooseCaptureEngine",
    "CapturedPacket",
    # 类型
    "GooseDataSetEntry",
    "GooseSubscriptionInfo",
    "GooseState",
    "IecDataType",
    "MmsType",
    "PublisherConfig",
    "ReceiverConfig",
    # 持久化
    "PersistenceAdapter",
]
