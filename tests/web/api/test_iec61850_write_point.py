"""IEC61850 本地设值与客户端控制写入的角色隔离回归测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.device.core.point.point_operator import PointOperator
from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler
from src.enums.point_data import Yc, Yx
from src.enums.points.base_point import BasePoint
from src.web.api.channel import iec61850 as api
from src.web.api.exceptions import ValidationError


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
