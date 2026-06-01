"""
协议配置模块
为不同协议（Modbus、IEC104、DLT645、IEC61850）提供特定的配置参数
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.enums.points.iec104_quality import IEC104QualityDescriptor


@dataclass
class ModbusConfig:
    """Modbus 协议配置"""

    decode_code: str = "0x41"  # 解析码（数据格式）
    register_count: int = 2  # 寄存器数量
    is_signed: bool = True  # 是否有符号
    byteorder: str = "big"  # 字节序（big/little）
    wordorder: str = "big"  # 字序（big/little）

    def to_dict(self) -> dict[str, Any]:
        return {
            "decode_code": self.decode_code,
            "register_count": self.register_count,
            "is_signed": self.is_signed,
            "byteorder": self.byteorder,
            "wordorder": self.wordorder,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModbusConfig":
        return cls(
            decode_code=data.get("decode_code", "0x41"),
            register_count=data.get("register_count", 2),
            is_signed=data.get("is_signed", True),
            byteorder=data.get("byteorder", "big"),
            wordorder=data.get("wordorder", "big"),
        )


@dataclass
class IEC104Config:
    """IEC104 协议配置"""

    common_address: int = 1  # 公共地址（站地址）
    cot: int = 3  # 传送原因 (Cause of Transmission)
    quality: int = 0  # 品质描述符（位标志: OV=0x01 BL=0x02 SB=0x04 NT=0x08 IV=0x10）
    type_id: str | None = None  # 类型标识（如 M_ME_NC_1）

    # COT 常用值
    COT_PERIODIC = 1  # 周期/循环
    COT_BACKGROUND = 2  # 背景扫描
    COT_SPONTANEOUS = 3  # 突发（自发）
    COT_INITIALIZED = 4  # 被初始化
    COT_REQUEST = 5  # 请求
    COT_ACTIVATION = 6  # 激活
    COT_ACTIVATION_CON = 7  # 激活确认

    @property
    def quality_descriptor(self) -> IEC104QualityDescriptor:
        """获取品质描述符对象"""
        return IEC104QualityDescriptor.from_int(self.quality)

    @quality_descriptor.setter
    def quality_descriptor(self, descriptor: IEC104QualityDescriptor):
        """设置品质描述符对象"""
        self.quality = descriptor.to_int()

    def to_dict(self) -> dict[str, Any]:
        return {
            "common_address": self.common_address,
            "cot": self.cot,
            "quality": self.quality,
            "type_id": self.type_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IEC104Config":
        return cls(
            common_address=data.get("common_address", 1),
            cot=data.get("cot", 3),
            quality=data.get("quality", 0),
            type_id=data.get("type_id"),
        )


@dataclass
class DLT645Config:
    """DLT645 协议配置"""

    data_identifier: str = ""  # 数据标识 (4字节 BCD)
    data_length: int = 4  # 数据长度
    meter_address: str = "000000000000"  # 电表地址 (12位)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_identifier": self.data_identifier,
            "data_length": self.data_length,
            "meter_address": self.meter_address,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DLT645Config":
        return cls(
            data_identifier=data.get("data_identifier", ""),
            data_length=data.get("data_length", 4),
            meter_address=data.get("meter_address", "000000000000"),
        )


@dataclass
class IEC61850Config:
    """IEC61850 协议配置"""

    port: int = 102  # MMS TCP 端口
    model_name: str = "EMS"  # IED 模型名称
    ied_name: str = "EMSDevice"  # IED 名称
    ld_name: str = "GenericLD"  # 逻辑设备名称

    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "model_name": self.model_name,
            "ied_name": self.ied_name,
            "ld_name": self.ld_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IEC61850Config":
        return cls(
            port=data.get("port", 102),
            model_name=data.get("model_name", "EMS"),
            ied_name=data.get("ied_name", "EMSDevice"),
            ld_name=data.get("ld_name", "GenericLD"),
        )


# 协议配置工厂
def get_default_protocol_config(protocol_type: str) -> Any | None:
    """根据协议类型获取默认配置"""
    config_map = {
        "ModbusTcp": ModbusConfig(),
        "ModbusRtu": ModbusConfig(),
        "ModbusRtuClient": ModbusConfig(),
        "ModbusRtuServer": ModbusConfig(),
        "ModbusRtuOverTcp": ModbusConfig(),
        "ModbusTcpClient": ModbusConfig(),
        "Iec104Server": IEC104Config(),
        "Iec104Client": IEC104Config(),
        "Dlt645Server": DLT645Config(),
        "Dlt645Client": DLT645Config(),
        "Iec61850Server": IEC61850Config(),
        "Iec61850Client": IEC61850Config(),
    }
    return config_map.get(protocol_type)


def create_protocol_config(protocol_type: str, data: dict[str, Any]) -> Any | None:
    """根据协议类型和数据创建配置对象"""
    if protocol_type in [
        "ModbusTcp",
        "ModbusRtu",
        "ModbusRtuClient",
        "ModbusRtuServer",
        "ModbusRtuOverTcp",
        "ModbusTcpClient",
    ]:
        return ModbusConfig.from_dict(data)
    elif protocol_type in ["Iec104Server", "Iec104Client"]:
        return IEC104Config.from_dict(data)
    elif protocol_type in ["Dlt645Server", "Dlt645Client"]:
        return DLT645Config.from_dict(data)
    elif protocol_type in ["Iec61850Server", "Iec61850Client"]:
        return IEC61850Config.from_dict(data)
    return None
