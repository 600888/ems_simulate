"""IEC 61850 插件注册表

使用注册表模式 (Registry Pattern)，
支持按需加载、热插拔、依赖检查。
"""

from typing import Type, Dict, Optional, Any

from .base import Iec61850Plugin
from ..log import log


# 注册内置插件 (延迟导入，避免循环依赖)
def _register_builtin_plugins(target_registry: "PluginRegistry" = None):
    """注册所有内置插件到指定注册表 (默认使用全局单例)"""
    reg = target_registry or registry
    from .goose import GoosePlugin
    from .datasets import DataSetsPlugin
    from .datamodels import DataModelsPlugin
    from .reports import ReportsPlugin
    from .sv import SVPlugin
    from .log_plugin import LogPlugin
    from .setting_groups import SettingGroupsPlugin
    from .files import FilesPlugin
    from .model_exporter import ModelExporterPlugin

    reg.register("goose", GoosePlugin)
    reg.register("datasets", DataSetsPlugin)
    reg.register("datamodels", DataModelsPlugin)
    reg.register("reports", ReportsPlugin)
    reg.register("sv", SVPlugin)
    reg.register("log", LogPlugin)
    reg.register("setting_groups", SettingGroupsPlugin)
    reg.register("files", FilesPlugin)
    reg.register("model_exporter", ModelExporterPlugin)


class PluginRegistry:
    """插件注册与管理

    使用注册表模式，支持按需加载和热插拔。
    """

    def __init__(self, auto_register: bool = True):
        self._plugins: Dict[str, Iec61850Plugin] = {}
        self._factories: Dict[str, Type[Iec61850Plugin]] = {}
        if auto_register:
            _register_builtin_plugins(self)

    def register(self, name: str, factory: Type[Iec61850Plugin]) -> None:
        """注册插件工厂

        Args:
            name: 插件名称
            factory: 插件类 (需实现 Iec61850Plugin 协议)
        """
        self._factories[name] = factory
        log.debug(f"插件工厂已注册: {name}")

    def get(self, name: str) -> Optional[Iec61850Plugin]:
        """获取插件实例 (懒创建)

        Args:
            name: 插件名称

        Returns:
            插件实例，如果不可用则返回 None
        """
        if name in self._plugins:
            return self._plugins[name]

        if name not in self._factories:
            return None

        factory = self._factories[name]
        try:
            instance = factory()
            if instance.available:
                self._plugins[name] = instance
                return instance
            else:
                log.debug(f"插件 {name} 不可用，跳过初始化")
                return None
        except Exception as e:
            log.error(f"创建插件 {name} 失败: {e}")
            return None

    def get_all_available(self) -> Dict[str, Iec61850Plugin]:
        """获取所有可用插件"""
        result = {}
        for name in self._factories:
            plugin = self.get(name)
            if plugin is not None:
                result[name] = plugin
        return result

    def initialize_all(self, connection: Any, **kwargs) -> None:
        """初始化所有可用插件

        Args:
            connection: 连接实例
            **kwargs: 额外参数 (如 registry)
        """
        for name in self._factories:
            plugin = self.get(name)
            if plugin is not None:
                try:
                    plugin.initialize(connection, **kwargs)
                    log.info(f"插件 {name} 已初始化")
                except Exception as e:
                    log.error(f"插件 {name} 初始化失败: {e}")

    def shutdown_all(self) -> None:
        """关闭所有插件"""
        for name, plugin in self._plugins.items():
            try:
                plugin.shutdown()
                log.info(f"插件 {name} 已关闭")
            except Exception as e:
                log.error(f"插件 {name} 关闭失败: {e}")
        self._plugins.clear()


# 全局注册表实例 (不自动注册，由下方 _register_builtin_plugins 手动注册)
registry = PluginRegistry(auto_register=False)
_register_builtin_plugins(registry)
