"""Application parsing helpers missing from the pinned pydnp3-pure release."""

from __future__ import annotations

from pydnp3_pure.app.constants import FunctionCode
from pydnp3_pure.app.fragment import AppMessage, ObjectData, parse_fragment
from pydnp3_pure.app.header import AppControl, AppHeader
from pydnp3_pure.app.object_header import parse_object_header
from pydnp3_pure.util.buffer import ReadBuffer

_SELECTOR_FUNCTIONS = {
    FunctionCode.READ,
    FunctionCode.FREEZE,
    FunctionCode.FREEZE_NO_ACK,
    FunctionCode.FREEZE_CLEAR,
    FunctionCode.FREEZE_CLEAR_NO_ACK,
    FunctionCode.FREEZE_AT_TIME,
    FunctionCode.FREEZE_AT_TIME_NO_ACK,
    FunctionCode.ENABLE_UNSOLICITED,
    FunctionCode.DISABLE_UNSOLICITED,
    FunctionCode.ASSIGN_CLASS,
}


def parse_application_fragment(data: bytes) -> AppMessage:
    """解析仅含对象选择范围的请求，避免把范围误当测点载荷。"""
    if len(data) < 2:
        raise ValueError("application fragment is shorter than two bytes")
    function = FunctionCode(data[1])
    if function not in _SELECTOR_FUNCTIONS:
        return parse_fragment(data)

    buffer = ReadBuffer(data)
    control = AppControl.from_byte(buffer.read_uint8())
    parsed_function = FunctionCode(buffer.read_uint8())
    objects: list[ObjectData] = []
    while buffer.remaining:
        objects.append(ObjectData(header=parse_object_header(buffer)))
    return AppMessage(header=AppHeader(control=control, function=parsed_function), objects=objects)
