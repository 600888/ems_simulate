"""
协议策略模块
为不同协议（Modbus、IEC104、DLT645、IEC61850）提供统一的地址转换和配置策略
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


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
    def get_point_type_mapping(self) -> Dict[int, Any]:
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

    def get_point_type_mapping(self) -> Dict[int, Any]:
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

    def get_point_type_mapping(self) -> Dict[int, Any]:
        # 映射到 c104.Type 的值（实际使用时需要导入 c104 模块）
        return {
            0: "M_ME_NC_1",  # 遥测 - 短浮点数
            1: "M_SP_NA_1",  # 遥信 - 单点信息
            2: "C_SC_NA_1",  # 遥控 - 单点命令
            3: "C_SE_NC_1",  # 遥调 - 设点命令浮点数
        }

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

    def get_point_type_mapping(self) -> Dict[int, Any]:
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
    """IEC61850 协议策略（预留接口）"""

    def get_address_offset(self, frame_type: int) -> int:
        # TODO: 实现 IEC61850 地址偏移逻辑
        return 0

    def get_default_decode(self) -> str:
        # TODO: 实现 IEC61850 默认解析码
        return "0x42"

    def get_point_type_mapping(self) -> Dict[int, Any]:
        # TODO: 实现 IEC61850 点类型映射
        # IEC61850 使用逻辑节点和数据对象模型
        return {
            0: "MV",  # 遥测 - Measured Value
            1: "SPS",  # 遥信 - Single Point Status
            2: "SPC",  # 遥控 - Single Point Control
            3: "APC",  # 遥调 - Analog Point Control
        }

    def process_address(self, address: str, frame_type: int) -> str:
        # TODO: 实现 IEC61850 地址处理（可能是逻辑节点路径）
        return address


# 协议策略工厂
def get_protocol_strategy(protocol_type: str) -> ProtocolStrategy:
    """根据协议类型获取对应的策略实例"""
    strategy_map = {
        "ModbusTcp": ModbusStrategy(),
        "ModbusRtu": ModbusStrategy(),
        "ModbusRtuOverTcp": ModbusStrategy(),
        "ModbusTcpClient": ModbusStrategy(),
        "Iec104Server": IEC104Strategy(),
        "Iec104Client": IEC104Strategy(),
        "Dlt645Server": DLT645Strategy(),
        "Dlt645Client": DLT645Strategy(),
        "Iec61850": IEC61850Strategy(),
    }
    return strategy_map.get(protocol_type, ModbusStrategy())
