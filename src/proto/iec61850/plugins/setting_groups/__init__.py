"""Setting Groups 插件 - 定值组 (SGCB) 操作

骨架实现，Phase 3.9 中完成具体逻辑。
"""

from typing import Any

from ...defs.constants import HAS_IEC61850
from ...log import log
from ..base import Iec61850Plugin


class SettingGroupsPlugin:
    """Setting Groups 插件

    管理定值组控制块操作。
    """

    def __init__(self):
        """保存插件宿主引用；协议能力在 initialize 阶段装配，在 shutdown 阶段统一释放。"""
        self._connection = None
        self._initialized = False

    @property
    def name(self) -> str:
        """返回SettingGroupsPlugin当前的名称。"""
        return "setting_groups"

    @property
    def available(self) -> bool:
        """返回SettingGroupsPlugin当前的可用状态。"""
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        """装配依赖并开放插件能力。"""
        self._connection = connection
        self._initialized = True
        log.info("SettingGroups 插件已初始化 (骨架)")

    def shutdown(self) -> None:
        """停止插件任务并释放其持有的资源。"""
        self._connection = None
        self._initialized = False
