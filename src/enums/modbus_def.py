from enum import Enum


class ProtocolType(Enum):
    ModbusRtu = "ModbusRtu"
    ModbusTcp = "ModbusTcp"
    ModbusTcpClient = "ModbusTcpClient"
    ModbusUdp = "ModbusUdp"
    ModbusRtuOverTcp = "ModbusRtuOverTcp"
    Iec104Server = "Iec104Server"
    Iec104Client = "Iec104Client"
    Dlt645Server = "Dlt645Server"
    Dlt645Client = "Dlt645Client"


class RegisterType(Enum):
    INPUT = 0
    OUTPUT = 1


def get_protocol_type_by_value(value: str) -> ProtocolType:
    """通过枚举值反推枚举类型"""
    for member in ProtocolType:
        if member.value == value:
            return member
    raise ValueError(f"'{value}' is not a valid ProtocolType")
