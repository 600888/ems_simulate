"""IEC61850 本地设值与客户端控制写入的角色隔离回归测试。"""

from importlib import import_module
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
import pytest

from src.device.core.point.point_operator import PointOperator
from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc, Yk, Yx
from src.enums.points.base_point import BasePoint
from src.proto.iec61850.iec61850_client import IEC61850Client
from src.web.api.channel import iec61850 as api
from src.web.api.exceptions import OperationError, ValidationError
from src.web.api.point import router as point_api


def make_device(monkeypatch, handler, points):
    point_manager = Mock()
    point_manager.get_point_by_code.side_effect = lambda code, *_: next(
        (point for point in points if point.code == code), None
    )
    point_manager.get_all_points.return_value = points
    device = SimpleNamespace(protocol_handler=handler, point_manager=point_manager, log=Mock())
    monkeypatch.setattr(api, "_get_iec61850_device", lambda *_: device)
    return device


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("point_cls", "address", "fc", "value", "has_control"),
    [
        (Yc, "LD0/MMXU1.TotW.mag.f", "MX", 12.5, False),
        (Yx, "LD0/GGIO1.Pos.stVal", "ST", 1, False),
        (Yx, "LD0/GGIO1.Pos.stVal", "ST", 1, True),
    ],
)
async def test_server_updates_selected_attribute(monkeypatch, point_cls, address, fc, value, has_control):
    point = point_cls(
        address=address,
        code=address.split("/")[1],
        fc=fc,
        decode="FLOAT32_ABCD" if point_cls is Yc else "UINT16_AB",
    )
    points = [point]
    if has_control:
        points.append(
            BasePoint(address="LD0/GGIO1.Pos.Oper.ctlVal", code="GGIO1.Pos.Oper.ctlVal", fc="CO", frame_type=2)
        )
    handler = IEC61850ServerHandler()
    handler._server = Mock()
    device = make_device(monkeypatch, handler, points)
    device.edit_point_data_async = PointOperator(device).edit_value_async

    response = await api.iec61850_write_single_point(
        api.Iec61850WritePointRequest(channel_id=1, point_code=point.code, point_value=value), Mock()
    )

    assert response.data == {"point_code": point.code, "value": value}
    assert point.real_value == value
    handler._server.set_point_value.assert_called_once_with(address=address, value=point.value, fc=fc)
    device.point_manager.get_all_points.assert_not_called()


@pytest.mark.asyncio
async def test_client_rejects_status_without_control_attribute(monkeypatch):
    point = BasePoint(address="LD0/GGIO1.Pos.stVal", code="GGIO1.Pos.stVal", fc="ST", frame_type=1)
    device = make_device(monkeypatch, IEC61850ClientHandler(), [point])
    device.edit_point_data_async = AsyncMock(return_value=True)

    with pytest.raises(ValidationError, match="未发现可写属性"):
        await api.iec61850_write_single_point(
            api.Iec61850WritePointRequest(channel_id=1, point_code=point.code, point_value=1), Mock()
        )

    device.edit_point_data_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_client_control_write_exposes_native_refusal(monkeypatch):
    point = Yk(address="IED001PROT/LLN0.FuncEna4.Oper.ctlVal", code="FuncEna4", fc="CO")
    error = "IEC61850 控制操作失败: IED_ERROR_ACCESS_DENIED, addCause=ADD_CAUSE_BLOCKED_BY_INTERLOCKING"
    client = object.__new__(IEC61850Client)
    client._writer = SimpleNamespace(write=lambda *_args: False, last_error=error)
    handler = IEC61850ClientHandler()
    handler._client = client
    device = make_device(monkeypatch, handler, [point])
    device.edit_point_data_async = PointOperator(device).edit_value_async

    with pytest.raises(OperationError, match="IED_ERROR_ACCESS_DENIED") as failure:
        await api.iec61850_write_single_point(
            api.Iec61850WritePointRequest(channel_id=1, point_code=point.code, point_value=1), Mock()
        )

    assert "ADD_CAUSE_BLOCKED_BY_INTERLOCKING" in str(failure.value)
    assert "请检查配置或物理连接" not in str(failure.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("write_api", ["iec61850", "point"])
async def test_write_failure_http_message_preserves_device_reason(monkeypatch, write_api):
    app_module = import_module("src.web.app")
    application = FastAPI(exception_handlers=app_module.app.exception_handlers)
    application.include_router(api.router, prefix="/api/channels")
    application.include_router(point_api.point_router)
    point_code = "IED001PROT_LLN0_FuncEna4_Oper_ctlVal"
    reason = (
        f"测点 {point_code} 协议写入失败: IEC61850 控制带值选择失败: "
        "ref=IED001PROT/LLN0.FuncEna4, error=21(IED_ERROR_ACCESS_DENIED（访问被拒绝）), "
        "ctlNum=7, application_error=0, addCause=ADD_CAUSE_POSITION_REACHED"
    )
    point = Yk(address="IED001PROT/LLN0.FuncEna4.Oper.ctlVal", code=point_code, fc="CO")
    device = make_device(monkeypatch, IEC61850ClientHandler(), [point])
    device.protocol_type = ProtocolType.Iec61850Client
    device.ip, device.port = "127.0.0.1", 102
    device.edit_point_data_async = AsyncMock(side_effect=ValueError(reason))
    monkeypatch.setattr(point_api, "_get_device", lambda *_: device)
    if write_api == "iec61850":
        path = "/api/channels/iec61850-write-point"
        payload = {"channel_id": 1, "point_code": point_code, "point_value": 1}
    else:
        path = "/api/points/edit-data"
        payload = {"device_name": "IED001", "point_code": point_code, "point_value": 1}

    sent = []

    async def receive():
        return {"type": "http.request", "body": json.dumps(payload).encode(), "more_body": False}

    async def send(message):
        sent.append(message)

    await application(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
        send,
    )
    response = json.loads(b"".join(item["body"] for item in sent if item["type"] == "http.response.body"))

    assert sent[0]["status"] == 500
    assert response["code"] == 500
    assert response["message"] == reason
    assert "服务器内部错误" not in response["message"]


def test_client_sync_control_write_exposes_native_refusal(monkeypatch):
    point = Yk(address="IED001PROT/LLN0.FuncEna4.Oper.ctlVal", code="FuncEna4", fc="CO")
    client = object.__new__(IEC61850Client)
    client._writer = SimpleNamespace(write=lambda *_args: False, last_error="IED_ERROR_TEMPORARILY_UNAVAILABLE")
    handler = IEC61850ClientHandler()
    handler._client = client
    device = make_device(monkeypatch, handler, [point])

    with pytest.raises(ValueError, match="IED_ERROR_TEMPORARILY_UNAVAILABLE"):
        PointOperator(device).edit_value(point.code, 1)


@pytest.mark.asyncio
async def test_client_redirects_status_to_control_attribute(monkeypatch):
    status = BasePoint(address="LD0/GGIO1.Pos.stVal", code="GGIO1.Pos.stVal", fc="ST", frame_type=1)
    control = BasePoint(address="LD0/GGIO1.Pos.Oper.ctlVal", code="GGIO1.Pos.Oper.ctlVal", fc="CO", frame_type=2)
    device = make_device(monkeypatch, IEC61850ClientHandler(), [status, control])
    device.edit_point_data_async = AsyncMock(return_value=True)

    response = await api.iec61850_write_single_point(
        api.Iec61850WritePointRequest(channel_id=1, point_code=status.code, point_value=1), Mock()
    )

    assert response.data["point_code"] == control.code
    device.edit_point_data_async.assert_awaited_once_with(control.code, 1)


@pytest.mark.asyncio
async def test_server_rejects_empty_point_code(monkeypatch):
    device = make_device(monkeypatch, IEC61850ServerHandler(), [])
    device.edit_point_data_async = AsyncMock(return_value=True)

    with pytest.raises(ValidationError, match="测点编码不能为空"):
        await api.iec61850_write_single_point(
            api.Iec61850WritePointRequest(channel_id=1, point_code="", point_value=1), Mock()
        )

    device.edit_point_data_async.assert_not_awaited()
