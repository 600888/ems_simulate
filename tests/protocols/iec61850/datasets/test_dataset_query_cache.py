from types import SimpleNamespace
from unittest.mock import Mock

from src.device.protocol.iec61850_handler import IEC61850ClientHandler
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
