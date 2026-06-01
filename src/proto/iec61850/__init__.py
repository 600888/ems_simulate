"""IEC 61850 协议模块

提供 IEC 61850 MMS 客户端/服务端/模型导出/GOOSE 等功能。
支持从包级别直接导入关键类:

    from src.proto.iec61850 import IEC61850Client, IEC61850Server
    from src.proto.iec61850 import pyiec61850 as iec61850  # 条件性导出
"""

from .defs.constants import HAS_IEC61850

# 条件性导出 pyiec61850 (向后兼容: debug_browsing.py 等脚本使用)
if HAS_IEC61850:
    from pyiec61850 import pyiec61850  # noqa: F401


# 延迟导入关键类，避免循环依赖
def __getattr__(name):
    """延迟导入，仅在首次访问时加载"""
    if name == "IEC61850Client":
        from .iec61850_client import IEC61850Client

        return IEC61850Client
    if name == "IEC61850Server":
        from .iec61850_server import IEC61850Server

        return IEC61850Server
    if name == "IEC61850ModelExporter":
        from .plugins.model_exporter import IEC61850ModelExporter

        return IEC61850ModelExporter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
