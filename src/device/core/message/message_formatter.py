"""
报文格式化模块
负责从协议处理器获取原始报文并格式化为统一的展示格式。
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from src.device.core.message.message_parser import (
    DLT645MessageParser,
    IEC104MessageParser,
    ModbusMessageParser,
)
from src.device.core.message.parsers import (
    describe_mms,
    parse_dlt645,
    parse_dnp3,
    parse_iec101,
    parse_iec104,
    parse_mms,
    parse_modbus,
)
from src.enums.modbus_def import ProtocolType
from src.enums.modbus_register import Decode

if TYPE_CHECKING:
    from src.device.core.device import Device

# Modbus TCP 类协议类型集合
_MODBUS_TCP_TYPES = {
    ProtocolType.ModbusTcpServer,
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

_IEC101_TYPES = {
    ProtocolType.Iec101Server,
    ProtocolType.Iec101Client,
}

_MMS_TYPES = {
    ProtocolType.Iec61850Server,
    ProtocolType.Iec61850Client,
}

_DNP3_TYPES = {
    ProtocolType.Dnp3Server,
    ProtocolType.Dnp3Client,
}


def _join_object_raw(objects: list[dict]) -> str:
    return " ".join(str(item.get("raw_value", "")).strip() for item in objects).strip()


class MessageFormatter:
    """报文格式化器

    从协议处理器获取原始报文记录，统一处理方向推导和格式化。
    """

    def __init__(self, device: Device) -> None:
        self._device = device

    @staticmethod
    def _extract_slave_id(raw_hex: str, protocol_type: ProtocolType) -> int | None:
        """Extract the Modbus unit ID or IEC104 common address from one frame."""
        try:
            raw = bytes.fromhex(raw_hex)
        except (TypeError, ValueError):
            return None

        if protocol_type in _MODBUS_TCP_TYPES:
            return raw[6] if len(raw) >= 7 else None
        if protocol_type in _MODBUS_RTU_TYPES:
            return raw[0] if raw else None
        if protocol_type in _IEC104_TYPES:
            # Only I-format frames contain an ASDU and therefore a common address.
            if len(raw) < 12 or raw[0] != 0x68 or raw[2] & 0x01:
                return None
            return int.from_bytes(raw[10:12], "little")
        if protocol_type in _IEC101_TYPES:
            if not raw:
                return None
            if raw[0] == 0x10 and len(raw) >= 5:
                return raw[2]
            if raw[0] == 0x68 and len(raw) >= 8:
                return raw[5]
        return None

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
            ProtocolType.Iec101Client,
            ProtocolType.Dlt645Client,
            ProtocolType.Iec61850Client,
            ProtocolType.Dnp3Client,
        ]

        # 判断协议类型以选择解析方式
        protocol_type = self._device.protocol_type
        is_modbus = protocol_type in _MODBUS_ALL_TYPES
        is_tcp = protocol_type in _MODBUS_TCP_TYPES
        is_dlt645 = protocol_type in _DLT645_TYPES
        is_iec104 = protocol_type in _IEC104_TYPES
        is_iec101 = protocol_type in _IEC101_TYPES
        is_mms = protocol_type in _MMS_TYPES
        is_dnp3 = protocol_type in _DNP3_TYPES

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
            elif is_iec101 and raw_hex:
                try:
                    description = parse_iec101(
                        bytes.fromhex(raw_hex),
                        role=msg_type,
                        link_address_size=int(self._device.runtime_config.get("link_address_size", 1)),
                    )["summary"]
                except (TypeError, ValueError):
                    description = "IEC101报文格式无效"
            elif is_mms and raw_hex:
                try:
                    description = describe_mms(bytes.fromhex(raw_hex), role=msg_type)
                except (TypeError, ValueError):
                    description = "MMS报文格式无效"
            elif is_dnp3 and raw_hex:
                try:
                    parsed = parse_dnp3(bytes.fromhex(raw_hex), role=msg_type)
                    description = parsed["summary"]
                except (TypeError, ValueError):
                    description = "DNP3报文格式无效"

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
                    "protocol_type": protocol_type.value,
                    "slave_id": self._extract_slave_id(raw_hex, protocol_type),
                    "fragment_correlation_id": msg.get("fragment_correlation_id"),
                    "transport_sequence": msg.get("transport_sequence"),
                    "transport_first": msg.get("transport_first"),
                    "transport_final": msg.get("transport_final"),
                }
            )

        # 按序号正序排列
        result.sort(
            key=lambda x: (x.get("sequence_id", 0), x["timestamp"]),
            reverse=False,
        )
        return result[:limit] if limit else result

    def get_message_detail(self, sequence_id: int) -> dict | None:
        """Parse one captured frame into byte-addressable detail data."""
        messages = self.get_messages(10_000)
        message = next((item for item in messages if item.get("sequence_id") == sequence_id), None)
        if message is None:
            return None
        try:
            raw = bytes.fromhex(message.get("raw_hex", ""))
        except (TypeError, ValueError):
            raw = b""
        protocol_type = self._device.protocol_type
        role = message.get("msg_type", "")
        if protocol_type in _MODBUS_ALL_TYPES:
            request_context = self._find_modbus_request_context(messages, message, protocol_type in _MODBUS_TCP_TYPES)
            detail = parse_modbus(
                raw,
                tcp=protocol_type in _MODBUS_TCP_TYPES,
                role=role,
                request_context=request_context,
            )
        elif protocol_type in _DLT645_TYPES:
            detail = parse_dlt645(raw, role=role)
        elif protocol_type in _IEC104_TYPES:
            detail = parse_iec104(raw, role=role)
        elif protocol_type in _IEC101_TYPES:
            detail = parse_iec101(
                raw,
                role=role,
                link_address_size=int(self._device.runtime_config.get("link_address_size", 1)),
            )
        elif protocol_type in _MMS_TYPES:
            detail = parse_mms(raw, role=role)
        elif protocol_type in _DNP3_TYPES:
            request_context = self._find_dnp3_request_context(messages, message)
            detail = parse_dnp3(raw, role=role, request_context=request_context)
        else:
            return None
        detail.update(
            sequence_id=sequence_id,
            direction=message.get("direction", ""),
            msg_type=role,
            timestamp=message.get("timestamp", 0),
            formatted_time=message.get("formatted_time", ""),
        )
        fragment_id = message.get("fragment_correlation_id")
        if fragment_id:
            related = [item["sequence_id"] for item in messages if item.get("fragment_correlation_id") == fragment_id]
            detail["fragment_correlation"] = {
                "id": fragment_id,
                "frame_sequence_ids": related,
                "transport_sequence": message.get("transport_sequence"),
                "first": message.get("transport_first"),
                "final": message.get("transport_final"),
            }
        self._enrich_with_points(detail, protocol_type)
        return detail

    @staticmethod
    def _find_dnp3_request_context(messages: list[dict], message: dict) -> dict | None:
        """Correlate application responses by the four-bit application sequence."""
        try:
            current = parse_dnp3(bytes.fromhex(message.get("raw_hex", "")), role=message.get("msg_type", ""))
        except (TypeError, ValueError):
            return None
        sequence = current.get("application_sequence")
        function = current.get("application_function_code")
        if sequence is None or function not in (129, 130):
            return None
        current_id = message.get("sequence_id", 0)
        for candidate in reversed(messages):
            if candidate.get("sequence_id", 0) >= current_id or candidate.get("msg_type") != "Request":
                continue
            try:
                parsed = parse_dnp3(bytes.fromhex(candidate.get("raw_hex", "")), role="Request")
            except (TypeError, ValueError):
                continue
            if parsed.get("application_sequence") != sequence:
                continue
            context = {
                "application_sequence": sequence,
                "request_sequence_id": candidate.get("sequence_id"),
                "request_function_code": parsed.get("application_function_code"),
                "request_function": parsed.get("application_function"),
            }
            if parsed.get("application_function_code") == 4:
                operate_addresses = {item.get("address") for item in parsed.get("objects", [])}
                for selected in reversed(messages):
                    selected_id = selected.get("sequence_id", 0)
                    if selected_id >= candidate.get("sequence_id", 0) or selected.get("msg_type") != "Request":
                        continue
                    try:
                        select_detail = parse_dnp3(bytes.fromhex(selected.get("raw_hex", "")), role="Request")
                    except (TypeError, ValueError):
                        continue
                    select_addresses = {item.get("address") for item in select_detail.get("objects", [])}
                    if select_detail.get("application_function_code") == 3 and (
                        not operate_addresses or operate_addresses == select_addresses
                    ):
                        context["select_sequence_id"] = selected_id
                        break
            return context
        return None

    def _enrich_with_points(self, detail: dict, protocol_type: ProtocolType) -> None:
        """Attach configured point semantics without mixing point lookup into wire parsers."""
        point_manager = getattr(self._device, "point_manager", None)
        points = point_manager.get_all_points() if point_manager is not None else []
        if not points or not detail.get("objects"):
            return
        if protocol_type in _MODBUS_ALL_TYPES:
            self._enrich_modbus_objects(detail, points)
        elif protocol_type in _DLT645_TYPES:
            self._enrich_address_objects(detail, points, dlt645=True)
        elif protocol_type in _IEC104_TYPES:
            self._enrich_address_objects(detail, points, dlt645=False)
        elif protocol_type in _IEC101_TYPES:
            self._enrich_address_objects(detail, points, dlt645=False)
        elif protocol_type in _DNP3_TYPES:
            self._enrich_dnp3_objects(detail, points)

    @staticmethod
    def _point_metadata(point) -> dict:
        multiplier = float(getattr(point, "mul_coe", 1.0))
        addition = float(getattr(point, "add_coe", 0.0))
        return {
            "name": point.name,
            "code": point.code,
            "address": point.address,
            "slave_id": point.rtu_addr,
            "function_code": point.func_code,
            "frame_type": point.frame_type,
            "decode_code": point.decode,
            "iec_type_id": point.iec_type_id,
            "multiplier": multiplier,
            "addition": addition,
        }

    def _enrich_modbus_objects(self, detail: dict, points: list) -> None:
        raw = bytes.fromhex(detail["raw_hex"])
        is_tcp = detail["protocol"] == "Modbus TCP"
        unit = raw[6] if is_tcp else raw[0]
        function_code = (raw[7] if is_tcp else raw[1]) & 0x7F
        objects = detail["objects"]
        object_index = {item.get("address"): index for index, item in enumerate(objects)}
        for point in points:
            if point.rtu_addr != unit or point.func_code != function_code or point.address not in object_index:
                continue
            index = object_index[point.address]
            item = objects[index]
            metadata = self._point_metadata(point)
            item["point"] = metadata
            if function_code in (1, 2):
                item["engineering_value"] = bool(item["value"])
                continue
            info = Decode.get_info(point.decode)
            registers = objects[index : index + info.register_cnt]
            if len(registers) != info.register_cnt:
                item.setdefault("warnings", []).append("响应寄存器不足，无法按测点解析码组合")
                continue
            try:
                buffer = b"".join(bytes.fromhex(str(register["raw_value"])) for register in registers)
                expected_size = info.register_cnt * 2
                if info.pack_format[-1:] in ("b", "B"):
                    buffer = buffer[:1]
                elif len(buffer) != expected_size:
                    raise ValueError("register byte count mismatch")
                decoded = Decode.unpack_value(info.pack_format, buffer)
                item["decoded_value"] = decoded
                item["engineering_value"] = round(decoded * metadata["multiplier"] + metadata["addition"], 6)
                item["combined_raw"] = _join_object_raw(registers)
                for covered in registers[1:]:
                    covered["covered_by_point"] = point.code
            except (ValueError, TypeError, struct.error):
                item.setdefault("warnings", []).append("按测点解析码组合寄存器失败")

    def _enrich_address_objects(self, detail: dict, points: list, *, dlt645: bool) -> None:
        common_address = None
        if not dlt645:
            common_field = next((field for field in detail["fields"] if field["key"] == "common_address"), None)
            common_address = common_field.get("value") if common_field else None
        for item in detail["objects"]:
            address = item.get("address")
            if dlt645 and isinstance(address, str):
                address = int(address, 16)
            point = next(
                (
                    candidate
                    for candidate in points
                    if candidate.address == address and (common_address is None or candidate.rtu_addr == common_address)
                ),
                None,
            )
            if point is None:
                continue
            metadata = self._point_metadata(point)
            item["point"] = metadata
            item["name"] = point.name or item.get("name", "")
            value = item.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                item["engineering_value"] = round(value * metadata["multiplier"] + metadata["addition"], 6)

    def _enrich_dnp3_objects(self, detail: dict, points: list) -> None:
        group_frame_types = {
            30: 0,
            32: 0,
            1: 1,
            2: 1,
            10: 2,
            12: 2,
            40: 3,
            41: 3,
        }
        for item in detail["objects"]:
            address = item.get("address")
            frame_type = group_frame_types.get(item.get("dnp3_group"))
            if not isinstance(address, int) or frame_type is None:
                continue
            point = next(
                (
                    candidate
                    for candidate in points
                    if int(candidate.address) == address and candidate.frame_type == frame_type
                ),
                None,
            )
            if point is None:
                continue
            metadata = self._point_metadata(point)
            item["point"] = metadata
            item["name"] = point.name or item.get("name", "")
            value = item.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                item["engineering_value"] = round(value * metadata["multiplier"] + metadata["addition"], 6)

    @staticmethod
    def _find_modbus_request_context(messages: list[dict], message: dict, is_tcp: bool) -> dict | None:
        if message.get("msg_type") != "Response":
            return None
        try:
            response = bytes.fromhex(message.get("raw_hex", ""))
            response_unit = response[6] if is_tcp else response[0]
            response_fc = (response[7] if is_tcp else response[1]) & 0x7F
            response_transaction = int.from_bytes(response[:2], "big") if is_tcp else None
        except (ValueError, IndexError, TypeError):
            return None
        previous = [item for item in messages if item.get("sequence_id", 0) < message.get("sequence_id", 0)]
        for candidate in reversed(previous):
            if candidate.get("msg_type") != "Request":
                continue
            info = ModbusMessageParser.extract_request_info(candidate.get("raw_hex", ""), is_tcp=is_tcp)
            if not info or info["slave_id"] != response_unit or info["func_code"] != response_fc:
                continue
            if is_tcp:
                try:
                    request_transaction = int.from_bytes(bytes.fromhex(candidate["raw_hex"])[:2], "big")
                except (ValueError, KeyError, TypeError):
                    continue
                if request_transaction != response_transaction:
                    continue
            return {
                "request_sequence_id": candidate.get("sequence_id"),
                "start_address": info["start_addr"],
                "end_address": info["end_addr"],
                "quantity": info["end_addr"] - info["start_addr"] + 1,
                "match_method": "transaction_id" if is_tcp else "slave_function_time_order",
            }
        return None

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
