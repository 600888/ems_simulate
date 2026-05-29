"""GOOSE 插件 - 包装现有 goose 模块

将 goose_publisher, goose_subscriber, goose_capture, goose_manager
统一封装为 Iec61850Plugin 协议实现。
"""

from typing import Any, Optional

from ..base import Iec61850Plugin
from ...defs.constants import HAS_IEC61850
from ...log import log


class GoosePlugin:
    """GOOSE 插件

    管理GOOSE发布、订阅、捕获等功能。
    """

    def __init__(self):
        self._connection = None
        self._goose_manager = None
        self._initialized = False

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
        """
        self._connection = connection
        self._initialized = True
        log.info("GOOSE 插件已初始化")

    def shutdown(self) -> None:
        """关闭 GOOSE 插件"""
        if self._goose_manager:
            try:
                self._goose_manager.stop()
            except Exception:
                pass
        self._connection = None
        self._goose_manager = None
        self._initialized = False

    @property
    def manager(self):
        """获取 GOOSE Manager 实例 (懒创建)"""
        if self._goose_manager is None and self._initialized:
            from ...goose_manager import GooseManager
            self._goose_manager = GooseManager()
        return self._goose_manager

    def create_publisher(self, **kwargs):
        """创建 GOOSE 发布者"""
        from ...goose_publisher import GoosePublisher
        return GoosePublisher(**kwargs)

    def create_subscriber(self, **kwargs):
        """创建 GOOSE 订阅者"""
        from ...goose_subscriber import GooseSubscriber
        return GooseSubscriber(**kwargs)
