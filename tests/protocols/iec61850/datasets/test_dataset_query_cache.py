from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.device.protocol.iec61850_handler import IEC61850ClientHandler
from src.web.api.channel import iec61850
from src.web.api.channel.iec61850 import _build_iec61850_dataset_tree


def test_dataset_tree_uses_snapshot_without_protocol_read():
    handler = IEC61850ClientHandler()
    handler._discovered_datasets = [
        {
            "ref": "LD0/LLN0$ds1",
            "name": "ds1",
            "members": [{"ref": "LD0/MMXU1.TotW.mag.f", "fc": "MX"}],
        }
    ]
    handler.read_dataset_values = Mock(side_effect=AssertionError("query must not perform MMS read"))
    device = SimpleNamespace(
        protocol_handler=handler,
        get_dataset_snapshot=Mock(
            return_value={
                "values": {"LD0/MMXU1.TotW.mag.f": 12.5},
                "updated_at": "2026-08-23T08:00:00+00:00",
                "stale": False,
                "last_error": None,
            }
        ),
    )

    tree = _build_iec61850_dataset_tree(device, "LD0/LLN0.ds1")

    handler.read_dataset_values.assert_not_called()
    assert tree["items"][0]["children"][0]["value"] == "12.5"
    assert tree["last_updated_at"] == "2026-08-23T08:00:00+00:00"
    assert tree["stale"] is False


@pytest.mark.asyncio
async def test_dataset_tree_and_detail_use_datamodel_du_without_changing_members(monkeypatch):
    handler = IEC61850ClientHandler()
    ref = "LD0/MMXU1.TotW.mag.f"
    members = [{"ref": ref, "name": "TotW.mag.f", "description": "旧描述", "fc": "MX"}]
    handler._discovered_datasets = [{"ref": "LD0/LLN0$ds", "name": "ds", "members": members}]
    handler.read_dataset_values = Mock(side_effect=AssertionError("must use cached metadata"))
    point = SimpleNamespace(address=ref, name="总有功功率", code="totw", fc="MX")
    device = SimpleNamespace(
        protocol_handler=handler,
        point_manager=SimpleNamespace(get_all_points=lambda: [point]),
        get_dataset_snapshot=lambda _: {"values": {ref: 12.5}, "stale": False},
    )
    monkeypatch.setattr(iec61850, "_get_iec61850_device", lambda *_: device)

    tree = _build_iec61850_dataset_tree(device, "LD0/LLN0$ds")
    detail = await iec61850.get_iec61850_dataset_detail(
        iec61850.Iec61850DatasetDetailRequest(channel_id=7, dataset_ref="LD0/LLN0$ds"), None
    )

    assert tree["items"][0]["du_name"] == "总有功功率"
    assert tree["items"][0]["children"][0]["point_name"] == "总有功功率"
    assert tree["items"][0]["children"][0]["description"] == "总有功功率"
    assert tree["items"][0]["children"][0]["fc"] == "MX"
    assert detail.data["members"][0]["description"] == "总有功功率"
    assert detail.data["members"][0]["value"] == 12.5
    assert members[0]["description"] == "旧描述"
    handler.read_dataset_values.assert_not_called()
