"""SV 插件 - 采样值 (Sampled Values) 操作

骨架实现，Phase 3.7 中完成具体逻辑。
"""

from typing import Any

from ..base import Iec61850Plugin
from ...defs.constants import HAS_IEC61850
from ...log import log


class SVPlugin:
    """SV 插件

    管理采样值发布/订阅。
    """

    def __init__(self):
        self._connection = None
        self._initialized = False

    @property
    def name(self) -> str:
        return "sv"

    @property
    def available(self) -> bool:
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        self._connection = connection
        self._initialized = True
        log.info("SV 插件已初始化 (骨架)")

    def shutdown(self) -> None:
        self._connection = None
        self._initialized = False
