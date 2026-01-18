"""
数据测点类模块（向后兼容）
此文件保持向后兼容，实际实现已迁移到 src.enums.points 模块

Classes:
    - DeviceType: 设备类型枚举
    - SimulateMethod: 模拟方法枚举
    - Yc: 遥测类（从 points.yc 导入）
    - Yx: 遥信类（从 points.yx 导入）
    - Yt: 遥调类（从 points.yt 导入）
    - Yk: 遥控类（从 points.yk 导入）
    - BasePoint: 测点基类（从 points.base_point 导入）
"""

from enum import Enum


class DeviceType(Enum):
    Pcs = 0
    Bms = 1
    ElectricityMeter = 2
    GridMeter = 3
    CircuitBreaker = 4
    Other = 5


class SimulateMethod(Enum):
    Random = "Random"  # 随机模拟
    AutoIncrement = "AutoIncrement"  # 自增模拟
    AutoDecrement = "AutoDecrement"  # 自减模拟
    Plan = "Plan"  # 计划模拟
    SineWave = "SineWave"  # 正弦波模拟
    Ramp = "Ramp"  # 斜坡模拟
    Pulse = "Pulse"  # 脉冲模拟


# 从新模块导入测点类（向后兼容）
from src.enums.points.base_point import BasePoint, decimal_to_hex_formatted
from src.enums.points.yc import Yc
from src.enums.points.yx import Yx
from src.enums.points.yt import Yt
from src.enums.points.yk import Yk
from src.enums.points.protocol_strategy import (
    ProtocolStrategy,
    ModbusStrategy,
    IEC104Strategy,
    DLT645Strategy,
    IEC61850Strategy,
    get_protocol_strategy,
)


__all__ = [
    "DeviceType",
    "SimulateMethod",
    "BasePoint",
    "Yc",
    "Yx",
    "Yt",
    "Yk",
    "ProtocolStrategy",
    "ModbusStrategy",
    "IEC104Strategy",
    "DLT645Strategy",
    "IEC61850Strategy",
    "get_protocol_strategy",
    "decimal_to_hex_formatted",
]
