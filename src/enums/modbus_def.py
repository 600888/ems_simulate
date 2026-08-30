from enum import Enum


class ProtocolType(Enum):
    ModbusRtu = "ModbusRtu"  # 串口从站（向后兼容）
    ModbusRtuClient = "ModbusRtuClient"  # 串口主站（主动采集）
    ModbusRtuServer = "ModbusRtuServer"  # 串口从站（被动响应）
    ModbusTcpServer = "ModbusTcpServer"
    ModbusTcpClient = "ModbusTcpClient"
    ModbusUdp = "ModbusUdp"
    ModbusRtuOverTcp = "ModbusRtuOverTcp"
    Iec104Server = "Iec104Server"
    Iec104Client = "Iec104Client"
    Iec101Server = "Iec101Server"
    Iec101Client = "Iec101Client"
    Dlt645Server = "Dlt645Server"
    Dlt645Client = "Dlt645Client"
    Iec61850Server = "Iec61850Server"
    Iec61850Client = "Iec61850Client"
    Dnp3Server = "Dnp3Server"
    Dnp3Client = "Dnp3Client"


class RegisterType(Enum):
    INPUT = 0
    OUTPUT = 1


def get_protocol_type_by_value(value: str) -> ProtocolType:
    """通过枚举值反推枚举类型"""
    if value == "ModbusTcp":
        return ProtocolType.ModbusTcpServer
    for member in ProtocolType:
        if member.value == value:
            return member
    raise ValueError(f"'{value}' is not a valid ProtocolType")
