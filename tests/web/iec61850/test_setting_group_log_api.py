import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from src.web.api.channel import iec61850_log as log_api
from src.web.api.channel import setting_group as setting_api
from src.web.api.schemas.iec61850_log import Iec61850LogQueryRequest
from src.web.api.schemas.setting_group import SettingGroupDetailRequest


class _Controller:
    def __init__(self, handler):
        self._device = SimpleNamespace(protocol_handler=handler)

    def get_device_by_channel_id(self, _channel_id):
        return self._device


def _request_for(handler):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=_Controller(handler))))


def test_setting_group_detail_combines_state_and_values():
    plugin = SimpleNamespace(
        get_detail=lambda _ref: {"ref": "LD0/LLN0.SGCB", "act_sg": 2},
        list_settings=lambda _ref: [{"address": "LD0/PTOC1.StrVal.setMag.f"}],
    )
    body = SettingGroupDetailRequest(channel_id=7, sgcb_ref="LD0/LLN0.SGCB")
    with patch.object(setting_api, "_get_plugin", return_value=plugin):
        response = asyncio.run(setting_api.get_setting_group_detail(body, SimpleNamespace()))

    assert response.data["act_sg"] == 2
    assert response.data["settings"][0]["address"] == "LD0/PTOC1.StrVal.setMag.f"


def test_log_query_filters_before_pagination():
    entries = [
        {
            "entry_id": "1",
            "level": "warning",
            "service": "Control",
            "object_ref": "LD0/CSWI1.Pos.Oper",
            "message": "SBO timeout",
            "source": "LD0/LLN0.EventLog",
        },
        {
            "entry_id": "2",
            "level": "info",
            "service": "Report",
            "object_ref": "LD0/XCBR1.Pos.stVal",
            "message": "position changed",
            "source": "LD0/LLN0.EventLog",
        },
    ]
    plugin = SimpleNamespace(query=lambda *_args: (entries, False))
    body = Iec61850LogQueryRequest(
        channel_id=7,
        log_ref="LD0/LLN0.EventLog",
        start_time_ms=1,
        end_time_ms=2,
        keyword="SBO",
        level="warning",
        service="Control",
        page_size=1,
    )
    with patch.object(log_api, "_get_plugin", return_value=plugin):
        response = asyncio.run(log_api.query_iec61850_logs(body, SimpleNamespace()))

    assert response.data["total"] == 1
    assert response.data["entries"][0]["entry_id"] == "1"


def test_setting_group_api_accepts_server_handler():
    from src.device.protocol.iec61850_handler import IEC61850ServerHandler

    plugin = SimpleNamespace(discover=lambda: [])
    handler = IEC61850ServerHandler()
    handler._server = SimpleNamespace(setting_groups=plugin)

    assert setting_api._get_plugin(7, _request_for(handler)) is plugin


def test_log_api_accepts_server_handler():
    from src.device.protocol.iec61850_handler import IEC61850ServerHandler

    plugin = SimpleNamespace(discover=lambda: [])
    handler = IEC61850ServerHandler()
    handler._server = SimpleNamespace(logs=plugin)

    assert log_api._get_plugin(7, _request_for(handler)) is plugin
