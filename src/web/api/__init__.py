"""API 路由模块

统一导出所有路由器
"""

from src.web.api.channel import channel_router
from src.web.api.device import device_router
from src.web.api.device_group import device_group_router
from src.web.api.network_interfaces import router as network_interfaces_router
from src.web.api.point import point_mapping_router, point_router, point_tree_router
from src.web.api.settings import settings_router

__all__ = [
    "channel_router",
    "device_router",
    "point_router",
    "point_mapping_router",
    "point_tree_router",
    "device_group_router",
    "settings_router",
    "network_interfaces_router",
]
