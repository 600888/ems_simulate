"""DL/T 698.45 capture inspection using the installed protocol codec.

Link checks remain independent so a damaged checksum never hides the captured
bytes. Application decoding and Data semantics belong to dlt698, not this UI.
"""

from __future__ import annotations

import json
import math
from typing import Any

from .common import _fail, _field, _hex, _result, _validation

_SERVICES = {
    0x01: "预连接请求",
    0x81: "预连接响应",
    0x02: "建立应用连接请求",
    0x82: "建立应用连接响应",
    0x03: "断开应用连接请求",
    0x83: "断开应用连接响应",
    0x84: "应用连接释放通知",
    0x05: "读取请求 GET",
    0x85: "读取响应 GET",
    0x06: "设置请求 SET",
    0x86: "设置响应 SET",
    0x07: "操作请求 ACTION",
    0x87: "操作响应 ACTION",
    0x08: "上报确认",
    0x88: "主动上报 REPORT",
    0x09: "代理请求 PROXY",
    0x89: "代理响应 PROXY",
    0x10: "安全请求",
    0x90: "安全响应",
    0x6E: "客户端异常 ERROR",
    0xEE: "异常响应 ERROR",
}
_CHOICES = {
    5: {1: "单个属性", 2: "多个属性", 3: "记录", 4: "多个记录", 5: "分块", 6: "MD5"},
    6: {1: "单个属性", 2: "多个属性", 3: "设置后读取"},
    7: {1: "单个方法", 2: "多个方法", 3: "操作后读取"},
    8: {1: "属性列表", 2: "记录列表", 3: "透明数据"},
    9: {
        1: "代理读取",
        2: "代理记录读取",
        3: "代理设置",
        4: "代理设置后读取",
        5: "代理操作",
        6: "代理操作后读取",
        7: "代理透明转发",
    },
}
_DAR = {
    0: "成功",
    1: "硬件失效",
    2: "暂时失效",
    3: "拒绝读写",
    4: "对象未定义",
    5: "对象接口类不符合",
    6: "对象不存在",
    7: "类型不匹配",
    8: "越界",
    9: "数据块不可用",
    10: "分帧传输已取消",
    11: "不处于分帧传输状态",
    12: "块写取消",
    13: "不存在块写状态",
    14: "数据块序号无效",
    15: "密码错",
    16: "通信速率不能更改",
    17: "年时区数超",
    18: "日时段数超",
    19: "费率数超",
    20: "安全认证不匹配",
    21: "重复充值",
    22: "ESAM验证失败",
    255: "其他",
}


def _json_value(value: Any, depth: int = 0) -> Any:
    """Convert pybind models to lossless, JSON-safe values (including uint64)."""
    if depth > 40:
        return "嵌套层数超出展示限制"
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return str(value) if abs(value) > 2**53 - 1 else value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, bytes):
        return value.hex().upper()
    if isinstance(value, (list, tuple)):
        return [_json_value(item, depth + 1) for item in value]
    if hasattr(value, "name"):
        return value.name
    return {
        key: _json_value(getattr(value, key), depth + 1)
        for key in dir(type(value))
        if not key.startswith("_") and isinstance(getattr(type(value), key), property)
    }


def _display(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


class _Reader:
    """Byte spans for common services; read semantics are supplied by the codec."""

    def __init__(self, result: dict, payload: bytes, wire: bytes, base: int, position: int):
        self.result, self.payload, self.wire = result, payload, wire
        self.base, self.pos = base, position

    def take(self, size: int, key: str, name: str, value: Any, description: str = "") -> dict:
        end = self.pos + size
        if end > len(self.payload):
            raise ValueError("应用字段长度不足")
        field = _field(key, name, self.base + self.pos, self.wire[self.pos : end], value, description)
        field["display_value"] = _display(value)
        self.result["fields"].append(field)
        self.pos = end
        return field

    def count(self) -> None:
        first = self.payload[self.pos]
        size = 1 if first < 0x80 else 1 + (first & 0x7F)
        value = first if size == 1 else int.from_bytes(self.payload[self.pos + 1 : self.pos + size], "big")
        self.take(size, "object_count", "对象数量", value)

    def descriptor(self, method: bool = False) -> dict:
        data = self.payload[self.pos : self.pos + 4]
        if len(data) != 4:
            raise ValueError("对象描述符长度不足")
        text = data.hex().upper()
        label = "OMD" if method else "OAD"
        field = self.take(
            4,
            label.lower(),
            f"对象{'方法' if method else '属性'}描述符{label}",
            text,
            f"OI={text[:4]}，{'方法' if method else '属性'}={data[2]}，索引/模式={data[3]}",
        )
        obj = {
            "index": len(self.result["objects"]),
            "offset": field["offset"],
            "length": 4,
            "address": text,
            "name": label,
            "value": None,
            "raw_value": field["raw_hex"],
            "quality": None,
            "timestamp": None,
            "fields": [field],
        }
        self.result["objects"].append(obj)
        return obj

    def attach(self, obj: dict, field: dict) -> None:
        obj["fields"].append(field)
        start = obj["offset"] - self.base
        obj["length"] = self.pos - start
        obj["raw_value"] = _hex(self.wire[start : self.pos])

    def data(self, obj: dict, value: Any) -> None:
        from dlt698.codec import encode_data

        encoded = encode_data(value)
        if self.payload[self.pos : self.pos + len(encoded)] != encoded:
            raise ValueError("Data 编码与捕获字节不一致")
        converted = _json_value(value)
        field = self.take(len(encoded), "data", "有类型数据 Data", converted)
        self.attach(obj, field)
        obj["value"] = converted

    def dar(self, obj: dict) -> None:
        dar = self.payload[self.pos]
        name = _DAR.get(dar, "未定义错误")
        field = self.take(1, "dar", "访问结果 DAR", dar, name)
        field["display_value"] = f"{dar} ({name})"
        field["level"] = "normal" if dar == 0 else "warning"
        self.attach(obj, field)
        obj["value"], obj["quality"] = name, {"dar": dar, "success": dar == 0}

    def attribute_result(self, item: Any) -> None:
        obj = self.descriptor()
        choice = self.payload[self.pos]
        self.attach(obj, self.take(1, "result_choice", "结果类型", "Data" if choice else "DAR"))
        if isinstance(item.result, int):
            self.dar(obj)
        else:
            self.data(obj, item.result)

    def record_result(self, item: Any) -> None:
        from dlt698.codec import encode_apdu
        from dlt698.protocol import GetRecordResponse

        # An isolated record has a three-byte APDU header and two absent optionals.
        encoded = encode_apdu(GetRecordResponse(records=[item]))[3:-2]
        if self.payload[self.pos : self.pos + len(encoded)] != encoded:
            raise ValueError("记录编码与捕获字节不一致")
        obj = self.descriptor()
        field = self.take(len(encoded) - 4, "record", "记录列及结果", _json_value(item))
        self.attach(obj, field)
        obj["name"] = "记录"
        obj["value"] = _json_value(item.result)
        if isinstance(item.result, int):
            obj["quality"] = {"dar": item.result, "success": item.result == 0}
            obj["value"] = _DAR.get(item.result, f"DAR {item.result}")

    def record_request(self, item: Any) -> None:
        from dlt698.codec import encode_apdu
        from dlt698.protocol import GetRecordRequest

        encoded = encode_apdu(GetRecordRequest(records=[item]))[3:-1]
        if self.payload[self.pos : self.pos + len(encoded)] != encoded:
            raise ValueError("记录查询编码与捕获字节不一致")
        obj = self.descriptor()
        self.attach(obj, self.take(len(encoded) - 4, "record_query", "记录选择及列选择", _json_value(item)))
        obj["name"] = "记录查询"
        obj["value"] = _json_value(item)

    def tail(self, apdu: Any) -> None:
        if hasattr(apdu, "follow_report"):
            follow = apdu.follow_report
            self.take(1, "follow_report_present", "跟随上报标志", follow is not None)
            if follow is not None:
                self.take(1, "follow_report_choice", "跟随上报类型", self.payload[self.pos])
                self.count()
                for item in follow:
                    if type(item).__name__ == "AttributeResult":
                        self.attribute_result(item)
                    else:
                        self.record_result(item)
        if hasattr(apdu, "time_tag"):
            self.take(1, "time_tag_present", "时间标签标志", apdu.time_tag is not None)
            if apdu.time_tag is not None:
                self.take(10, "time_tag", "时间标签", _json_value(apdu.time_tag), "发送时标和允许传输延时")


def _common_objects(reader: _Reader, apdu: Any) -> bool:
    kind = type(apdu).__name__
    if kind in ("GetRequest", "GetResponse", "SetRequest", "SetResponse", "ActionRequest", "ActionResponse"):
        if apdu.list:
            reader.count()
        items = apdu.methods if kind.startswith("Action") else apdu.attributes
        for item in items:
            if kind == "GetResponse":
                reader.attribute_result(item)
                continue
            obj = reader.descriptor(kind.startswith("Action"))
            if kind == "SetRequest":
                reader.data(obj, item.value)
            elif kind == "ActionRequest":
                reader.data(obj, item.parameter)
            elif kind in ("SetResponse", "ActionResponse"):
                reader.dar(obj)
                if kind == "ActionResponse":
                    reader.attach(obj, reader.take(1, "data_present", "返回数据标志", item.data is not None))
                    if item.data is not None:
                        reader.data(obj, item.data)
        return True
    if kind == "GetRecordResponse" or (kind == "ReportNotification" and isinstance(apdu.payload, list)):
        if kind == "ReportNotification" or apdu.list:
            reader.count()
        for item in apdu.payload if kind == "ReportNotification" else apdu.records:
            if type(item).__name__ == "AttributeResult":
                reader.attribute_result(item)
            else:
                reader.record_result(item)
        return True
    if kind == "GetRecordRequest":
        if apdu.list:
            reader.count()
        for item in apdu.records:
            reader.record_request(item)
        return True
    if kind.startswith(("SetThenGet", "ActionThenGet")):
        reader.count()
        action = kind.startswith("Action")
        response = kind.endswith("Response")
        for item in apdu.items:
            operation = item.action if action else item.set
            obj = reader.descriptor(action)
            if response:
                reader.dar(obj)
                if action:
                    reader.attach(obj, reader.take(1, "data_present", "返回数据标志", operation.data is not None))
                    if operation.data is not None:
                        reader.data(obj, operation.data)
                reader.attribute_result(item.read)
            else:
                reader.data(obj, operation.parameter if action else operation.value)
                reader.descriptor()
                reader.take(1, "delay", "读取延时（秒）", item.delay_seconds)
        return True
    if kind in ("GetNextRequest", "GetNextResponse"):
        if kind == "GetNextResponse":
            reader.take(1, "last_block", "最后一块", apdu.last)
        reader.take(2, "block_number", "数据块序号", apdu.block)
        if kind == "GetNextResponse":
            choice = reader.payload[reader.pos]
            reader.take(1, "block_choice", "分块结果类型", choice)
            if isinstance(apdu.result, int):
                reader.take(1, "dar", "访问结果 DAR", apdu.result, _DAR.get(apdu.result, "未定义错误"))
            else:
                reader.count()
                for item in apdu.result:
                    if type(item).__name__ == "AttributeResult":
                        reader.attribute_result(item)
                    else:
                        reader.record_result(item)
        return True
    if kind in ("GetMd5Request", "GetMd5Response"):
        obj = reader.descriptor()
        if kind == "GetMd5Response":
            reader.attach(obj, reader.take(1, "result_choice", "结果类型", reader.payload[reader.pos]))
            if isinstance(apdu.result, int):
                reader.dar(obj)
            else:
                obj["value"] = bytes(apdu.result).hex().upper()
                reader.attach(obj, reader.take(16, "md5", "MD5", obj["value"]))
        return True
    if kind == "ReportResponse":
        reader.count()
        for _item in apdu.attributes:
            reader.descriptor()
        return True
    if kind == "ErrorResponse":
        reader.take(1, "error_type", "异常类型", apdu.type)
        reader.result["summary"] += f"，异常类型={apdu.type}"
        return True
    return False


def _parse_apdu(result: dict, payload: bytes, wire: bytes, base: int) -> None:
    from dlt698.codec import decode_apdu, decode_security
    from dlt698.errors import Dlt698Error

    if not payload:
        _fail(result, "DL/T698 应用数据为空")
        return
    service = payload[0]
    name = _SERVICES.get(service, f"未知应用服务 0x{service:02X}")
    result["summary"] = name
    reader = _Reader(result, payload, wire, base, 0)
    reader.take(1, "service", "应用服务", f"0x{service:02X} {name}")
    family = service & 0x7F
    has_choice = family in (5, 6, 7, 8, 9)
    if has_choice and len(payload) > 1:
        choice = payload[1]
        choice_name = _CHOICES.get(family, {}).get(choice, f"选择 {choice}")
        reader.take(1, "service_choice", "服务类型", f"{choice} {choice_name}")
        result["summary"] += f"，{choice_name}"
    try:
        apdu = decode_security(payload) if service in (0x10, 0x90) else decode_apdu(payload)
    except Dlt698Error as error:
        if service not in _SERVICES or error.code.name == "unsupported":
            result["complete"] = False
            result["warnings"].append(f"应用服务暂不能解码: {error}")
        else:
            _fail(result, f"DL/T698 应用数据解析失败: {error}")
        if reader.pos < len(payload):
            reader.take(len(payload) - reader.pos, "apdu_raw", "应用数据", _hex(payload[reader.pos :]))
        return
    # Expose every native service, including records, proxy, connection and security.
    result["apdu"] = {"type": type(apdu).__name__, "value": _json_value(apdu)}
    result["purpose"] = name
    if service in (0x10, 0x90):
        reader.take(len(payload) - reader.pos, "security", "安全数据", _json_value(apdu))
        result["complete"] = False
        result["warnings"].append("安全封装仅展示安全数据，内层业务需验签/解密后解析")
        return
    piid = getattr(apdu, "piid", getattr(apdu, "piid_acd", None))
    if piid is not None:
        reader.take(
            1,
            "piid",
            "服务序号 PIID-ACD" if hasattr(apdu, "piid_acd") else "服务序号 PIID",
            piid,
            f"服务序号={piid & 0x3F}，优先级={piid >> 7}",
        )
    result["frame_kind"] = name
    try:
        detailed = _common_objects(reader, apdu)
        if detailed:
            reader.tail(apdu)
    except (ValueError, IndexError) as error:
        # Future library encodings can still be inspected through the native tree.
        result["complete"] = False
        result["warnings"].append(f"字段定位未完成: {error}")
        detailed = False
    if reader.pos < len(payload):
        value = _hex(payload[reader.pos :]) if detailed else _json_value(apdu)
        reader.take(len(payload) - reader.pos, "apdu_body", "附加信息" if detailed else "服务数据", value)
    objects = result["objects"]
    if objects:
        addresses = ", ".join(item["address"] for item in objects[:4])
        result["summary"] += f"，{addresses}" + (f" 等{len(objects)}项" if len(objects) > 4 else "")
    failures = [field["description"] for field in result["fields"] if field["key"] == "dar" and field["value"] != 0]
    failures.extend(
        item["value"]
        for item in objects
        if item["name"] == "记录" and (item.get("quality") or {}).get("success") is False
    )
    if failures:
        result["summary"] += "，" + "/".join(dict.fromkeys(failures))


def parse_dlt698(raw: bytes, *, role: str) -> dict[str, Any]:
    """Inspect one captured frame, preserving transmitted bytes and absolute offsets."""
    result = _result("DL/T 698.45", raw)
    result["role"] = role.lower()
    start = 0
    while start < len(raw) and raw[start] == 0xFE:
        start += 1
    fields = result["fields"]
    if start:
        fields.append(_field("preamble", "前导符", 0, raw[:start], _hex(raw[:start])))
    frame = raw[start:]
    if len(frame) < 5:
        return _fail(result, "未找到完整的 DL/T698 帧头")
    _validation(result, "起始符", frame[0] == 0x68, f"实际值 0x{frame[0]:02X}，期望 0x68")
    if frame[0] != 0x68:
        return _fail(result, "DL/T698 起始符无效")
    length_word = int.from_bytes(frame[1:3], "little")
    length = (length_word & 0x3FFF) * (1024 if length_word & 0x4000 else 1)
    control, feature = frame[3:5]
    address_length = (feature & 0x0F) + 1
    client_pos = 5 + address_length
    hcs_pos, payload_pos = client_pos + 1, client_pos + 3
    total = length + 2
    fields.extend(
        [
            _field("start", "起始符", start, frame[:1], "0x68"),
            _field("length", "长度域 L", start + 1, frame[1:3], length, "长度域到帧校验的字节数，低字节在前"),
            _field(
                "control",
                "控制域 C",
                start + 3,
                frame[3:4],
                f"0x{control:02X}",
                f"DIR={control >> 7}，PRM={(control >> 6) & 1}，分帧={bool(control & 0x20)}，"
                f"加扰={bool(control & 8)}，功能码={control & 7}",
            ),
            _field(
                "address_feature",
                "服务器地址特征",
                start + 4,
                frame[4:5],
                f"0x{feature:02X}",
                f"地址类型={feature >> 6}，逻辑地址={(feature >> 4) & 3}，地址长度={address_length}",
            ),
        ]
    )
    if total < payload_pos + 3:
        return _fail(result, "DL/T698 声明帧长小于链路头和校验字段长度")
    _validation(result, "帧长度", len(frame) == total, f"声明{total}字节，实际{len(frame)}字节（不含前导符）")
    if len(frame) < total:
        return _fail(result, f"DL/T698 报文截断：声明{total}字节，实际{len(frame)}字节")
    if len(frame) > total:
        result["complete"] = False
        result["warnings"].append("帧后有额外字节，可能包含粘连报文；仅解析第一帧")
        fields.append(_field("trailing", "帧后数据", start + total, frame[total:], _hex(frame[total:])))
    frame = frame[:total]
    # SA is transmitted low byte first; display the readable meter/configuration address.
    address = frame[5:client_pos][::-1].hex().upper()
    fields.extend(
        [
            _field(
                "server_address",
                "服务器地址 SA",
                start + 5,
                frame[5:client_pos],
                address,
                "低字节在前传输，解析值按正常表地址顺序显示",
            ),
            _field(
                "client_address",
                "客户机地址 CA",
                start + client_pos,
                frame[client_pos : client_pos + 1],
                frame[client_pos],
            ),
        ]
    )
    result["frame_kind"] = "链路管理帧" if control & 7 == 1 else "用户数据帧"
    result["summary"] = f"{result['frame_kind']}，服务器地址:{address}"
    try:
        from dlt698.codec import crc16, decode_frame
        from dlt698.errors import Dlt698Error
    except ImportError:
        result["complete"] = False
        result["warnings"].append("未安装 dlt698，无法校验和解码应用数据")
        return result
    fcs_pos = total - 3
    for key, name, pos, expected in (
        ("hcs", "HCS", hcs_pos, crc16(frame[1:hcs_pos])),
        ("fcs", "FCS", fcs_pos, crc16(frame[1:fcs_pos])),
    ):
        actual = int.from_bytes(frame[pos : pos + 2], "little")
        _validation(result, name, actual == expected, f"实际0x{actual:04X}，计算0x{expected:04X}")
        fields.append(_field(key, name, start + pos, frame[pos : pos + 2], f"0x{actual:04X}"))
    fields.append(_field("end", "结束符", start + total - 1, frame[-1:], f"0x{frame[-1]:02X}"))
    _validation(result, "结束符", frame[-1] == 0x16, f"实际0x{frame[-1]:02X}，期望0x16")
    try:
        decode_frame(frame)
    except Dlt698Error as error:
        # CRC failures are already reported, while semantic link errors need their own diagnosis.
        _validation(result, "链路解码", False, str(error))
    wire = frame[payload_pos:fcs_pos]
    payload = bytes((byte - 0x33) & 0xFF for byte in wire) if control & 8 else wire
    fields.append(
        _field(
            "apdu",
            "应用数据域",
            start + payload_pos,
            wire,
            _hex(payload),
            "逐字节减0x33解除加扰" if control & 8 else "未加扰",
        )
    )
    if control & 0x20:
        result["complete"] = False
        result["summary"] = f"DL/T698 链路分帧，服务器地址:{address}"
        result["warnings"].append("链路分帧需重组后解码应用服务")
        return result
    _parse_apdu(result, payload, wire, start + payload_pos)
    result["summary"] += f"，服务器地址:{address}"
    return result
