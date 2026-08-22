"""
协议策略模块
为不同协议（Modbus、IEC104、DLT645、IEC61850）提供统一的地址转换和配置策略
"""

from abc import ABC, abstractmethod
from typing import Any

from src.enums.points.iec104_type import (
    IEC104_DEFAULT_TYPE,
    IEC104Type,
    get_iec104_types_by_frame_type,
)


class ProtocolStrategy(ABC):
    """协议策略基类"""

    @abstractmethod
    def get_address_offset(self, frame_type: int) -> int:
        """获取地址偏移量"""
        pass

    @abstractmethod
    def get_default_decode(self) -> str:
        """获取默认解析码"""
        pass

    @abstractmethod
    def get_point_type_mapping(self) -> dict[int, Any]:
        """获取帧类型到协议点类型的映射"""
        pass

    @abstractmethod
    def process_address(self, address: str, frame_type: int) -> str:
        """处理地址转换"""
        pass


class ModbusStrategy(ProtocolStrategy):
    """Modbus 协议策略"""

    def get_address_offset(self, frame_type: int) -> int:
        return 0  # Modbus 不需要地址偏移

    def get_default_decode(self) -> str:
        return "0x41"  # 默认大端有符号长整型

    def get_point_type_mapping(self) -> dict[int, Any]:
        return {
            0: "yc",  # 遥测 - 保持寄存器
            1: "yx",  # 遥信 - 线圈/离散输入
            2: "yk",  # 遥控 - 写线圈
            3: "yt",  # 遥调 - 写寄存器
        }

    def process_address(self, address: str, frame_type: int) -> str:
        return address  # Modbus 直接使用原地址


class IEC104Strategy(ProtocolStrategy):
    """IEC104 协议策略"""

    # IEC104 地址偏移配置
    YC_OFFSET = 16385  # 遥测信息体地址起始偏移
    YX_OFFSET = 1  # 遥信信息体地址起始偏移
    YT_OFFSET = 0  # 遥调信息体地址偏移
    YK_OFFSET = 0  # 遥控信息体地址偏移

    def get_address_offset(self, frame_type: int) -> int:
        offset_map = {
            0: self.YC_OFFSET,  # 遥测
            1: self.YX_OFFSET,  # 遥信
            2: self.YK_OFFSET,  # 遥控
            3: self.YT_OFFSET,  # 遥调
        }
        return offset_map.get(frame_type, 0)

    def get_default_decode(self) -> str:
        return "0x42"  # IEC104 默认使用浮点数

    def get_point_type_mapping(self) -> dict[int, Any]:
        """获取帧类型到默认 IEC104 类型的映射（向后兼容）"""
        return {ft: t.value for ft, t in IEC104_DEFAULT_TYPE.items()}

    def get_available_types(self, frame_type: int) -> list:
        """获取指定帧类型的所有可用 IEC104 类型列表

        Args:
            frame_type: 帧类型 (0-3)

        Returns:
            IEC104TypeInfo 列表
        """
        return get_iec104_types_by_frame_type(frame_type)

    def resolve_type(self, type_id: str | None, frame_type: int) -> IEC104Type:
        """解析 IEC104 类型标识

        Args:
            type_id: 类型标识字符串（如 "M_ME_NC_1"），为 None 时使用默认
            frame_type: 帧类型

        Returns:
            IEC104Type 枚举
        """
        from src.enums.points.iec104_type import resolve_iec104_type

        return resolve_iec104_type(type_id, frame_type)

    def process_address(self, address: str, frame_type: int) -> str:
        """将地址转换为 IEC104 信息对象地址"""
        base_addr = int(address, 16) if address.startswith("0x") else int(address)
        offset = self.get_address_offset(frame_type)
        return hex(base_addr + offset)


class DLT645Strategy(ProtocolStrategy):
    """DLT645 协议策略（电力行业标准）"""

    def get_address_offset(self, frame_type: int) -> int:
        return 0  # DLT645 使用数据标识，不需要偏移

    def get_default_decode(self) -> str:
        return "0x20"  # DLT645 使用 BCD 编码

    def get_point_type_mapping(self) -> dict[int, Any]:
        return {
            0: "read_data",  # 遥测 - 读数据
            1: "read_status",  # 遥信 - 读状态
            2: "write_ctrl",  # 遥控 - 写控制
            3: "write_data",  # 遥调 - 写数据
        }

    def process_address(self, address: str, frame_type: int) -> str:
        """DLT645 地址需要 BCD 转换"""
        return address  # 实际转换由外部 transform 函数处理


class IEC61850Strategy(ProtocolStrategy):
    """IEC61850 协议策略"""

    def get_address_offset(self, frame_type: int) -> int:
        return 0  # IEC61850 使用逻辑节点路径，不需要数值偏移

    def get_default_decode(self) -> str:
        return "0x42"  # IEC61850 默认使用浮点数

    def get_point_type_mapping(self) -> dict[int, Any]:
        # IEC61850 使用逻辑节点和数据对象模型
        return {
            0: "MV",  # 遥测 - Measured Value (MMXU)
            1: "SPS",  # 遥信 - Single Point Status (GGIO)
            2: "SPC",  # 遥控 - Single Point Control (GGIO)
            3: "APC",  # 遥调 - Analog Point Control (GGIO)
        }

    def process_address(self, address: str, frame_type: int) -> str:
        """IEC61850 地址直接使用，后续由 handler 转换为 MMS 引用路径"""
        return address


# 协议策略工厂
def get_protocol_strategy(protocol_type: str) -> ProtocolStrategy:
    """根据协议类型获取对应的策略实例"""
    strategy_map = {
        "ModbusTcpServer": ModbusStrategy(),
        "ModbusRtu": ModbusStrategy(),
        "ModbusRtuClient": ModbusStrategy(),
        "ModbusRtuServer": ModbusStrategy(),
        "ModbusRtuOverTcp": ModbusStrategy(),
        "ModbusTcpClient": ModbusStrategy(),
        "Iec104Server": IEC104Strategy(),
        "Iec104Client": IEC104Strategy(),
        "Dlt645Server": DLT645Strategy(),
        "Dlt645Client": DLT645Strategy(),
        "Iec61850": IEC61850Strategy(),
        "Iec61850Server": IEC61850Strategy(),
        "Iec61850Client": IEC61850Strategy(),
    }
    return strategy_map.get(protocol_type, ModbusStrategy())
