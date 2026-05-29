"""IEC 61850 协议常量定义

包含逻辑节点 (LN) 分类表、数据对象 (DO) 名称集合等常量，
供 IEC61850Client / IEC61850Server 等模块共用。

注意: 实际定义已迁移至 defs.ln_classes，此文件保留以向后兼容。
"""

# 从 defs 包重导出，保持向后兼容
from .defs.ln_classes import (
    YC_LN_CLASSES,
    YX_LN_CLASSES,
    YK_LN_CLASSES,
    YT_LN_CLASSES,
    ALL_LN_CLASSES,
    SKIP_SYSTEM_DOS,
    SIGNAL_DOS,
)
