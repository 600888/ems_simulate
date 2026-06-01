"""IEC 61850 插件协议定义

所有 IEC 61850 功能模块插件必须实现此协议。
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Iec61850Plugin(Protocol):
    """IEC 61850 功能模块插件协议

    所有插件必须实现此协议，以便被 PluginRegistry 管理。
    """

    @property
    def name(self) -> str:
        """插件名称"""
        ...

    @property
    def available(self) -> bool:
        """插件是否可用 (依赖库是否安装)"""
        ...

    def initialize(self, connection: Any, **kwargs) -> None:
        """初始化插件 (注入连接等依赖)"""
        ...

    def shutdown(self) -> None:
        """关闭插件，释放资源"""
        ...
