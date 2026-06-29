"""Regression tests for IEC 61850 connection/discovery progress snapshots."""

from unittest.mock import Mock

from src.device.protocol.iec61850_handler import IEC61850ClientHandler


def _make_handler(client: Mock) -> IEC61850ClientHandler:
    handler = IEC61850ClientHandler()
    handler._client = client
    return handler


def test_remote_discovery_reports_real_stages_and_keeps_final_snapshot():
    client = Mock(is_connected=True)
    client._discovered_goose_items = []
    client.get_discovered_datasets.return_value = []
    client.reports = None
    client.get_discovered_points.return_value = []

    observed: list[dict] = []

    def discover(*, progress):
        progress("discovering", 0, 2, "发现 LD0")
        observed.append(handler.get_connect_progress())
        progress("discovering", 1, 2, "发现 LD1")
        observed.append(handler.get_connect_progress())
        progress("building", 0, 1, "构建索引")
        observed.append(handler.get_connect_progress())
        return True

    client.remote_discover_model.side_effect = discover
    handler = _make_handler(client)

    assert handler.remote_discover_model() is True

    assert [snapshot["progress"] for snapshot in observed] == [20, 45, 75]
    assert all(snapshot["active"] for snapshot in observed)
    final = handler.get_connect_progress()
    assert final["phase"] == "done"
    assert final["progress"] == 100
    assert final["active"] is False
    assert final["operation"] == "discover"


def test_remote_discovery_exception_finishes_in_failed_state():
    client = Mock(is_connected=True)
    client.remote_discover_model.side_effect = RuntimeError("browse failed")
    handler = _make_handler(client)

    assert handler.remote_discover_model() is False

    progress = handler.get_connect_progress()
    assert progress["phase"] == "failed"
    assert progress["active"] is False
    assert progress["progress"] == 20
    assert progress["message"] == "browse failed"


def test_second_progress_task_is_rejected_while_discovery_is_active():
    client = Mock(is_connected=True)
    handler = _make_handler(client)
    handler._begin_progress("discover", handler.PHASE_DISCOVERING, 30, "发现中")

    assert handler.remote_discover_model() is False
    assert handler.get_connect_progress()["progress"] == 30
    client.remote_discover_model.assert_not_called()
