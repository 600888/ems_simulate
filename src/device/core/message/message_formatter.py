"""
报文格式化模块
负责从协议处理器获取原始报文并格式化为统一的展示格式。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.device.core.message.message_parser import (
    DLT645MessageParser,
    IEC104MessageParser,
    ModbusMessageParser,
)
from src.enums.modbus_def import ProtocolType

if TYPE_CHECKING:
    from src.device.core.device import Device

# Modbus TCP 类协议类型集合
_MODBUS_TCP_TYPES = {
    ProtocolType.ModbusTcp,
    ProtocolType.ModbusTcpClient,
    ProtocolType.ModbusUdp,
}

# Modbus RTU 类协议类型集合
_MODBUS_RTU_TYPES = {
    ProtocolType.ModbusRtu,
    ProtocolType.ModbusRtuClient,
    ProtocolType.ModbusRtuServer,
    ProtocolType.ModbusRtuOverTcp,
}

# 所有 Modbus 协议类型
_MODBUS_ALL_TYPES = _MODBUS_TCP_TYPES | _MODBUS_RTU_TYPES

# DLT645 协议类型集合
_DLT645_TYPES = {
    ProtocolType.Dlt645Server,
    ProtocolType.Dlt645Client,
}

# IEC104 协议类型集合
_IEC104_TYPES = {
    ProtocolType.Iec104Server,
    ProtocolType.Iec104Client,
}


class MessageFormatter:
    """报文格式化器

    从协议处理器获取原始报文记录，统一处理方向推导和格式化。
    """

    def __init__(self, device: Device) -> None:
        self._device = device

    @property
    def _handler(self):
        """获取协议处理器"""
        return self._device.protocol_handler

    def get_messages(self, limit: int | None = None) -> list[dict]:
        """获取报文历史记录

        从协议处理器获取原始报文。

        Args:
            limit: 最大返回数量，None表示返回全部

        Returns:
            报文记录列表（字典格式）
        """
        if not self._handler:
            return []

        messages = self._handler.get_captured_messages(limit or 100)
        if not messages:
            return []

        # 判断是否为客户端模式
        is_client = self._device.protocol_type in [
            ProtocolType.ModbusTcpClient,
            ProtocolType.Iec104Client,
            ProtocolType.Dlt645Client,
            ProtocolType.Iec61850Client,
        ]

        # 判断协议类型以选择解析方式
        protocol_type = self._device.protocol_type
        is_modbus = protocol_type in _MODBUS_ALL_TYPES
        is_tcp = protocol_type in _MODBUS_TCP_TYPES
        is_dlt645 = protocol_type in _DLT645_TYPES
        is_iec104 = protocol_type in _IEC104_TYPES

        # 统一显示格式
        result = []
        last_request_info = None  # 用于关联请求/响应

        for msg in messages:
            direction = msg.get("direction", "")
            raw_hex = msg.get("data", "")

            # 推导报文类型 (Request/Response)
            if is_client:
                # 客户端: TX是请求, RX是响应
                msg_type = "Request" if direction == "TX" else "Response"
            else:
                # 服务端: RX是请求, TX是响应
                msg_type = "Request" if direction == "RX" else "Response"

            # 解析报文描述
            description = ""
            if is_modbus and raw_hex:
                if msg_type == "Request":
                    # 提取请求信息用于后续响应关联
                    last_request_info = ModbusMessageParser.extract_request_info(raw_hex, is_tcp=is_tcp)
                    # 解析请求描述
                    if is_tcp:
                        description = ModbusMessageParser.parse_tcp(raw_hex)
                    else:
                        description = ModbusMessageParser.parse_rtu(raw_hex)
                else:
                    # 解析响应描述（传入上一条请求信息）
                    if is_tcp:
                        description = ModbusMessageParser.parse_tcp(raw_hex, last_request_info)
                    else:
                        description = ModbusMessageParser.parse_rtu(raw_hex, last_request_info)
                    # 响应处理完后清空请求信息，避免错误关联
                    last_request_info = None
            elif is_dlt645 and raw_hex:
                description = DLT645MessageParser.parse(raw_hex)
            elif is_iec104 and raw_hex:
                description = IEC104MessageParser.parse(raw_hex)

            # 原始16进制数据和长度
            hex_data = msg.get("hex_string", msg.get("data", ""))
            length = msg.get("length", 0)
            if not length and hex_data:
                # 从hex_data计算字节长度
                length = len(hex_data.replace(" ", "")) // 2

            result.append(
                {
                    "sequence_id": msg.get("sequence_id", 0),
                    "timestamp": msg.get("timestamp", 0),
                    "formatted_time": msg.get("time", msg.get("formatted_time", "")),
                    "direction": direction,
                    "msg_type": msg_type,
                    "hex_data": hex_data,
                    "raw_hex": raw_hex,
                    "description": description,
                    "length": length,
                }
            )

        # 按序号正序排列
        result.sort(
            key=lambda x: (x.get("sequence_id", 0), x["timestamp"]),
            reverse=False,
        )
        return result[:limit] if limit else result

    def clear_messages(self) -> None:
        """清空报文历史记录"""
        if self._handler:
            self._handler.clear_captured_messages()

    def get_avg_time(self) -> dict:
        """获取平均收发时间

        Returns:
            统计字典，包含发送/接收报文数量、平均间隔等
        """
        if self._handler:
            return self._handler.get_avg_time()
        return {}
